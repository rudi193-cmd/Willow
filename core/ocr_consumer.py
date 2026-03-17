#!/usr/bin/env python3
"""
OCR Queue Consumer — Bridge Ring Enrichment Daemon

Role: Enrich pending review queue items with full OCR extraction, importance
scoring, and categorization. Does NOT ingest to LOAM — that's confirm_review()'s
job after human approval.

Pipeline position:
  Source Ring:  File lands in Nest (raw source)
  Bridge Ring:  Pigeon stages → review queue → OCR Consumer enriches → human reviews
  Continuity Ring: confirm_review() ingests to LOAM after approval

Two enrichment paths per cycle:
  1. Queue enrichment: pending items with short/missing ocr_text
  2. Screenshot scoring: pending image items scored for importance

Run standalone:  python core/ocr_consumer.py [--batch N] [--username NAME]
Triggered via:   POST /api/binder/process-queue

ΔΣ=42
"""

import json
import hashlib
import logging
import re
from pathlib import Path
from datetime import datetime, timezone

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

USERNAME = "Sweet-Pea-Rudi19"
NEST = Path(r"/mnt/c/Users/Sean/Willow/Nest")
MAX_BATCH = 20
MAX_TEXT_LEN = 4000
MIN_SCORE = 3  # importance threshold for screenshot ingestion

log = logging.getLogger(__name__)

UTC = timezone.utc


# ---------------------------------------------------------------------------
# DB connection
# ---------------------------------------------------------------------------

def _connect():
    from core.db import get_connection
    return get_connection()


# ---------------------------------------------------------------------------
# Importance scoring (ported from die-namic-system/apps/eyes/content_scan.py)
# ---------------------------------------------------------------------------

_KEYWORDS_HIGH = [
    "error", "exception", "failed", "critical", "urgent",
    "password", "secret", "key", "token", "auth",
    "interview", "offer", "salary", "contract",
    "deadline", "due", "asap", "important",
    "question", "answer", "decision",
    "signal", "pending", "queue", "divergence",
]

_KEYWORDS_MED = [
    "todo", "task", "note", "remember",
    "meeting", "call", "schedule",
    "commit", "push", "pull", "merge", "branch",
    "test", "build", "deploy",
    "email", "message", "reply",
    "name", "phone", "address",
]

_LOW_VALUE = [
    re.compile(r"^(\s*heartbeat\s*)*$"),
    re.compile(r"^\s*$"),
    re.compile(r"^(desktop|taskbar|start menu)\s*$", re.IGNORECASE),
]

# ---------------------------------------------------------------------------
# Chrome detection — browser UI vs actual content
# ---------------------------------------------------------------------------

_CHROME_PATTERNS = [
    re.compile(r"(new tab|×|🔒|🔍|⋮|\.com\s*[×x])", re.IGNORECASE),
    re.compile(r"https?://\S+", re.IGNORECASE),
    re.compile(r"(bookmarks?\s*bar|favorites?\s*bar)", re.IGNORECASE),
    re.compile(r"(file\s+edit\s+view|extensions|settings|downloads|history)\s*$", re.IGNORECASE),
    re.compile(r"(type here to search|cortana|task view)", re.IGNORECASE),
    re.compile(r"^[^a-zA-Z]*$"),       # no letters at all
    re.compile(r"^.{1,3}$"),           # 1-3 char noise
]


def detect_chrome_regions(text: str) -> dict:
    """
    Tag text lines as chrome vs content.
    Returns {content_lines, chrome_lines, chrome_ratio, content_text}.

    Governance: observation only. Tags text, doesn't modify or delete.
    """
    lines = text.split('\n')
    content_lines = []
    chrome_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        is_chrome = any(p.search(stripped) for p in _CHROME_PATTERNS)
        if is_chrome:
            chrome_lines.append(stripped)
        else:
            content_lines.append(stripped)
    total = len(content_lines) + len(chrome_lines)
    return {
        "content_lines": content_lines,
        "chrome_lines": chrome_lines,
        "chrome_ratio": len(chrome_lines) / max(total, 1),
        "content_text": '\n'.join(content_lines),
    }


def score_importance(text: str) -> tuple:
    """Score text 0-10. Returns (score, reasons)."""
    if not text:
        return 0, ["empty"]
    tl = text.lower()
    if len(text) < 50:
        return 1, ["short_text"]
    for pat in _LOW_VALUE:
        if pat.match(tl):
            return 0, ["low_value_pattern"]
    score = 0
    reasons = []
    for w in _KEYWORDS_HIGH:
        if w in tl:
            score += 3
            reasons.append(f"high:{w}")
    for w in _KEYWORDS_MED:
        if w in tl:
            score += 2
            reasons.append(f"med:{w}")
    score = min(score, 10)
    if score == 0 and len(text) > 100:
        score = 2
        reasons.append("substantive_text")
    return score, reasons[:5]


# ---------------------------------------------------------------------------
# Extraction functions (Tesseract OCR, PDF, text)
# ---------------------------------------------------------------------------

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff"}
_TEXT_EXTS = {".txt", ".md", ".csv"}
_PROCESSABLE = _IMAGE_EXTS | _TEXT_EXTS | {".pdf"}


def _extract_image(path: Path) -> str:
    try:
        import subprocess, os
        from PIL import Image

        tess_wsl = "/mnt/c/Program Files/Tesseract-OCR/tesseract.exe"
        if os.path.exists(tess_wsl):
            def _wsl_to_win(p):
                s = str(p)
                if s.startswith("/mnt/"):
                    parts = s[5:].split("/", 1)
                    return parts[0].upper() + ":\\" + (parts[1].replace("/", "\\") if len(parts) > 1 else "")
                return s

            win_tmp = "C:\\Users\\Sean\\AppData\\Local\\Temp"
            wsl_tmp = Path("/mnt/c/Users/Sean/AppData/Local/Temp")
            out_name = f"willow_ocr_{path.stem}"
            subprocess.run(
                [tess_wsl, _wsl_to_win(path), win_tmp + "\\" + out_name, "--psm", "6"],
                capture_output=True
            )
            out_file = wsl_tmp / (out_name + ".txt")
            if out_file.exists():
                text = out_file.read_text(encoding="utf-8", errors="replace").strip()
                out_file.unlink()
                return text.replace("\x00", "")
            return ""
        else:
            import pytesseract
            pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
            img = Image.open(path)
            if img.mode in ("CMYK", "P", "LA", "RGBA"):
                img = img.convert("RGB")
            return pytesseract.image_to_string(img).strip().replace("\x00", "")
    except Exception as e:
        log.warning(f"OCR failed {path.name}: {e}")
        return ""


def _extract_pdf(path: Path) -> str:
    # Try pypdf first (installed), then pdfplumber as fallback
    try:
        import pypdf
        reader = pypdf.PdfReader(str(path))
        parts = []
        for page in reader.pages[:20]:
            t = page.extract_text()
            if t:
                parts.append(t)
        text = "\n".join(parts).strip()
        if text:
            return text
    except Exception as e:
        log.debug(f"pypdf extract failed {path.name}: {e}")
    try:
        import pdfplumber
        parts = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages[:20]:
                t = page.extract_text()
                if t:
                    parts.append(t)
        return "\n".join(parts).strip()
    except Exception as e:
        log.warning(f"PDF extract failed {path.name}: {e}")
        return ""


def _extract_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace").replace("\x00", "")
    except Exception as e:
        log.warning(f"Text read failed {path.name}: {e}")
        return ""


def _category(filename: str, text: str) -> str:
    tl = text.lower()
    if any(k in tl for k in ["bankruptcy", "chapter 13", "schedule", "creditor", "mortgage", "case number", "court"]):
        return "legal_document"
    if any(k in tl for k in ["bernco", "parid", "assessed value", "property record", "assessor"]):
        return "property_record"
    if any(k in tl for k in ["workers comp", "workers' comp", "wc benefit", "injury", "medical leave"]):
        return "legal_document"
    fn = filename.lower()
    if fn.endswith((".jpg", ".jpeg", ".png", ".gif")):
        return "screenshot"
    if fn.endswith(".pdf"):
        return "document"
    return "personal_document"


def _pg_safe(s: str) -> str:
    """Strip NUL bytes — Postgres rejects them in string literals."""
    return s.replace("\x00", "") if s else s


# ---------------------------------------------------------------------------
# Queue enrichment — the new role
# ---------------------------------------------------------------------------

def _get_pending_items(username: str, max_batch: int = MAX_BATCH) -> list:
    """Fetch pending review queue items that need OCR enrichment."""
    conn = _connect()
    try:
        rows = conn.execute(
            """SELECT id, filename, original_path, ocr_text, proposed_category
               FROM nest_review_queue
               WHERE username = ? AND status = 'pending'
               ORDER BY staged_at ASC
               LIMIT ?""",
            (username, max_batch)
        ).fetchall()
        return [
            {
                "id": r[0], "filename": r[1], "original_path": r[2],
                "ocr_text": r[3], "proposed_category": r[4]
            }
            for r in rows
        ]
    finally:
        conn.close()


def _needs_enrichment(item: dict) -> bool:
    """Item needs OCR enrichment if ocr_text is short/missing."""
    ocr = item.get("ocr_text") or ""
    return len(ocr.strip()) < 200


def _enrich_item(item: dict) -> dict:
    """
    Full OCR extraction + scoring + categorization for a review queue item.
    Returns dict of fields to update, or None if nothing to do.
    """
    path = Path(item["original_path"])

    # File may have been removed by Pigeon after staging — that's fine,
    # we can still enrich from what Pigeon already extracted
    if not path.exists():
        # Check processed/ — Pigeon doesn't move there, but OCR Consumer used to
        processed = NEST / "processed" / item["filename"]
        if processed.exists():
            path = processed
        else:
            return None

    suffix = path.suffix.lower()
    text = ""

    if suffix in _IMAGE_EXTS:
        text = _extract_image(path)
    elif suffix == ".pdf":
        text = _extract_pdf(path)
    elif suffix in _TEXT_EXTS:
        text = _extract_text(path)
    else:
        return None

    if not text or len(text.strip()) < 20:
        return None

    text = _pg_safe(text[:MAX_TEXT_LEN])

    # Chrome context detection — tag regions before scoring
    chrome_info = detect_chrome_regions(text)
    chrome_ratio = chrome_info["chrome_ratio"]

    # Score on content text (chrome lines excluded from scoring)
    score_text = chrome_info["content_text"] if chrome_ratio > 0.3 else text
    score, reasons = score_importance(score_text)

    # Penalize high-chrome screenshots
    if chrome_ratio > 0.5:
        score = max(0, score - 2)
        reasons.append(f"chrome_ratio:{chrome_ratio:.2f}")

    cat = _category(item["filename"], text)

    return {
        "ocr_text": text,
        "proposed_category": cat,
        "importance_score": score,
        "importance_reasons": reasons,
        "chrome_ratio": chrome_ratio,
    }


def _update_queue_item(item_id: int, updates: dict):
    """Write enrichment data back to the review queue."""
    conn = _connect()
    try:
        conn.execute(
            """UPDATE nest_review_queue SET
               ocr_text = ?, proposed_category = ?, chrome_ratio = ?
               WHERE id = ?""",
            (_pg_safe(updates["ocr_text"]),
             _pg_safe(updates["proposed_category"]),
             updates.get("chrome_ratio", 0.0),
             item_id)
        )
        conn.commit()
    finally:
        conn.close()


def enrich_queue(username: str = USERNAME, max_batch: int = MAX_BATCH) -> dict:
    """
    Enrich pending review queue items with full OCR extraction.
    Does NOT ingest to LOAM — that happens after human approval via confirm_review().
    """
    items = _get_pending_items(username, max_batch)
    enriched, skipped, failed = [], [], []

    for item in items:
        if not _needs_enrichment(item):
            skipped.append(item["filename"])
            continue

        try:
            updates = _enrich_item(item)
            if updates:
                _update_queue_item(item["id"], updates)
                enriched.append(item["filename"])
                score = updates.get("importance_score", 0)
                log.info(f"OCR: enriched #{item['id']} {item['filename']} → {updates['proposed_category']} (score={score})")
            else:
                skipped.append(item["filename"])
        except Exception as e:
            log.error(f"OCR: enrichment failed for #{item['id']} {item['filename']}: {e}")
            failed.append(item["filename"])

    return {
        "enriched": len(enriched),
        "skipped": len(skipped),
        "failed": len(failed),
        "enriched_files": enriched,
        "queue_pending": len(items),
    }


# ---------------------------------------------------------------------------
# Screenshot scoring — flag low-value screenshots for easy bulk dismiss
# ---------------------------------------------------------------------------

def score_screenshots(username: str = USERNAME, max_batch: int = MAX_BATCH) -> dict:
    """
    Score pending screenshot items in the review queue.
    Items below MIN_SCORE get proposed_category updated to 'screenshot_low_value'
    so the UI can offer bulk dismiss.
    """
    conn = _connect()
    try:
        rows = conn.execute(
            """SELECT id, filename, original_path, ocr_text, proposed_category
               FROM nest_review_queue
               WHERE username = ? AND status = 'pending'
                 AND proposed_category IN ('screenshot', 'media')
               ORDER BY staged_at ASC
               LIMIT ?""",
            (username, max_batch)
        ).fetchall()
    finally:
        conn.close()

    scored, low = [], []
    for r in rows:
        item_id, filename, original_path, ocr_text = r[0], r[1], r[2], r[3] or ""

        if len(ocr_text.strip()) < 20:
            # No text to score — mark low value
            conn = _connect()
            try:
                conn.execute(
                    "UPDATE nest_review_queue SET proposed_category = ? WHERE id = ?",
                    ("screenshot_low_value", item_id)
                )
                conn.commit()
            finally:
                conn.close()
            low.append(filename)
            continue

        score, reasons = score_importance(ocr_text)
        if score < MIN_SCORE:
            conn = _connect()
            try:
                conn.execute(
                    "UPDATE nest_review_queue SET proposed_category = ? WHERE id = ?",
                    ("screenshot_low_value", item_id)
                )
                conn.commit()
            finally:
                conn.close()
            low.append(filename)
            log.debug(f"EYES: {filename} score={score} < {MIN_SCORE}, flagged low_value")
        else:
            scored.append(filename)

    return {
        "scored": len(scored),
        "low_value": len(low),
        "source": "screenshots",
    }


# ---------------------------------------------------------------------------
# Legacy compat — process_queue and process_screenshots still callable
# but now route through the bridge
# ---------------------------------------------------------------------------

def process_queue(username: str = USERNAME, max_batch: int = MAX_BATCH) -> dict:
    """Legacy entry point — now enriches the review queue instead of direct LOAM ingest."""
    return enrich_queue(username, max_batch)


def process_screenshots(username: str = USERNAME, max_batch: int = MAX_BATCH) -> dict:
    """Legacy entry point — now scores screenshots in the review queue."""
    return score_screenshots(username, max_batch)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    import argparse
    parser = argparse.ArgumentParser(description="Enrich Willow review queue with OCR extraction")
    parser.add_argument("--batch", type=int, default=MAX_BATCH)
    parser.add_argument("--username", default=USERNAME)
    parser.add_argument("--screenshots-only", action="store_true", help="Only score screenshots")
    args = parser.parse_args()
    if args.screenshots_only:
        result = score_screenshots(username=args.username, max_batch=args.batch)
    else:
        result = enrich_queue(username=args.username, max_batch=args.batch)
        ss_result = score_screenshots(username=args.username, max_batch=args.batch)
        result["screenshots"] = ss_result
    print(json.dumps(result, indent=2))

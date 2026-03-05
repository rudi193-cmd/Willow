#!/usr/bin/env python3
"""
OCR Queue Consumer — Willow Drop Processing Daemon

Drains ocr_queue_*.json entries from Pickup by processing each source file:
- Images (.jpg, .jpeg, .png, .gif): pytesseract Tesseract OCR
- PDFs: pdfplumber text extraction
- Text (.txt, .md): direct read

Results ingested into Willow knowledge graph via loam.ingest_file_knowledge().
Queue files renamed ocr_done_* on success, ocr_skip_* if not processable.

Run standalone:  python core/ocr_consumer.py [--batch N] [--username NAME]
Triggered via:   POST /api/binder/process-queue
"""

import json
import hashlib
import logging
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from core import loam

USERNAME = "Sweet-Pea-Rudi19"
GDRIVE_PICKUP = Path(r"G:\My Drive\Willow\Auth Users") / USERNAME / "Pickup"
LOCAL_PICKUP = Path(__file__).parent.parent / "artifacts" / "willow" / "Auth Users" / USERNAME / "Pickup"
MAX_BATCH = 20
MAX_TEXT_LEN = 4000

log = logging.getLogger(__name__)


def _pickup() -> Path:
    return GDRIVE_PICKUP if GDRIVE_PICKUP.exists() else LOCAL_PICKUP


def _extract_image(path: Path) -> str:
    try:
        import pytesseract
        from PIL import Image
        pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        img = Image.open(path)
        if img.mode in ("CMYK", "P", "LA", "RGBA"):
            img = img.convert("RGB")
        return pytesseract.image_to_string(img).strip()
    except Exception as e:
        log.warning(f"OCR failed {path.name}: {e}")
        return ""


def _extract_pdf(path: Path) -> str:
    try:
        import pdfplumber
        parts = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages[:10]:
                t = page.extract_text()
                if t:
                    parts.append(t)
        return "\n".join(parts).strip()
    except Exception as e:
        log.warning(f"PDF extract failed {path.name}: {e}")
        return ""


def _extract_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
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


def process_queue(username: str = USERNAME, max_batch: int = MAX_BATCH) -> dict:
    """
    Drain up to max_batch items from the OCR queue.
    Returns dict with processed/skipped/failed counts.
    """
    pickup = _pickup()
    if not pickup.exists():
        return {"processed": 0, "skipped": 0, "failed": 0, "error": "Pickup not found"}

    queue_files = sorted(pickup.glob("ocr_queue_*.json"))[:max_batch]
    processed, skipped, failed = [], [], []

    for qf in queue_files:
        try:
            entry = json.loads(qf.read_text())
            src = Path(entry["path"])

            if not src.exists():
                qf.rename(qf.with_name(qf.name.replace("ocr_queue_", "ocr_skip_")))
                skipped.append(src.name)
                continue

            suffix = src.suffix.lower()

            if suffix in {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff"}:
                text = _extract_image(src)
            elif suffix == ".pdf":
                text = _extract_pdf(src)
            elif suffix in {".txt", ".md", ".csv"}:
                text = _extract_text(src)
            else:
                qf.rename(qf.with_name(qf.name.replace("ocr_queue_", "ocr_skip_")))
                skipped.append(src.name)
                continue

            if not text or len(text.strip()) < 20:
                qf.rename(qf.with_name(qf.name.replace("ocr_queue_", "ocr_skip_")))
                skipped.append(src.name)
                continue

            file_hash = hashlib.md5(text.encode()).hexdigest()
            cat = _category(src.name, text)

            loam.ingest_file_knowledge(
                username=username,
                filename=src.name,
                file_hash=file_hash,
                category=cat,
                content_text=text[:MAX_TEXT_LEN],
                provider="ocr_consumer",
            )

            qf.rename(qf.with_name(qf.name.replace("ocr_queue_", "ocr_done_")))
            processed.append(src.name)
            log.info(f"OCR: {src.name} -> {cat}")

        except Exception as e:
            log.error(f"OCR queue error {qf.name}: {e}")
            failed.append(qf.name)

    remaining = len(list(pickup.glob("ocr_queue_*.json")))
    return {
        "processed": len(processed),
        "skipped": len(skipped),
        "failed": len(failed),
        "processed_files": processed,
        "queue_remaining": remaining,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    import argparse
    parser = argparse.ArgumentParser(description="Drain Willow OCR queue")
    parser.add_argument("--batch", type=int, default=MAX_BATCH)
    parser.add_argument("--username", default=USERNAME)
    args = parser.parse_args()
    result = process_queue(username=args.username, max_batch=args.batch)
    print(json.dumps(result, indent=2))

#!/usr/bin/env python3
"""
Willow OCR Worker
=================
Drains the OCR queue from Pickup/.
Reads ocr_queue_*.json entries, OCRs images via Gemini vision fleet,
writes results to willow_knowledge.db, deletes queue files.

Usage:
    python apps/ocr_worker.py              # Process up to 20 images
    python apps/ocr_worker.py --all        # Drain entire queue
    python apps/ocr_worker.py --limit 5    # Process 5 images

GOVERNANCE: Safe to run manually. Does not delete source images.
"""

import sys
import json
import base64
import hashlib
import time
import argparse
from datetime import datetime
from pathlib import Path

# Add Willow root to path for core imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.db import get_connection
from core import llm_router
from apps.watcher import classify_lattice

# ─── PATHS ────────────────────────────────────────────────────────────────────

PICKUP_PATH  = Path(r"C:\Users\Sean\My Drive\Willow\Auth Users\Sweet-Pea-Rudi19\Pickup")
KNOWLEDGE_DB = Path(r"C:\Users\Sean\Documents\GitHub\Willow\artifacts\Sweet-Pea-Rudi19\willow_knowledge.db")
CREDENTIALS  = Path(r"C:\Users\Sean\Documents\GitHub\Willow\credentials.json")
EVENT_LOG    = Path(r"C:\Users\Sean\.willow\events.log")

RATE_LIMIT_SLEEP = 4.0  # seconds between Gemini calls (3 keys × ~15 RPM = ~1 req/4s safe rate)

OCR_PROMPT = (
    "Extract all text from this image. "
    "Return only the raw extracted text, preserving line breaks where present. "
    "No commentary, no formatting notes, just the text."
)


# ─── LOGGING ──────────────────────────────────────────────────────────────────

def log_event(event_type: str, details: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"{event_type} | {timestamp} | {details}\n"
    EVENT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(EVENT_LOG, "a", encoding="utf-8") as f:
        f.write(entry)
    safe = details.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(
        sys.stdout.encoding or "utf-8", errors="replace"
    )
    print(f"[{event_type}] {safe}")


# ─── DB INGESTION ─────────────────────────────────────────────────────────────

def ingest_ocr_result(image_path: str, ocr_text: str) -> bool:
    """Insert OCR result into willow_knowledge.db. Returns True if inserted."""
    source_id = hashlib.md5(image_path.encode("utf-8")).hexdigest()
    title = Path(image_path).name
    summary = ocr_text[:200].replace("\n", " ").strip()
    snippet = ocr_text[:400].replace("\n", " ").strip()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lattice = classify_lattice("ocr_image", "reference", title)

    try:
        conn = get_connection()
        existing = conn.execute(
            "SELECT id FROM knowledge WHERE source_id=?", (source_id,)
        ).fetchone()
        if existing:
            conn.close()
            return False  # already ingested

        conn.execute(
            """INSERT INTO knowledge
               (source_type, source_id, title, summary, content_snippet, category, ring, created_at,
                lattice_domain, lattice_type, lattice_status)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            ("ocr_image", source_id, title, summary, snippet, "reference", "bridge", now,
             lattice["lattice_domain"], lattice["lattice_type"], lattice["lattice_status"]),
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        log_event("DB_ERROR", f"{title} | {e}")
        return False


# ─── QUEUE PROCESSING ─────────────────────────────────────────────────────────

def process_queue_file(queue_file: Path) -> str:
    """
    Process one ocr_queue_*.json entry.
    Returns: 'ingested', 'duplicate', 'skip', or 'error'
    """
    try:
        entry = json.loads(queue_file.read_text(encoding="utf-8"))
    except Exception as e:
        log_event("QUEUE_READ_ERROR", f"{queue_file.name} | {e}")
        return "error"

    image_path = entry.get("path", "")
    if not image_path:
        log_event("QUEUE_BAD_ENTRY", f"{queue_file.name} | missing path")
        queue_file.unlink(missing_ok=True)
        return "skip"

    img = Path(image_path)
    if not img.exists():
        log_event("IMAGE_MISSING", f"{img.name}")
        queue_file.unlink(missing_ok=True)
        return "skip"

    # Base64 encode the image
    try:
        img_b64 = base64.b64encode(img.read_bytes()).decode("ascii")
    except Exception as e:
        log_event("IMAGE_READ_ERROR", f"{img.name} | {e}")
        return "error"

    # OCR via Gemini fleet
    ocr_text = llm_router.ask_with_vision(OCR_PROMPT, img_b64)

    if ocr_text is None:
        log_event("OCR_FAILED", f"{img.name} | all Gemini providers exhausted — will retry")
        return "error"  # leave queue file for retry

    ocr_text = ocr_text.strip()
    if not ocr_text:
        log_event("OCR_EMPTY", f"{img.name} | no text extracted")
        queue_file.unlink(missing_ok=True)
        return "skip"

    # Ingest to knowledge DB
    ingested = ingest_ocr_result(image_path, ocr_text)
    status = "ingested" if ingested else "duplicate"
    log_event(status.upper(), f"{img.name} | chars={len(ocr_text)}")

    # Delete queue file (source image stays in Drop — watcher manages it)
    queue_file.unlink(missing_ok=True)
    return status


def run(limit: int):
    """Drain OCR queue up to limit entries."""
    log_event("OCR_WORKER_START", f"limit={limit if limit > 0 else 'all'}")

    llm_router.load_keys_from_json()

    queue_files = sorted(PICKUP_PATH.glob("ocr_queue_*.json"))
    if not queue_files:
        log_event("OCR_WORKER_IDLE", "No queue files found")
        return

    to_process = queue_files if limit <= 0 else queue_files[:limit]
    log_event("OCR_WORKER_QUEUE", f"{len(to_process)} of {len(queue_files)} files to process")

    counts = {"ingested": 0, "duplicate": 0, "skip": 0, "error": 0}

    for i, qf in enumerate(to_process):
        result = process_queue_file(qf)
        counts[result] = counts.get(result, 0) + 1

        # Rate limit — don't hammer Gemini on the last item
        if i < len(to_process) - 1:
            time.sleep(RATE_LIMIT_SLEEP)

    log_event(
        "OCR_WORKER_DONE",
        f"ingested={counts['ingested']} duplicate={counts['duplicate']} "
        f"skip={counts['skip']} error={counts['error']} "
        f"remaining={len(queue_files) - len(to_process)}",
    )


# ─── ENTRY POINT ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Drain Willow OCR queue")
    parser.add_argument("--limit", type=int, default=20,
                        help="Max images to process (default: 20)")
    parser.add_argument("--all", dest="all_files", action="store_true",
                        help="Process all queue files (overrides --limit)")
    args = parser.parse_args()

    limit = 0 if args.all_files else args.limit
    run(limit)

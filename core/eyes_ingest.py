"""
Eyes -> Knowledge Pipeline

Connects: eyes_events.py capture -> content_scan.py scoring -> loam.py ingestion.
High-value screenshots (score >= 3) become knowledge atoms.

Can run as:
1. Standalone polling loop (python -m core.eyes_ingest)
2. Called per-screenshot from eyes_events.py capture()

GOVERNANCE:
- Requires willow.eyes consent via consent_gate
- Human must start this process
- Read-only on screenshots (no deletion)
- Append-only to knowledge DB

CHECKSUM: DS=42
"""

import os
import sys
import time
import hashlib
import logging
from pathlib import Path
from datetime import datetime

# Wire imports
_willow_root = Path(__file__).parent.parent
_eyes_path = str(Path(__file__).parent.parent.parent / "die-namic-system" / "apps" / "eyes")

if str(_willow_root) not in sys.path:
    sys.path.insert(0, str(_willow_root))
if _eyes_path not in sys.path:
    sys.path.insert(0, _eyes_path)

from core import loam

# Try to import content_scan (may not be available if die-namic-system not present)
try:
    import content_scan
    _CONTENT_SCAN_AVAILABLE = True
except ImportError:
    _CONTENT_SCAN_AVAILABLE = False
    logging.warning("EYES_INGEST: content_scan.py not found — OCR scoring disabled")

# Config
SCREENSHOT_DIR = Path(r"C:\Users\Sean\screenshots")
PROCESSED_LOG = SCREENSHOT_DIR / "knowledge_ingested.log"
USERNAME = "Sweet-Pea-Rudi19"
POLL_INTERVAL = 30  # seconds
MIN_SCORE = 3       # content_scan "keep" threshold

_processed = set()


def _file_hash(filepath) -> str:
    """SHA-256 of file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_processed() -> set:
    """Load set of already-ingested file hashes."""
    if PROCESSED_LOG.exists():
        try:
            return set(PROCESSED_LOG.read_text(encoding='utf-8').strip().split("\n"))
        except Exception:
            return set()
    return set()


def _mark_processed(fhash: str):
    """Append hash to processed log."""
    PROCESSED_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(PROCESSED_LOG, "a", encoding='utf-8') as f:
        f.write(f"{fhash}\n")


def ingest_screenshot(filepath, username: str = USERNAME) -> bool:
    """
    Score a single screenshot and ingest into knowledge if high-value.

    Returns True if ingested, False if skipped.
    Can be called from eyes_events.py capture() or from polling loop.
    """
    filepath = Path(filepath)
    if not filepath.exists():
        return False

    global _processed
    if not _processed:
        _processed = _load_processed()

    fhash = _file_hash(filepath)
    if fhash in _processed:
        return False

    # Score via content_scan if available
    text = ""
    score = 0
    if _CONTENT_SCAN_AVAILABLE:
        result = content_scan.scan_screenshot(str(filepath))
        if result.get("error"):
            return False
        score = result.get("score", 0)
        text = result.get("text", "")
    else:
        # No OCR — just record the file metadata
        text = f"Screenshot captured: {filepath.name}"
        score = MIN_SCORE  # Ingest anyway for the record

    if score < MIN_SCORE:
        _mark_processed(fhash)  # Don't re-score low-value screenshots
        return False

    if not text:
        return False

    # Ingest into knowledge DB
    loam.ingest_file_knowledge(
        username=username,
        filename=filepath.name,
        file_hash=fhash,
        category="eyes_capture",
        content_text=text,
        provider="content_scan"
    )

    _mark_processed(fhash)
    _processed.add(fhash)
    logging.info(f"EYES->KNOWLEDGE: {filepath.name} score={score} ingested")
    return True


def run_pipeline(username: str = USERNAME):
    """Main polling loop: watch screenshots dir, score, ingest."""
    global _processed

    # Check consent
    try:
        from core.consent_gate import check_signal_consent
        if not check_signal_consent("eyes"):
            print("CONSENT REQUIRED: willow.eyes not granted.")
            print("Grant via opauth before running eyes pipeline.")
            return
    except ImportError:
        print("WARNING: consent_gate not available, proceeding with caution")

    _processed = _load_processed()
    print(f"Eyes->Knowledge pipeline online. Watching {SCREENSHOT_DIR}")
    print(f"Already processed: {len(_processed)} files")
    print(f"OCR scoring: {'content_scan.py' if _CONTENT_SCAN_AVAILABLE else 'DISABLED'}")

    try:
        while True:
            if SCREENSHOT_DIR.exists():
                for png in sorted(SCREENSHOT_DIR.glob("screen_*.png")):
                    try:
                        ingest_screenshot(png, username)
                    except Exception as e:
                        logging.error(f"EYES_INGEST: {png.name}: {e}")
            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        print(f"\nEyes pipeline stopped. {len(_processed)} total processed.")


if __name__ == "__main__":
    run_pipeline()

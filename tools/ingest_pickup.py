"""
ingest_pickup.py — Route Pickup folder documents into Willow knowledge graph.
==============================================================================
The Pickup folder is where Ganesha drops handoffs, specs, context docs, and
session logs. This tool ingests them into the knowledge graph via
POST /api/knowledge/ingest, then archives processed files.

Usage:
    python tools/ingest_pickup.py              # batch all unprocessed files
    python tools/ingest_pickup.py --watch      # continuous poll loop
    python tools/ingest_pickup.py --dry-run    # show what would be ingested

CHECKSUM: ΔΣ=42
"""

import argparse
import hashlib
import json
import logging
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

WILLOW_ROOT  = Path(__file__).resolve().parent.parent
PICKUP_DIR   = Path("/mnt/c/Users/Sean/My Drive/Willow/Auth Users/Sweet-Pea-Rudi19/Pickup")
ARCHIVE_DIR  = PICKUP_DIR / ".processed"
INGEST_URL   = "http://localhost:8420/api/knowledge/ingest"
USERNAME     = "Sweet-Pea-Rudi19"
DEFAULT_INTERVAL = 30  # seconds

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - ingest_pickup - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
    ]
)
log = logging.getLogger("ingest_pickup")


# ── Category detection ────────────────────────────────────────────────────────

def _category(path: Path) -> str:
    name = path.name.upper()
    if any(k in name for k in ("SESSION_HANDOFF", "HANDOFF")):
        return "session-log"
    if any(k in name for k in ("_SPEC_", "SPEC_V", "FRAMEWORK")):
        return "spec"
    if any(k in name for k in ("BANKRUPTCY", "MOTION_", "LAW_GAZELLE", "CREDITOR",
                                "SCHEDULE", "COPARENTING", "MEDIATION", "MED_")):
        return "legal"
    if "CONTEXT_FOR" in name or "CONTEXT_" in name:
        return "context"
    if "CONVERSATION LOG" in name or path.suffix.lower() in (".jsonl",):
        return "session-log"
    if "KNOWLEDGE_ATOMS" in name or "ATOM" in name:
        return "knowledge"
    return "reference"


# ── Ingest one file ───────────────────────────────────────────────────────────

def _ingest(path: Path, dry_run: bool = False) -> bool:
    """Read file, POST to knowledge ingest endpoint. Returns True on success."""
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        log.warning(f"cannot read {path.name}: {e}")
        return False

    if not content.strip():
        log.info(f"skip empty: {path.name}")
        return True  # treat as done — nothing to ingest

    category  = _category(path)
    file_hash = hashlib.md5(content.encode("utf-8", errors="replace")).hexdigest()

    if dry_run:
        log.info(f"[dry-run] {path.name} → {category} ({len(content)} chars)")
        return True

    try:
        r = requests.post(
            INGEST_URL,
            json={
                "username":     USERNAME,
                "filename":     path.name,
                "content_text": content,
                "category":     category,
                "provider":     "pickup-ingestor",
                "file_hash":    file_hash,
            },
            timeout=30,
        )
        result = r.json()
        if r.status_code in (200, 202):
            log.info(f"ingested: {path.name} → {category}")
            return True
        else:
            log.warning(f"rejected ({r.status_code}): {path.name} — {result}")
            return False
    except requests.ConnectionError:
        log.error("Willow not reachable — is the server running on port 8420?")
        return False
    except Exception as e:
        log.error(f"ingest failed {path.name}: {e}")
        return False


# ── Archive ───────────────────────────────────────────────────────────────────

def _archive(path: Path):
    """Move processed file to .processed/ subdirectory."""
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    ts   = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    dest = ARCHIVE_DIR / f"{ts}_{path.name}"
    shutil.move(str(path), str(dest))
    log.info(f"archived → .processed/{dest.name}")


# ── Scan ──────────────────────────────────────────────────────────────────────

PROCESSABLE = {".md", ".txt", ".jsonl", ".json"}

def scan_once(dry_run: bool = False) -> int:
    """Scan Pickup folder for unprocessed files. Returns count ingested."""
    if not PICKUP_DIR.exists():
        log.error(f"Pickup folder not found: {PICKUP_DIR}")
        return 0

    ingested = 0
    paths = sorted(
        p for p in PICKUP_DIR.iterdir()
        if p.is_file()
        and p.suffix.lower() in PROCESSABLE
        and not p.name.startswith(".")
        and not p.name.startswith("_")
        and ".processed" not in p.parts
    )

    if not paths:
        log.info("nothing to process")
        return 0

    log.info(f"found {len(paths)} file(s) to process")

    for path in paths:
        if _ingest(path, dry_run=dry_run):
            if not dry_run:
                _archive(path)
            ingested += 1

    return ingested


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Ingest Pickup folder → Willow knowledge graph")
    parser.add_argument("--watch",    action="store_true", help="Continuous poll loop")
    parser.add_argument("--dry-run",  action="store_true", help="Show what would be ingested, no writes")
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL,
                        help=f"Poll interval in seconds when watching (default: {DEFAULT_INTERVAL})")
    args = parser.parse_args()

    if args.dry_run:
        log.info("DRY RUN — no files will be ingested or archived")

    if args.watch:
        log.info(f"watching {PICKUP_DIR} (interval: {args.interval}s)")
        while True:
            try:
                n = scan_once(dry_run=args.dry_run)
                if n:
                    log.info(f"processed {n} file(s)")
            except Exception as e:
                log.error(f"scan error: {e}")
            time.sleep(args.interval)
    else:
        n = scan_once(dry_run=args.dry_run)
        print(f"\nDone — ingested {n} file(s)")
        if n > 0 and not args.dry_run:
            print(f"Archived to: {ARCHIVE_DIR}")


if __name__ == "__main__":
    main()

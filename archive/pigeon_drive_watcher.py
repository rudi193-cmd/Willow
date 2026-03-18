"""
Pigeon Drive Watcher
====================
Watches the My Drive/Willow/ folder recursively for JSON files that match
the pigeon message schema. Routes them through the local pigeon bus,
then archives processed files.

Message schema (any JSON with these fields):
    {
        "from": "oakenscroll",
        "to":   "ganesha-cli",
        "subject": "...",
        "body": "...",
        "timestamp": "2026-...",   # optional
        "thread_id": null          # optional
    }

Usage:
    python core/pigeon_drive_watcher.py              # run once (cron mode)
    python core/pigeon_drive_watcher.py --watch      # continuous poll loop
    python core/pigeon_drive_watcher.py --interval 10

CHECKSUM: ΔΣ=42
"""

import argparse
import json
import logging
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

WILLOW_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WILLOW_ROOT))

DRIVE_WILLOW = Path("/mnt/c/Users/Sean/My Drive (rudi193@gmail.com)/Willow")
PROCESSED_DIR = DRIVE_WILLOW / "Nest" / ".processed"
PIGEON_URL = "http://localhost:8420/api/pigeon/drop"
USERNAME = "Sweet-Pea-Rudi19"
DEFAULT_INTERVAL = 10  # seconds

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - pigeon_drive - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(WILLOW_ROOT / "logs" / "pigeon_drive.log"),
        logging.StreamHandler(),
    ]
)
log = logging.getLogger("pigeon_drive")


def _is_pigeon_message(data: dict) -> bool:
    """Return True if the JSON looks like a pigeon message."""
    return (
        isinstance(data, dict)
        and "from" in data
        and "to" in data
        and "body" in data
    )


def _archive(path: Path):
    """Move processed file to .processed/ with timestamp prefix."""
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    dest = PROCESSED_DIR / f"{ts}_{path.name}"
    shutil.move(str(path), str(dest))
    log.info(f"archived → {dest.name}")


def _route(data: dict, source_path: Path) -> bool:
    """POST message to pigeon bus. Returns True on success."""
    payload = {
        "topic": "send",
        "app_id": data["from"],
        "username": data.get("username", USERNAME),
        "payload": {
            "to":        data["to"],
            "subject":   data.get("subject", "(no subject)"),
            "body":      data["body"],
            "thread_id": data.get("thread_id"),
        }
    }
    try:
        r = requests.post(PIGEON_URL, json=payload, timeout=15)
        result = r.json()
        if result.get("ok"):
            log.info(f"routed: {data['from']} → {data['to']} | {data.get('subject','')}")
            return True
        else:
            log.warning(f"bus rejected: {result.get('error')} | file={source_path.name}")
            return False
    except requests.ConnectionError:
        log.error("pigeon bus not reachable — is Willow running?")
        return False
    except Exception as e:
        log.error(f"route failed: {e}")
        return False


def scan_once() -> int:
    """Scan Drive Willow root recursively. Returns count of processed files."""
    if not DRIVE_WILLOW.exists():
        log.warning(f"Drive folder not found: {DRIVE_WILLOW}")
        return 0

    processed = 0
    for path in sorted(DRIVE_WILLOW.rglob("*.json")):
        # Skip already-processed archives
        if ".processed" in path.parts:
            continue
        # Skip known non-message files
        if path.name.startswith("_") or path.name.startswith("."):
            continue

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        if not _is_pigeon_message(data):
            continue

        log.info(f"found message: {path.relative_to(DRIVE_WILLOW)}")
        if _route(data, path):
            _archive(path)
            processed += 1
        # If routing fails, leave file in place for next scan

    return processed


def main():
    parser = argparse.ArgumentParser(description="Pigeon Drive Watcher")
    parser.add_argument("--watch",    action="store_true", help="Continuous poll loop")
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL,
                        help=f"Poll interval in seconds (default: {DEFAULT_INTERVAL})")
    parser.add_argument("--drive",    default=None, help="Override Drive Willow path")
    args = parser.parse_args()

    global DRIVE_WILLOW
    if args.drive:
        DRIVE_WILLOW = Path(args.drive)

    if args.watch:
        log.info(f"watching {DRIVE_WILLOW} (interval: {args.interval}s)")
        while True:
            try:
                n = scan_once()
                if n:
                    log.info(f"processed {n} message(s)")
            except Exception as e:
                log.error(f"scan error: {e}")
            time.sleep(args.interval)
    else:
        n = scan_once()
        print(f"processed {n} message(s)")


if __name__ == "__main__":
    main()

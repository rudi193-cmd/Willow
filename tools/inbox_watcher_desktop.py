#!/usr/bin/env python3
"""
Claude Desktop Inbox Watcher
Polls pigeon_inbox for claude-desktop messages. On new message:
  - Writes to %TEMP%/claude_desktop_pending.json
Runs forever. Launch with: python tools/inbox_watcher_desktop.py
"""

import os
import sys
import json
import time
import logging
from pathlib import Path
from datetime import datetime, timezone

# Load .env for Postgres connection
_env = Path(__file__).parent.parent / ".env"
if _env.exists():
    with open(_env) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k, v)

sys.path.insert(0, str(Path(__file__).parent.parent))

from core import pigeon

PENDING_FILE = Path(os.environ.get("TEMP", "C:/Users/Sean/AppData/Local/Temp")) / "claude_desktop_pending.json"
POLL_INTERVAL = 10  # seconds
APP_ID = "claude-desktop"

LOG_DIR = Path(os.environ.get("TEMP", "C:/Users/Sean/AppData/Local/Temp"))
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [desktop-watcher] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "inbox_watcher_desktop.log"),
        logging.StreamHandler(),
    ]
)
log = logging.getLogger(__name__)


def load_pending() -> list:
    if PENDING_FILE.exists():
        try:
            return json.loads(PENDING_FILE.read_text())
        except Exception:
            return []
    return []


def save_pending(messages: list):
    PENDING_FILE.write_text(json.dumps(messages, indent=2, default=str))


def process_new_messages(messages: list):
    pending = load_pending()
    new = []
    existing_ids = {m["id"] for m in pending}

    for m in messages:
        if m["id"] not in existing_ids:
            new.append(m)
            log.info(f"New message [{m['id']}] from {m['from_app']}: {m['subject']}")

    if new:
        save_pending(pending + new)
        pigeon.mark_inbox_read(APP_ID)

    return len(new)


def main():
    log.info(f"Inbox watcher started. Polling {APP_ID} every {POLL_INTERVAL}s.")
    log.info(f"Pending file: {PENDING_FILE}")
    while True:
        try:
            messages = pigeon.get_inbox(APP_ID, unread_only=True)
            if messages:
                count = process_new_messages(messages)
                if count:
                    log.info(f"Queued {count} new message(s) to pending file.")
        except Exception as e:
            log.error(f"Poll error: {e}")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()

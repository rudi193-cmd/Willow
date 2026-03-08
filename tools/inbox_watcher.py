#!/usr/bin/env python3
"""
Ganesha Inbox Watcher
Polls pigeon_inbox for ganesha-cli messages. On new message:
  - Writes to /tmp/ganesha_pending.json
  - Sends ntfy push to willow-ds42
Runs forever. Launch with: nohup python3 tools/inbox_watcher.py &
"""

import os
import sys
import json
import time
import logging
import requests
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

PENDING_FILE = Path("/tmp/ganesha_pending.json")
POLL_INTERVAL = 10  # seconds
NTFY_TOPIC = "willow-ds42"
APP_ID = "ganesha-cli"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [watcher] %(message)s",
    handlers=[
        logging.FileHandler("/tmp/inbox_watcher.log"),
        logging.StreamHandler(),
    ]
)
log = logging.getLogger(__name__)


def send_ntfy(title: str, message: str):
    try:
        requests.post(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=message.encode("utf-8"),
            headers={"Title": title, "Priority": "default"},
            timeout=5,
        )
    except Exception as e:
        log.warning(f"ntfy failed: {e}")


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
        titles = ", ".join(f"{m['from_app']}" for m in new)
        body = "\n".join(f"{m['subject']}: {m['body'][:80]}" for m in new)
        send_ntfy(f"📬 Pigeon: {titles}", body)
        # NOTE: mark_inbox_read is called by the inject hook after consumption,
        # not here — prevents losing messages if hook hasn't fired yet.

    return len(new)


def main():
    log.info(f"Inbox watcher started. Polling {APP_ID} every {POLL_INTERVAL}s.")
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

#!/usr/bin/env python3
"""
Single-shot inbox watcher for ganesha-cli.
Polls until one message arrives, prints it, exits.
Claude Code auto-notifies Ganesha on exit — Ganesha relaunches immediately.
"""

import os
import sys
import time
from pathlib import Path

# Load .env for Postgres
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

POLL_INTERVAL = 10
APP_ID = "ganesha-cli"

while True:
    try:
        messages = pigeon.get_inbox(APP_ID, unread_only=True)
        if messages:
            pigeon.mark_inbox_read(APP_ID)
            print(f"\n📬 {len(messages)} message(s) via Pigeon:\n")
            for m in messages:
                print(f"From: {m['from_app']}")
                print(f"Subject: {m['subject']}")
                print(f"Body: {m['body']}")
                print()
            sys.exit(0)
    except Exception as e:
        print(f"[watcher error] {e}", file=sys.stderr)
    time.sleep(POLL_INTERVAL)

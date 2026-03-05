#!/usr/bin/env python3
r"""
Willow Nest Watcher

Monitors C:\Users\Sean\Willow\Nest for new files and triggers Pigeon scan.

GOVERNANCE: This script must be started by human action only.
AI cannot invoke this script directly.
"""

import json
import time
from datetime import datetime
from pathlib import Path

# Config
NEST_PATH            = Path(r'C:\Users\Sean\Willow\Nest')
STATE_FILE           = Path(r'C:\Users\Sean\.willow\watcher_state.json')
EVENT_LOG            = Path(r'C:\Users\Sean\.willow\events.log')
POLL_INTERVAL        = 5   # seconds
PIGEON_SCAN_URL      = 'http://localhost:8420/api/pigeon/scan'
PIGEON_USERNAME      = 'Sweet-Pea-Rudi19'


def ensure_dirs():
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"known_files": [], "last_run": None}


def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2, default=str))


def log_event(event_type: str, details: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"{event_type} | {timestamp} | {details}\n"
    try:
        with open(EVENT_LOG, "a", encoding="utf-8") as f:
            f.write(entry)
    except Exception:
        pass
    print(f"[{event_type}] {details}")


def trigger_pigeon_scan() -> bool:
    """Write trigger file for pigeon_daemon (non-blocking).""" 
    try:
        trigger = Path(r"C:\Users\Sean\Documents\GitHub\Willow\artifacts\Sweet-Pea-Rudi19\.pigeon_trigger")
        trigger.parent.mkdir(parents=True, exist_ok=True)
        trigger.touch()
        log_event("PIGEON_TRIGGERED", "trigger file written")
        return True
    except Exception as e:
        log_event("PIGEON_ERROR", str(e))
        return False


def scan_nest() -> set:
    if not NEST_PATH.exists():
        return set()
    return {
        str(item)
        for item in NEST_PATH.iterdir()
        if item.is_file() and not item.name.startswith(".")
    }


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-consent", action="store_true",
                        help="Skip consent prompt (for background service)")
    args = parser.parse_args()

    print("Willow Nest Watcher")
    print(f"Watching: {NEST_PATH}")
    print(f"Poll interval: {POLL_INTERVAL}s")

    if not args.no_consent:
        consent = input("Start watching? (yes/no): ").strip().lower()
        if consent != "yes":
            print("Aborted.")
            return
    else:
        print("Background mode: consent assumed from human startup.")

    ensure_dirs()
    state = load_state()
    known = set(state.get("known_files", []))

    log_event("WATCHER_ON", f"nest={NEST_PATH}")
    print(f"\nWatcher online. Press Ctrl+C to stop.\n")

    try:
        while True:
            current = scan_nest()
            new_files = current - known

            if new_files:
                for f in sorted(new_files):
                    log_event("NEW_FILE", Path(f).name)
                # Debounce: wait 2s for additional files before triggering scan
                time.sleep(2)
                current = scan_nest()
                new_files = current - known
                trigger_pigeon_scan()
                known = current

            removed = known - current
            for f in removed:
                log_event("FILE_REMOVED", Path(f).name)
            if removed:
                known = current

            save_state({"known_files": list(known), "last_run": datetime.now().isoformat()})
            time.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        pass
    finally:
        log_event("WATCHER_OFF", f"known_files={len(known)}")
        save_state({"known_files": list(known), "last_run": datetime.now().isoformat()})
        print(f"\nWatcher off. Tracking {len(known)} files.")


if __name__ == "__main__":
    main()

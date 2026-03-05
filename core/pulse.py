"""
Kart Daemon -- Background Task Worker

Bridge Ring engine: polls graft.db for pending actionable tasks,
routes them through KartOrchestrator, marks results.

Launch: python core/pulse.py [--username NAME] [--interval SECS]
Server: started as subprocess by server.py on startup (same pattern as pigeon_daemon)

GOVERNANCE: kart-daemon-worker-1997f1a1a903
CHECKSUM: ΔΣ=42
"""

import os
import sys
import time
import signal
import logging
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import graft
from core.rings import KartOrchestrator

logging.basicConfig(
    level=logging.INFO,
    format="[kart-daemon] %(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

POLL_INTERVAL = int(os.environ.get("KART_POLL_INTERVAL", "30"))
USERNAME = os.environ.get("WILLOW_USERNAME", "Sweet-Pea-Rudi19")

# Session-marker tasks logged by agents — not actionable work items
SKIP_SUBJECTS = {
    "Ganesha CLI session",
    "ganesha cli session",
}

_running = True


def _handle_signal(sig, frame):
    global _running
    logger.info("Shutdown signal received — stopping after current task")
    _running = False


def _is_actionable(task: dict) -> bool:
    return task.get("subject", "") not in SKIP_SUBJECTS


def _archive_stale(username: str) -> int:
    """On startup: archive non-actionable pending tasks so they don't clog the queue."""
    tasks = graft.list_tasks(username, status="pending")
    count = 0
    for t in tasks:
        if not _is_actionable(t):
            graft.update_task(username, t["task_id"], "archived", "pulse")
            count += 1
    return count


def run(username: str, poll_interval: int = POLL_INTERVAL):
    global _running
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    logger.info(f"Kart daemon starting — user={username} interval={poll_interval}s")

    stale = _archive_stale(username)
    if stale:
        logger.info(f"Archived {stale} stale session-marker tasks")

    orchestrator = KartOrchestrator(username, agent_name="kart")
    consecutive_errors = 0

    while _running:
        try:
            tasks = graft.list_tasks(username, status="pending")
            actionable = [t for t in tasks if _is_actionable(t)]

            if actionable:
                task = actionable[0]
                task_id = task["task_id"]
                description = task["description"]

                logger.info(f"Task {task_id}: {description[:80]!r}")
                graft.update_task(username, task_id, "in_progress", "pulse")

                try:
                    result = orchestrator.execute(description)
                    status = "COMPLETED" if result.get("success") else "FAILED"
                    summary = str(result.get("result", ""))[:120]
                    logger.info(f"Task {task_id} {status} — {summary}")
                    graft.update_task(username, task_id, status, "pulse")
                    consecutive_errors = 0
                except Exception as e:
                    logger.error(f"Task {task_id} execution error: {e}")
                    graft.update_task(username, task_id, "FAILED", "pulse")
                    consecutive_errors += 1

                # Back off if repeatedly failing
                if consecutive_errors >= 3:
                    logger.warning(f"{consecutive_errors} consecutive failures — pausing 5min")
                    time.sleep(300)
                    consecutive_errors = 0
                    continue

            consecutive_errors = 0

        except Exception as e:
            logger.error(f"Daemon loop error: {e}")
            consecutive_errors += 1

        time.sleep(poll_interval)

    logger.info("Kart daemon stopped cleanly")


def main():
    parser = argparse.ArgumentParser(description="Kart background task daemon")
    parser.add_argument("--username", default=USERNAME, help="Willow username")
    parser.add_argument("--interval", type=int, default=POLL_INTERVAL, help="Poll interval in seconds")
    parser.add_argument("--daemon", action="store_true", help="No-op flag for compat with WILLOW.bat")
    args = parser.parse_args()
    run(args.username, args.interval)


if __name__ == "__main__":
    main()

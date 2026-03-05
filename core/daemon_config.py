"""
daemon_config.py -- System-wide daemon timing constants.

Slot assignments:
    0 = pigeon_daemon   (3s poll, 0s delay)
    1 = watcher         (3s poll, +7s delay)
    2 = ocr_consumer    (4s poll, +14s delay)
    3 = future          (4s poll, +21s delay)
    4 = future          (3s poll, +28s delay)
"""

POLL_INTERVALS = [3, 3, 4, 4, 3]   # seconds per slot
STARTUP_OFFSET = 7                   # seconds between daemon starts
BASE_DELAY     = 12                  # minimum startup wait (lets server finish init)


def get_poll_interval(slot: int) -> int:
    return POLL_INTERVALS[slot % len(POLL_INTERVALS)]


def get_startup_delay(slot: int) -> int:
    return BASE_DELAY + slot * STARTUP_OFFSET

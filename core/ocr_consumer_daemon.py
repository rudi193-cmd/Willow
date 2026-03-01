"""
ocr_consumer_daemon.py -- OCR queue drain daemon (slot 2).
Launched as subprocess by server.py on startup.
Poll: 4s. Startup delay: 14s.
"""
import time, sys, logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.daemon_config import get_poll_interval, get_startup_delay

DAEMON_SLOT = 2
USERNAME = "Sweet-Pea-Rudi19"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [OCR] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)


def _has_queue_files() -> bool:
    from core.ocr_consumer import GDRIVE_PICKUP, LOCAL_PICKUP
    for pickup in (GDRIVE_PICKUP, LOCAL_PICKUP):
        try:
            if any(pickup.glob("ocr_queue_*.json")):
                return True
        except Exception:
            pass
    return False


def main():
    from core import ocr_consumer
    delay = get_startup_delay(DAEMON_SLOT)
    poll  = get_poll_interval(DAEMON_SLOT)
    if delay:
        logger.info("Startup delay: %ds (slot %d)", delay, DAEMON_SLOT)
        time.sleep(delay)
    logger.info("OCR consumer daemon ready -- poll every %ds (slot %d)", poll, DAEMON_SLOT)
    while True:
        try:
            if _has_queue_files():
                logger.info("Queue files found -- draining")
                result = ocr_consumer.process_queue(USERNAME)
                processed = result.get("processed", 0)
                remaining = result.get("queue_remaining", 0)
                logger.info("Drained %d item(s), %d remaining", processed, remaining)
        except Exception as e:
            logger.error("Error: %s", e)
        time.sleep(poll)


if __name__ == "__main__":
    main()

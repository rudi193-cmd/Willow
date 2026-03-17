"""
ocr_consumer_daemon.py -- OCR enrichment daemon (slot 2).
Launched as subprocess by server.py on startup.
Poll: 4s. Startup delay: 14s.

Bridge Ring service: enriches pending review queue items with full OCR
extraction and importance scoring. Does not ingest to LOAM — that's
confirm_review()'s job after human approval.

Two enrichment paths per cycle:
  1. Queue enrichment (every cycle) — pending items with short/missing ocr_text
  2. Screenshot scoring (every 5th cycle) — flag low-value screenshots
"""
import time, sys, logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass
from core.daemon_config import get_poll_interval, get_startup_delay

DAEMON_SLOT = 2
USERNAME = "Sweet-Pea-Rudi19"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [OCR] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)


def _has_pending_items() -> bool:
    """Check if there are pending review queue items that need enrichment."""
    try:
        from core.ocr_consumer import _get_pending_items, _needs_enrichment
        items = _get_pending_items(USERNAME, max_batch=5)
        return any(_needs_enrichment(item) for item in items)
    except Exception:
        return False


SCREENSHOT_EVERY_N = 5  # score screenshots every Nth cycle (~20s at 4s poll)


def main():
    from core import ocr_consumer
    delay = get_startup_delay(DAEMON_SLOT)
    poll  = get_poll_interval(DAEMON_SLOT)
    if delay:
        logger.info("Startup delay: %ds (slot %d)", delay, DAEMON_SLOT)
        time.sleep(delay)
    logger.info("OCR enrichment daemon ready -- poll every %ds (slot %d)", poll, DAEMON_SLOT)
    cycle = 0
    while True:
        try:
            # Path 1: Enrich pending queue items (every cycle)
            if _has_pending_items():
                logger.info("Pending items found -- enriching")
                result = ocr_consumer.enrich_queue(USERNAME)
                enriched = result.get("enriched", 0)
                pending = result.get("queue_pending", 0)
                if enriched > 0:
                    logger.info("Enriched %d item(s), %d pending", enriched, pending)

            # Path 2: Score screenshots (every Nth cycle)
            if cycle % SCREENSHOT_EVERY_N == 0:
                ss = ocr_consumer.score_screenshots(USERNAME, max_batch=5)
                low = ss.get("low_value", 0)
                if low > 0:
                    logger.info("Eyes: flagged %d low-value screenshot(s)", low)
        except Exception as e:
            logger.error("Error: %s", e)
        cycle += 1
        time.sleep(poll)


if __name__ == "__main__":
    main()

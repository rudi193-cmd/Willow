"""
pigeon_daemon.py -- Pigeon file-intake daemon (slot 0).
Launched as subprocess by server.py on startup.
Poll: 3s. Startup delay: 0s.
"""
import time, sys, logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.daemon_config import get_poll_interval, get_startup_delay

DAEMON_SLOT = 0
TRIGGER = Path(r"C:\Users\Sean\Documents\GitHub\Willow\artifacts\Sweet-Pea-Rudi19\.pigeon_trigger")
USERNAME = "Sweet-Pea-Rudi19"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [PIGEON] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)


def main():
    from core import pigeon
    pigeon.init_droppings_table()
    delay = get_startup_delay(DAEMON_SLOT)
    poll  = get_poll_interval(DAEMON_SLOT)
    if delay:
        logger.info("Startup delay: %ds (slot %d)", delay, DAEMON_SLOT)
        time.sleep(delay)
    logger.info("Pigeon daemon ready -- poll every %ds (slot %d)", poll, DAEMON_SLOT)
    while True:
        try:
            if TRIGGER.exists():
                TRIGGER.unlink()
                logger.info("Trigger received -- scanning Nest")
                new = pigeon.scan_and_process(USERNAME)
                logger.info("Scan complete: %d new droppings", len(new) if new else 0)
        except Exception as e:
            logger.error("Error: %s", e)
        time.sleep(poll)


if __name__ == "__main__":
    main()

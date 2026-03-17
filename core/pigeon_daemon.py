"""
pigeon_daemon.py -- Pigeon file-intake daemon (slot 0).
Launched as subprocess by server.py on startup.
Poll: 3s. Startup delay: 0s.
"""
import time, sys, logging
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.daemon_config import get_poll_interval, get_startup_delay

DAEMON_SLOT = 0
USERNAME = "Sweet-Pea-Rudi19"
AUTO_SCAN_SECS = 30

_WIN = sys.platform == "win32"
_BASE = r"C:\Users\Sean" if _WIN else "/mnt/c/Users/Sean"
_REPO = (r"C:\Users\Sean\Documents\GitHub\Willow" if _WIN
         else "/mnt/c/Users/Sean/Documents/GitHub/Willow")
TRIGGER = Path(_REPO) / "artifacts" / "Sweet-Pea-Rudi19" / ".pigeon_trigger"
NEST_PATH = Path(_BASE) / "Willow" / "Nest"

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
    _last_auto = 0
    while True:
        try:
            now = time.monotonic()
            triggered = False

            if TRIGGER.exists():
                TRIGGER.unlink()
                logger.info("Trigger received -- scanning Nest")
                triggered = True
            elif (now - _last_auto) >= AUTO_SCAN_SECS:
                _last_auto = now
                if NEST_PATH.exists() and any(
                    f.is_file() and not f.name.startswith(".")
                    for f in NEST_PATH.iterdir()  # root only, not rglob — skip processed/
                ):
                    logger.info("Auto-trigger: files in Nest")
                    triggered = True

            if triggered:
                new = pigeon.scan_and_process(USERNAME)
                _last_auto = time.monotonic()
                logger.info("Scan complete: %d new droppings", len(new) if new else 0)
                # Clean up empty subdirectories
                if NEST_PATH.exists():
                    for d in sorted(NEST_PATH.rglob("*"), reverse=True):
                        if d.is_dir() and not any(d.iterdir()):
                            logger.info("Removing empty dir: %s", d.name)
                            d.rmdir()
        except Exception as e:
            logger.error("Error: %s", e)
        time.sleep(poll)


if __name__ == "__main__":
    main()

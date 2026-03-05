#!/usr/bin/env python3
import argparse
import logging
import os
import signal
import sys
import time
from pathlib import Path
from typing import Optional

# Constants
DEFAULT_INTERVAL = 60  # seconds
DEFAULT_THRESHOLD = 86400  # 24 hours in seconds
LOG_FILE = Path("governance/violations.log")
COMMITS_DIR = Path("governance/commits/")

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class GovernanceMonitor:
    def __init__(self, interval: int, threshold: int, daemon: bool):
        self.interval = interval
        self.threshold = threshold
        self.daemon = daemon
        self.running = False

    def _scan_pending_files(self) -> list[Path]:
        """Scan for .pending files in the commits directory."""
        try:
            pending_files = list(COMMITS_DIR.glob("*.pending"))
            return pending_files
        except Exception as e:
            logger.error(f"Error scanning for pending files: {e}")
            return []

    def _check_violation(self, file_path: Path) -> bool:
        """Check if a pending file is older than the threshold."""
        try:
            creation_time = file_path.stat().st_ctime
            current_time = time.time()
            age = current_time - creation_time
            return age > self.threshold
        except Exception as e:
            logger.error(f"Error checking file {file_path}: {e}")
            return False

    def _log_violation(self, file_path: Path) -> None:
        """Log a governance violation."""
        try:
            logger.warning(f"Governance violation detected: {file_path} is older than {self.threshold} seconds")
            with open(LOG_FILE, "a") as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - WARNING - Governance violation: {file_path} is older than {self.threshold} seconds\n")
        except Exception as e:
            logger.error(f"Error logging violation for {file_path}: {e}")

    def _handle_signal(self, signum: int, frame) -> None:
        """Handle termination signals."""
        self.running = False
        logger.info("Shutting down gracefully...")

    def run(self) -> None:
        """Main monitoring loop."""
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        self.running = True
        logger.info(f"Starting governance monitor (interval: {self.interval}s, threshold: {self.threshold}s, daemon: {self.daemon})")

        while self.running:
            try:
                pending_files = self._scan_pending_files()
                for file_path in pending_files:
                    if self._check_violation(file_path):
                        self._log_violation(file_path)
                        if not self.daemon:
                            print(f"WARNING: Governance violation detected: {file_path} is older than {self.threshold} seconds")

                time.sleep(self.interval)
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                time.sleep(self.interval)

def main():
    parser = argparse.ArgumentParser(description="Governance monitor for Willow's Dual Commit system")
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL,
                        help=f"Monitoring interval in seconds (default: {DEFAULT_INTERVAL})")
    parser.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD,
                        help=f"Violation threshold in seconds (default: {DEFAULT_THRESHOLD})")
    parser.add_argument("--daemon", action="store_true",
                        help="Run in background daemon mode (no stdout warnings)")

    args = parser.parse_args()

    # Validate arguments
    if args.interval <= 0:
        logger.error("Interval must be positive")
        sys.exit(1)
    if args.threshold <= 0:
        logger.error("Threshold must be positive")
        sys.exit(1)

    # Ensure directories exist
    COMMITS_DIR.mkdir(parents=True, exist_ok=True)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    monitor = GovernanceMonitor(args.interval, args.threshold, args.daemon)
    monitor.run()

if __name__ == "__main__":
    main()

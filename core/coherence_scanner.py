#!/usr/bin/env python3
import argparse
import logging
import signal
import sys
import time
from pathlib import Path

# Ensure Willow root is on sys.path so 'from core.x import' works
sys.path.insert(0, str(Path(__file__).parent.parent))

from typing import Dict, List

from core import coherence, knowledge

USERNAME = "Sweet-Pea-Rudi19"
SCAN_TOPICS = [
    "knowledge", "memory", "conversation", "code",
    "documents", "tasks", "system", "files",
]

# Configure logging
LOG_FILE = Path(__file__).parent / "coherence_scan.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class CoherenceScannerDaemon:
    def __init__(self, interval: int = 3600, drift_threshold: float = 0.5, contradiction_threshold: float = 0.8):
        self.interval = interval
        self.drift_threshold = drift_threshold
        self.contradiction_threshold = contradiction_threshold
        self.running = False

    def scan_coherence(self) -> None:
        """Scan knowledge clusters for coherence drift."""
        try:
            scanned = 0
            for topic in SCAN_TOPICS:
                atoms = knowledge.search(USERNAME, topic, max_results=20)
                summaries = [a.get("summary") or a.get("content_snippet", "") for a in atoms]
                summaries = [s for s in summaries if s]
                if not summaries:
                    continue
                result = coherence.get_cluster_coherence(topic, summaries)
                scanned += 1
                if result["state"] == "decaying":
                    logger.warning(
                        f"Drift in '{topic}': coherence={result['coherence']:.3f} "
                        f"({result['members']} atoms, {result['pairs_measured']} pairs)"
                    )
                else:
                    logger.info(
                        f"Cluster '{topic}': {result['state']} "
                        f"coherence={result['coherence']:.3f} ({result['members']} atoms)"
                    )
            report = coherence.get_coherence_report()
            logger.info(f"System coherence report: {report}")
            if scanned == 0:
                logger.warning("No knowledge atoms found across any scan topic")
        except Exception as e:
            logger.error(f"Error during coherence scan: {str(e)}", exc_info=True)

    def run(self) -> None:
        """Run the daemon in a loop."""
        self.running = True
        logger.info(f"Starting coherence scanner with interval {self.interval} seconds")

        try:
            while self.running:
                self.scan_coherence()
                time.sleep(self.interval)
        except KeyboardInterrupt:
            logger.info("Shutting down coherence scanner")
        except Exception as e:
            logger.error(f"Unexpected error in daemon: {str(e)}", exc_info=True)
        finally:
            self.running = False

def main():
    parser = argparse.ArgumentParser(description="Coherence Scanner Daemon")
    parser.add_argument("--interval", type=int, default=3600,
                        help="Scan interval in seconds (default: 3600)")
    parser.add_argument("--threshold", type=float, default=0.5,
                        help="Drift threshold (default: 0.5)")
    parser.add_argument("--daemon", action="store_true",
                        help="Run as a daemon")
    args = parser.parse_args()

    scanner = CoherenceScannerDaemon(
        interval=args.interval,
        drift_threshold=args.threshold,
        contradiction_threshold=0.8  # Hardcoded contradiction threshold
    )

    if args.daemon:
        scanner.run()
    else:
        scanner.scan_coherence()

if __name__ == "__main__":
    main()

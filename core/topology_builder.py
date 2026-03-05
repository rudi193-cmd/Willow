#!/usr/bin/env python3
"""
Topology Builder Daemon

Runs build_edges + cluster_atoms on a schedule so the Möbius strip
stays connected as new knowledge atoms arrive.

Launched by WILLOW.bat step 8:
    python core\topology_builder.py --interval 3600 --daemon
"""
import argparse
import logging
import sys
import time
from pathlib import Path

# Ensure Willow root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core import topology, knowledge

LOG_FILE = Path(__file__).parent / "topology_build.log"
DEFAULT_INTERVAL = 3600  # 1 hour
USERNAME = "Sweet-Pea-Rudi19"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - topology_builder - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()]
)
log = logging.getLogger("topology_builder")


def run_cycle():
    """One build cycle: edges then clusters."""
    try:
        edges = topology.build_edges(USERNAME, batch_size=200)
        log.info(f"Edges built: {edges}")
    except Exception as e:
        log.error(f"build_edges failed: {e}")
        edges = 0

    try:
        clusters = topology.cluster_atoms(USERNAME, n_clusters=15)
        log.info(f"Clusters created: {len(clusters)}")
    except Exception as e:
        log.error(f"cluster_atoms failed: {e}")

    # Update cube spatial index after topology changes
    try:
        import subprocess, sys as _sys
        result = subprocess.run(
            [_sys.executable, str(Path(__file__).parent.parent / "tools" / "cube_indexer.py")],
            capture_output=True, text=True, timeout=120
        )
        log.info(f"cube_indexer: {result.stdout.strip()}")
        if result.returncode != 0:
            log.warning(f"cube_indexer stderr: {result.stderr.strip()}")
    except Exception as e:
        log.error(f"cube_indexer failed: {e}")


def main():
    parser = argparse.ArgumentParser(description="Topology Builder Daemon")
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL)
    parser.add_argument("--daemon", action="store_true")
    args = parser.parse_args()

    knowledge.init_db(USERNAME)

    if args.daemon:
        log.info(f"Starting topology builder daemon (interval: {args.interval}s)")
        while True:
            run_cycle()
            time.sleep(args.interval)
    else:
        run_cycle()


if __name__ == "__main__":
    main()

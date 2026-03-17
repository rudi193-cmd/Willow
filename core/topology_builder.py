#!/usr/bin/env python3
"""
Topology Builder Daemon

Builds edges + clusters on a schedule so the knowledge graph stays connected.
Edges and clusters are structural — they reshape how knowledge relates.

Governance: edges/clusters are proposed (logged), not silently applied.
All writes logged to topology_build.log for audit.

Launched by WILLOW.bat step 8:
    python core/topology_builder.py --interval 3600 --daemon

ΔΣ=42
"""
import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core import topology, knowledge, loam

LOG_FILE = Path(__file__).parent / "topology_build.log"
DEFAULT_INTERVAL = 3600  # 1 hour
USERNAME = "Sweet-Pea-Rudi19"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - topology_builder - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()]
)
log = logging.getLogger("topology_builder")


def _flush_pool():
    """Return all idle connections and clear dirty transaction state."""
    try:
        from core.db import _get_pg_pool
        pool = _get_pg_pool()
        conn = pool.getconn()
        try:
            conn.rollback()
        finally:
            pool.putconn(conn)
    except Exception:
        pass


def run_cycle():
    """One build cycle: edges then clusters. All changes logged."""
    try:
        edges = topology.build_edges(USERNAME, batch_size=200)
        log.info(f"Edges built: {edges}")
    except Exception as e:
        log.error(f"build_edges failed: {e}")
        edges = 0

    _flush_pool()

    try:
        clusters = topology.cluster_atoms(USERNAME, n_clusters=15)
        log.info(f"Clusters created: {len(clusters)}")
    except Exception as e:
        log.error(f"cluster_atoms failed: {e}")

    _flush_pool()

    # Entity promotion: layer 1→2 for entities that meet evidence thresholds
    # Observational — pattern detection, not executive decision.
    try:
        result = loam.promote_entities(USERNAME, dry_run=False)
        if result["promoted"]:
            log.info(f"Promoted {len(result['promoted'])} entities to layer 2 "
                     f"(skipped {result['skipped']} chrome/blocked)")
    except Exception as e:
        log.error(f"promote_entities failed: {e}")

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

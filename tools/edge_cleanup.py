#!/usr/bin/env python3
"""
Edge Cleanup — Archive chrome/axiom edges

Moves edges connected to never_promote=1 entities (chrome/garbage)
and axiom entities (Sean, Willow) to an archive table. Reversible.

Does NOT delete edges permanently — archives them to knowledge_edges_archive.

Crown witnesses the archival with batch summary.

Usage:
  python tools/edge_cleanup.py --dry-run        # count what would be archived
  python tools/edge_cleanup.py --dry-run --axioms   # include axiom entities
  python tools/edge_cleanup.py                  # archive chrome edges (human approved)
  python tools/edge_cleanup.py --axioms         # archive chrome + axiom edges

ΔΣ=42
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# Use raw psycopg2 — db.py wrapper fights bulk Postgres operations
import os
import psycopg2
import psycopg2.extras

AXIOM_ENTITY_NAMES = {"Sean", "Sean Campbell", "Willow"}


def _pg_connect():
    """Direct psycopg2 connection with correct schema (user-scoped)."""
    dsn = os.environ.get("WILLOW_DB_URL", "")
    if not dsn:
        raise RuntimeError("WILLOW_DB_URL not set")
    # db.py uses user-scoped schema: sweet_pea_rudi19 (from WILLOW_USERNAME)
    username = os.environ.get("WILLOW_USERNAME", "Sweet-Pea-Rudi19")
    schema = username.lower().replace("-", "_")
    conn = psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)
    cur = conn.cursor()
    cur.execute(f"SET search_path TO {schema}, public")
    conn.commit()
    return conn


def _ensure_archive_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS knowledge_edges_archive (
            id BIGINT,
            source_id INTEGER,
            target_id INTEGER,
            edge_type TEXT NOT NULL,
            weight REAL DEFAULT 1.0,
            canonical INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            archived_at TEXT NOT NULL,
            archive_reason TEXT
        )
    """)


def archive_chrome_edges(dry_run=True, include_axioms=False):
    conn = _pg_connect()
    conn.autocommit = False
    cur = conn.cursor()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    try:
        _ensure_archive_table(cur)
        conn.commit()

        # Get chrome entity IDs
        cur.execute("SELECT id FROM entities WHERE never_promote = 1")
        chrome_ids = [r["id"] for r in cur.fetchall()]

        axiom_ids = []
        if include_axioms:
            cur.execute("SELECT id FROM entities WHERE name = ANY(%s)", (list(AXIOM_ENTITY_NAMES),))
            axiom_ids = [r["id"] for r in cur.fetchall()]

        target_ids = list(set(chrome_ids + axiom_ids))
        if not target_ids:
            print("No target entities found.")
            return {"archived": 0}

        print(f"Target entities: {len(chrome_ids)} chrome + {len(axiom_ids)} axiom = {len(target_ids)}")

        # Find linked knowledge atom IDs
        cur.execute(
            "SELECT DISTINCT knowledge_id FROM knowledge_entities WHERE entity_id = ANY(%s)",
            (target_ids,)
        )
        atom_ids = [r["knowledge_id"] for r in cur.fetchall()]
        print(f"Knowledge atoms linked: {len(atom_ids)}")

        if not atom_ids:
            print("No linked atoms.")
            return {"archived": 0}

        # Count
        cur.execute(
            "SELECT COUNT(*) as cnt FROM knowledge_edges WHERE source_id = ANY(%s) OR target_id = ANY(%s)",
            (atom_ids, atom_ids)
        )
        edge_count = cur.fetchone()["cnt"]
        print(f"Edges to archive: {edge_count:,}")

        if dry_run:
            cur.execute(
                """SELECT edge_type, COUNT(*) as cnt FROM knowledge_edges
                   WHERE source_id = ANY(%s) OR target_id = ANY(%s)
                   GROUP BY edge_type ORDER BY COUNT(*) DESC""",
                (atom_ids, atom_ids)
            )
            print("\nBy edge type:")
            for r in cur.fetchall():
                print(f"  {r['edge_type']}: {r['cnt']:,}")

            cur.execute("SELECT COUNT(*) as cnt FROM knowledge_edges")
            total = cur.fetchone()["cnt"]
            print(f"\nTotal edges: {total:,}")
            print(f"After archival: {total - edge_count:,}")
            print("\n[DRY RUN] No changes made.")
            return {"would_archive": edge_count, "total": total, "dry_run": True}

        # Archive in batches
        BATCH = 50_000
        archived_total = 0
        reason = "chrome_entity" if not include_axioms else "chrome_and_axiom_entity"

        while True:
            cur.execute(
                """SELECT id FROM knowledge_edges
                   WHERE source_id = ANY(%s) OR target_id = ANY(%s)
                   LIMIT %s""",
                (atom_ids, atom_ids, BATCH)
            )
            batch = [r["id"] for r in cur.fetchall()]
            if not batch:
                break

            # Archive batch
            cur.execute(
                """INSERT INTO knowledge_edges_archive
                   (id, source_id, target_id, edge_type, weight, created_at, archived_at, archive_reason)
                   SELECT id, source_id, target_id, edge_type, weight,
                          created_at, %s, %s
                   FROM knowledge_edges WHERE id = ANY(%s)""",
                (now, reason, batch)
            )

            # Delete
            cur.execute("DELETE FROM knowledge_edges WHERE id = ANY(%s)", (batch,))
            conn.commit()

            archived_total += len(batch)
            print(f"  Archived batch: {len(batch):,} (total: {archived_total:,})")

        # Crown witness
        try:
            from core.crown import witness_entity_event
            witness_entity_event(
                "edge_archived", f"batch_{len(target_ids)}_entities",
                agent="edge_cleanup", username="Sweet-Pea-Rudi19",
                details={
                    "archived_count": archived_total,
                    "chrome_entities": len(chrome_ids),
                    "axiom_entities": len(axiom_ids),
                    "archived_at": now,
                },
            )
        except Exception:
            pass

        cur.execute("SELECT COUNT(*) as cnt FROM knowledge_edges")
        remaining = cur.fetchone()["cnt"]
        print(f"\nArchived: {archived_total:,}")
        print(f"Remaining edges: {remaining:,}")
        return {"archived": archived_total, "remaining": remaining}

    except Exception as e:
        conn.rollback()
        print(f"Error: {e}")
        raise
    finally:
        cur.close()
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Archive chrome/axiom entity edges")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--axioms", action="store_true")
    args = parser.parse_args()
    archive_chrome_edges(dry_run=args.dry_run, include_axioms=args.axioms)


if __name__ == "__main__":
    main()

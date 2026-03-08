"""
Cube Indexer — maps knowledge atoms and entities to 23³ lattice coordinates.
Writes to cube_cells table (derived index — safe to drop and rebuild anytime).

See CUBE_INDEX_SPEC.md for axis definitions and mapping rules.

Usage:
    python tools/cube_indexer.py              # incremental (new nodes only)
    python tools/cube_indexer.py --rebuild    # drop and rebuild all
    python tools/cube_indexer.py --dry-run    # print coords, don't write
    python tools/cube_indexer.py --stats      # show distribution across axes
"""

import argparse
import math
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

WILLOW_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WILLOW_ROOT))
sys.path.insert(0, str(WILLOW_ROOT / "core"))

from user_lattice import DOMAINS, TEMPORAL_STATES

# ── Coordinate mapping tables ─────────────────────────────────────────────────

CATEGORY_TO_CX = {
    "personal_document": DOMAINS.index("identity"),
    "personal":          DOMAINS.index("relationships"),
    "conversation":      DOMAINS.index("emotional_state"),
    "architecture":      DOMAINS.index("work"),
    "narrative":         DOMAINS.index("history"),
    "reference":         DOMAINS.index("meta"),
    "media":             DOMAINS.index("media"),
    "code":              DOMAINS.index("work"),
    "legal":             DOMAINS.index("finance"),
    "handoff":           DOMAINS.index("meta"),
    "archive":           DOMAINS.index("history"),
}

CATEGORY_DEPTH_TIERS = {
    "personal_document": 21, "personal": 20, "legal": 19,
    "conversation": 17, "narrative": 16, "architecture": 15, "handoff": 14,
    "reference": 11, "media": 10, "code": 9, "education": 8,
    "archive": 4, "merged": 3,
}

ENTITY_TYPE_TO_CX = {
    "person":   DOMAINS.index("relationships"),
    "project":  DOMAINS.index("work"),
    "tool":     DOMAINS.index("work"),
    "concept":  DOMAINS.index("meta"),
    "location": DOMAINS.index("location"),
    "event":    DOMAINS.index("schedule"),
    "belief":   DOMAINS.index("beliefs"),
}

PROMO_TO_CZ = {
    "promoted":  TEMPORAL_STATES.index("established"),
    "candidate": TEMPORAL_STATES.index("inferred"),
    "untracked": TEMPORAL_STATES.index("pending"),
    "flagged":   TEMPORAL_STATES.index("flagged"),
    "ignored":   TEMPORAL_STATES.index("dormant"),
}

_CZ_META = TEMPORAL_STATES.index("meta")
_CX_META = DOMAINS.index("meta")
_CZ_ARCHIVED = TEMPORAL_STATES.index("archived")
_CZ_THIS_WEEK = TEMPORAL_STATES.index("this_week")


# ── Helper functions ──────────────────────────────────────────────────────────

def _days_ago(ts_str: str) -> float:
    """Return float days since an ISO timestamp string, or 9999 if unparseable."""
    if not ts_str:
        return 9999.0
    try:
        for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z",
                    "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(ts_str[:26], fmt[:len(ts_str[:26])])
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return (datetime.now(timezone.utc) - dt).total_seconds() / 86400
            except ValueError:
                continue
    except Exception:
        pass
    return 9999.0


def _age_to_cz(created_at: str, category: str) -> int:
    if category == "archive":
        return _CZ_ARCHIVED
    days = _days_ago(created_at)
    if days < 1:
        return TEMPORAL_STATES.index("today")
    if days < 7:
        return TEMPORAL_STATES.index("this_week")
    if days < 30:
        return TEMPORAL_STATES.index("this_month")
    if days < 180:
        return TEMPORAL_STATES.index("recent")
    return TEMPORAL_STATES.index("established")


# ── Coordinate functions ──────────────────────────────────────────────────────

def coords_for_knowledge(row) -> tuple:
    """Return (cx, cy, cz) for a knowledge row."""
    d = dict(row) if not isinstance(row, dict) else row

    # cx
    ld = d.get("lattice_domain") or ""
    if ld and ld in DOMAINS:
        cx = DOMAINS.index(ld)
    else:
        cx = CATEGORY_TO_CX.get(d.get("category") or "", _CX_META)

    # cy
    base = CATEGORY_DEPTH_TIERS.get(d.get("category") or "", 7)
    cy = min(23, base + (2 if d.get("embedding") else 0))

    # cz
    ls = d.get("lattice_status") or ""
    if ls and ls in TEMPORAL_STATES:
        cz = TEMPORAL_STATES.index(ls)
    else:
        cz = _age_to_cz(d.get("created_at") or "", d.get("category") or "")

    return cx, max(1, cy), cz


def coords_for_entity(row) -> tuple:
    """Return (cx, cy, cz) for an entity row."""
    d = dict(row) if not isinstance(row, dict) else row

    # cx
    dom = d.get("domain") or ""
    if dom and dom in DOMAINS:
        cx = DOMAINS.index(dom)
    else:
        cx = ENTITY_TYPE_TO_CX.get(d.get("entity_type") or "", _CX_META)

    # cy
    mc = max(1, d.get("mention_count") or 1)
    cy = min(23, max(1, int(math.log2(mc + 1) * 4)))
    if d.get("verified") or d.get("promotion_status") == "promoted":
        cy = min(23, cy + 3)

    # cz
    promo = d.get("promotion_status") or ""
    cz = PROMO_TO_CZ.get(promo, TEMPORAL_STATES.index("pending"))
    if _days_ago(d.get("last_mentioned") or "") <= 7:
        cz = _CZ_THIS_WEEK

    return cx, cy, cz


# ── DB connection ─────────────────────────────────────────────────────────────

_DEFAULT_DB = WILLOW_ROOT / "artifacts" / "Sweet-Pea-Rudi19" / "willow_knowledge.db"


def connect(db_path=None):
    """Open DB connection. Uses PostgreSQL pool when configured, else SQLite."""
    try:
        from core.db import get_connection as _gc, is_postgres
        if is_postgres():
            conn = _gc()
            conn.row_factory = sqlite3.Row  # triggers RealDictCursor on Postgres
            return conn
    except Exception:
        pass
    path = str(db_path or _DEFAULT_DB)
    conn = sqlite3.connect(path, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_table(conn):
    try:
        from core.db import is_postgres
        if is_postgres():
            return  # cube_cells schema managed by pg_schema.sql
    except Exception:
        pass
    conn.execute("""CREATE TABLE IF NOT EXISTS cube_cells (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        node_id       INTEGER NOT NULL,
        node_type     TEXT NOT NULL CHECK (node_type IN ('knowledge', 'entity')),
        cx            INTEGER NOT NULL CHECK (cx BETWEEN 0 AND 22),
        cy            INTEGER NOT NULL CHECK (cy BETWEEN 1 AND 23),
        cz            INTEGER NOT NULL CHECK (cz BETWEEN 0 AND 22),
        domain_name   TEXT NOT NULL,
        temporal_name TEXT NOT NULL,
        indexed_at    TEXT NOT NULL,
        UNIQUE (node_id, node_type)
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cube_xyz  ON cube_cells(cx, cy, cz)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cube_type ON cube_cells(node_type)")
    conn.commit()


# ── Indexing functions ────────────────────────────────────────────────────────

def index_knowledge(conn, rebuild=False, dry_run=False) -> int:
    _ensure_table(conn)
    now = datetime.now(timezone.utc).isoformat()

    if rebuild and not dry_run:
        conn.execute("DELETE FROM cube_cells WHERE node_type='knowledge'")
        conn.commit()

    if rebuild:
        rows = conn.execute(
            "SELECT id, category, lattice_domain, lattice_status, created_at, embedding "
            "FROM knowledge"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, category, lattice_domain, lattice_status, created_at, embedding "
            "FROM knowledge WHERE id NOT IN "
            "(SELECT node_id FROM cube_cells WHERE node_type='knowledge')"
        ).fetchall()

    count = 0
    for row in rows:
        cx, cy, cz = coords_for_knowledge(row)
        if dry_run:
            print(f"  knowledge:{row['id']:5d}  ({cx:2d},{cy:2d},{cz:2d})  "
                  f"{DOMAINS[cx]:20s}  {TEMPORAL_STATES[cz]}")
        else:
            conn.execute(
                "INSERT OR REPLACE INTO cube_cells "
                "(node_id, node_type, cx, cy, cz, domain_name, temporal_name, indexed_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (row["id"], "knowledge", cx, cy, cz,
                 DOMAINS[cx], TEMPORAL_STATES[cz], now)
            )
        count += 1

    if not dry_run:
        conn.commit()
    return count


def index_entities(conn, rebuild=False, dry_run=False) -> int:
    _ensure_table(conn)
    now = datetime.now(timezone.utc).isoformat()

    if rebuild and not dry_run:
        conn.execute("DELETE FROM cube_cells WHERE node_type='entity'")
        conn.commit()

    if rebuild:
        rows = conn.execute(
            "SELECT id, name, entity_type, mention_count, domain, promotion_status, "
            "verified, last_mentioned FROM entities"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, name, entity_type, mention_count, domain, promotion_status, "
            "verified, last_mentioned FROM entities WHERE id NOT IN "
            "(SELECT node_id FROM cube_cells WHERE node_type='entity')"
        ).fetchall()

    count = 0
    for row in rows:
        cx, cy, cz = coords_for_entity(row)
        if dry_run:
            print(f"  entity:{row['id']:5d}  ({cx:2d},{cy:2d},{cz:2d})  "
                  f"{DOMAINS[cx]:20s}  {row['name'][:30]}")
        else:
            conn.execute(
                "INSERT OR REPLACE INTO cube_cells "
                "(node_id, node_type, cx, cy, cz, domain_name, temporal_name, indexed_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (row["id"], "entity", cx, cy, cz,
                 DOMAINS[cx], TEMPORAL_STATES[cz], now)
            )
        count += 1

    if not dry_run:
        conn.commit()
    return count


def print_stats(conn):
    _ensure_table(conn)
    print("=== CUBE INDEX STATS ===")
    total = conn.execute("SELECT COUNT(*) FROM cube_cells").fetchone()[0]
    print(f"Total indexed: {total:,}")
    print()
    print("By node_type:")
    for r in conn.execute("SELECT node_type, COUNT(*) FROM cube_cells GROUP BY node_type"):
        print(f"  {r[0]:12s}: {r[1]:,}")
    print()
    print("Top 10 domains (cx):")
    for r in conn.execute(
        "SELECT domain_name, COUNT(*) as n FROM cube_cells GROUP BY domain_name "
        "ORDER BY n DESC LIMIT 10"
    ):
        bar = "#" * (r[1] // max(1, total // 50))
        print(f"  {r[0]:20s} {r[1]:5d}  {bar}")
    print()
    print("Temporal distribution (cz):")
    for r in conn.execute(
        "SELECT temporal_name, COUNT(*) as n FROM cube_cells GROUP BY temporal_name "
        "ORDER BY n DESC LIMIT 10"
    ):
        print(f"  {r[0]:20s} {r[1]:5d}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Willow 23³ Cube Indexer")
    parser.add_argument("--rebuild",  action="store_true", help="Drop and rebuild all cube_cells")
    parser.add_argument("--dry-run",  action="store_true", help="Print coords, don't write")
    parser.add_argument("--stats",    action="store_true", help="Show distribution stats")
    parser.add_argument("--db",       default=None,        help="Path to knowledge DB (default: artifacts/Sweet-Pea-Rudi19/willow_knowledge.db)")
    args = parser.parse_args()

    conn = connect(args.db)

    if args.stats:
        print_stats(conn)
        conn.close()
        return

    if args.dry_run:
        print("=== DRY RUN — first 20 knowledge atoms ===")
        rows = conn.execute(
            "SELECT id, category, lattice_domain, lattice_status, created_at, embedding "
            "FROM knowledge LIMIT 20"
        ).fetchall()
        for row in rows:
            cx, cy, cz = coords_for_knowledge(row)
            print(f"  knowledge:{row['id']:5d}  ({cx:2d},{cy:2d},{cz:2d})  "
                  f"{DOMAINS[cx]:20s}  {TEMPORAL_STATES[cz]}")
        print()
        print("=== first 20 entities ===")
        rows = conn.execute(
            "SELECT id, name, entity_type, mention_count, domain, promotion_status, "
            "verified, last_mentioned FROM entities LIMIT 20"
        ).fetchall()
        for row in rows:
            cx, cy, cz = coords_for_entity(row)
            print(f"  entity:{row['id']:5d}  ({cx:2d},{cy:2d},{cz:2d})  "
                  f"{DOMAINS[cx]:20s}  {row['name'][:30]}")
        conn.close()
        return

    mode = "rebuild" if args.rebuild else "incremental"
    print(f"=== CUBE INDEXER ({mode}) ===")

    k = index_knowledge(conn, rebuild=args.rebuild)
    e = index_entities(conn, rebuild=args.rebuild)

    total = conn.execute("SELECT COUNT(*) FROM cube_cells").fetchone()[0]
    print(f"Indexed: {k} knowledge atoms + {e} entities")
    print(f"Total cube_cells: {total:,}")
    conn.close()


if __name__ == "__main__":
    main()

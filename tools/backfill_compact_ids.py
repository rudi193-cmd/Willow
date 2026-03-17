"""
backfill_compact_ids.py — Assign BASE 17 IDs to all existing atoms

Every atom, every entity, every document, every tracked process gets a
5-char BASE 17 ID. This is the backfill for everything ingested before
the compact system was built.

Usage:
    python tools/backfill_compact_ids.py --dry-run     # Show what would change
    python tools/backfill_compact_ids.py               # Apply changes
    python tools/backfill_compact_ids.py --schema-only # Just add missing columns

Authority: Sean Campbell
System: Willow
ΔΣ=42
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'core'))

from compact import _gen_id

# Tables that need compact_id, with their primary key column
TABLES = [
    # (table, pk_column, description)
    ("knowledge", "id", "knowledge atoms"),
    ("entities", "id", "entities"),
    ("agents", "name", "agents"),
    ("nest_review_queue", "id", "review queue items"),
    ("pigeon_droppings", "id", "pigeon droppings"),
    ("knowledge_gaps", "id", "knowledge gaps"),
    ("shiva_corrections", "id", "shiva corrections"),
    ("tasks", "id", "tasks"),
    ("cost_usage", "id", "cost usage records"),
    ("health_checks", "id", "health checks"),
    ("knowledge_clusters", "cluster_id", "knowledge clusters"),
    ("conversation_memory", "id", "conversation memory"),
    ("witness_log", "witness_id", "crown witness records"),
]


def get_conn():
    """Raw psycopg2 with autocommit off."""
    import psycopg2
    conn = psycopg2.connect(os.environ["WILLOW_DB_URL"])
    conn.autocommit = False
    username = os.getenv("WILLOW_USERNAME", "Sweet-Pea-Rudi19")
    import re
    safe = re.sub(r"[^a-z0-9]", "_", username.lower())[:63]
    cur = conn.cursor()
    cur.execute(f"SET search_path = {safe}, public")
    cur.close()
    return conn


def add_column_if_missing(conn, table: str, dry_run: bool) -> bool:
    """Add compact_id column if it doesn't exist. Returns True if added."""
    cur = conn.cursor()
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = %s AND column_name = 'compact_id'
    """, (table,))
    if cur.fetchone():
        return False

    if dry_run:
        print(f"  [DRY RUN] Would add compact_id column to {table}")
        return True

    cur.execute(f"ALTER TABLE {table} ADD COLUMN compact_id TEXT")
    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_compact_id ON {table}(compact_id)")
    print(f"  Added compact_id column + index to {table}")
    return True


def backfill_table(conn, table: str, pk_col: str, desc: str,
                   dry_run: bool, batch_size: int = 1000) -> dict:
    """Backfill compact_ids for one table. Returns stats dict."""
    cur = conn.cursor()

    # Ensure column exists before querying it
    try:
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = %s AND column_name = 'compact_id'
        """, (table,))
        if not cur.fetchone():
            if dry_run:
                # Can't count without the column
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                total = cur.fetchone()[0]
                return {"table": table, "total": total, "need": total, "backfilled": 0, "dry_run": True}
            else:
                return {"table": table, "error": "compact_id column missing (run --schema-only first)", "backfilled": 0}
    except Exception:
        return {"table": table, "error": "table not found", "backfilled": 0}

    # Count rows needing backfill
    try:
        cur.execute(f"SELECT COUNT(*) FROM {table} WHERE compact_id IS NULL OR compact_id = ''")
        need_backfill = cur.fetchone()[0]
    except Exception:
        return {"table": table, "error": "table query failed", "backfilled": 0}

    cur.execute(f"SELECT COUNT(*) FROM {table}")
    total = cur.fetchone()[0]

    if need_backfill == 0:
        return {"table": table, "total": total, "backfilled": 0, "already_done": True}

    if dry_run:
        print(f"  [DRY RUN] {table}: {need_backfill:,}/{total:,} {desc} need compact_id")
        return {"table": table, "total": total, "need": need_backfill, "backfilled": 0, "dry_run": True}

    # Batch backfill
    backfilled = 0
    while True:
        cur.execute(f"""
            SELECT {pk_col} FROM {table}
            WHERE compact_id IS NULL OR compact_id = ''
            LIMIT %s
        """, (batch_size,))
        rows = cur.fetchall()
        if not rows:
            break

        for (pk,) in rows:
            cid = _gen_id()
            cur.execute(f"UPDATE {table} SET compact_id = %s WHERE {pk_col} = %s", (cid, pk))
            backfilled += 1

        conn.commit()
        sys.stdout.write(f"\r  {table}: {backfilled:,}/{need_backfill:,} backfilled")
        sys.stdout.flush()

    if backfilled > 0:
        print()
    return {"table": table, "total": total, "backfilled": backfilled}


def main():
    parser = argparse.ArgumentParser(description="Backfill BASE 17 compact IDs")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change")
    parser.add_argument("--schema-only", action="store_true", help="Just add missing columns")
    parser.add_argument("--table", type=str, help="Only process this table")
    args = parser.parse_args()

    conn = get_conn()
    t0 = time.time()

    print(f"\n{'='*60}")
    print(f"BASE 17 COMPACT ID BACKFILL")
    print(f"{'='*60}")
    if args.dry_run:
        print("[DRY RUN MODE — no changes will be made]\n")

    tables = TABLES
    if args.table:
        tables = [(t, pk, d) for t, pk, d in TABLES if t == args.table]
        if not tables:
            print(f"Table '{args.table}' not in backfill list")
            sys.exit(1)

    # Phase 1: Add missing columns
    print("Phase 1: Schema check")
    columns_added = 0
    for table, pk, desc in tables:
        try:
            added = add_column_if_missing(conn, table, args.dry_run)
            if added:
                columns_added += 1
        except Exception as e:
            print(f"  {table}: column check failed — {e}")

    if not args.dry_run and columns_added > 0:
        conn.commit()
    print(f"  {columns_added} column(s) {'would be ' if args.dry_run else ''}added\n")

    if args.schema_only:
        conn.close()
        print("Schema-only mode — done.")
        return

    # Phase 2: Backfill IDs
    print("Phase 2: Backfill compact_ids")
    results = []
    total_backfilled = 0
    for table, pk, desc in tables:
        try:
            result = backfill_table(conn, table, pk, desc, args.dry_run)
            results.append(result)
            total_backfilled += result.get("backfilled", 0)
        except Exception as e:
            print(f"  {table}: backfill failed — {e}")
            conn.rollback()
            results.append({"table": table, "error": str(e), "backfilled": 0})

    # Summary
    elapsed = time.time() - t0
    print(f"\n{'='*60}")
    print(f"BACKFILL SUMMARY ({elapsed:.1f}s)")
    print(f"{'='*60}")
    for r in results:
        table = r["table"]
        if r.get("error"):
            print(f"  {table:30s} ERROR: {r['error']}")
        elif r.get("already_done"):
            print(f"  {table:30s} {r['total']:>10,} rows — all have compact_id ✓")
        elif r.get("dry_run"):
            print(f"  {table:30s} {r['need']:>10,}/{r['total']:,} need backfill")
        else:
            print(f"  {table:30s} {r['backfilled']:>10,} backfilled")

    print(f"\nTotal backfilled: {total_backfilled:,}")
    conn.close()


if __name__ == "__main__":
    main()

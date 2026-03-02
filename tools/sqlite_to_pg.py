"""
sqlite_to_pg.py — Migrate Willow SQLite → PostgreSQL (PG 17, port 5437)

Preserves all IDs. Batches large tables. Resets sequences after load.
Run with server STOPPED: python tools/sqlite_to_pg.py
"""
import sqlite3
import psycopg2
import psycopg2.extras
import sys
from pathlib import Path

SQLITE_DB = r"C:\Users\Sean\Documents\GitHub\Willow\artifacts\Sweet-Pea-Rudi19\willow_knowledge.db"
PG_DSN    = "host=localhost port=5437 dbname=willow user=postgres password=willow"
BATCH     = 5000

# Tables in dependency order (parents before children)
TABLES = [
    "agents",
    "agent_mailbox",
    "willow_state",
    "schema_versions",
    "anonymous_mentions",
    "knowledge",
    "entities",
    "knowledge_entities",
    "entity_connections",
    "knowledge_clusters",
    "cluster_members",
    "knowledge_edges",
    "knowledge_gaps",
    "conversation_memory",
    "pigeon_droppings",
    "pigeon_errors",
]


def migrate_table(sq_cur, pg_cur, table: str) -> int:
    sq_cur.execute(f'SELECT * FROM "{table}"')
    cols = [d[0] for d in sq_cur.description]
    col_list = ", ".join(f'"{c}"' for c in cols)
    placeholders = ", ".join(["%s"] * len(cols))

    total = 0
    batch = sq_cur.fetchmany(BATCH)
    while batch:
        # Sanitize: strip NUL bytes from strings, convert bytes for BYTEA
        def clean(v):
            if isinstance(v, str):
                return v.replace('\x00', '')
            if isinstance(v, (bytes, bytearray)):
                return bytes(v)
            return v
        rows = [tuple(clean(v) for v in row) for row in batch]
        psycopg2.extras.execute_batch(
            pg_cur,
            f'INSERT INTO "{table}" ({col_list}) VALUES ({placeholders}) ON CONFLICT DO NOTHING',
            rows,
            page_size=BATCH,
        )
        total += len(rows)
        sys.stdout.write(f"\r  {table}: {total} rows")
        sys.stdout.flush()
        batch = sq_cur.fetchmany(BATCH)
    print()
    return total


def reset_sequences(pg_conn):
    """Reset all BIGSERIAL sequences to max(id)+1 so new inserts don't conflict."""
    cur = pg_conn.cursor()
    seq_tables = [
        "agent_mailbox", "schema_versions", "anonymous_mentions",
        "knowledge", "entities", "entity_connections",
        "knowledge_clusters", "knowledge_edges", "knowledge_gaps",
        "conversation_memory", "pigeon_droppings", "pigeon_errors",
    ]
    for t in seq_tables:
        cur.execute(f"""
            SELECT setval(pg_get_serial_sequence('"{t}"', 'id'),
                   COALESCE((SELECT MAX(id) FROM "{t}"), 1))
        """)
    pg_conn.commit()
    print("Sequences reset.")


def main():
    print(f"=== SQLite → PostgreSQL Migration ===")
    print(f"Source: {SQLITE_DB}")
    print(f"Target: {PG_DSN}")
    print()

    sq_conn = sqlite3.connect(SQLITE_DB)
    sq_conn.row_factory = None
    sq_cur  = sq_conn.cursor()

    pg_conn = psycopg2.connect(PG_DSN)
    pg_conn.autocommit = False
    pg_cur  = pg_conn.cursor()

    # Disable triggers during load (skip tsvector recalc — we'll update after)
    pg_cur.execute("SET session_replication_role = replica")

    total = 0
    for table in TABLES:
        try:
            n = migrate_table(sq_cur, pg_cur, table)
            total += n
        except Exception as e:
            pg_conn.rollback()
            print(f"\nERROR on {table}: {e}")
            sq_conn.close()
            pg_conn.close()
            sys.exit(1)

    pg_conn.commit()
    print(f"\n{total} total rows migrated.")

    # Re-enable triggers
    pg_cur.execute("SET session_replication_role = DEFAULT")
    pg_conn.commit()

    # Backfill search_vector for all knowledge rows
    print("Backfilling search_vector on knowledge table...")
    pg_cur.execute("""
        UPDATE knowledge SET search_vector =
            setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
            setweight(to_tsvector('english', coalesce(summary, '')), 'B') ||
            setweight(to_tsvector('english', coalesce(content_snippet, '')), 'C') ||
            setweight(to_tsvector('english', coalesce(category, '')), 'D')
    """)
    pg_conn.commit()
    print("search_vector backfilled.")

    reset_sequences(pg_conn)

    sq_conn.close()
    pg_conn.close()
    print("\nMigration complete. Set WILLOW_DB_URL=postgresql://willow:willow@localhost:5437/willow")


if __name__ == "__main__":
    main()

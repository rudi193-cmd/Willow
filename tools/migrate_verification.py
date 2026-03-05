#!/usr/bin/env python3
#
# Willow/tools/migrate_verification.py
#
# Adds verification columns to the PostgreSQL knowledge graph tables.
# This script is idempotent and can be run multiple times safely.

import sys
import psycopg2

# --- Configuration ---
PG_DSN = "postgresql://willow:willow@localhost:5437/willow"
SCHEMA = "sweet_pea_rudi19"

ENTITIES_COLUMNS = [
    ("verified",    "BOOLEAN DEFAULT FALSE"),
    ("confidence",  "TEXT DEFAULT 'low'"),
    ("source_type", "TEXT DEFAULT 'oral_history_consented'"),
    ("sources",     "TEXT DEFAULT '[]'"),
    ("corrections", "TEXT DEFAULT '[]'"),
    ("verified_at", "TEXT"),
    ("verified_by", "TEXT DEFAULT 'jeles'"),
]

CONNECTIONS_COLUMNS = [
    ("confidence",  "TEXT DEFAULT 'low'"),
    ("source_type", "TEXT DEFAULT 'oral_history_consented'"),
]


def add_columns(cur, table, columns):
    added = 0
    for col_name, col_def in columns:
        stmt = f"ALTER TABLE {SCHEMA}.{table} ADD COLUMN IF NOT EXISTS {col_name} {col_def}"
        cur.execute(stmt)
        # rowcount is not reliable for DDL; we check information_schema instead
        cur.execute(
            """
            SELECT COUNT(*)
            FROM information_schema.columns
            WHERE table_schema = %s
              AND table_name   = %s
              AND column_name  = %s
            """,
            (SCHEMA, table, col_name),
        )
        exists = cur.fetchone()[0]
        if exists:
            added += 1  # column is present (may have just been created)
    return added


def main():
    print(f"Connecting to {PG_DSN} ...")
    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = False
    cur = conn.cursor()

    # Set search path
    cur.execute(f"SET search_path = {SCHEMA}, public")

    print(f"Adding columns to {SCHEMA}.entities ...")
    entities_count = add_columns(cur, "entities", ENTITIES_COLUMNS)

    print(f"Adding columns to {SCHEMA}.entity_connections ...")
    connections_count = add_columns(cur, "entity_connections", CONNECTIONS_COLUMNS)

    conn.commit()
    cur.close()
    conn.close()

    print()
    print("=== Migration complete ===")
    print(f"  {SCHEMA}.entities          : {entities_count}/{len(ENTITIES_COLUMNS)} columns present")
    print(f"  {SCHEMA}.entity_connections: {connections_count}/{len(CONNECTIONS_COLUMNS)} columns present")
    print("OK")


if __name__ == "__main__":
    main()

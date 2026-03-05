#!/usr/bin/env python3
"""migrate_schemas.py -- Migrate Willow PostgreSQL from single public schema to schema-per-user.

Run ONCE after updating core/db.py and pg_schema.sql.

What it does:
  1. Creates user schema (sweet_pea_rudi19) via init_user_schema()
  2. Moves user data tables from public to user schema
  3. Creates community tables in public schema
  4. Registers user in schema_registry
  5. Creates all missing tables in user schema (runs pg_schema DDL with search_path set)

Safe to run multiple times -- checks table schema before moving.

Usage:
  python tools/migrate_schemas.py
  python tools/migrate_schemas.py --username Sweet-Pea-Rudi19
  python tools/migrate_schemas.py --dry-run
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "core"))

from db import get_connection, init_user_schema, _safe_schema_name, is_postgres

# Tables that belong to the user (move from public → user schema)
USER_TABLES = [
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
]

# Tables that stay in public (system + community layer)
PUBLIC_TABLES = [
    "agents",
    "agent_mailbox",
    "willow_state",
    "schema_versions",
    "pigeon_droppings",
    "pigeon_errors",
    "schema_registry",
    "community_entities",
    "community_connections",
    "community_knowledge",
]


def table_schema(conn, table_name: str) -> str | None:
    """Return the schema where table_name currently lives, or None if missing."""
    row = conn._conn.cursor()
    row.execute(
        "SELECT table_schema FROM information_schema.tables "
        "WHERE table_name = %s AND table_catalog = current_database() "
        "ORDER BY table_schema LIMIT 1",
        (table_name,),
    )
    result = row.fetchone()
    row.close()
    return result[0] if result else None


def run_sql(conn, sql: str, dry_run: bool, label: str = ""):
    if dry_run:
        print(f"  [DRY] {label or sql.strip()[:80]}")
        return
    cur = conn._conn.cursor()
    try:
        cur.execute(sql)
        conn._conn.commit()
        if label:
            print(f"  OK: {label}")
    except Exception as e:
        conn._conn.rollback()
        print(f"  WARN: {label or sql[:60]} -- {e}", file=sys.stderr)
    finally:
        cur.close()


def migrate(username: str, dry_run: bool):
    if not is_postgres():
        print("Not PostgreSQL -- nothing to migrate.")
        return

    print(f"\nMigrating schema for: {username}")
    safe = _safe_schema_name(username)
    print(f"Target schema:        {safe}")
    print(f"Dry run:              {dry_run}")
    print()

    # 1. Create user schema
    if not dry_run:
        result = init_user_schema(username)
        print(f"OK: schema '{result}' created (or already exists)")
    else:
        print(f"  [DRY] CREATE SCHEMA IF NOT EXISTS {safe}")

    # 2. Get a raw PG connection for DDL (autocommit for schema ops)
    import psycopg2
    from db import DATABASE_URL
    conn_raw = psycopg2.connect(DATABASE_URL)
    conn_raw.autocommit = True

    # Wrap in a simple object so run_sql can access conn._conn
    class _Wrap:
        _conn = conn_raw

    conn = _Wrap()

    # 3. Move user tables from public → user schema
    print("Moving user tables:")
    for table in USER_TABLES:
        cur_schema = table_schema(conn, table)
        if cur_schema is None:
            print(f"  SKIP: {table} -- not found (will be created fresh)")
            continue
        if cur_schema == safe:
            print(f"  SKIP: {table} -- already in {safe}")
            continue
        if cur_schema != "public":
            print(f"  SKIP: {table} -- in schema '{cur_schema}', unexpected", file=sys.stderr)
            continue
        run_sql(
            conn,
            f"ALTER TABLE public.{table} SET SCHEMA {safe}",
            dry_run,
            label=f"public.{table} -> {safe}.{table}",
        )

    # 4. Create community + registry tables in public (idempotent DDL)
    print("\nCreating public community tables:")
    pg_schema_sql = Path(__file__).parent / "pg_schema.sql"
    if pg_schema_sql.exists():
        ddl = pg_schema_sql.read_text(encoding="utf-8")
        # Only run the community section (after the last USER_TABLES block)
        community_marker = "-- SCHEMA REGISTRY"
        idx = ddl.find(community_marker)
        if idx != -1:
            community_ddl = ddl[idx:]
            if not dry_run:
                cur = conn_raw.cursor()
                try:
                    cur.execute("SET search_path = public")
                    cur.execute(community_ddl)
                    print("  OK: community tables created in public schema")
                except Exception as e:
                    print(f"  WARN: community DDL -- {e}", file=sys.stderr)
                finally:
                    cur.close()
            else:
                print(f"  [DRY] execute community DDL ({len(community_ddl)} chars) in public")
        else:
            print("  WARN: community marker not found in pg_schema.sql", file=sys.stderr)
    else:
        print("  WARN: pg_schema.sql not found", file=sys.stderr)

    # 5. Register user in schema_registry
    print("\nRegistering user in schema_registry:")
    import datetime
    now = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    run_sql(
        conn,
        f"INSERT INTO public.schema_registry (username, schema_name, created_at) "
        f"VALUES ('{username}', '{safe}', '{now}') "
        f"ON CONFLICT (username) DO NOTHING",
        dry_run,
        label=f"schema_registry: {username} -> {safe}",
    )

    # 6. Create all user tables in user schema (for any that didn't exist in public)
    print("\nEnsuring user schema tables exist:")
    if not dry_run:
        pg_schema_sql = Path(__file__).parent / "pg_schema.sql"
        ddl = pg_schema_sql.read_text(encoding="utf-8")
        # Run full DDL with search_path pointed at user schema
        # (CREATE TABLE IF NOT EXISTS will skip already-existing tables)
        community_marker = "-- SCHEMA REGISTRY"
        idx = ddl.find(community_marker)
        user_ddl = ddl[:idx] if idx != -1 else ddl
        cur = conn_raw.cursor()
        try:
            cur.execute(f"SET search_path = {safe}, public")
            cur.execute(user_ddl)
            print(f"  OK: all user tables verified in {safe}")
        except Exception as e:
            print(f"  WARN: user DDL -- {e}", file=sys.stderr)
        finally:
            cur.close()
    else:
        print(f"  [DRY] run user DDL with search_path = {safe}, public")

    conn_raw.close()
    print(f"\nDone. Schema '{safe}' is ready.")
    print(f"Add to .env:  WILLOW_USERNAME={username}")
    print(f"Verify:  psql -c \"\\dn\" # should list {safe}")
    print(f"Verify:  psql -c \"SET search_path = {safe}; \\dt\" # should list all user tables")


def main():
    parser = argparse.ArgumentParser(description="Migrate Willow to schema-per-user PostgreSQL")
    parser.add_argument("--username", default="Sweet-Pea-Rudi19", help="Username to migrate")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen without doing it")
    args = parser.parse_args()
    migrate(args.username, args.dry_run)


if __name__ == "__main__":
    main()

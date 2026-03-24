"""
migrate_kart_sqlite.py -- Consolidate 5 kart_tasks.db (SQLite) into Postgres schema `kart`.

Idempotent. Deduplicates by task_id (tasks) and (task_id, timestamp, action) (task_log).
Does NOT delete source SQLite files.

Usage:
    python3 migrate_kart_sqlite.py [--dry-run]

Connection: Uses WILLOW_DB_URL env var or defaults to dbname=willow user=willow host=<resolved>.
"""

import os
import sys
import sqlite3
import argparse
from datetime import datetime
from typing import List, Tuple, Dict, Any

# ---------------------------------------------------------------------------
# Postgres connection (same pattern as genealogy_db.py)
# ---------------------------------------------------------------------------

SCHEMA = "kart"

SQLITE_SOURCES: List[Tuple[str, str]] = [
    ("/mnt/c/Users/Sean/Documents/GitHub/Willow/artifacts/Sweet-Pea-Rudi19/kart_tasks.db", "willow-artifacts"),
    ("/mnt/c/Users/Sean/Documents/GitHub/aios-minimal/agents/Sweet-Pea-Rudi19/kart_tasks.db", "aios-agents"),
    ("/mnt/c/Users/Sean/Documents/GitHub/aios-minimal/artifacts/Sweet-Pea-Rudi19/kart_tasks.db", "aios-artifacts"),
    ("/mnt/c/Users/Sean/Documents/GitHub/safe-app-nasa-archive/artifacts/Sweet-Pea-Rudi19/kart_tasks.db", "nasa-archive"),
    ("/mnt/c/Users/Sean/Documents/GitHub/safe-app-utety-chat/artifacts/Sweet-Pea-Rudi19/kart_tasks.db", "utety-chat"),
]


def _resolve_host() -> str:
    """Return localhost, falling back to WSL resolv.conf nameserver."""
    host = "localhost"
    try:
        with open("/etc/resolv.conf") as f:
            for line in f:
                if line.strip().startswith("nameserver"):
                    host = line.strip().split()[1]
                    break
    except FileNotFoundError:
        pass
    return host


def get_connection():
    """Return a Postgres connection with search_path = kart, public."""
    import psycopg2
    dsn = os.getenv("WILLOW_DB_URL", "")
    if not dsn:
        host = _resolve_host()
        dsn = f"dbname=willow user=willow host={host}"
    conn = psycopg2.connect(dsn)
    conn.autocommit = False
    cur = conn.cursor()
    cur.execute(f"SET search_path = {SCHEMA}, public")
    cur.close()
    return conn


# ---------------------------------------------------------------------------
# Schema creation (idempotent)
# ---------------------------------------------------------------------------

def init_schema(conn):
    """Create kart schema and tables. Idempotent."""
    cur = conn.cursor()

    cur.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    cur.execute(f"SET search_path = {SCHEMA}, public")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            task_id     TEXT UNIQUE NOT NULL,
            subject     TEXT NOT NULL,
            description TEXT NOT NULL,
            status      TEXT DEFAULT 'pending',
            agent       TEXT NOT NULL,
            created_at  TIMESTAMPTZ NOT NULL,
            updated_at  TIMESTAMPTZ NOT NULL,
            completed_at TIMESTAMPTZ,
            metadata    JSONB,
            source_file TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS task_log (
            id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            task_id     TEXT NOT NULL,
            timestamp   TIMESTAMPTZ NOT NULL,
            action      TEXT NOT NULL,
            agent       TEXT NOT NULL,
            details     TEXT,
            source_file TEXT NOT NULL,
            UNIQUE (task_id, timestamp, action)
        )
    """)

    # Indices
    cur.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks (status)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_tasks_agent ON tasks (agent)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks (created_at)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_task_log_task_id ON task_log (task_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_task_log_agent ON task_log (agent)")

    conn.commit()
    print(f"[OK] Schema '{SCHEMA}' and tables created/verified.")


# ---------------------------------------------------------------------------
# SQLite reading
# ---------------------------------------------------------------------------

def read_sqlite_tasks(path: str) -> List[Dict[str, Any]]:
    """Read all rows from tasks table in a SQLite file."""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT task_id, subject, description, status, agent, "
                "created_at, updated_at, completed_at, metadata FROM tasks")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def read_sqlite_logs(path: str) -> List[Dict[str, Any]]:
    """Read all rows from task_log table in a SQLite file."""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT task_id, timestamp, action, agent, details FROM task_log")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------

def _parse_metadata(raw: str) -> str:
    """Convert SQLite metadata text to valid JSON string for JSONB, or NULL."""
    if raw is None:
        return None
    import json
    # Already valid JSON? Return as-is.
    try:
        json.loads(raw)
        return raw
    except (json.JSONDecodeError, TypeError):
        # Wrap raw text as a JSON string
        return json.dumps({"raw": raw})


def migrate(dry_run: bool = False):
    """Run the full migration."""
    pg = get_connection()
    init_schema(pg)
    cur = pg.cursor()

    stats = {
        "tasks_inserted": 0,
        "tasks_skipped": 0,
        "logs_inserted": 0,
        "logs_skipped": 0,
        "sources": {},
    }

    # --- Tasks ---
    for path, label in SQLITE_SOURCES:
        if not os.path.exists(path):
            print(f"[SKIP] {label}: file not found at {path}")
            continue

        tasks = read_sqlite_tasks(path)
        source_inserted = 0
        source_skipped = 0

        for t in tasks:
            metadata_json = _parse_metadata(t["metadata"])

            if dry_run:
                print(f"  [DRY] Would insert task {t['task_id']} from {label}")
                source_inserted += 1
                continue

            cur.execute("""
                INSERT INTO tasks (task_id, subject, description, status, agent,
                                   created_at, updated_at, completed_at, metadata, source_file)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                ON CONFLICT (task_id) DO NOTHING
                RETURNING id
            """, (
                t["task_id"], t["subject"], t["description"], t["status"],
                t["agent"], t["created_at"], t["updated_at"], t["completed_at"],
                metadata_json, label,
            ))
            row = cur.fetchone()
            if row is not None:
                source_inserted += 1
            else:
                source_skipped += 1

        stats["tasks_inserted"] += source_inserted
        stats["tasks_skipped"] += source_skipped
        stats["sources"][label] = {"tasks": len(tasks), "inserted": source_inserted, "skipped": source_skipped}
        print(f"[{label}] tasks: {len(tasks)} total, {source_inserted} inserted, {source_skipped} duplicates")

    # --- Task Log ---
    for path, label in SQLITE_SOURCES:
        if not os.path.exists(path):
            continue

        logs = read_sqlite_logs(path)
        inserted = 0
        skipped = 0

        for log in logs:
            if dry_run:
                inserted += 1
                continue

            cur.execute("""
                INSERT INTO task_log (task_id, timestamp, action, agent, details, source_file)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (task_id, timestamp, action) DO NOTHING
                RETURNING id
            """, (
                log["task_id"], log["timestamp"], log["action"],
                log["agent"], log["details"], label,
            ))
            row = cur.fetchone()
            if row is not None:
                inserted += 1
            else:
                skipped += 1

        stats["logs_inserted"] += inserted
        stats["logs_skipped"] += skipped
        if label in stats["sources"]:
            stats["sources"][label]["logs"] = len(logs)
            stats["sources"][label]["logs_inserted"] = inserted
            stats["sources"][label]["logs_skipped"] = skipped
        print(f"[{label}] logs: {len(logs)} total, {inserted} inserted, {skipped} duplicates")

    if not dry_run:
        pg.commit()
    else:
        pg.rollback()
        print("\n[DRY RUN] No changes committed.")

    pg.close()

    # --- Summary ---
    print("\n" + "=" * 60)
    print("MIGRATION SUMMARY")
    print("=" * 60)
    print(f"Tasks:  {stats['tasks_inserted']} inserted, {stats['tasks_skipped']} duplicates skipped")
    print(f"Logs:   {stats['logs_inserted']} inserted, {stats['logs_skipped']} duplicates skipped")
    print(f"Total:  {stats['tasks_inserted'] + stats['logs_inserted']} rows migrated")
    print()
    for label, s in stats["sources"].items():
        print(f"  {label}: {s.get('tasks', 0)} tasks ({s.get('inserted', 0)} new), "
              f"{s.get('logs', 0)} logs ({s.get('logs_inserted', 0)} new)")
    print("\nSQLite files left intact (evidence preserved).")
    return stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate kart_tasks.db SQLite files to Postgres")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing to Postgres")
    args = parser.parse_args()
    migrate(dry_run=args.dry_run)

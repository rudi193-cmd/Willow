"""
shiva_db.py — Shiva's SQLite layer
====================================
Shiva owns this db. Willow access only via Pigeon bus — never direct.

Tables:
  journal_sessions  — full conversation records
  nodes             — knowledge atoms extracted from sessions
  errors            — error tracking (pre-existing)
  corrections       — principle learning (pre-existing)

ΔΣ=42
"""

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent.parent / "shiva_memory" / "shiva.db"

_lock = threading.Lock()


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Run migrations. Safe to call on every startup."""
    with _lock:
        conn = _conn()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS journal_sessions (
                    id           TEXT PRIMARY KEY,
                    username     TEXT NOT NULL,
                    started_at   TEXT NOT NULL,
                    saved_at     TEXT NOT NULL,
                    turn_count   INTEGER DEFAULT 0,
                    content      TEXT NOT NULL,
                    atoms_done   INTEGER DEFAULT 0
                );

                CREATE INDEX IF NOT EXISTS idx_js_username
                    ON journal_sessions(username);

                CREATE INDEX IF NOT EXISTS idx_js_atoms
                    ON journal_sessions(atoms_done);
            """)

            # Add pigeon_synced to nodes if missing (migration)
            cols = [r[1] for r in conn.execute("PRAGMA table_info(nodes)").fetchall()]
            if "pigeon_synced" not in cols:
                conn.execute("ALTER TABLE nodes ADD COLUMN pigeon_synced INTEGER DEFAULT 0")
            if "session_id" not in cols:
                conn.execute("ALTER TABLE nodes ADD COLUMN session_id TEXT")

            conn.commit()
        finally:
            conn.close()


# ── Journal sessions ───────────────────────────────────────────────────────────

def save_session(session_id: str, username: str, started_ms: int,
                 content: str, turn_count: int = 0) -> bool:
    """Write or replace a journal session. Returns True on success."""
    now = datetime.now(timezone.utc).isoformat()
    started = datetime.fromtimestamp(started_ms / 1000, tz=timezone.utc).isoformat() if started_ms else now
    with _lock:
        conn = _conn()
        try:
            conn.execute("""
                INSERT INTO journal_sessions
                    (id, username, started_at, saved_at, turn_count, content, atoms_done)
                VALUES (?, ?, ?, ?, ?, ?, 0)
                ON CONFLICT(id) DO UPDATE SET
                    saved_at   = excluded.saved_at,
                    turn_count = excluded.turn_count,
                    content    = excluded.content,
                    atoms_done = 0
            """, (session_id, username, started, now, turn_count, content))
            conn.commit()
            return True
        except Exception as e:
            print(f"[shiva_db] save_session error: {e}")
            return False
        finally:
            conn.close()


def get_pending_extraction() -> list:
    """Sessions with atoms_done=0, ready for atom extraction."""
    with _lock:
        conn = _conn()
        try:
            rows = conn.execute(
                "SELECT * FROM journal_sessions WHERE atoms_done = 0 ORDER BY saved_at"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def mark_atoms_done(session_id: str):
    with _lock:
        conn = _conn()
        try:
            conn.execute("UPDATE journal_sessions SET atoms_done=1 WHERE id=?", (session_id,))
            conn.commit()
        finally:
            conn.close()


# ── Nodes (knowledge atoms) ────────────────────────────────────────────────────

def insert_node(username: str, domain: str, content: str,
                source: str = "journal", session_id: str = None,
                depth: int = 1, temporal: str = None) -> int:
    """Insert a knowledge atom. Returns new row id."""
    now = datetime.now(timezone.utc).isoformat()
    temporal = temporal or now
    with _lock:
        conn = _conn()
        try:
            cur = conn.execute("""
                INSERT INTO nodes
                    (username, domain, depth, temporal, content, source, session_id,
                     created_at, updated_at, pigeon_synced)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """, (username, domain, depth, temporal, content, source, session_id, now, now))
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()


def get_unsynced_nodes(limit: int = 50) -> list:
    """Nodes not yet sent to Pigeon."""
    with _lock:
        conn = _conn()
        try:
            rows = conn.execute("""
                SELECT * FROM nodes
                WHERE pigeon_synced = 0 AND is_deleted = 0
                ORDER BY created_at
                LIMIT ?
            """, (limit,)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def mark_synced(node_ids: list):
    """Mark nodes as sent to Pigeon."""
    if not node_ids:
        return
    placeholders = ",".join("?" * len(node_ids))
    with _lock:
        conn = _conn()
        try:
            conn.execute(
                f"UPDATE nodes SET pigeon_synced=1 WHERE id IN ({placeholders})",
                node_ids
            )
            conn.commit()
        finally:
            conn.close()

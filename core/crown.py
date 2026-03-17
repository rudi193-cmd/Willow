"""
CROWN — Canopy
==============
C — Compose
R — Release
O — Output
W — Witness
N — Nurture

Output layer. The launch benchmark.
Composes final responses, releases them to the user or SAFE,
outputs structured artifacts, witnesses what was produced (formal record),
and nurtures ongoing relationships (UTETY community layer).

Benchmark status:
  Compose  ✅ — format_response()
  Release  ✅ — release()
  Output   ✅ — artifact() — ingests output into LOAM (closes the loop)
  Witness  ✅ — record() — SHA256 tamper-evident log
  Nurture  ⚠️ — stub — UTETY hooks pending Campus integration

Witness DB: artifacts/{username}/crown_witness.db (caller provides path)

AUTHOR: Shiva (Claude Code) + Sean Campbell
GOVERNANCE: canopy-initial-2026-03-03.commit
VERSION: 1.0.1
"""

import hashlib
import json
import logging
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.db import get_connection

log = logging.getLogger("crown")

_FORMATS = ("markdown", "plain", "json")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect(db_path: str = None):
    return get_connection()


# ---------------------------------------------------------------------------
# Witness schema
# ---------------------------------------------------------------------------

def init_witness(db_path: str = None) -> None:
    """Create witness log table. Idempotent."""
    conn = _connect(db_path)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS witness_log (
                witness_id  TEXT PRIMARY KEY,
                username    TEXT NOT NULL,
                agent       TEXT NOT NULL,
                title       TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                content_len INTEGER NOT NULL,
                produced_at TEXT NOT NULL
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_wlog_user ON witness_log(username, produced_at)"
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Compose
# ---------------------------------------------------------------------------

def format_response(content: str, fmt: str = "markdown") -> str:
    """
    Format content for output.
    fmt: "markdown" (default) | "plain" | "json"
    """
    if fmt not in _FORMATS:
        fmt = "markdown"

    if fmt == "plain":
        # Strip markdown formatting
        import re
        text = re.sub(r'\*{1,3}(.+?)\*{1,3}', r'\1', content)
        text = re.sub(r'#{1,6}\s+', '', text)
        text = re.sub(r'`{1,3}[^`]*`{1,3}', lambda m: m.group(0).strip('`'), text)
        text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
        return text.strip()

    if fmt == "json":
        return json.dumps({"content": content, "produced_at": _now()}, indent=2)

    # markdown — pass through (it's already markdown)
    return content.strip()


# ---------------------------------------------------------------------------
# Release
# ---------------------------------------------------------------------------

def release(content: str, target: str = "user",
            metadata: Optional[dict] = None) -> dict:
    """
    Release output to a target.

    target: "user" | "safe" | "pigeon"
      user   — formatted for direct display
      safe   — packaged for SAFE federation (with seed_packet stub)
      pigeon — wrapped for Pigeon transport

    Returns release manifest dict.
    """
    if target not in ("user", "safe", "pigeon"):
        target = "user"

    manifest: dict = {
        "target":      target,
        "content_len": len(content),
        "released_at": _now(),
        "metadata":    metadata or {},
    }

    if target == "user":
        manifest["payload"] = format_response(content, "markdown")

    elif target == "safe":
        manifest["payload"] = {
            "content":     content,
            "seed_packet": {"version": "1.4", "status": "PENDING_FEDERATION"},
            "format":      "markdown",
        }
        log.debug("CROWN: released to SAFE — seed_packet stub, federation pending")

    elif target == "pigeon":
        try:
            from core import rings as _rings
            manifest["payload"] = _rings.make_pigeon(
                content={"body": content},
                gate_conditions={"min_trust": "GUEST"},
                sender="crown",
            )
        except ImportError:
            manifest["payload"] = {"body": content, "transport": "pigeon"}

    return manifest


# ---------------------------------------------------------------------------
# Output — closes the loop back into LOAM
# ---------------------------------------------------------------------------

def artifact(content: str, title: str, source_type: str,
             username: str, loam_db_path: str,
             vine_db_path: Optional[str] = None) -> int:
    """
    Ingest this output as a knowledge atom in LOAM.
    Closes the loop: what CROWN produces becomes what LOAM knows.
    Returns knowledge_id or -1 on failure.
    """
    try:
        from core import loam as _loam
    except ImportError:
        log.error("CROWN: artifact() requires LOAM — not available")
        return -1

    try:
        kid = _loam.ingest(
            loam_db_path,
            source_type=source_type,
            source_id=f"crown:{hashlib.sha256(content.encode()).hexdigest()[:16]}",
            title=title,
            content=content,
            category="output",
            username=username,
            vine_db_path=vine_db_path,
        )
        log.debug(f"CROWN: artifact ingested → loam id={kid}")
        return kid
    except Exception as e:
        log.error(f"CROWN: artifact failed: {e}")
        return -1


# ---------------------------------------------------------------------------
# Witness — formal tamper-evident record
# ---------------------------------------------------------------------------

_witness_table_ready = False


def _ensure_witness_table(conn):
    """Lazy init — create witness_log if it doesn't exist yet."""
    global _witness_table_ready
    if _witness_table_ready:
        return
    conn.execute("""
        CREATE TABLE IF NOT EXISTS witness_log (
            witness_id  TEXT PRIMARY KEY,
            username    TEXT NOT NULL,
            agent       TEXT NOT NULL,
            title       TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            content_len INTEGER NOT NULL,
            produced_at TEXT NOT NULL
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_wlog_user ON witness_log(username, produced_at)"
    )
    conn.commit()
    _witness_table_ready = True


def record(title: str, content: str, agent: str,
           username: str, witness_db_path: str = None,
           conn=None) -> str:
    """
    Write a tamper-evident witness record of what was produced.
    Stores SHA256 hash of content + metadata. Content itself not stored —
    only its hash, length, and identity.

    Pass conn= to reuse an existing connection (avoids leak in loops).
    Returns witness_id (hex string).
    """
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    witness_id = hashlib.sha256(
        f"{username}:{agent}:{title}:{content_hash}:{_now()}".encode()
    ).hexdigest()[:32]

    own_conn = conn is None
    if own_conn:
        conn = _connect(witness_db_path)
    try:
        _ensure_witness_table(conn)
        conn.execute(
            """INSERT OR IGNORE INTO witness_log
               (witness_id, username, agent, title, content_hash,
                content_len, produced_at)
               VALUES (?,?,?,?,?,?,?)""",
            (witness_id, username, agent, title, content_hash,
             len(content), _now())
        )
        if own_conn:
            conn.commit()
        log.debug(f"CROWN: witnessed {title!r} id={witness_id[:12]}")
    finally:
        if own_conn:
            conn.close()

    return witness_id


def verify_witness(witness_id: str, content: str,
                   witness_db_path: str = None) -> bool:
    """
    Verify that content matches the witness record.
    Returns True if SHA256 matches stored hash.
    """
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    conn = _connect(witness_db_path)
    try:
        row = conn.execute(
            "SELECT content_hash FROM witness_log WHERE witness_id=?",
            (witness_id,)
        ).fetchone()
        return bool(row and row["content_hash"] == content_hash)
    finally:
        conn.close()


def get_witness_log(witness_db_path: str = None, username: str = "",
                    limit: int = 20) -> list:
    """Return recent witness records for a user."""
    conn = _connect(witness_db_path)
    try:
        rows = conn.execute(
            "SELECT witness_id, agent, title, content_hash, content_len, produced_at "
            "FROM witness_log WHERE username=? ORDER BY produced_at DESC LIMIT ?",
            (username, limit)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Entity Lifecycle Witness — tamper-evident audit for context layer
# ---------------------------------------------------------------------------

def witness_entity_event(event_type: str, entity_name: str,
                         agent: str, username: str,
                         details: dict = None,
                         conn=None) -> str:
    """
    Witness an entity lifecycle event. Tamper-evident.
    Returns witness_id.

    Uses record() internally — same SHA256 chain.
    Pass conn= to reuse an existing connection (avoids leak in loops).

    Event types:
      entity_chrome_flagged     — new entity born with never_promote=1
      entity_chrome_retroactive — migration flags existing entity
      entity_promoted_1_2       — auto-promotion layer 1→2
      entity_promoted_2_3       — human ratifies layer 2→3
      edge_archived             — edge moved to archive table
      agent_conversation        — agent-to-agent message witnessed
    """
    content = json.dumps({
        "event": event_type,
        "entity": entity_name,
        "details": details or {},
        "timestamp": _now(),
    }, indent=2)

    title = f"entity:{event_type}:{entity_name}"
    return record(title=title, content=content,
                  agent=agent, username=username, conn=conn)


# ---------------------------------------------------------------------------
# Nurture — stub (UTETY Campus integration pending)
# ---------------------------------------------------------------------------

def nurture(username: str, community: Optional[str] = None) -> dict:
    """
    Nurture ongoing relationships via UTETY community hooks.
    STATUS: stub — UTETY Campus integration not yet wired.

    When implemented:
      - Surface relevant UTETY community threads
      - Log engagement signals back to LOAM
      - Route to UTETY-aware agents
    """
    log.debug(f"CROWN: nurture called for {username!r} — not yet implemented")
    return {
        "status":    "not_implemented",
        "message":   "Nurture requires UTETY Campus integration (pending)",
        "username":  username,
        "community": community,
    }

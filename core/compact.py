"""
compact.py — BASE 17 Compact Context Store

Pre-shared context by reference, not inline.
Agents register reusable context blocks under 5-char BASE 17 IDs.
Prompts reference the ID instead of embedding full content.

On free models with 4-8K context windows, this is the difference
between a usable rubric and output truncation.

Authority: Sean Campbell
System: Willow
ΔΣ=42
"""

import json
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, List

# BASE 17 alphabet — same as cli/base17.py
_ALPHABET = "0123456789ACEHKLNRTXZ"
_BASE = 17

# TTL defaults per category (hours). 0 = permanent.
_TTL_DEFAULTS = {
    "rubric": 30 * 24,      # 30 days
    "prompt": 30 * 24,      # 30 days
    "handoff": 1,            # 1 hour
    "pattern": 0,            # permanent
    "seed": 7 * 24,          # 7 days
}

# Direct psycopg2 — bypasses the db.py wrapper which has commit/rollback
# issues that make cross-connection persistence unreliable for new modules.
_DSN = os.getenv("WILLOW_DB_URL", "")


def _gen_id(length=5) -> str:
    """Generate a BASE 17 ID. Uses time + randomness like cli/base17.py."""
    import time, random
    seed = int(time.time() * 1000) ^ os.getpid() ^ random.randint(0, 0xFFFFFF)
    chars = []
    for _ in range(length):
        seed, rem = divmod(seed, _BASE)
        chars.append(_ALPHABET[rem])
    return "".join(reversed(chars))


def _connect():
    """Raw psycopg2 connection with autocommit off."""
    import psycopg2
    conn = psycopg2.connect(_DSN)
    conn.autocommit = False
    # Set search_path to match the Willow convention
    username = os.getenv("WILLOW_USERNAME", "")
    if username:
        import re
        safe = re.sub(r"[^a-z0-9]", "_", username.lower())[:63]
        cur = conn.cursor()
        cur.execute(f"SET search_path = {safe}, public")
        cur.close()
    return conn


_SCHEMA_INIT = False

def _ensure_table(conn):
    """Create compact_contexts table if it doesn't exist."""
    global _SCHEMA_INIT
    if _SCHEMA_INIT:
        return
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS compact_contexts (
            id TEXT PRIMARY KEY,
            content TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'pattern',
            label TEXT,
            agent TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP,
            access_count INTEGER DEFAULT 0,
            last_accessed TIMESTAMP
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_compact_category ON compact_contexts (category)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_compact_label ON compact_contexts (label)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_compact_expires ON compact_contexts (expires_at)")
    conn.commit()
    _SCHEMA_INIT = True


def register(content: str, category: str = "pattern", label: str = None,
             agent: str = None, ttl_hours: float = None, ctx_id: str = None) -> str:
    """
    Register a context block under a BASE 17 ID.

    Returns 5-char BASE 17 ID.
    """
    if len(content) > 100_000:
        raise ValueError("Context too large (max 100KB). Compact it first.")

    conn = _connect()
    try:
        _ensure_table(conn)
        cur = conn.cursor()

        cid = ctx_id or _gen_id()
        now = datetime.now()

        ttl = ttl_hours if ttl_hours is not None else _TTL_DEFAULTS.get(category, 0)
        expires = (now + timedelta(hours=ttl)) if ttl > 0 else None

        cur.execute("""
            INSERT INTO compact_contexts (id, content, category, label, agent, created_at, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                content = EXCLUDED.content,
                category = EXCLUDED.category,
                label = EXCLUDED.label,
                agent = EXCLUDED.agent,
                expires_at = EXCLUDED.expires_at
        """, (cid, content, category, label, agent, now, expires))
        conn.commit()
        return cid
    finally:
        conn.close()


def resolve(ctx_id: str) -> Optional[Dict]:
    """
    Resolve a BASE 17 ID to its content.

    Returns dict or None. None = anti-hallucination signal.
    """
    conn = _connect()
    try:
        _ensure_table(conn)
        cur = conn.cursor()

        cur.execute("""
            SELECT id, content, category, label, agent, created_at, expires_at, access_count
            FROM compact_contexts
            WHERE id = %s
        """, (ctx_id,))
        row = cur.fetchone()

        if not row:
            return None

        # Check expiry
        if row[6] and row[6] < datetime.now():
            return None

        # Update access stats
        cur.execute("""
            UPDATE compact_contexts
            SET access_count = access_count + 1, last_accessed = %s
            WHERE id = %s
        """, (datetime.now(), ctx_id))
        conn.commit()

        return {
            "id": row[0],
            "content": row[1],
            "category": row[2],
            "label": row[3],
            "agent": row[4],
            "created_at": str(row[5]),
            "access_count": row[7] + 1,
        }
    finally:
        conn.close()


def resolve_many(ctx_ids: List[str]) -> Dict[str, Optional[Dict]]:
    """Resolve multiple IDs. Returns {id: result_or_None}."""
    return {cid: resolve(cid) for cid in ctx_ids}


def find_by_label(label: str) -> Optional[Dict]:
    """Find a context by its human-readable label. Returns most recent match."""
    conn = _connect()
    try:
        _ensure_table(conn)
        cur = conn.cursor()
        cur.execute("""
            SELECT id, content, category, label, agent, created_at
            FROM compact_contexts
            WHERE label = %s
            ORDER BY created_at DESC
            LIMIT 1
        """, (label,))
        row = cur.fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "content": row[1],
            "category": row[2],
            "label": row[3],
            "agent": row[4],
            "created_at": str(row[5]),
        }
    finally:
        conn.close()


def compact_prompt(context_ids: List[str], content: str, instruction: str) -> str:
    """
    Build a prompt from pre-shared context references + inline content.

    Missing IDs produce "[MISSING: {id}]" — the model sees the gap
    instead of hallucinating over it.
    """
    sections = []

    for cid in context_ids:
        ctx = resolve(cid)
        if ctx:
            sections.append(f"[CTX:{cid}:{ctx['category']}]\n{ctx['content']}")
        else:
            sections.append(f"[MISSING:{cid}] — Context not found. Do NOT fabricate. Acknowledge this gap.")

    sections.append(f"[CONTENT]\n{content}")
    sections.append(f"[INSTRUCTION]\n{instruction}")

    return "\n\n".join(sections)


def handoff_packet(what_happened: str, what_next: str,
                   session_id: str = None, context_ids: List[str] = None,
                   agent: str = None) -> str:
    """
    Create an N2N handoff packet. Max 4KB.
    """
    sid = session_id or _gen_id()
    packet = {
        "type": "HANDOFF",
        "session": sid,
        "from": agent,
        "what_happened": what_happened[:500],
        "what_next": what_next[:500],
        "context_ids": context_ids or [],
        "timestamp": datetime.now().isoformat(),
    }
    encoded = json.dumps(packet, separators=(",", ":"))
    if len(encoded) > 4096:
        raise ValueError(f"Handoff packet too large ({len(encoded)} bytes, max 4096)")
    return encoded


def receive_handoff(packet_json: str) -> Dict:
    """
    Receive and resolve an N2N handoff packet.
    Missing contexts are flagged — not fabricated.
    """
    packet = json.loads(packet_json)
    resolved = {}
    missing = []

    for cid in packet.get("context_ids", []):
        ctx = resolve(cid)
        if ctx:
            resolved[cid] = ctx
        else:
            missing.append(cid)

    return {
        "session": packet["session"],
        "from": packet.get("from"),
        "what_happened": packet["what_happened"],
        "what_next": packet["what_next"],
        "contexts": resolved,
        "missing_contexts": missing,
        "timestamp": packet["timestamp"],
    }


def list_contexts(category: str = None, agent: str = None, limit: int = 50) -> List[Dict]:
    """List registered contexts, optionally filtered."""
    conn = _connect()
    try:
        _ensure_table(conn)
        cur = conn.cursor()
        query = "SELECT id, category, label, agent, created_at, access_count FROM compact_contexts WHERE 1=1"
        params = []

        if category:
            query += " AND category = %s"
            params.append(category)
        if agent:
            query += " AND agent = %s"
            params.append(agent)

        query += " ORDER BY created_at DESC LIMIT %s"
        params.append(limit)

        cur.execute(query, params)
        rows = cur.fetchall()
        return [{"id": r[0], "category": r[1], "label": r[2], "agent": r[3],
                 "created_at": str(r[4]), "access_count": r[5]} for r in rows]
    finally:
        conn.close()


def prune_expired() -> int:
    """Delete expired contexts. Returns count deleted."""
    conn = _connect()
    try:
        _ensure_table(conn)
        cur = conn.cursor()
        cur.execute("""
            DELETE FROM compact_contexts
            WHERE expires_at IS NOT NULL AND expires_at < %s
        """, (datetime.now(),))
        count = cur.rowcount
        conn.commit()
        return count
    finally:
        conn.close()

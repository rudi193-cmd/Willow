"""
AGENT_AUTH v1.0.0
Token-based check-in for registered Willow agents

Owner: Sean Campbell
System: Willow
Version: 1.0.0
Status: Active
Last Updated: 2026-02-25
Checksum: DS=42

Flow:
  1. Agent calls POST /api/agents/checkin {agent_name: ganesha}
  2. Willow validates agent exists in DB, records last_seen
  3. Willow issues 24h token, stores in willow_state + ~/.willow/agent_tokens.json
  4. Agent includes X-Willow-Agent: {token} in subsequent requests
  5. validate_token() resolves to (agent_name, trust_level) or None
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from core.db import get_connection as _get_connection
TOKEN_FILE = Path.home() / ".willow" / "agent_tokens.json"
TOKEN_TTL_HOURS = 24
CONTEXT_STORE_DB = Path.home() / ".claude" / "context_store.db"


def _fetch_pending() -> list:
    """Fetch unexpired governance items from context_store for this agent."""
    if not CONTEXT_STORE_DB.exists():
        return []
    try:
        conn = _get_connection(str(CONTEXT_STORE_DB))
        rows = conn.execute(
            """
            SELECT key, result FROM context_items
            WHERE key LIKE 'governance:pending_apply:%'
              AND created_at + (ttl_hours * interval '1 hour') > NOW()
            ORDER BY created_at DESC LIMIT 10
            """
        ).fetchall()
        conn.close()
        return [
            {
                "type": "governance_approval",
                "key": r[0],
                "commit_id": r[0].split(":")[-1],
                "result": r[1],
            }
            for r in rows
        ]
    except Exception:
        return []


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _db():
    return _get_connection()


def checkin(agent_name: str) -> dict:
    """
    Validate agent, issue token, record last_seen.
    Returns {token, trust_level, expires_at, agent_name} or raises ValueError.
    """
    db = _db()
    try:
        row = db.execute(
            "SELECT name, trust_level FROM agents WHERE name = ?", (agent_name,)
        ).fetchone()
        if not row:
            raise ValueError(f"Agent '{agent_name}' not registered.")

        name, trust_level = row
        token = str(uuid.uuid4())
        expires_at = (datetime.now(timezone.utc) + timedelta(hours=TOKEN_TTL_HOURS)).isoformat()
        now = _now()

        # Store in willow_state KV
        db.execute(
            "INSERT OR REPLACE INTO willow_state (key, value, set_at) VALUES (?, ?, ?)",
            (f"agent_token:{token}", json.dumps({"agent": name, "trust_level": trust_level, "expires_at": expires_at}), now),
        )
        # Update last_seen
        db.execute("UPDATE agents SET last_seen = ? WHERE name = ?", (now, name))
        db.commit()
    finally:
        db.close()

    # Mirror to ~/.willow/agent_tokens.json
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    existing = json.loads(TOKEN_FILE.read_text(encoding="utf-8")) if TOKEN_FILE.exists() else {}
    existing[agent_name] = {"token": token, "expires_at": expires_at}
    TOKEN_FILE.write_text(json.dumps(existing, indent=2), encoding="utf-8")

    # Lazy purge: clean expired tokens on each new issuance
    purge_expired_tokens()

    pending = _fetch_pending()
    return {"token": token, "trust_level": trust_level, "expires_at": expires_at, "agent_name": name, "pending": pending}


def validate_token(token: str) -> Optional[dict]:
    """
    Validate a token. Returns {agent_name, trust_level} or None if invalid/expired.
    """
    db = _db()
    try:
        row = db.execute(
            "SELECT value FROM willow_state WHERE key = ?", (f"agent_token:{token}",)
        ).fetchone()
    finally:
        db.close()
    if not row:
        return None
    data = json.loads(row[0])
    expires_at = datetime.fromisoformat(data["expires_at"])
    if datetime.now(timezone.utc) > expires_at:
        return None
    return {"agent_name": data["agent"], "trust_level": data["trust_level"]}


def purge_expired_tokens() -> int:
    """Delete expired agent tokens from willow_state. Called lazily on each new token issuance."""
    db = _db()
    try:
        now = _now()
        rows = db.execute(
            "SELECT key, value FROM willow_state WHERE key LIKE 'agent_token:%'"
        ).fetchall()
        expired = []
        for row in rows:
            try:
                val = json.loads(row["value"])
                if val.get("expires_at", "") < now:
                    expired.append(row["key"])
            except Exception:
                pass
        if expired:
            placeholders = ",".join("?" * len(expired))
            db.execute(f"DELETE FROM willow_state WHERE key IN ({placeholders})", expired)
            db.commit()
        return len(expired)
    except Exception:
        return 0
    finally:
        db.close()


def load_my_token(agent_name: str) -> Optional[str]:
    """
    Load this agent's current token from ~/.willow/agent_tokens.json.
    Returns token string or None if missing/expired.
    """
    if not TOKEN_FILE.exists():
        return None
    data = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
    entry = data.get(agent_name)
    if not entry:
        return None
    expires_at = datetime.fromisoformat(entry["expires_at"])
    if datetime.now(timezone.utc) > expires_at:
        return None
    return entry["token"]

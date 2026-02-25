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
import sqlite3
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent.parent / "artifacts" / "Sweet-Pea-Rudi19" / "willow_knowledge.db"
TOKEN_FILE = Path.home() / ".willow" / "agent_tokens.json"
TOKEN_TTL_HOURS = 24


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _db() -> sqlite3.Connection:
    return sqlite3.connect(str(DB_PATH))


def checkin(agent_name: str) -> dict:
    """
    Validate agent, issue token, record last_seen.
    Returns {token, trust_level, expires_at, agent_name} or raises ValueError.
    """
    db = _db()
    row = db.execute(
        "SELECT name, trust_level FROM agents WHERE name = ?", (agent_name,)
    ).fetchone()
    if not row:
        db.close()
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
    db.close()

    # Mirror to ~/.willow/agent_tokens.json
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    existing = json.loads(TOKEN_FILE.read_text(encoding="utf-8")) if TOKEN_FILE.exists() else {}
    existing[agent_name] = {"token": token, "expires_at": expires_at}
    TOKEN_FILE.write_text(json.dumps(existing, indent=2), encoding="utf-8")

    return {"token": token, "trust_level": trust_level, "expires_at": expires_at, "agent_name": name}


def validate_token(token: str) -> Optional[dict]:
    """
    Validate a token. Returns {agent_name, trust_level} or None if invalid/expired.
    """
    db = _db()
    row = db.execute(
        "SELECT value FROM willow_state WHERE key = ?", (f"agent_token:{token}",)
    ).fetchone()
    db.close()
    if not row:
        return None
    data = json.loads(row[0])
    expires_at = datetime.fromisoformat(data["expires_at"])
    if datetime.now(timezone.utc) > expires_at:
        return None
    return {"agent_name": data["agent"], "trust_level": data["trust_level"]}


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

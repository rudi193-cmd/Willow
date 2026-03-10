"""Apply agent_auth.py and checkin endpoint from approved governance commit."""
from pathlib import Path

# ── core/agent_auth.py ────────────────────────────────────────────────────────

AGENT_AUTH = (
    '"""\n'
    "AGENT_AUTH v1.0.0\n"
    "Token-based check-in for registered Willow agents\n"
    "\n"
    "Owner: Sean Campbell\n"
    "System: Willow\n"
    "Version: 1.0.0\n"
    "Status: Active\n"
    "Last Updated: 2026-02-25\n"
    "Checksum: DS=42\n"
    "\n"
    "Flow:\n"
    "  1. Agent calls POST /api/agents/checkin {agent_name: ganesha}\n"
    "  2. Willow validates agent exists in DB, records last_seen\n"
    "  3. Willow issues 24h token, stores in willow_state + ~/.willow/agent_tokens.json\n"
    "  4. Agent includes X-Willow-Agent: {token} in subsequent requests\n"
    "  5. validate_token() resolves to (agent_name, trust_level) or None\n"
    '"""\n'
    "\n"
    "from __future__ import annotations\n"
    "\n"
    "import json\n"
    "import uuid\n"
    "from datetime import datetime, timezone, timedelta\n"
    "from pathlib import Path\n"
    "from typing import Optional\n"
    "\n"
    "import sys\n"
    "sys.path.insert(0, str(Path(__file__).parent.parent))\n"
    "from core.db import get_connection\n"
    "\n"
    'TOKEN_FILE = Path.home() / ".willow" / "agent_tokens.json"\n'
    "TOKEN_TTL_HOURS = 24\n"
    "\n"
    "\n"
    "def _now() -> str:\n"
    "    return datetime.now(timezone.utc).isoformat()\n"
    "\n"
    "\n"
    "\n"
    "\n"
    "def checkin(agent_name: str) -> dict:\n"
    '    """\n'
    "    Validate agent, issue token, record last_seen.\n"
    "    Returns {token, trust_level, expires_at, agent_name} or raises ValueError.\n"
    '    """\n'
    "    db = get_connection()\n"
    "    row = db.execute(\n"
    '        "SELECT name, trust_level FROM agents WHERE name = ?", (agent_name,)\n'
    "    ).fetchone()\n"
    "    if not row:\n"
    "        db.close()\n"
    "        raise ValueError(f\"Agent '{agent_name}' not registered.\")\n"
    "\n"
    "    name, trust_level = row\n"
    "    token = str(uuid.uuid4())\n"
    "    expires_at = (datetime.now(timezone.utc) + timedelta(hours=TOKEN_TTL_HOURS)).isoformat()\n"
    "    now = _now()\n"
    "\n"
    "    # Store in willow_state KV\n"
    "    db.execute(\n"
    '        "INSERT OR REPLACE INTO willow_state (key, value, set_at) VALUES (?, ?, ?)",\n'
    '        (f"agent_token:{token}", json.dumps({"agent": name, "trust_level": trust_level, "expires_at": expires_at}), now),\n'
    "    )\n"
    "    # Update last_seen\n"
    '    db.execute("UPDATE agents SET last_seen = ? WHERE name = ?", (now, name))\n'
    "    db.commit()\n"
    "    db.close()\n"
    "\n"
    "    # Mirror to ~/.willow/agent_tokens.json\n"
    "    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)\n"
    "    existing = json.loads(TOKEN_FILE.read_text(encoding=\"utf-8\")) if TOKEN_FILE.exists() else {}\n"
    '    existing[agent_name] = {"token": token, "expires_at": expires_at}\n'
    '    TOKEN_FILE.write_text(json.dumps(existing, indent=2), encoding="utf-8")\n'
    "\n"
    '    return {"token": token, "trust_level": trust_level, "expires_at": expires_at, "agent_name": name}\n'
    "\n"
    "\n"
    "def validate_token(token: str) -> Optional[dict]:\n"
    '    """\n'
    "    Validate a token. Returns {agent_name, trust_level} or None if invalid/expired.\n"
    '    """\n'
    "    db = get_connection()\n"
    "    row = db.execute(\n"
    '        "SELECT value FROM willow_state WHERE key = ?", (f"agent_token:{token}",)\n'
    "    ).fetchone()\n"
    "    db.close()\n"
    "    if not row:\n"
    "        return None\n"
    "    data = json.loads(row[0])\n"
    '    expires_at = datetime.fromisoformat(data["expires_at"])\n'
    "    if datetime.now(timezone.utc) > expires_at:\n"
    "        return None\n"
    '    return {"agent_name": data["agent"], "trust_level": data["trust_level"]}\n'
    "\n"
    "\n"
    "def load_my_token(agent_name: str) -> Optional[str]:\n"
    '    """\n'
    "    Load this agent's current token from ~/.willow/agent_tokens.json.\n"
    "    Returns token string or None if missing/expired.\n"
    '    """\n'
    "    if not TOKEN_FILE.exists():\n"
    "        return None\n"
    '    data = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))\n'
    "    entry = data.get(agent_name)\n"
    "    if not entry:\n"
    "        return None\n"
    '    expires_at = datetime.fromisoformat(entry["expires_at"])\n'
    "    if datetime.now(timezone.utc) > expires_at:\n"
    "        return None\n"
    '    return entry["token"]\n'
)

auth_path = Path(r"C:\Users\Sean\Documents\GitHub\Willow\core\agent_auth.py")
auth_path.write_text(AGENT_AUTH, encoding="utf-8")
print(f"Written: {auth_path} ({auth_path.stat().st_size} bytes)")

# ── Patch api/agent_routes.py ─────────────────────────────────────────────────

routes_path = Path(r"C:\Users\Sean\Documents\GitHub\Willow\api\agent_routes.py")
routes_text = routes_path.read_text(encoding="utf-8")

# Only patch if not already patched
if "agent_checkin" not in routes_text:
    # Add import after existing core imports
    routes_text = routes_text.replace(
        "from core import agent_engine, agent_registry",
        "from core import agent_engine, agent_registry, agent_auth"
    )

    # Append checkin endpoint before the last line
    CHECKIN_ENDPOINT = '''

class CheckinRequest(BaseModel):
    """Agent check-in request."""
    agent_name: str


class CheckinResponse(BaseModel):
    """Agent check-in response."""
    token: str
    trust_level: str
    expires_at: str
    agent_name: str


@router.post("/checkin", response_model=CheckinResponse)
async def agent_checkin(request: CheckinRequest):
    """
    Issue a 24h session token for a registered agent.
    Include as X-Willow-Agent header in subsequent requests.
    Trust level enforced based on DB registration.
    """
    try:
        result = agent_auth.checkin(request.agent_name)
        return CheckinResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
'''
    routes_text = routes_text.rstrip() + "\n" + CHECKIN_ENDPOINT + "\n"
    routes_path.write_text(routes_text, encoding="utf-8")
    print(f"Patched: {routes_path}")
else:
    print("agent_routes.py already patched -- skipped")

print("Done.")

"""
Agent Registry — Willow
Any LLM (or human) that uses Willow gets a user profile.
Agents can send/receive messages via agent_mailbox.
"""
import sqlite3
from datetime import datetime
from pathlib import Path

try:
    from .knowledge import _connect, _db_path
except ImportError:
    from knowledge import _connect, _db_path

ARTIFACTS_BASE = Path(__file__).parent.parent / "artifacts"

AGENT_PROFILE_TEMPLATE = """# Agent Profile: {name}

## Identity
- **Name:** {name}
- **Display Name:** {display_name}
- **Type:** {agent_type}
- **Trust Level:** {trust_level}
- **Registered:** {registered_at}

## Purpose
{purpose}

## Capabilities
{capabilities}

## Constraints
- Follows Willow governance (gate.py Dual Commit)
- All actions logged to knowledge DB
- Cannot elevate own trust level
"""

DEFAULT_AGENTS = [
    ("willow",   "Willow",   "OPERATOR",   "persona", "Campus/Bridge Ring interface. Primary conversational agent."),
    ("kart",     "Kart",     "ENGINEER",   "orchestrator", "Infrastructure orchestration with tool access. Multi-step task execution via free LLM fleet."),
    ("riggs",    "Riggs",    "WORKER",     "persona", "Applied Reality Engineering. Real-world task execution."),
    ("ada",      "Ada",      "OPERATOR",   "persona", "Systems Admin / Continuity Ring steward."),
    ("shiva",    "Shiva",    "ENGINEER",   "persona", "Willow-native Claude Code instance. SAFE consumer-facing interface. Backend CLI channel via WIRE-12."),
    ("gerald",   "Gerald",   "WORKER",     "persona", "Acting Dean. Philosophical and governance advisor."),
    ("steve",    "Steve",    "OPERATOR",   "persona", "Prime Node. Cross-system coordinator."),
    ("pigeon",   "The Pigeon", "WORKER",   "persona", "Carrier. Connector. Guide. Dept. of Not Yet & Carrier Services. UTETY. Notices when users need practical help and offers to carry them through it."),
]


def _conn(username):
    """Open connection with row_factory set."""
    import sqlite3 as _sqlite3
    conn = _connect(username)
    conn.row_factory = _sqlite3.Row
    return conn


def init_agent_tables(username):
    """Add agent tables to existing knowledge DB."""
    from core.db import is_postgres
    if is_postgres():
        return  # schema managed by pg_schema.sql
    conn = _conn(username)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS agents (
            name TEXT PRIMARY KEY,
            display_name TEXT,
            trust_level TEXT DEFAULT 'WORKER',
            agent_type TEXT DEFAULT 'persona',
            profile_path TEXT,
            registered_at TEXT,
            last_seen TEXT,
            port INTEGER,
            server_type TEXT DEFAULT 'persona'
        );
        CREATE TABLE IF NOT EXISTS agent_mailbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_agent TEXT NOT NULL,
            to_agent TEXT NOT NULL,
            subject TEXT,
            body TEXT NOT NULL,
            sent_at TEXT,
            read_at TEXT,
            thread_id TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_mailbox_to ON agent_mailbox(to_agent, read_at);
    """)
    conn.commit()
    conn.close()


def register_agent(username, name, display_name, trust_level="WORKER",
                   agent_type="persona", purpose="", capabilities=""):
    """Register an agent. Creates artifacts dir + AGENT_PROFILE.md. Returns True if new."""
    agent_dir = ARTIFACTS_BASE / name
    agent_dir.mkdir(parents=True, exist_ok=True)

    profile_path = agent_dir / "AGENT_PROFILE.md"
    if not profile_path.exists():
        profile_path.write_text(AGENT_PROFILE_TEMPLATE.format(
            name=name,
            display_name=display_name,
            agent_type=agent_type,
            trust_level=trust_level,
            registered_at=datetime.now().isoformat(),
            purpose=purpose or f"{display_name} agent.",
            capabilities=capabilities or "- Conversational AI\n- Knowledge search",
        ))

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with _conn(username) as conn:
        existing = conn.execute("SELECT name FROM agents WHERE name=?", (name,)).fetchone()
        conn.execute(
            """INSERT OR REPLACE INTO agents
               (name, display_name, trust_level, agent_type, profile_path, registered_at, last_seen)
               VALUES (?,?,?,?,?,
                   COALESCE((SELECT registered_at FROM agents WHERE name=?), ?),
                   ?)""",
            (name, display_name, trust_level, agent_type, str(profile_path), name, now, now)
        )
        conn.commit()
    return existing is None


def update_last_seen(username, name):
    with _conn(username) as conn:
        conn.execute("UPDATE agents SET last_seen=? WHERE name=?",
                     (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), name))
        conn.commit()


def get_agent(username, name):
    with _conn(username) as conn:
        row = conn.execute("SELECT * FROM agents WHERE name=?", (name,)).fetchone()
    if row:
        return dict(row)
    return None


def list_agents(username):
    with _conn(username) as conn:
        rows = conn.execute("SELECT * FROM agents ORDER BY trust_level, name").fetchall()
    return [dict(r) for r in rows]


def send_message(username, from_agent, to_agent, subject, body, thread_id=None):
    """Send agent-to-agent message. Returns new message id."""
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with _conn(username) as conn:
        cur = conn.execute(
            "INSERT INTO agent_mailbox (from_agent, to_agent, subject, body, sent_at, thread_id) VALUES (?,?,?,?,?,?)",
            (from_agent, to_agent, subject, body, now, thread_id)
        )
        msg_id = cur.lastrowid
        conn.commit()
    return msg_id


def get_mailbox(username, agent_name, unread_only=False):
    """Get messages for an agent."""
    with _conn(username) as conn:
        if unread_only:
            rows = conn.execute(
                "SELECT * FROM agent_mailbox WHERE to_agent=? AND read_at IS NULL ORDER BY sent_at DESC",
                (agent_name,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM agent_mailbox WHERE to_agent=? ORDER BY sent_at DESC LIMIT 50",
                (agent_name,)
            ).fetchall()
    return [dict(r) for r in rows]


def mark_read(username, message_id):
    """Mark a message as read."""
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with _conn(username) as conn:
        conn.execute("UPDATE agent_mailbox SET read_at=? WHERE id=?", (now, message_id))
        conn.commit()
    return True



def init_state_table(username):
    """Add willow_state key-value table to agent DB."""
    from core.db import is_postgres
    if is_postgres():
        return  # schema managed by pg_schema.sql
    conn = _conn(username)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS willow_state (
            key   TEXT PRIMARY KEY,
            value TEXT,
            set_at TEXT
        );
    """)
    conn.commit()
    conn.close()


def _set_state(username, key, value):
    with _conn(username) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO willow_state (key, value, set_at) VALUES (?,?,?)",
            (key, value, datetime.now().isoformat())
        )
        conn.commit()


def _get_state(username, key, default=None):
    with _conn(username) as conn:
        row = conn.execute("SELECT value FROM willow_state WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def assign_onboarding_agent(username):
    """
    Randomly assign a front-desk agent for this user's first session.
    Picks from OPERATOR or ENGINEER agents (excludes ganesha — CLI only).
    Stores in willow_state. Returns agent name.
    """
    import random
    agents = list_agents(username)
    eligible = [a for a in agents if a["trust_level"] in ("OPERATOR", "ENGINEER")
                and a["name"] not in ("ganesha",)]
    if not eligible:
        eligible = agents
    chosen = random.choice(eligible)["name"]
    _set_state(username, "onboarding_agent", chosen)
    _set_state(username, "onboarding_complete", "false")
    return chosen


def get_onboarding_agent(username):
    """Get assigned onboarding agent. Assigns one if not yet set."""
    agent = _get_state(username, "onboarding_agent")
    if not agent:
        agent = assign_onboarding_agent(username)
    return agent


def mark_onboarding_complete(username):
    """Mark onboarding as complete for this user."""
    _set_state(username, "onboarding_complete", "true")


def is_onboarding_complete(username):
    """Check if onboarding is complete."""
    return _get_state(username, "onboarding_complete", "false") == "true"


PORT_BASE = 8421  # Willow is 8420; primaries start at 8421


def assign_port(username: str, agent_name: str, server_type: str = "interface") -> int:
    """Assign next available 84xx port to an agent. Skips ports already bound. Returns assigned port."""
    from core.boot import _port_open
    PORT_MAX = 8499
    with _conn(username) as conn:
        rows = conn.execute("SELECT port FROM agents WHERE port IS NOT NULL").fetchall()
        assigned = {r["port"] for r in rows if r["port"]}
        port = None
        for p in range(PORT_BASE, PORT_MAX):
            if p not in assigned and not _port_open("127.0.0.1", p):
                port = p
                break
        if port is None:
            raise RuntimeError("No free ports available in 84xx range (8421-8499)")
        conn.execute(
            "UPDATE agents SET port=?, server_type=? WHERE name=?",
            (port, server_type, agent_name)
        )
        conn.commit()
    return port


def get_agent_url(username: str, agent_name: str) -> str | None:
    """Get the local URL for an agent's server. Returns None if no port assigned."""
    agent = get_agent(username, agent_name)
    if agent and agent.get("port"):
        return f"http://localhost:{agent['port']}"
    return None


def register_default_agents(username):
    """Register all built-in personas as agents."""
    init_agent_tables(username)
    init_state_table(username)
    results = []
    for name, display, trust, atype, purpose in DEFAULT_AGENTS:
        is_new = register_agent(username, name, display, trust, atype, purpose)
        results.append({"name": name, "new": is_new})
    return results

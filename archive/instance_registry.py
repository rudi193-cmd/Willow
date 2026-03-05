"""
INSTANCE_REGISTRY.PY - Centralized Instance & Trust Management
===============================================================
Single source of truth for:
- Instance identities and capabilities
- Trust levels and permissions
- Routing rules and escalation paths

All components query this instead of rebuilding trust logic.
"""

import sqlite3
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass
from typing import List, Dict, Optional, Set
from enum import IntEnum

# =============================================================================
# CONFIGURATION
# =============================================================================

BRIDGE_RING = Path(__file__).parent.resolve()
DB_PATH = BRIDGE_RING / ".instance_registry.db"

# =============================================================================
# TRUST LEVELS
# =============================================================================

class TrustLevel(IntEnum):
    """
    Trust tiers - what an instance can do autonomously.

    OBSERVER (0): Read-only, no actions
    WORKER (1):   Execute pre-approved tasks
    OPERATOR (2): Execute tasks, limited writes
    ENGINEER (3): Full local autonomy, propose changes
    ARCHITECT (4): Cross-system changes, requires human approval
    """
    OBSERVER = 0
    WORKER = 1
    OPERATOR = 2
    ENGINEER = 3
    ARCHITECT = 4

TRUST_NAMES = {
    TrustLevel.OBSERVER: "OBSERVER",
    TrustLevel.WORKER: "WORKER",
    TrustLevel.OPERATOR: "OPERATOR",
    TrustLevel.ENGINEER: "ENGINEER",
    TrustLevel.ARCHITECT: "ARCHITECT",
}

# What each trust level can do
TRUST_CAPABILITIES = {
    TrustLevel.OBSERVER: {"read", "search", "query"},
    TrustLevel.WORKER: {"read", "search", "query", "execute_approved"},
    TrustLevel.OPERATOR: {"read", "search", "query", "execute_approved", "write_local", "build"},
    TrustLevel.ENGINEER: {"read", "search", "query", "execute_approved", "write_local", "build", "write_any", "propose"},
    TrustLevel.ARCHITECT: {"read", "search", "query", "execute_approved", "write_local", "build", "write_any", "propose", "cross_system", "governance"},
}

# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class Instance:
    """An AI or service instance in the system."""
    instance_id: str          # e.g., "kart-interface", "willow-local"
    name: str                 # Human name, e.g., "Kartikeya", "Willow"
    instance_type: str        # "interface", "substrate", "service", "api"
    trust_level: TrustLevel
    capabilities: Set[str]    # What this instance can do
    escalates_to: str         # Instance to escalate complex tasks to
    created: str
    last_seen: str
    metadata: Dict

    @property
    def trust_name(self) -> str:
        return TRUST_NAMES.get(self.trust_level, "UNKNOWN")

@dataclass
class RoutingRule:
    """A routing rule for task delegation."""
    rule_id: str
    from_instance: str        # Who sends
    to_instance: str          # Who receives
    action_pattern: str       # Regex pattern for actions
    priority: int             # Lower = higher priority
    requires_ack: bool        # Must acknowledge?
    active: bool

# =============================================================================
# DATABASE
# =============================================================================

def init_db() -> sqlite3.Connection:
    """Initialize the instance registry database."""
    conn = sqlite3.connect(str(DB_PATH))

    # Instances table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS instances (
            instance_id TEXT PRIMARY KEY,
            name TEXT,
            instance_type TEXT,
            trust_level INTEGER DEFAULT 1,
            capabilities TEXT,
            escalates_to TEXT,
            created TEXT,
            last_seen TEXT,
            metadata TEXT
        )
    """)

    # Routing rules table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS routing_rules (
            rule_id TEXT PRIMARY KEY,
            from_instance TEXT,
            to_instance TEXT,
            action_pattern TEXT,
            priority INTEGER DEFAULT 100,
            requires_ack INTEGER DEFAULT 1,
            active INTEGER DEFAULT 1
        )
    """)

    # Trust audit log
    conn.execute("""
        CREATE TABLE IF NOT EXISTS trust_audit (
            id INTEGER PRIMARY KEY,
            timestamp TEXT,
            instance_id TEXT,
            action TEXT,
            old_level INTEGER,
            new_level INTEGER,
            reason TEXT,
            approved_by TEXT
        )
    """)

    # Capability grants (temporary elevated permissions)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS capability_grants (
            grant_id TEXT PRIMARY KEY,
            instance_id TEXT,
            capability TEXT,
            granted_at TEXT,
            expires_at TEXT,
            reason TEXT
        )
    """)

    conn.commit()
    return conn

def get_connection() -> sqlite3.Connection:
    """Get a connection to the registry."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

# =============================================================================
# INSTANCE MANAGEMENT
# =============================================================================

def register_instance(
    instance_id: str,
    name: str,
    instance_type: str = "service",
    trust_level: TrustLevel = TrustLevel.WORKER,
    capabilities: Set[str] = None,
    escalates_to: str = "",
    metadata: Dict = None
) -> bool:
    """Register a new instance or update existing."""
    conn = get_connection()

    caps = capabilities or TRUST_CAPABILITIES.get(trust_level, set())
    now = datetime.now().isoformat()

    conn.execute("""
        INSERT INTO instances (instance_id, name, instance_type, trust_level,
                              capabilities, escalates_to, created, last_seen, metadata)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(instance_id) DO UPDATE SET
            name = excluded.name,
            instance_type = excluded.instance_type,
            trust_level = excluded.trust_level,
            capabilities = excluded.capabilities,
            escalates_to = excluded.escalates_to,
            last_seen = excluded.last_seen,
            metadata = excluded.metadata
    """, (
        instance_id,
        name,
        instance_type,
        int(trust_level),
        ",".join(caps),
        escalates_to,
        now,
        now,
        str(metadata or {})
    ))

    conn.commit()
    conn.close()
    return True

def get_instance(instance_id: str) -> Optional[Instance]:
    """Get instance by ID."""
    conn = get_connection()

    row = conn.execute(
        "SELECT * FROM instances WHERE instance_id = ?",
        (instance_id,)
    ).fetchone()

    conn.close()

    if not row:
        return None

    return Instance(
        instance_id=row['instance_id'],
        name=row['name'],
        instance_type=row['instance_type'],
        trust_level=TrustLevel(row['trust_level']),
        capabilities=set(row['capabilities'].split(',')) if row['capabilities'] else set(),
        escalates_to=row['escalates_to'] or "",
        created=row['created'],
        last_seen=row['last_seen'],
        metadata=eval(row['metadata']) if row['metadata'] else {}
    )

def list_instances(instance_type: str = None) -> List[Instance]:
    """List all registered instances."""
    conn = get_connection()

    if instance_type:
        rows = conn.execute(
            "SELECT * FROM instances WHERE instance_type = ? ORDER BY trust_level DESC",
            (instance_type,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM instances ORDER BY trust_level DESC"
        ).fetchall()

    conn.close()

    return [
        Instance(
            instance_id=row['instance_id'],
            name=row['name'],
            instance_type=row['instance_type'],
            trust_level=TrustLevel(row['trust_level']),
            capabilities=set(row['capabilities'].split(',')) if row['capabilities'] else set(),
            escalates_to=row['escalates_to'] or "",
            created=row['created'],
            last_seen=row['last_seen'],
            metadata=eval(row['metadata']) if row['metadata'] else {}
        )
        for row in rows
    ]

def update_last_seen(instance_id: str):
    """Update last_seen timestamp for an instance."""
    conn = get_connection()
    conn.execute(
        "UPDATE instances SET last_seen = ? WHERE instance_id = ?",
        (datetime.now().isoformat(), instance_id)
    )
    conn.commit()
    conn.close()

# =============================================================================
# TRUST MANAGEMENT
# =============================================================================

def set_trust_level(
    instance_id: str,
    new_level: TrustLevel,
    reason: str,
    approved_by: str = "system"
) -> bool:
    """Change an instance's trust level. Logs the change."""
    conn = get_connection()

    # Get current level
    row = conn.execute(
        "SELECT trust_level FROM instances WHERE instance_id = ?",
        (instance_id,)
    ).fetchone()

    if not row:
        conn.close()
        return False

    old_level = row['trust_level']

    # Update trust level and capabilities
    new_caps = TRUST_CAPABILITIES.get(new_level, set())

    conn.execute(
        "UPDATE instances SET trust_level = ?, capabilities = ? WHERE instance_id = ?",
        (int(new_level), ",".join(new_caps), instance_id)
    )

    # Log the change
    conn.execute("""
        INSERT INTO trust_audit (timestamp, instance_id, action, old_level, new_level, reason, approved_by)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        datetime.now().isoformat(),
        instance_id,
        "TRUST_CHANGE",
        old_level,
        int(new_level),
        reason,
        approved_by
    ))

    conn.commit()
    conn.close()
    return True

def can_do(instance_id: str, capability: str) -> bool:
    """Check if an instance has a specific capability."""
    instance = get_instance(instance_id)
    if not instance:
        return False

    # Check base capabilities
    if capability in instance.capabilities:
        return True

    # Check temporary grants
    conn = get_connection()
    grant = conn.execute("""
        SELECT * FROM capability_grants
        WHERE instance_id = ? AND capability = ?
        AND datetime(expires_at) > datetime('now')
    """, (instance_id, capability)).fetchone()
    conn.close()

    return grant is not None

def grant_capability(
    instance_id: str,
    capability: str,
    duration_hours: int = 24,
    reason: str = ""
) -> str:
    """Grant temporary capability to an instance."""
    import uuid
    conn = get_connection()

    grant_id = f"grant-{uuid.uuid4().hex[:8]}"
    granted_at = datetime.now().isoformat()
    from datetime import timedelta
    expires_at = (datetime.now() + timedelta(hours=duration_hours)).isoformat()

    conn.execute("""
        INSERT INTO capability_grants (grant_id, instance_id, capability, granted_at, expires_at, reason)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (grant_id, instance_id, capability, granted_at, expires_at, reason))

    # Log it
    conn.execute("""
        INSERT INTO trust_audit (timestamp, instance_id, action, old_level, new_level, reason, approved_by)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (granted_at, instance_id, "CAPABILITY_GRANT", 0, 0, f"Granted {capability}: {reason}", "system"))

    conn.commit()
    conn.close()
    return grant_id

# =============================================================================
# ROUTING RULES
# =============================================================================

def add_routing_rule(
    from_instance: str,
    to_instance: str,
    action_pattern: str,
    priority: int = 100,
    requires_ack: bool = True
) -> str:
    """Add a routing rule."""
    import uuid
    conn = get_connection()

    rule_id = f"rule-{uuid.uuid4().hex[:8]}"

    conn.execute("""
        INSERT INTO routing_rules (rule_id, from_instance, to_instance, action_pattern, priority, requires_ack, active)
        VALUES (?, ?, ?, ?, ?, ?, 1)
    """, (rule_id, from_instance, to_instance, action_pattern, priority, int(requires_ack)))

    conn.commit()
    conn.close()
    return rule_id

def get_escalation_target(instance_id: str, action: str = None) -> Optional[str]:
    """Get the instance to escalate to for a given action."""
    instance = get_instance(instance_id)
    if not instance:
        return None

    # Check routing rules first
    if action:
        import re
        conn = get_connection()
        rules = conn.execute("""
            SELECT * FROM routing_rules
            WHERE from_instance = ? AND active = 1
            ORDER BY priority ASC
        """, (instance_id,)).fetchall()
        conn.close()

        for rule in rules:
            if re.match(rule['action_pattern'], action, re.IGNORECASE):
                return rule['to_instance']

    # Fall back to default escalation
    return instance.escalates_to if instance.escalates_to else None

def list_routing_rules(from_instance: str = None) -> List[RoutingRule]:
    """List routing rules."""
    conn = get_connection()

    if from_instance:
        rows = conn.execute(
            "SELECT * FROM routing_rules WHERE from_instance = ? ORDER BY priority",
            (from_instance,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM routing_rules ORDER BY from_instance, priority"
        ).fetchall()

    conn.close()

    return [
        RoutingRule(
            rule_id=row['rule_id'],
            from_instance=row['from_instance'],
            to_instance=row['to_instance'],
            action_pattern=row['action_pattern'],
            priority=row['priority'],
            requires_ack=bool(row['requires_ack']),
            active=bool(row['active'])
        )
        for row in rows
    ]

# =============================================================================
# BOOTSTRAP DEFAULT INSTANCES
# =============================================================================

def bootstrap_defaults():
    """Register the default system instances."""
    # Kart - Chief Engineer (Interface)
    register_instance(
        instance_id="kart-interface",
        name="Kartikeya",
        instance_type="interface",
        trust_level=TrustLevel.ENGINEER,
        escalates_to="willow-local",
        metadata={"role": "Chief Engineer", "checksum": "42"}
    )

    # Willow - Substrate (Hands & Eyes)
    register_instance(
        instance_id="willow-local",
        name="Willow",
        instance_type="substrate",
        trust_level=TrustLevel.OPERATOR,
        escalates_to="claude-api",  # Willow escalates to Claude for complex reasoning
        metadata={"role": "Local Substrate", "has_filesystem": True}
    )

    # Claude API - External reasoning (Tier 2)
    register_instance(
        instance_id="claude-api",
        name="Claude",
        instance_type="api",
        trust_level=TrustLevel.ENGINEER,
        capabilities={"read", "search", "query", "execute_approved", "propose", "write_any"},
        escalates_to="human-chief",  # Claude escalates to human for governance
        metadata={"role": "External Reasoning", "model": "claude-sonnet-4", "paid": True}
    )

    # Human (The Chief)
    register_instance(
        instance_id="human-chief",
        name="Sean Campbell",
        instance_type="human",
        trust_level=TrustLevel.ARCHITECT,
        capabilities={"all"},
        escalates_to="",
        metadata={"role": "The Chief", "authority": "final"}
    )

    # Default routing: Kart -> Willow for IO (Tier 1)
    add_routing_rule(
        from_instance="kart-interface",
        to_instance="willow-local",
        action_pattern=r"^(read|write|edit|list|build|transcribe|remember|pending|apps).*",
        priority=10
    )

    # Kart -> Claude for complex reasoning (Tier 2)
    add_routing_rule(
        from_instance="kart-interface",
        to_instance="claude-api",
        action_pattern=r"^(refactor|debug|implement|review|escalate|architect|design).*",
        priority=5
    )

    # Willow -> Claude for complex tasks
    add_routing_rule(
        from_instance="willow-local",
        to_instance="claude-api",
        action_pattern=r"^(analyze|explain|generate|refactor).*",
        priority=10
    )

    # Claude -> Human for governance (final authority)
    add_routing_rule(
        from_instance="claude-api",
        to_instance="human-chief",
        action_pattern=r"^(governance|delete|security|money|deploy|publish).*",
        priority=1
    )

    # Willow -> Human for governance
    add_routing_rule(
        from_instance="willow-local",
        to_instance="human-chief",
        action_pattern=r"^(governance|delete|security|money).*",
        priority=1
    )

# =============================================================================
# CLI
# =============================================================================

def main():
    import sys

    if len(sys.argv) < 2:
        print("""
Instance Registry - Trust & Routing Management

Usage:
    python instance_registry.py init           Initialize with defaults
    python instance_registry.py list           List all instances
    python instance_registry.py show <id>      Show instance details
    python instance_registry.py trust <id>     Show trust level
    python instance_registry.py rules          Show routing rules
    python instance_registry.py can <id> <cap> Check capability
""")
        return

    cmd = sys.argv[1]

    if cmd == "init":
        init_db()
        bootstrap_defaults()
        print("Registry initialized with defaults.")
        print(f"Database: {DB_PATH}")

    elif cmd == "list":
        instances = list_instances()
        if not instances:
            print("No instances registered. Run 'init' first.")
            return

        print("\nRegistered Instances:")
        print("-" * 60)
        for inst in instances:
            print(f"  {inst.instance_id}")
            print(f"    Name: {inst.name}")
            print(f"    Type: {inst.instance_type}")
            print(f"    Trust: {inst.trust_name} ({inst.trust_level})")
            print(f"    Escalates: {inst.escalates_to or 'HUMAN'}")
            print()

    elif cmd == "show" and len(sys.argv) > 2:
        instance_id = sys.argv[2]
        inst = get_instance(instance_id)
        if not inst:
            print(f"Instance not found: {instance_id}")
            return

        print(f"\nInstance: {inst.instance_id}")
        print(f"  Name: {inst.name}")
        print(f"  Type: {inst.instance_type}")
        print(f"  Trust Level: {inst.trust_name} ({inst.trust_level})")
        print(f"  Capabilities: {', '.join(inst.capabilities)}")
        print(f"  Escalates To: {inst.escalates_to or 'HUMAN'}")
        print(f"  Created: {inst.created}")
        print(f"  Last Seen: {inst.last_seen}")

    elif cmd == "trust" and len(sys.argv) > 2:
        instance_id = sys.argv[2]
        inst = get_instance(instance_id)
        if not inst:
            print(f"Instance not found: {instance_id}")
            return

        print(f"\n{inst.name} ({inst.instance_id})")
        print(f"  Trust Level: {inst.trust_name}")
        print(f"  Can do: {', '.join(inst.capabilities)}")

    elif cmd == "rules":
        rules = list_routing_rules()
        if not rules:
            print("No routing rules. Run 'init' first.")
            return

        print("\nRouting Rules:")
        print("-" * 60)
        for rule in rules:
            status = "[ON]" if rule.active else "[OFF]"
            ack = "(ack)" if rule.requires_ack else ""
            print(f"  {status} {rule.from_instance} -> {rule.to_instance}")
            print(f"       Pattern: {rule.action_pattern}")
            print(f"       Priority: {rule.priority} {ack}")
            print()

    elif cmd == "can" and len(sys.argv) > 3:
        instance_id = sys.argv[2]
        capability = sys.argv[3]
        result = can_do(instance_id, capability)
        print(f"{instance_id} can '{capability}': {'YES' if result else 'NO'}")

    else:
        print(f"Unknown command: {cmd}")

if __name__ == "__main__":
    main()

"""
test_full_loop.py — The Whole Loop
From a 3x3x3 SQLite seed to the Postgres hulk and back.

Tests the Dual Commit Mobius: agent proposes → store accepts →
Willow (Postgres) receives → agent reads back → knowledge grows.

The strip only turns when both sides touch it.
"""

import json
import math
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

# Setup paths
SANDBOX_DIR = Path(__file__).parent
sys.path.insert(0, str(SANDBOX_DIR))
sys.path.insert(0, str(SANDBOX_DIR.parent))
sys.path.insert(0, str(SANDBOX_DIR.parent / "core"))

from willow_store import WillowStore, angular_action, net_trajectory, PI4, PI2, PI

# Postgres connection
PG_HOST = "172.26.176.1"
PG_PORT = 5437
PG_DB = "willow"
PG_USER = "willow"
PG_PASS = "willow"

passed = 0
failed = 0
skipped = 0


def test(name, fn):
    global passed, failed, skipped
    try:
        result = fn()
        if result is None:
            print(f"  SKIP: {name}")
            skipped += 1
        elif result:
            print(f"  PASS: {name}")
            passed += 1
        else:
            print(f"  FAIL: {name}")
            failed += 1
    except Exception as e:
        print(f"  FAIL: {name} — {e}")
        failed += 1


# ═══════════════════════════════════════════════════════════════════════
# PHASE 1: The Seed (3x3x3 SQLite)
# ═══════════════════════════════════════════════════════════════════════

print("=" * 60)
print("PHASE 1: THE SEED — 3x3x3 SQLite")
print("An empty store. First conversation. First atoms.")
print("=" * 60 + "\n")

SEED_DIR = str(SANDBOX_DIR / "test_seed")
os.system(f"rm -rf {SEED_DIR}")
seed = WillowStore(SEED_DIR)

# 3 domains × 3 temporal × 3 depth = 27 cells (the minimal lattice)
DOMAINS = ["identity", "patterns", "relationships"]
TEMPORALS = ["immediate", "established", "permanent"]
DEPTHS = [1, 3, 5]

# Simulate first conversation: user says hello, system creates first atoms
test("Empty store has zero atoms", lambda: len(seed.all("knowledge/atoms")) == 0)
test("Empty store has zero entities", lambda: len(seed.all("knowledge/entities")) == 0)

# First bite: "What is your first bite today?"
first_atoms = []
a1, act = seed.put("knowledge/atoms", {
    "title": "User introduced themselves",
    "domain": "identity", "temporal": "immediate", "depth": 1,
    "source": "conversation:first",
}, deviation=0.0)
first_atoms.append(a1)

a2, act = seed.put("knowledge/atoms", {
    "title": "User prefers direct communication",
    "domain": "patterns", "temporal": "immediate", "depth": 1,
    "source": "conversation:first",
}, deviation=0.0)
first_atoms.append(a2)

a3, act = seed.put("knowledge/entities", {
    "name": "User", "type": "person",
    "description": "The person talking to Shiva",
}, record_id="user")

seed.add_edge(a1, "user", "about")
seed.add_edge(a2, "user", "pattern_of")

test("First conversation created 2 atoms", lambda: len(seed.all("knowledge/atoms")) == 2)
test("First conversation created 1 entity", lambda: len(seed.all("knowledge/entities")) == 1)
test("First conversation created 2 edges", lambda: len(seed.all("knowledge/edges")) == 2)

# Second conversation: system reads back, user corrects
test("search_all finds user", lambda: len(seed.search_all("User")) >= 1)

# User correction: "I actually prefer to be called Sean"
a4, act = seed.put("knowledge/atoms", {
    "title": "User corrected: name is Sean, not User",
    "domain": "identity", "temporal": "established", "depth": 3,
    "source": "conversation:second",
    "corrects": a1,
}, deviation=PI4)  # significant — name correction

test("Correction flagged (pi/4 deviation)", lambda: act == "flag")

seed.put("knowledge/entities", {
    "name": "Sean", "type": "person",
    "description": "Sean Campbell. Prefers direct communication.",
}, record_id="sean")
seed.add_edge(a4, "sean", "identifies")

# Dual Commit: the correction exists but isn't verified until human ratifies
test("Correction atom exists", lambda: seed.get("knowledge/atoms", a4) is not None)
atom4 = seed.get("knowledge/atoms", a4)
test("Correction has flag action", lambda: atom4["_action"] == "flag")

# Human ratifies by updating verified status
seed.update("knowledge/atoms", a4, {
    "title": "User corrected: name is Sean, not User",
    "domain": "identity", "temporal": "established", "depth": 3,
    "source": "conversation:second",
    "corrects": a1,
    "verified_by": "human",
}, deviation=0.0)  # ratification is quiet

test("Ratification recorded in audit", lambda: any(
    e["operation"] == "update" for e in seed.audit_log("knowledge/atoms", limit=5)
))

# Third conversation: system uses ratified knowledge
results = seed.search_all("Sean")
test("Search finds Sean after ratification", lambda: any(
    r.get("name") == "Sean" or "Sean" in r.get("title", "") for r in results
))

# Stats show the seed growing
stats = seed.stats()
test("Seed has 3 collections with data", lambda: len(stats) >= 3)
test("knowledge/atoms trajectory stable or improving", lambda: stats.get("knowledge/atoms", {}).get("trajectory") in ("stable", "improving"))

print(f"\nSeed stats: {json.dumps(stats, indent=2)}")


# ═══════════════════════════════════════════════════════════════════════
# PHASE 2: The Bridge (SQLite → Postgres)
# ═══════════════════════════════════════════════════════════════════════

print("\n" + "=" * 60)
print("PHASE 2: THE BRIDGE — SQLite seed → Postgres Willow")
print("Agent findings bubble up to the permanent graph.")
print("=" * 60 + "\n")

pg_available = False
try:
    import psycopg2
    conn = psycopg2.connect(
        dbname=PG_DB, user=PG_USER, password=PG_PASS,
        host=PG_HOST, port=PG_PORT, connect_timeout=3
    )
    pg_available = True
    conn.close()
except Exception as e:
    print(f"  Postgres not available: {e}")

if pg_available:
    # Read all atoms from seed
    seed_atoms = seed.all("knowledge/atoms")
    seed_entities = seed.all("knowledge/entities")
    seed_edges = seed.all("knowledge/edges")

    conn = psycopg2.connect(
        dbname=PG_DB, user=PG_USER, password=PG_PASS,
        host=PG_HOST, port=PG_PORT
    )
    conn.autocommit = True
    cur = conn.cursor()

    # Count before
    cur.execute("SELECT count(*) FROM ganesha.atoms")
    atoms_before = cur.fetchone()[0]

    # Translate seed atoms → Postgres
    migrated = 0
    for atom in seed_atoms:
        data = {k: v for k, v in atom.items() if not k.startswith("_")}
        content = json.dumps(data, default=str)
        domain = data.get("domain", "patterns")
        depth = data.get("depth", 1)
        source = data.get("source", "seed-migration")
        cur.execute(
            """INSERT INTO ganesha.atoms (content, source_session, domain, depth, verified_by)
               VALUES (%s, %s, %s, %s, %s)""",
            (content, source, domain, depth, data.get("verified_by", "unverified"))
        )
        migrated += 1

    cur.execute("SELECT count(*) FROM ganesha.atoms")
    atoms_after = cur.fetchone()[0]

    test(f"Migrated {migrated} atoms to Postgres", lambda: atoms_after == atoms_before + migrated)

    # Read back from Postgres to verify
    cur.execute(
        "SELECT content FROM ganesha.atoms WHERE source_session = 'conversation:second' ORDER BY id DESC LIMIT 1"
    )
    row = cur.fetchone()
    if row:
        pg_atom = json.loads(row[0])
        test("Postgres has the correction atom", lambda: "Sean" in pg_atom.get("title", ""))
        test("Correction is human-verified in Postgres", lambda: pg_atom.get("verified_by") == "human")
    else:
        test("Postgres has the correction atom", lambda: False)
        test("Correction is human-verified in Postgres", lambda: False)

    cur.close()
    conn.close()
else:
    test("Postgres migration", lambda: None)
    test("Postgres read-back", lambda: None)


# ═══════════════════════════════════════════════════════════════════════
# PHASE 3: The Hulk (Postgres → SQLite agent)
# ═══════════════════════════════════════════════════════════════════════

print("\n" + "=" * 60)
print("PHASE 3: THE HULK — Postgres Willow → Agent SQLite")
print("Agent boots, pulls context from Willow, works locally.")
print("=" * 60 + "\n")

if pg_available:
    # Simulate agent boot: pull relevant atoms from Postgres into local store
    AGENT_DIR = str(SANDBOX_DIR / "test_agent_ganesha")
    os.system(f"rm -rf {AGENT_DIR}")
    agent = WillowStore(AGENT_DIR)

    conn = psycopg2.connect(
        dbname=PG_DB, user=PG_USER, password=PG_PASS,
        host=PG_HOST, port=PG_PORT
    )
    cur = conn.cursor()

    # Agent asks Willow: "What do you know about Sean?"
    cur.execute(
        "SELECT id, content, domain, depth, verified_by FROM ganesha.atoms WHERE content ILIKE %s LIMIT 10",
        ("%Sean%",)
    )
    sean_atoms = cur.fetchall()

    pulled = 0
    for row in sean_atoms:
        pg_id, content_str, domain, depth, verified = row
        try:
            data = json.loads(content_str)
        except:
            data = {"raw": content_str[:500]}
        data["pg_source_id"] = pg_id
        data["pulled_from"] = "willow_postgres"
        try:
            agent.put("knowledge/atoms", data, deviation=0.0)
            pulled += 1
        except:
            pass  # size limit or collision

    test(f"Agent pulled {pulled} Sean-related atoms from Willow", lambda: pulled > 0)

    # Agent works locally — no Postgres calls needed
    local_results = agent.search_all("Sean")
    test("Agent can search locally for Sean", lambda: len(local_results) > 0)

    # Agent discovers something new
    discovery_id, discovery_act = agent.put("knowledge/atoms", {
        "title": "Sean built a portless server architecture",
        "domain": "patterns", "temporal": "established", "depth": 5,
        "source": "session:test_full_loop",
        "verified_by": "ganesha",
    }, deviation=PI4)
    test("Agent discovery flagged", lambda: discovery_act == "flag")

    # Agent pushes discovery back to Willow
    discovery = agent.get("knowledge/atoms", discovery_id)
    discovery_data = {k: v for k, v in discovery.items() if not k.startswith("_")}

    cur.execute(
        """INSERT INTO ganesha.atoms (content, source_session, domain, depth, verified_by)
           VALUES (%s, %s, %s, %s, %s) RETURNING id""",
        (json.dumps(discovery_data, default=str),
         discovery_data.get("source", ""),
         discovery_data.get("domain", "patterns"),
         discovery_data.get("depth", 1),
         discovery_data.get("verified_by", "ganesha"))
    )
    pg_new_id = cur.fetchone()[0]
    conn.commit()

    test("Discovery pushed to Willow Postgres", lambda: pg_new_id is not None)

    # Verify the round trip: Postgres → Agent → Postgres
    cur.execute("SELECT content FROM ganesha.atoms WHERE id = %s", (pg_new_id,))
    roundtrip = json.loads(cur.fetchone()[0])
    test("Round trip preserved title", lambda: "portless" in roundtrip.get("title", "").lower())
    test("Round trip preserved verified_by", lambda: roundtrip.get("verified_by") == "ganesha")

    cur.close()
    conn.close()
    agent.close()
else:
    test("Agent pull from Willow", lambda: None)
    test("Agent local search", lambda: None)
    test("Agent push to Willow", lambda: None)


# ═══════════════════════════════════════════════════════════════════════
# PHASE 4: The Mobius (Dual Commit across the boundary)
# ═══════════════════════════════════════════════════════════════════════

print("\n" + "=" * 60)
print("PHASE 4: THE MOBIUS — Dual Commit")
print("Neither side acts alone. The strip only turns at the seam.")
print("=" * 60 + "\n")

# Test: AI proposes a major change (deviation = pi → stop)
major_id, major_act = seed.put("knowledge/atoms", {
    "title": "PROPOSAL: Restructure entire knowledge graph to card catalog",
    "domain": "patterns", "temporal": "projected", "depth": 5,
    "status": "proposed",
    "proposer": "ganesha",
}, deviation=PI)

test("Major proposal gets STOP action", lambda: major_act == "stop")
test("Proposal exists but unratified", lambda: seed.get("knowledge/atoms", major_id) is not None)

# Test: Human ratifies
seed.update("knowledge/atoms", major_id, {
    "title": "RATIFIED: Restructure entire knowledge graph to card catalog",
    "domain": "patterns", "temporal": "established", "depth": 5,
    "status": "ratified",
    "proposer": "ganesha",
    "ratified_by": "sean",
    "ratified_at": datetime.now().isoformat(),
}, deviation=0.0)  # ratification is quiet

ratified = seed.get("knowledge/atoms", major_id)
test("Ratified proposal has human stamp", lambda: ratified.get("ratified_by") == "sean")
test("Ratification logged in audit", lambda: any(
    e["record_id"] == major_id and e["operation"] == "update"
    for e in seed.audit_log("knowledge/atoms", limit=5)
))

# Test: AI cannot self-approve (deviation=pi must stop)
test("AI alone cannot bypass stop", lambda: angular_action(PI) == "stop")

# Test: Silence is not approval — unratified proposals stay proposed
unratified_id, _ = seed.put("knowledge/atoms", {
    "title": "PROPOSAL: Delete all handoffs older than 30 days",
    "domain": "patterns", "temporal": "projected", "depth": 3,
    "status": "proposed",
    "proposer": "ganesha",
}, deviation=PI2)

unratified = seed.get("knowledge/atoms", unratified_id)
test("Unratified proposal stays proposed", lambda: unratified.get("status") == "proposed")
test("Silence is not approval", lambda: unratified.get("ratified_by") is None)


# ═══════════════════════════════════════════════════════════════════════
# PHASE 5: The Cascade (retrieval order)
# ═══════════════════════════════════════════════════════════════════════

print("\n" + "=" * 60)
print("PHASE 5: THE CASCADE — Local → Willow → Fleet")
print("Each layer cheaper and faster than the next.")
print("=" * 60 + "\n")

# Simulate the retrieval cascade
def cascade_search(query, agent_store, pg_cur=None):
    """Search local first, then Willow, then report where found."""
    # Layer 1: Agent local
    local = agent_store.search_all(query)
    if local:
        return "local", local

    # Layer 2: Willow Postgres
    if pg_cur:
        pg_cur.execute(
            "SELECT id, content FROM ganesha.atoms WHERE content ILIKE %s LIMIT 5",
            (f"%{query}%",)
        )
        rows = pg_cur.fetchall()
        if rows:
            return "postgres", [{"pg_id": r[0], "content": r[1][:100]} for r in rows]

    # Layer 3: Fleet (simulated — would be llm_router.ask())
    return "fleet", None

# Recreate agent for cascade test
AGENT_DIR2 = str(SANDBOX_DIR / "test_agent_cascade")
os.system(f"rm -rf {AGENT_DIR2}")
cascade_agent = WillowStore(AGENT_DIR2)

# Put one thing locally
cascade_agent.put("knowledge/atoms", {
    "title": "The jingle: If you dont know, go ask Willow",
    "type": "slogan",
})

if pg_available:
    conn = psycopg2.connect(
        dbname=PG_DB, user=PG_USER, password=PG_PASS,
        host=PG_HOST, port=PG_PORT
    )
    cur = conn.cursor()

    # Query that hits LOCAL
    layer, results = cascade_search("jingle", cascade_agent, cur)
    test("'jingle' found at LOCAL layer", lambda: layer == "local")

    # Query that misses local, hits POSTGRES
    layer, results = cascade_search("pigeon.py", cascade_agent, cur)
    test("'pigeon.py' found at POSTGRES layer", lambda: layer == "postgres")

    # Query that misses both, falls to FLEET
    layer, results = cascade_search("xyzzy_nonexistent_99999", cascade_agent, cur)
    test("Nonsense query falls to FLEET layer", lambda: layer == "fleet")

    cur.close()
    conn.close()
else:
    # Local-only cascade
    layer, results = cascade_search("jingle", cascade_agent)
    test("'jingle' found at LOCAL layer", lambda: layer == "local")
    test("Without Postgres, unknown falls to fleet", lambda: cascade_search("unknown", cascade_agent)[0] == "fleet")

cascade_agent.close()


# ═══════════════════════════════════════════════════════════════════════
# PHASE 6: The Trajectory (net system health)
# ═══════════════════════════════════════════════════════════════════════

print("\n" + "=" * 60)
print("PHASE 6: THE TRAJECTORY — Is the system improving?")
print("=" * 60 + "\n")

stats = seed.stats()
print(f"Seed final stats: {json.dumps(stats, indent=2)}")

atoms_stats = stats.get("knowledge/atoms", {})
test("Seed has atoms", lambda: atoms_stats.get("count", 0) > 0)
test("Trajectory is computed", lambda: atoms_stats.get("trajectory") in ("stable", "improving", "degrading"))

# The audit trail tells the full story
audit = seed.audit_log("knowledge/atoms", limit=50)
creates = [e for e in audit if e["operation"] == "create"]
updates = [e for e in audit if e["operation"] == "update"]
deletes = [e for e in audit if e["operation"] == "delete"]
print(f"\nAudit: {len(creates)} creates, {len(updates)} updates, {len(deletes)} deletes")

flags = [e for e in audit if e.get("action") == "flag"]
stops = [e for e in audit if e.get("action") == "stop"]
print(f"Governance: {len(flags)} flagged, {len(stops)} stopped")

test("Audit trail complete", lambda: len(audit) > 0)
test("At least one flag action recorded", lambda: len(flags) > 0)
test("At least one stop action recorded", lambda: len(stops) > 0)

seed.close()

# Cleanup
os.system(f"rm -rf {SEED_DIR}")
os.system(f"rm -rf {AGENT_DIR2}")
if pg_available:
    os.system(f"rm -rf {str(SANDBOX_DIR / 'test_agent_ganesha')}")


# ═══════════════════════════════════════════════════════════════════════
# RESULTS
# ═══════════════════════════════════════════════════════════════════════

print("\n" + "=" * 60)
print(f"RESULTS: {passed} passed, {failed} failed, {skipped} skipped")
print("=" * 60)

if failed == 0:
    print("\nThe whole loop works.")
    print("Seed → conversation → atoms → correction → ratification →")
    print("  Postgres → agent pull → local work → push back → cascade →")
    print("  trajectory. The strip turns.")
else:
    print(f"\n{failed} test(s) need attention.")

print("\nΔΣ=42")

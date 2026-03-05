"""
Willow DB Migration Script
Run with server STOPPED: python migrate.py
Applies all pending schema/data migrations idempotently.
DS=42
"""
import sqlite3
import sys

DB = r"C:\Users\Sean\Documents\GitHub\Willow\artifacts\Sweet-Pea-Rudi19\willow_knowledge.db"

conn = sqlite3.connect(DB, timeout=10)
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA busy_timeout=5000")

print("=== Willow DB Migration ===")
print(f"DB: {DB}")


# ── Migration 1: 3 pending entity merges ─────────────────────────────────────

def merge_entity(conn, keep_id, drop_ids, canonical_name, canonical_type):
    keep_row = conn.execute("SELECT name, mention_count FROM entities WHERE id=?", (keep_id,)).fetchone()
    if not keep_row:
        print(f"  SKIP keep_id={keep_id} not found")
        return 0
    total = keep_row[1]
    merged = 0
    for drop_id in drop_ids:
        drop_row = conn.execute("SELECT name, mention_count FROM entities WHERE id=?", (drop_id,)).fetchone()
        if not drop_row:
            print(f"  SKIP drop_id={drop_id} already gone")
            continue
        total += drop_row[1]
        # Delete direct keep<->drop edges
        conn.execute("DELETE FROM entity_connections WHERE (entity_a_id=? AND entity_b_id=?) OR (entity_a_id=? AND entity_b_id=?)", (keep_id, drop_id, drop_id, keep_id))
        # Delete rows where remapping entity_a_id would collide with an existing (keep_id, b, type)
        conn.execute("""DELETE FROM entity_connections WHERE entity_a_id=? AND EXISTS (
            SELECT 1 FROM entity_connections e2
            WHERE e2.entity_a_id=? AND e2.entity_b_id=entity_connections.entity_b_id
            AND e2.connection_type=entity_connections.connection_type)""", (drop_id, keep_id))
        # Delete rows where remapping entity_b_id would collide with an existing (a, keep_id, type)
        conn.execute("""DELETE FROM entity_connections WHERE entity_b_id=? AND EXISTS (
            SELECT 1 FROM entity_connections e2
            WHERE e2.entity_b_id=? AND e2.entity_a_id=entity_connections.entity_a_id
            AND e2.connection_type=entity_connections.connection_type)""", (drop_id, keep_id))
        conn.execute("UPDATE entity_connections SET entity_a_id=? WHERE entity_a_id=?", (keep_id, drop_id))
        conn.execute("UPDATE entity_connections SET entity_b_id=? WHERE entity_b_id=?", (keep_id, drop_id))
        conn.execute("UPDATE OR IGNORE knowledge_entities SET entity_id=? WHERE entity_id=?", (keep_id, drop_id))
        conn.execute("DELETE FROM knowledge_entities WHERE entity_id=?", (drop_id,))
        conn.execute("DELETE FROM entities WHERE id=?", (drop_id,))
        print(f"  Merged {drop_id} ({drop_row[0]}) -> {keep_id} ({keep_row[0]})")
        merged += 1
    conn.execute("UPDATE entities SET mention_count=?, name=?, entity_type=? WHERE id=?", (total, canonical_name, canonical_type, keep_id))
    return merged

print("\n[1] Entity merges")
pending_merges = [
    (815,  [2613],  "SAFE OS",    "project"),
    (2215, [2884],  "Llama",      "concept"),
    (2412, [962],   "3Dprinting", "community"),
]
total_merged = 0
for args in pending_merges:
    total_merged += merge_entity(conn, *args)

loops = conn.execute("DELETE FROM entity_connections WHERE entity_a_id = entity_b_id").rowcount
before = conn.execute("SELECT COUNT(*) FROM entity_connections").fetchone()[0]
conn.execute("DELETE FROM entity_connections WHERE rowid NOT IN (SELECT MIN(rowid) FROM entity_connections GROUP BY MIN(entity_a_id, entity_b_id), MAX(entity_a_id, entity_b_id), connection_type)")
after = conn.execute("SELECT COUNT(*) FROM entity_connections").fetchone()[0]
print(f"  Merged {total_merged} entities, {loops} loops, {before-after} dup edges removed")


# ── Migration 2: Add domain column ───────────────────────────────────────────

print("\n[2] Add domain column to entities")
cols = [c[1] for c in conn.execute("PRAGMA table_info(entities)").fetchall()]
if "domain" in cols:
    print("  Already exists — skipping")
else:
    conn.execute("ALTER TABLE entities ADD COLUMN domain TEXT DEFAULT 'world'")
    print("  Added domain column (default='world')")


# ── Migration 3: Tag known personal entities ─────────────────────────────────

print("\n[3] Tag personal entities")
personal_ids_query = """
    SELECT id FROM entities WHERE
        (entity_type = 'person' AND name IN (
            'Sean', 'Rudi193', 'Jessi', 'Nico', 'Isaac', 'G', 'L.E.E.',
            'me', 'You', 'Consus', 'suitable_Cicada_3336', 'OnceBittenz',
            '100yearsago', 'Wintervacht', 'IBroughtPower', 'Lay awesomespace2000'
        ))
        OR name IN (
            'Sweet-Pea-Rudi19', 'Rudi193/Kart-Llama', 'Rudi193/Kart',
            'Rudi193/Kart-Hugo'
        )
        OR entity_type IN ('anonymous_mention')
"""
personal_ids = [r[0] for r in conn.execute(personal_ids_query).fetchall()]
if personal_ids:
    placeholders = ",".join("?" * len(personal_ids))
    conn.execute(f"UPDATE entities SET domain='personal' WHERE id IN ({placeholders})", personal_ids)
    print(f"  Tagged {len(personal_ids)} personal entities")

# Tag Willow-self entities
self_names = [
    'Willow', 'SAFE OS', 'die-namic-system', 'die-namic', 'Die-Namic',
    'SAFE', 'gate.py', 'pigeon_daemon', 'Kart', 'Kartikeya', 'Jane',
    'OpAuth', 'agent_engine', 'vine', 'Ganesha',
    'bridge ring', 'source ring', 'continuity ring', 'AIONIC',
    'Aionic Continuity', 'Aionic System', 'dual commit', 'governance',
    'SEED_PACKET', 'context_store', 'llm_router', 'Eyes', 'Social Media Tracker',
    'Vision Board', 'The Auditor', 'Regarding Jane', 'Kart-Llama',
    'Kart-Hugo', 'KART_BOOTSTRAP', 'pigeon', 'watcher', 'atom_extractor',
    'Session-Aware Collaboration System',
]
placeholders = ",".join("?" * len(self_names))
updated = conn.execute(
    f"UPDATE entities SET domain='self' WHERE name IN ({placeholders}) AND domain='world'",
    self_names
).rowcount
print(f"  Tagged {updated} self (Willow-system) entities")


# ── Summary ───────────────────────────────────────────────────────────────────

conn.commit()
print("\n=== Done ===")
counts = conn.execute("SELECT domain, COUNT(*) FROM entities GROUP BY domain ORDER BY COUNT(*) DESC").fetchall()
for domain, count in counts:
    print(f"  {domain or 'NULL'}: {count}")
print(f"  Total entities: {conn.execute('SELECT COUNT(*) FROM entities').fetchone()[0]}")
print(f"  Total connections: {conn.execute('SELECT COUNT(*) FROM entity_connections').fetchone()[0]}")
conn.close()

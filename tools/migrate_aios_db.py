#!/usr/bin/env python3
"""
DB Migration: aios-minimal -> Willow canonical
Merges knowledge and entities from aios-minimal into the canonical Willow DB.

Usage:
    python tools/migrate_aios_db.py            # dry run (default)
    python tools/migrate_aios_db.py --apply    # actually migrate
"""
import sys
import sqlite3
from pathlib import Path
from datetime import datetime

SOURCE = Path(r"C:\Users\Sean\Documents\GitHub\aios-minimal\agents\Sweet-Pea-Rudi19\willow_knowledge.db")
DEST   = Path(r"C:\Users\Sean\Documents\GitHub\Willow\artifacts\Sweet-Pea-Rudi19\willow_knowledge.db")

DRY_RUN = "--apply" not in sys.argv

def migrate():
    if not SOURCE.exists():
        print(f"[FAIL] Source not found: {SOURCE}")
        sys.exit(1)
    if not DEST.exists():
        print(f"[FAIL] Destination not found: {DEST}")
        sys.exit(1)

    mode = "[DRY RUN]" if DRY_RUN else "[APPLY]"
    print(f"{mode} Migrating aios-minimal -> Willow canonical")
    print(f"  Source: {SOURCE} ({SOURCE.stat().st_size // 1024}KB)")
    print(f"  Dest:   {DEST} ({DEST.stat().st_size // 1024}KB)")
    print()

    src = sqlite3.connect(str(SOURCE))
    dst = sqlite3.connect(str(DEST))
    src.row_factory = sqlite3.Row
    dst.row_factory = sqlite3.Row

    # --- KNOWLEDGE ---
    src_knowledge = src.execute("SELECT * FROM knowledge").fetchall()
    print(f"Knowledge rows in source: {len(src_knowledge)}")
    dst_ids = {r[0] for r in dst.execute("SELECT source_id FROM knowledge").fetchall()}
    new_knowledge = [r for r in src_knowledge if r["source_id"] not in dst_ids]
    print(f"  New (not in dest): {len(new_knowledge)}")
    for r in new_knowledge:
        print(f"    - [{r['category']}] {r['title']}")

    if not DRY_RUN and new_knowledge:
        dst.executemany(
            """INSERT OR IGNORE INTO knowledge
               (source_type, source_id, title, summary, content_snippet, category, created_at, ring)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [(r["source_type"], r["source_id"], r["title"], r["summary"],
              r["content_snippet"], r["category"], r["created_at"],
              r["ring"] if "ring" in r.keys() else "source") for r in new_knowledge]
        )
        print(f"  [OK] Inserted {len(new_knowledge)} knowledge rows")

    # --- ENTITIES ---
    src_entities = src.execute("SELECT * FROM entities").fetchall()
    print(f"\nEntities in source: {len(src_entities)}")
    dst_names = {r[0].lower() for r in dst.execute("SELECT name FROM entities").fetchall()}
    new_entities = [r for r in src_entities if r["name"].lower() not in dst_names]
    print(f"  New (not in dest): {len(new_entities)}")
    for r in new_entities:
        print(f"    - [{r['entity_type']}] {r['name']}")

    if not DRY_RUN and new_entities:
        dst.executemany(
            """INSERT OR IGNORE INTO entities (name, entity_type, description, mention_count)
               VALUES (?, ?, ?, ?)""",
            [(r["name"], r["entity_type"], r["description"], r["mention_count"])
             for r in new_entities]
        )
        print(f"  [OK] Inserted {len(new_entities)} entity rows")

    # --- AGENTS --- report only
    src_agents = [r["name"] for r in src.execute("SELECT name FROM agents").fetchall()]
    dst_agents = sorted(r[0] for r in dst.execute("SELECT name FROM agents").fetchall())
    print(f"\nAgents in source: {src_agents}")
    print(f"Agents in dest:   {dst_agents}")
    print("  (agents not migrated — canonical dest already has full 9-agent set)")

    if not DRY_RUN:
        dst.commit()
        print(f"\n[OK] Migration complete at {datetime.now().isoformat()}")
    else:
        print(f"\n[DRY RUN] No changes made. Run with --apply to execute.")

    src.close()
    dst.close()

if __name__ == "__main__":
    migrate()

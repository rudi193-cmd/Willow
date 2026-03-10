#!/usr/bin/env python3
"""
Operation Paperclip Scientist Ingestor
=======================================
Reads the operation_paperclip_genealogy.db and creates:
  - One knowledge atom per scientist
  - One entity (person) per scientist
  - Institution entities (NASA, Marshall, Fort Bliss, etc.)
  - entity_connections: scientist → institution (worked_at)
  - entity_connections: scientist ↔ scientist (co-team, same field)

Run: /home/sean/.willow-venv/bin/python tools/ingest_paperclip.py
"""

import sys
import sqlite3
import hashlib
import logging
from datetime import datetime, UTC
from pathlib import Path

REPO = "/mnt/c/Users/Sean/Documents/GitHub/Willow"
sys.path.insert(0, REPO)

from core.db import get_connection
from core import knowledge as kmod

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("paperclip")

PAPERCLIP_DB = "/mnt/c/Users/Sean/My Drive (rudi193@gmail.com)/Willow/Nest/operation_paperclip_genealogy.db"
WILLOW_DB    = f"{REPO}/artifacts/Sweet-Pea-Rudi19/willow_knowledge.db"
USERNAME     = "Sweet-Pea-Rudi19"

# Known institutions all Paperclip scientists shared
SHARED_INSTITUTIONS = [
    ("Operation Paperclip", "program"),
    ("NASA",                "organization"),
    ("Marshall Space Flight Center", "organization"),
    ("Fort Bliss",          "location"),
    ("White Sands Proving Grounds", "location"),
    ("Peenemünde",          "location"),
]

FIELD_INSTITUTIONS = {
    "Aeronautics and Rocketry": [
        ("Marshall Space Flight Center", "organization"),
        ("NASA",                         "organization"),
    ],
    "Electronics": [
        ("NASA",                         "organization"),
    ],
    "Medicine": [
        ("US Army Chemical Corps",       "organization"),
    ],
    "Material Science": [
        ("NASA",                         "organization"),
    ],
    "Architecture": [
        ("NASA",                         "organization"),
    ],
}


def _hash(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()


def _connect_willow():
    return get_connection()


def _upsert_entity(conn, name: str, etype: str, description: str = None) -> int:
    """Insert or update an entity, return its id."""
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO entities (name, entity_type, description, mention_count) VALUES (?, ?, ?, 1) "
        "ON CONFLICT(name) DO UPDATE SET mention_count = mention_count + 1, "
        "description = COALESCE(excluded.description, entities.description)",
        (name, etype, description)
    )
    return cur.execute("SELECT id FROM entities WHERE name = ?", (name,)).fetchone()[0]


def _add_connection(conn, a_id: int, b_id: int, ctype: str, weight: float = 0.8, source: str = "paperclip_ingest"):
    """Add entity_connection if it doesn't exist."""
    conn.execute(
        """INSERT OR IGNORE INTO entity_connections
           (entity_a_id, entity_b_id, connection_type, weight, source, created_at, confirmed, confidence, source_type)
           VALUES (?, ?, ?, ?, ?, ?, 1, ?, 'structured')""",
        (a_id, b_id, ctype, weight, source, datetime.now(UTC).isoformat(), weight)
    )


def _atom_exists(conn, source_id: str) -> bool:
    return conn.execute(
        "SELECT id FROM knowledge WHERE source_type='paperclip' AND source_id=?", (source_id,)
    ).fetchone() is not None


def ingest_scientists():
    log.info("Loading Paperclip DB...")
    src = sqlite3.connect(PAPERCLIP_DB)
    src.row_factory = sqlite3.Row

    scientists = src.execute("SELECT * FROM scientists ORDER BY id").fetchall()
    log.info(f"Found {len(scientists)} scientists")

    # Ensure Willow schema is ready
    kmod.init_db(USERNAME)
    wdb = _connect_willow()

    # Step 1: Upsert shared institution entities
    log.info("Creating institution entities...")
    inst_ids = {}
    for name, etype in SHARED_INSTITUTIONS:
        inst_ids[name] = _upsert_entity(wdb, name, etype, f"Operation Paperclip associated {etype}")
    wdb.commit()

    # Step 2: Per-scientist: atom + entity + connections
    log.info("Ingesting scientists...")
    scientist_entity_ids = {}  # scientist name -> entity id
    field_buckets = {}         # field -> [entity_ids] for co-team edges

    now = datetime.now(UTC).isoformat()
    skipped = 0
    ingested = 0

    for row in scientists:
        name      = row["full_name"]
        field     = row["field"] or "Unknown"
        spec      = row["specialization"] or ""
        birth     = row["birth_year"]
        death     = row["death_year"]
        affil     = row["nazi_affiliation"] or "unknown"
        wiki      = row["wikipedia_url"] or ""
        notes     = row["notes"] or ""

        source_id = f"paperclip-scientist-{row['id']}"

        # Content text for the knowledge atom
        content = (
            f"Operation Paperclip scientist: {name}\n"
            f"Field: {field}"
            + (f" — {spec}" if spec else "") + "\n"
            + (f"Born: {birth}  " if birth else "")
            + (f"Died: {death}\n" if death else "\n")
            + f"Nazi affiliation: {affil}\n"
            + (f"Wikipedia: {wiki}\n" if wiki else "")
            + (f"Notes: {notes}" if notes else "")
        ).strip()

        summary = (
            f"{name} was a German {field.lower()} specialist brought to the United States "
            f"under Operation Paperclip after World War II."
            + (f" Nazi affiliation: {affil}." if affil and affil != "unknown" else "")
        )

        # --- Knowledge atom ---
        if not _atom_exists(wdb, source_id):
            wdb.execute(
                """INSERT INTO knowledge
                   (source_type, source_id, title, summary, content_snippet, category, ring, created_at)
                   VALUES ('paperclip', ?, ?, ?, ?, 'personal', 'source', ?)""",
                (source_id, name, summary, content[:1000], now)
            )
            k_id = wdb.execute("SELECT id FROM knowledge WHERE source_type='paperclip' AND source_id=?", (source_id,)).fetchone()[0]
            ingested += 1
        else:
            k_id = wdb.execute("SELECT id FROM knowledge WHERE source_type='paperclip' AND source_id=?", (source_id,)).fetchone()[0]
            skipped += 1

        # --- Person entity ---
        description = f"Operation Paperclip scientist, {field}"
        if birth: description += f", b.{birth}"
        if death: description += f"–d.{death}"
        ent_id = _upsert_entity(wdb, name, "person", description)
        scientist_entity_ids[name] = ent_id

        # Link atom ↔ entity
        wdb.execute(
            "INSERT OR IGNORE INTO knowledge_entities (knowledge_id, entity_id) VALUES (?, ?)",
            (k_id, ent_id)
        )

        # --- Scientist → shared institutions ---
        _add_connection(wdb, ent_id, inst_ids["Operation Paperclip"], "member_of", 1.0)
        _add_connection(wdb, ent_id, inst_ids["Fort Bliss"],          "stationed_at", 0.9)
        _add_connection(wdb, ent_id, inst_ids["Peenemünde"],          "worked_at", 0.9)

        # Field-specific institution connections
        for inst_name, _ in FIELD_INSTITUTIONS.get(field, []):
            if inst_name in inst_ids:
                _add_connection(wdb, ent_id, inst_ids[inst_name], "worked_at", 0.8)

        # Bucket for co-team edges
        field_buckets.setdefault(field, []).append(ent_id)

        if ingested % 20 == 0 and ingested > 0:
            wdb.commit()
            log.info(f"  {ingested} ingested, {skipped} skipped...")

    wdb.commit()
    log.info(f"Atoms done: {ingested} new, {skipped} already existed")

    # Step 3: Co-team edges (scientists in the same field worked together)
    log.info("Building co-team edges...")
    edge_count = 0
    for field, ids in field_buckets.items():
        # Connect each scientist to the first N others in their field (avoid N² explosion)
        # For small groups (<= 20): all pairs. For large groups: hub-and-spoke via first member.
        if len(ids) <= 20:
            for i, a in enumerate(ids):
                for b in ids[i+1:]:
                    _add_connection(wdb, a, b, "co-team", 0.6, "paperclip_field_grouping")
                    edge_count += 1
        else:
            hub = ids[0]
            for b in ids[1:]:
                _add_connection(wdb, hub, b, "co-team", 0.5, "paperclip_field_grouping")
                edge_count += 1

    wdb.commit()
    log.info(f"Co-team edges: {edge_count}")

    # Step 4: Connect Operation Paperclip entity to NASA (institutional continuity edge)
    _add_connection(wdb, inst_ids["Operation Paperclip"], inst_ids["NASA"], "became", 1.0, "historical_record")
    _add_connection(wdb, inst_ids["Peenemünde"], inst_ids["Marshall Space Flight Center"], "preceded", 1.0, "historical_record")
    wdb.commit()

    # Final counts
    total_atoms = wdb.execute("SELECT COUNT(*) FROM knowledge WHERE source_type='paperclip'").fetchone()[0]
    total_ents  = wdb.execute("SELECT COUNT(*) FROM entities WHERE source_type IS NULL OR source_type != 'ignore'").fetchone()[0]
    total_edges = wdb.execute("SELECT COUNT(*) FROM entity_connections").fetchone()[0]

    wdb.close()
    src.close()

    log.info("=" * 50)
    log.info(f"Paperclip atoms in knowledge: {total_atoms}")
    log.info(f"Total entities in graph:      {total_ents}")
    log.info(f"Total entity_connections:     {total_edges}")
    log.info("Done.")


if __name__ == "__main__":
    ingest_scientists()

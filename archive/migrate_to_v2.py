"""
migrate_to_v2.py — Willow DB Schema V2 Clean Rebuild + Data Import

Fixes accumulated ALTER TABLE debt by creating a fresh DB with all columns
defined in clean CREATE TABLE statements from the start.

USAGE:
    # Dry run — prints row counts, no writes
    python tools/migrate_to_v2.py

    # Apply — creates v2, verifies counts, swaps in
    python tools/migrate_to_v2.py --apply

Run with Willow server STOPPED.

DS=42
"""

import sys
import sqlite3
import shutil
from pathlib import Path
from datetime import datetime


# ── Paths ─────────────────────────────────────────────────────────────────────

DB_DIR = Path(__file__).parent.parent / "artifacts" / "Sweet-Pea-Rudi19"
SRC_DB = DB_DIR / "willow_knowledge.db"
V2_DB  = DB_DIR / "willow_knowledge_v2.db"

# Tables copied verbatim (FTS virtual tables are excluded — rebuilt from scratch)
COPY_TABLES = [
    "agent_mailbox",
    "agents",
    "anonymous_mentions",
    "cluster_members",
    "conversation_memory",
    "entities",
    "entity_connections",
    "knowledge",
    "knowledge_clusters",
    "knowledge_edges",
    "knowledge_entities",
    "knowledge_gaps",
    "pigeon_droppings",
    "pigeon_errors",
    "willow_state",
]


# ── V2 Schema ─────────────────────────────────────────────────────────────────

V2_DDL = [

    # ── schema_versions (NEW in V2) ───────────────────────────────────────────
    """CREATE TABLE schema_versions (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        version     TEXT NOT NULL,
        description TEXT,
        applied_at  TEXT NOT NULL
    )""",

    # ── knowledge ─────────────────────────────────────────────────────────────
    """CREATE TABLE knowledge (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        source_type     TEXT NOT NULL,
        source_id       TEXT NOT NULL,
        title           TEXT NOT NULL,
        summary         TEXT,
        content_snippet TEXT,
        category        TEXT,
        created_at      TEXT NOT NULL,
        embedding       BLOB,
        ring            TEXT DEFAULT 'bridge',
        ring_override   TEXT,
        lattice_domain  TEXT,
        lattice_type    TEXT,
        lattice_status  TEXT,
        UNIQUE(source_type, source_id)
    )""",

    # ── entities ──────────────────────────────────────────────────────────────
    """CREATE TABLE entities (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        name              TEXT NOT NULL UNIQUE,
        entity_type       TEXT NOT NULL,
        description       TEXT,
        mention_count     INTEGER DEFAULT 1,
        layer             INTEGER DEFAULT 1,
        reference_string  TEXT,
        first_seen        TEXT,
        last_mentioned    TEXT,
        mention_contexts  TEXT,
        emotional_valence REAL DEFAULT 0.0,
        promotion_status  TEXT DEFAULT 'untracked',
        never_promote     INTEGER DEFAULT 0,
        username          TEXT,
        promoted_from     INTEGER,
        domain            TEXT DEFAULT 'world'
    )""",

    # ── entity_connections ────────────────────────────────────────────────────
    """CREATE TABLE entity_connections (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        entity_a_id     INTEGER,
        entity_b_id     INTEGER,
        connection_type TEXT,
        weight          REAL DEFAULT 1.0,
        source          TEXT,
        created_at      TEXT,
        confirmed       INTEGER DEFAULT 0,
        UNIQUE(entity_a_id, entity_b_id, connection_type)
    )""",

    # ── knowledge_entities ────────────────────────────────────────────────────
    """CREATE TABLE knowledge_entities (
        knowledge_id INTEGER REFERENCES knowledge(id),
        entity_id    INTEGER REFERENCES entities(id),
        PRIMARY KEY (knowledge_id, entity_id)
    )""",

    # ── knowledge_edges ───────────────────────────────────────────────────────
    """CREATE TABLE knowledge_edges (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        source_id  INTEGER REFERENCES knowledge(id),
        target_id  INTEGER REFERENCES knowledge(id),
        edge_type  TEXT NOT NULL,
        weight     REAL DEFAULT 1.0,
        canonical  BOOLEAN DEFAULT 0,
        created_at TEXT NOT NULL,
        UNIQUE(source_id, target_id, edge_type)
    )""",

    # ── knowledge_clusters ────────────────────────────────────────────────────
    """CREATE TABLE knowledge_clusters (
        cluster_id INTEGER PRIMARY KEY AUTOINCREMENT,
        label      TEXT NOT NULL,
        method     TEXT NOT NULL,
        canonical  BOOLEAN DEFAULT 0,
        created_at TEXT NOT NULL,
        atom_count INTEGER DEFAULT 0,
        centroid   BLOB
    )""",

    # ── cluster_members ───────────────────────────────────────────────────────
    """CREATE TABLE cluster_members (
        cluster_id   INTEGER REFERENCES knowledge_clusters(cluster_id),
        knowledge_id INTEGER REFERENCES knowledge(id),
        distance     REAL,
        PRIMARY KEY (cluster_id, knowledge_id)
    )""",

    # ── conversation_memory ───────────────────────────────────────────────────
    """CREATE TABLE conversation_memory (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        knowledge_id        INTEGER REFERENCES knowledge(id),
        persona             TEXT,
        user_input          TEXT,
        assistant_response  TEXT,
        coherence_index     REAL,
        delta_e             REAL,
        topics              TEXT,
        created_at          TEXT NOT NULL
    )""",

    # ── knowledge_gaps ────────────────────────────────────────────────────────
    """CREATE TABLE knowledge_gaps (
        id                        INTEGER PRIMARY KEY AUTOINCREMENT,
        query                     TEXT NOT NULL,
        source                    TEXT NOT NULL,
        gap_type                  TEXT NOT NULL,
        entity_name               TEXT,
        times_hit                 INTEGER DEFAULT 1,
        first_seen                TEXT NOT NULL,
        last_seen                 TEXT NOT NULL,
        resolved                  INTEGER DEFAULT 0,
        resolved_by_knowledge_id  INTEGER,
        UNIQUE(query, source)
    )""",

    # ── pigeon_droppings ──────────────────────────────────────────────────────
    """CREATE TABLE pigeon_droppings (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        username      TEXT NOT NULL,
        filename      TEXT NOT NULL,
        original_path TEXT,
        filed_to      TEXT,
        category      TEXT,
        summary       TEXT,
        created_at    TEXT NOT NULL,
        file_hash     TEXT
    )""",

    # ── pigeon_errors ─────────────────────────────────────────────────────────
    """CREATE TABLE pigeon_errors (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        username   TEXT NOT NULL,
        filename   TEXT NOT NULL,
        error      TEXT,
        created_at TEXT NOT NULL
    )""",

    # ── agents ────────────────────────────────────────────────────────────────
    """CREATE TABLE agents (
        name          TEXT PRIMARY KEY,
        display_name  TEXT,
        trust_level   TEXT DEFAULT 'WORKER',
        agent_type    TEXT DEFAULT 'persona',
        profile_path  TEXT,
        registered_at TEXT,
        last_seen     TEXT
    )""",

    # ── agent_mailbox ─────────────────────────────────────────────────────────
    """CREATE TABLE agent_mailbox (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        from_agent TEXT NOT NULL,
        to_agent   TEXT NOT NULL,
        subject    TEXT,
        body       TEXT NOT NULL,
        sent_at    TEXT,
        read_at    TEXT,
        thread_id  TEXT
    )""",

    # ── anonymous_mentions ────────────────────────────────────────────────────
    """CREATE TABLE anonymous_mentions (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        username  TEXT,
        category  TEXT,
        count     INTEGER DEFAULT 0,
        last_seen TEXT,
        UNIQUE(username, category)
    )""",

    # ── willow_state ──────────────────────────────────────────────────────────
    """CREATE TABLE willow_state (
        key    TEXT PRIMARY KEY,
        value  TEXT,
        set_at TEXT
    )""",
]


# ── FTS5 virtual table + triggers ─────────────────────────────────────────────

FTS_DDL = """CREATE VIRTUAL TABLE knowledge_fts USING fts5(
    title, summary, content_snippet, category,
    content='knowledge', content_rowid='id',
    tokenize='porter unicode61'
)"""

FTS_TRIGGERS = [
    """CREATE TRIGGER knowledge_ai AFTER INSERT ON knowledge BEGIN
        INSERT INTO knowledge_fts(rowid, title, summary, content_snippet, category)
        VALUES (new.id, new.title, new.summary, new.content_snippet, new.category);
    END""",

    """CREATE TRIGGER knowledge_ad AFTER DELETE ON knowledge BEGIN
        INSERT INTO knowledge_fts(knowledge_fts, rowid, title, summary, content_snippet, category)
        VALUES ('delete', old.id, old.title, old.summary, old.content_snippet, old.category);
    END""",

    """CREATE TRIGGER knowledge_au AFTER UPDATE ON knowledge BEGIN
        INSERT INTO knowledge_fts(knowledge_fts, rowid, title, summary, content_snippet, category)
        VALUES ('delete', old.id, old.title, old.summary, old.content_snippet, old.category);
        INSERT INTO knowledge_fts(rowid, title, summary, content_snippet, category)
        VALUES (new.id, new.title, new.summary, new.content_snippet, new.category);
    END""",
]


# ── Indexes ───────────────────────────────────────────────────────────────────

INDEXES = [
    # ── Preserved from V1 ────────────────────────────────────────────────────
    "CREATE INDEX idx_mailbox_to ON agent_mailbox(to_agent, read_at)",
    "CREATE INDEX idx_cm_kid ON cluster_members(knowledge_id)",
    "CREATE INDEX idx_knowledge_ring ON knowledge(ring)",
    "CREATE INDEX idx_edges_source ON knowledge_edges(source_id, edge_type)",
    "CREATE INDEX idx_edges_target ON knowledge_edges(target_id, edge_type)",

    # ── New in V2 ─────────────────────────────────────────────────────────────
    "CREATE INDEX idx_entities_username_domain ON entities(username, domain)",
    "CREATE INDEX idx_entities_promotion ON entities(promotion_status)",
    "CREATE INDEX idx_entity_connections_confirmed ON entity_connections(confirmed, entity_a_id)",
    "CREATE INDEX idx_knowledge_created ON knowledge(created_at)",
    "CREATE INDEX idx_knowledge_category ON knowledge(category)",
    "CREATE INDEX idx_pigeon_username_cat ON pigeon_droppings(username, category, created_at)",
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def row_counts(conn: sqlite3.Connection, tables: list[str]) -> dict[str, int]:
    counts = {}
    for t in tables:
        try:
            n = conn.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]
        except Exception:
            n = -1
        counts[t] = n
    return counts


def print_counts(label: str, counts: dict[str, int]):
    sep = "-" * 50
    print(f"\n{sep}")
    print(f"  {label}")
    print(f"{sep}")
    for t, n in sorted(counts.items()):
        print(f"  {t:<35} {n:>8,}")
    print(f"{sep}")
    print(f"  TOTAL: {sum(v for v in counts.values() if v >= 0):,}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    apply = "--apply" in sys.argv

    # ── Sanity checks ─────────────────────────────────────────────────────────
    if not SRC_DB.exists():
        print(f"ERROR: Source DB not found: {SRC_DB}", file=sys.stderr)
        sys.exit(1)

    if V2_DB.exists() and apply:
        print(f"ERROR: V2 DB already exists: {V2_DB}")
        print("Delete it first if you want to re-run.", file=sys.stderr)
        sys.exit(1)

    src = sqlite3.connect(str(SRC_DB))
    src.execute("PRAGMA journal_mode=WAL")

    src_counts = row_counts(src, COPY_TABLES)
    print_counts("SOURCE row counts", src_counts)

    if not apply:
        print("\n[DRY RUN] No files written. Pass --apply to proceed.")
        src.close()
        return

    # ── Build V2 DB ───────────────────────────────────────────────────────────
    print(f"\nCreating {V2_DB} ...")
    v2 = sqlite3.connect(str(V2_DB))
    v2.execute("PRAGMA journal_mode=WAL")
    v2.execute("PRAGMA synchronous=NORMAL")
    v2.execute("PRAGMA foreign_keys=OFF")   # off during bulk load

    # Create all tables
    for ddl in V2_DDL:
        v2.execute(ddl)

    # Insert schema_versions record
    v2.execute(
        "INSERT INTO schema_versions (version, description, applied_at) VALUES (?, ?, ?)",
        ("v2", "v2-clean-schema", datetime.now().isoformat()),
    )

    # Create FTS5 virtual table + triggers
    v2.execute(FTS_DDL)
    for trig in FTS_TRIGGERS:
        v2.execute(trig)

    # Create indexes
    for idx in INDEXES:
        v2.execute(idx)

    v2.commit()

    # ── Bulk copy via ATTACH ───────────────────────────────────────────────────
    print("Copying data via ATTACH ...")
    v2.execute(f"ATTACH DATABASE '{SRC_DB}' AS src")

    for table in COPY_TABLES:
        src_n = src_counts.get(table, 0)
        if src_n == 0:
            print(f"  {table}: 0 rows (skipped)")
            continue
        print(f"  {table}: {src_n:,} rows ...", end=" ", flush=True)
        v2.execute(f"INSERT INTO main.[{table}] SELECT * FROM src.[{table}]")
        v2.commit()
        done = v2.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()[0]
        print(f"done ({done:,})")

    v2.execute("DETACH DATABASE src")

    # ── Verify counts ─────────────────────────────────────────────────────────
    v2_counts = row_counts(v2, COPY_TABLES)
    print_counts("V2 row counts", v2_counts)

    mismatches = []
    for t in COPY_TABLES:
        s = src_counts.get(t, 0)
        d = v2_counts.get(t, 0)
        if s != d:
            mismatches.append((t, s, d))

    if mismatches:
        print("\nMISMATCH DETECTED — aborting and deleting V2 DB:", file=sys.stderr)
        for t, s, d in mismatches:
            print(f"  {t}: src={s} v2={d}", file=sys.stderr)
        v2.close()
        V2_DB.unlink()
        src.close()
        sys.exit(1)

    # ── Rebuild FTS5 ──────────────────────────────────────────────────────────
    print("\nRebuilding FTS5 index ...")
    v2.execute("INSERT INTO knowledge_fts(knowledge_fts) VALUES('rebuild')")
    v2.commit()

    # ── VACUUM ────────────────────────────────────────────────────────────────
    print("Vacuuming V2 DB ...")
    v2.execute("VACUUM")
    v2.close()
    src.close()

    # ── Swap files ────────────────────────────────────────────────────────────
    stamp = datetime.now().strftime("%Y%m%d")
    bak = SRC_DB.with_suffix(f".db.bak.{stamp}")
    print(f"\nSwapping files ...")
    print(f"  {SRC_DB.name}  →  {bak.name}")
    shutil.move(str(SRC_DB), str(bak))
    print(f"  {V2_DB.name}  →  {SRC_DB.name}")
    shutil.move(str(V2_DB), str(SRC_DB))

    # ── Final verification ─────────────────────────────────────────────────────
    print("\nFinal verification on live DB ...")
    final = sqlite3.connect(str(SRC_DB))
    final_counts = row_counts(final, COPY_TABLES)
    sv = final.execute("SELECT * FROM schema_versions").fetchall()
    final.close()

    print_counts("FINAL row counts", final_counts)
    print(f"\n  schema_versions: {sv}")
    print("\n✓ Migration complete. Start Willow and verify /api/health.")


if __name__ == "__main__":
    main()

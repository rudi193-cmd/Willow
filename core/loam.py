"""
Knowledge Accumulation Layer — Willow's Structured Memory

Every document and conversation is training input. Memory lives in
structured context (FTS5-searchable DB), not model weights.

DB: artifacts/{username}/willow_knowledge.db

GOVERNANCE:
- Append-only knowledge ingestion (no deletions)
- LLM summaries via free fleet only (llm_router)
- NULL summaries are valid (backfilled later)
- Entity extraction: regex tier always, LLM tier when available

AUTHOR: Claude + Sean Campbell
VERSION: 1.0
CHECKSUM: DS=42
"""

import os
import re
import json
import logging
from datetime import datetime
from typing import Optional, List, Dict

# --- LLM Router for summaries + entity extraction ---
from core import llm_router


# === KNOWN ENTITIES (Tier 1 regex) ===
# People, projects, concepts the system already knows about.
# Additive: LLM extraction (Tier 2) discovers new ones.
KNOWN_ENTITIES = {
    "person": [
        "Sean Campbell", "Sean", "Christoph", "Kartikeya",
    ],
    "project": [
        "Die-Namic", "UTETY", "SAFE", "ECCR", "Willow",
        "Gateway Momentum", "Mann Convergence",
    ],
    "concept": [
        "governance", "dual commit", "delta E", "ΔE", "coherence",
        "fair exchange", "organic context", "source ring", "bridge ring",
        "continuity ring", "sovereign gate", "homoglyph",
    ],
    "tool": [
        "Ollama", "Gemini", "Claude", "llm_router",
    ],
    "location": [
        "Huntsville", "Albuquerque", "New Mexico", "Alabama",
        "London", "Cricklewood", "North London", "Oxford", "Cambridge",
        "Copenhagen", "Denmark", "Tivoli", "Germany",
        "United States",
        "The Main Hall", "The Living Wing", "The Gate", "The Workshop",
        "The Server Corridor", "The Observatory", "The Lantern Office",
        "The Candlelit Corner", "The Swamp", "Loop Room", "UTETY Campus",
    ],
    "persona": [
        "Gerald", "Oakenscroll", "Riggs", "Hanz", "Nova", "Ada",
        "Alexis", "Ofshield", "Steve", "Shiva", "Kart", "Mitra",
        "Consus", "Jeles", "Binder", "Pigeon",
    ],
}

# Pre-compile regex patterns for entity extraction
_ENTITY_PATTERNS = {}
for etype, names in KNOWN_ENTITIES.items():
    for name in names:
        # Case-insensitive word-boundary match
        _ENTITY_PATTERNS[name] = (re.compile(re.escape(name), re.IGNORECASE), etype)


def _db_path(username: str) -> str:
    """Path to per-user knowledge DB."""
    base = os.path.join(os.getcwd(), "artifacts", username)
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "willow_knowledge.db")


def _connect(username: str):
    import sqlite3 as _sqlite3
    from core.db import get_connection
    conn = get_connection()
    conn.row_factory = _sqlite3.Row  # triggers RealDictCursor in _PgConn
    return conn


def init_db(username: str):
    """No-op — schema managed by pg_schema.sql."""
    return
    conn = _connect(username)
    cur = conn.cursor()

    # --- Schema version tracking ---
    cur.execute("""CREATE TABLE IF NOT EXISTS schema_versions (
        id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        version     TEXT NOT NULL,
        description TEXT,
        applied_at  TEXT NOT NULL
    )""")

    # --- Knowledge atoms (V2: all columns in initial CREATE TABLE) ---
    cur.execute("""CREATE TABLE IF NOT EXISTS knowledge (
        id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
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
    )""")

    # --- FTS5 full-text search ---
    fts_exists = cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='knowledge_fts'"
    ).fetchone()

    if not fts_exists:
        cur.execute("""CREATE VIRTUAL TABLE knowledge_fts USING fts5(
            title, summary, content_snippet, category,
            content='knowledge', content_rowid='id',
            tokenize='porter unicode61'
        )""")

        cur.execute("""CREATE TRIGGER IF NOT EXISTS knowledge_ai AFTER INSERT ON knowledge BEGIN
            INSERT INTO knowledge_fts(rowid, title, summary, content_snippet, category)
            VALUES (new.id, new.title, new.summary, new.content_snippet, new.category);
        END""")

        cur.execute("""CREATE TRIGGER IF NOT EXISTS knowledge_ad AFTER DELETE ON knowledge BEGIN
            INSERT INTO knowledge_fts(knowledge_fts, rowid, title, summary, content_snippet, category)
            VALUES ('delete', old.id, old.title, old.summary, old.content_snippet, old.category);
        END""")

        cur.execute("""CREATE TRIGGER IF NOT EXISTS knowledge_au AFTER UPDATE ON knowledge BEGIN
            INSERT INTO knowledge_fts(knowledge_fts, rowid, title, summary, content_snippet, category)
            VALUES ('delete', old.id, old.title, old.summary, old.content_snippet, old.category);
            INSERT INTO knowledge_fts(rowid, title, summary, content_snippet, category)
            VALUES (new.id, new.title, new.summary, new.content_snippet, new.category);
        END""")

    # --- Entities (V2: all columns in initial CREATE TABLE) ---
    cur.execute("""CREATE TABLE IF NOT EXISTS entities (
        id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
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
    )""")

    # --- Knowledge <-> Entity links ---
    cur.execute("""CREATE TABLE IF NOT EXISTS knowledge_entities (
        knowledge_id INTEGER REFERENCES knowledge(id),
        entity_id    INTEGER REFERENCES entities(id),
        PRIMARY KEY (knowledge_id, entity_id)
    )""")

    # --- Conversation memory ---
    cur.execute("""CREATE TABLE IF NOT EXISTS conversation_memory (
        id                 BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        knowledge_id       INTEGER REFERENCES knowledge(id),
        persona            TEXT,
        user_input         TEXT,
        assistant_response TEXT,
        coherence_index    REAL,
        delta_e            REAL,
        topics             TEXT,
        created_at         TEXT NOT NULL
    )""")

    # --- Knowledge gaps (the loss function) ---
    cur.execute("""CREATE TABLE IF NOT EXISTS knowledge_gaps (
        id                       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        query                    TEXT NOT NULL,
        source                   TEXT NOT NULL,
        gap_type                 TEXT NOT NULL,
        entity_name              TEXT,
        times_hit                INTEGER DEFAULT 1,
        first_seen               TEXT NOT NULL,
        last_seen                TEXT NOT NULL,
        resolved                 INTEGER DEFAULT 0,
        resolved_by_knowledge_id INTEGER,
        UNIQUE(query, source)
    )""")

    # --- Indexes ---
    cur.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_ring ON knowledge(ring)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_created ON knowledge(created_at)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_category ON knowledge(category)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_entities_username_domain ON entities(username, domain)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_entities_promotion ON entities(promotion_status)")

    conn.commit()
    conn.close()


# =========================================================================
# Ring assignment (Möbius topology)
# =========================================================================

SOURCE_CATEGORIES = {"governance", "charter", "hard_stop", "seed", "architecture"}
CONTINUITY_CATEGORIES = {"handoff", "summary", "memory", "journal"}


def _assign_ring(category: str, source_type: str, title: str) -> str:
    """Derive ring position from existing category/source_type fields."""
    if source_type == "conversation":
        return "continuity"
    cat_lower = (category or "").lower()
    if cat_lower in SOURCE_CATEGORIES:
        return "source"
    title_upper = (title or "").upper()
    if any(kw in title_upper for kw in ("GOVERNANCE", "CHARTER", "HARD_STOP", "SEED_PACKET")):
        return "source"
    if cat_lower in CONTINUITY_CATEGORIES:
        return "continuity"
    if any(kw in title_upper for kw in ("HANDOFF", "JOURNAL", "ENTRY_")):
        return "continuity"
    return "bridge"


def get_ring(category: str, source_type: str, title: str, ring_override: Optional[str] = None) -> str:
    """Resolve ring position. Human override takes precedence (Aios Addendum §4)."""
    if ring_override:
        return ring_override
    return _assign_ring(category, source_type, title)


def backfill_rings(username: str) -> int:
    """Assign ring values to existing atoms. Respects ring_override. Returns count updated."""
    init_db(username)
    conn = _connect(username)
    cur = conn.cursor()
    rows = cur.execute(
        "SELECT id, category, source_type, title, ring_override FROM knowledge"
    ).fetchall()
    updated = 0
    for row_id, category, source_type, title, ring_override in rows:
        ring = get_ring(category, source_type, title, ring_override)
        cur.execute("UPDATE knowledge SET ring=? WHERE id=?", (ring, row_id))
        updated += 1
    conn.commit()
    conn.close()
    logging.info(f"KNOWLEDGE: Backfilled rings for {updated} atoms")
    return updated


# =========================================================================
# Entity extraction
# =========================================================================

def _extract_entities_regex(text: str) -> List[Dict]:
    """Tier 1: Extract known entities via regex. Always runs."""
    found = []
    seen = set()
    for name, (pattern, etype) in _ENTITY_PATTERNS.items():
        if pattern.search(text) and name not in seen:
            seen.add(name)
            found.append({"name": name, "type": etype})
    return found


def _extract_entities_llm(text: str) -> List[Dict]:
    """
    Tier 2: Extract entities via LLM fleet. Best-effort.
    Returns list of {name, type} dicts. Empty list on failure.
    """
    prompt = (
        "Extract named entities from this text. Return ONLY a JSON array of objects "
        "with 'name' and 'type' fields. Types: person, project, concept, tool, organization.\n"
        "If no entities found, return [].\n\n"
        f"Text: {text[:1500]}\n\nJSON:"
    )
    try:
        resp = llm_router.ask(prompt, preferred_tier="free")
        if resp and resp.content:
            # Try to parse JSON from response
            content = resp.content.strip()
            # Handle markdown code blocks
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
                content = content.strip()
            entities = json.loads(content)
            if isinstance(entities, list):
                return [e for e in entities if isinstance(e, dict) and "name" in e and "type" in e]
    except (json.JSONDecodeError, Exception) as e:
        logging.debug(f"KNOWLEDGE: LLM entity extraction failed: {e}")
    return []


# Canonical entity types — fleet models get normalized to these on ingestion
_CANONICAL_TYPES = {
    "concept", "project", "tool", "person", "organization",
    "persona", "location", "date", "platform", "event", "community",
    "credential",
}

_TYPE_NORMALIZE = {
    "organizaiton": "organization", "concepts": "concept",
    "tool/concept": "tool", "tool/file": "tool", "tool/command": "tool",
    "tool/person": "person", "tool/session_id/task_id": "tool",
    "tool/organization/project": "tool", "project/concept": "project",
    "project/tool": "project", "concept/project": "project",
    "concept/tool": "tool", "platform/tool": "platform",
    "location/concept": "location", "organization/project": "organization",
    "organization/person": "person", "organization/medium": "organization",
    "person/concept/project": "person", "geographic location": "location",
    "geolocation": "location", "program": "tool", "library": "tool",
    "endpoint": "tool", "system": "tool", "repository": "project",
    "work": "project", "document": "concept", "book": "concept",
    "statement": "concept", "abbreviation": "concept", "attribute": "concept",
    "commit": "concept", "no type found": "concept", "table": "concept",
    "unknown": "concept", "company": "organization", "place": "location",
    "type": "concept", "character": "persona", "agent": "persona",
    "key": "credential", "variable": "concept", "class": "concept",
    "function": "concept", "file": "concept", "session_id": "concept",
    "timestamp": "date",
}


def _normalize_entity_type(raw: str) -> str:
    """Normalize fleet-generated entity types to canonical set."""
    t = raw.strip().lower()
    # Check explicit map first
    if t in _TYPE_NORMALIZE:
        return _TYPE_NORMALIZE[t]
    # Check if already canonical (case-insensitive)
    for canon in _CANONICAL_TYPES:
        if t == canon:
            return canon
    # Compound type — take first segment
    if "/" in t:
        first = t.split("/")[0].strip()
        for canon in _CANONICAL_TYPES:
            if first == canon:
                return canon
    # Unknown — default to concept
    return "concept"


_CHROME_ENTITY_PATTERNS = [
    re.compile(r"https?://"),                          # URLs
    re.compile(r"\.(com|org|io|net|dev)$"),             # Domain suffixes
    re.compile(r"^localhost:\d+"),                      # Local dev URLs
    re.compile(r"^\d+$"),                              # Pure numbers
    re.compile(r"^\d{4}-\d{2}-\d{2}"),                 # Date strings (2026-03-02)
    re.compile(r"^\d+\.\d+"),                          # Timestamps / version numbers
    re.compile(r"^.{1,2}$"),                           # 1-2 char entities (R, D)
    re.compile(r"^(dash|www\.)\S+", re.IGNORECASE),    # Dashboard/www prefixes
    re.compile(r"^[/\\]"),                             # File paths (/handoff, C:\...)
    re.compile(r"^[A-Z]:\\"),                          # Windows paths
    # Claude Code tool names — these are tool invocations, not real entities
    re.compile(r"^(Read|Write|Edit|Bash|Grep|Glob|Agent|Skill|"
               r"TaskOutput|TaskCreate|TaskUpdate|TaskStop|TaskList|TaskGet|"
               r"WebFetch|WebSearch|NotebookEdit|AskUserQuestion|"
               r"ToolSearch|ExitPlanMode|EnterPlanMode|CronCreate|CronDelete|CronList|"
               r"SESSION_HANDOFF|SESSION_META|LAST_USER_MESSAGES|HARD STOPS)$"),
]

# Entities that match chrome patterns but are actually legitimate.
# Updated as false positives are discovered.
_CHROME_ENTITY_ALLOWLIST = {
    "Ru", "AI", "ΔE", "ΔΣ", "ξ", "δ", "ℏ",  # Real names / math symbols
}


def _is_chrome_name(name: str) -> bool:
    """Heuristic: does this entity name look like browser chrome / OCR garbage?"""
    if name in _CHROME_ENTITY_ALLOWLIST:
        return False
    return any(p.search(name) for p in _CHROME_ENTITY_PATTERNS)


def _upsert_entities(conn, knowledge_id: int, entities: List[Dict],
                     context_tags: dict = None):
    """
    Insert/update entities and link them to a knowledge atom.
    Chrome-context entities get never_promote=1 + confidence='chrome'.
    Crown witnesses chrome flagging events.
    """
    cur = conn.cursor()
    chrome_ratio = (context_tags or {}).get("chrome_ratio", 0.0)
    username = (context_tags or {}).get("username", "Sweet-Pea-Rudi19")

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    for ent in entities:
        name = ent["name"]
        etype = _normalize_entity_type(ent.get("type", "concept"))

        is_chrome_entity = (
            chrome_ratio > 0.5
            or _is_chrome_name(name)
            or ent.get("context") == "chrome"
        )

        if is_chrome_entity:
            cur.execute(
                "INSERT INTO entities (name, entity_type, mention_count, never_promote, "
                "first_seen, last_mentioned) "
                "VALUES (?, ?, 1, 1, ?, ?) "
                "ON CONFLICT(name) DO UPDATE SET "
                "mention_count = entities.mention_count + 1, last_mentioned = ?",
                (name, etype, now, now, now)
            )
            # Crown witness: entity born as chrome (tamper-evident timestamp)
            try:
                from core.crown import witness_entity_event
                witness_entity_event(
                    "entity_chrome_flagged", name, agent="loam",
                    username=username,
                    details={
                        "chrome_ratio": chrome_ratio,
                        "entity_type": etype,
                        "flagged_at": now,
                    },
                    conn=conn,
                )
            except Exception:
                pass  # Crown unavailable — don't block ingestion
        else:
            cur.execute(
                "INSERT INTO entities (name, entity_type, mention_count, "
                "first_seen, last_mentioned) "
                "VALUES (?, ?, 1, ?, ?) "
                "ON CONFLICT(name) DO UPDATE SET "
                "mention_count = entities.mention_count + 1, last_mentioned = ?",
                (name, etype, now, now, now)
            )

        row = cur.execute("SELECT id FROM entities WHERE name = ?", (name,)).fetchone()
        if not row:
            continue
        entity_id = row[0]

        # Link to knowledge atom (always — chrome entities still linked for traceability)
        cur.execute(
            "INSERT OR IGNORE INTO knowledge_entities (knowledge_id, entity_id) VALUES (?, ?)",
            (knowledge_id, entity_id)
        )


# =========================================================================
# Entity Promotion Pipeline
# =========================================================================

# Insight Layer mapping (PRODUCT_SPEC lines 147-160):
#   Layer 1 = anonymous ("147 items captured")
#   Layer 2 = pseudonymous ("You keep saving mid-century furniture")
#   Layer 3 = named ("Dream Kitchen board created") — human ratified
PROMOTION_MIN_MENTIONS = 5
PROMOTION_MIN_CATEGORIES = 2


def promote_entities(username: str = "Sweet-Pea-Rudi19",
                     dry_run: bool = True) -> dict:
    """
    Automatic promotion: layer 1 → 2 based on evidence thresholds.
    Layer 2 → 3 requires human ratification (not done here).

    Governance: 1→2 is pattern detection (PRODUCT_SPEC "pseudonymous/detected").
    Crown witnesses every promotion for tamper-evident audit.

    Returns: {promoted: [{name, mentions, categories}], skipped: int}
    """
    conn = _connect(username)
    # Clear any inherited dirty transaction state from pool
    try:
        conn.rollback()
    except Exception:
        pass
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        # Find layer-1 entities that meet promotion thresholds
        candidates = conn.execute(
            """SELECT e.id, e.name, e.entity_type, e.mention_count,
                      COUNT(DISTINCT k.category) as cat_count
               FROM entities e
               JOIN knowledge_entities ke ON ke.entity_id = e.id
               JOIN knowledge k ON k.id = ke.knowledge_id
               WHERE e.layer = 1
                 AND e.never_promote = 0
                 AND e.mention_count >= ?
               GROUP BY e.id, e.name, e.entity_type, e.mention_count
               HAVING COUNT(DISTINCT k.category) >= ?""",
            (PROMOTION_MIN_MENTIONS, PROMOTION_MIN_CATEGORIES)
        ).fetchall()

        promoted = []
        for row in candidates:
            eid = row["id"] if isinstance(row, dict) else row[0]
            name = row["name"] if isinstance(row, dict) else row[1]
            etype = row["entity_type"] if isinstance(row, dict) else row[2]
            mentions = row["mention_count"] if isinstance(row, dict) else row[3]
            cats = row["cat_count"] if isinstance(row, dict) else row[4]
            if not dry_run:
                conn.execute(
                    "UPDATE entities SET layer = 2, promotion_status = 'auto_promoted', "
                    "last_mentioned = ? WHERE id = ?",
                    (now, eid)
                )
                # Crown witness: promotion event
                try:
                    from core.crown import witness_entity_event
                    witness_entity_event(
                        "entity_promoted_1_2", name, agent="loam",
                        username=username,
                        details={
                            "mention_count": mentions,
                            "category_spread": cats,
                            "promoted_at": now,
                        },
                        conn=conn,
                    )
                except Exception:
                    pass
            promoted.append({
                "name": name, "type": etype,
                "mentions": mentions, "categories": cats,
            })

        if not dry_run:
            conn.commit()

        skip_row = conn.execute(
            "SELECT COUNT(*) as cnt FROM entities WHERE layer = 1 AND never_promote = 1"
        ).fetchone()
        skipped = skip_row["cnt"] if isinstance(skip_row, dict) else skip_row[0]

        logging.info(
            f"PROMOTE: {'[DRY RUN] ' if dry_run else ''}"
            f"{len(promoted)} promoted, {skipped} chrome/blocked"
        )
        return {"promoted": promoted, "skipped": skipped, "dry_run": dry_run}
    finally:
        conn.close()


# =========================================================================
# Ingestion
# =========================================================================

def ingest_file_knowledge(
    username: str,
    filename: str,
    file_hash: str,
    category: str,
    content_text: str,
    provider: str = "unknown",
    context_tags: dict = None,
):
    """
    Ingest a processed file into the knowledge DB.

    - Generates summary via free LLM fleet (NULL if unavailable)
    - Extracts entities (regex always, LLM when available)
    - Stores content_snippet (first 1000 chars)
    - Idempotent on (source_type, source_id) = ('file', file_hash)
    """
    init_db(username)

    # --- All fleet calls BEFORE opening the DB connection ---
    # This ensures the write transaction is never held open during slow I/O.

    # Content snippet (first 1000 chars, strip IMAGE:/TEXT: prefixes)
    snippet = content_text
    for prefix in ("IMAGE: ", "TEXT: "):
        if snippet.startswith(prefix):
            snippet = snippet[len(prefix):]
    snippet = snippet[:1000]

    # Generate summary via free fleet (best-effort, no DB connection open)
    summary = None
    try:
        summary_prompt = (
            f"Summarize this document in 2-3 sentences. Focus on what it IS and what it's about.\n\n"
            f"Title: {filename}\nCategory: {category}\n\n"
            f"Content:\n{snippet}\n\nSummary:"
        )
        resp = llm_router.ask(summary_prompt, preferred_tier="free")
        if resp and resp.content:
            summary = resp.content.strip()[:500]
    except Exception as e:
        logging.debug(f"KNOWLEDGE: Summary generation failed for {filename}: {e}")

    # Entity extraction via fleet (best-effort, no DB connection open)
    entities = _extract_entities_regex(f"{filename} {snippet}")
    llm_entities = _extract_entities_llm(snippet)
    seen_names = {e["name"].lower() for e in entities}
    for le in llm_entities:
        if le["name"].lower() not in seen_names:
            entities.append(le)
            seen_names.add(le["name"].lower())

    # Pre-compute embedding BEFORE opening DB (lazy model load can take 10-30s on first call)
    embed_vec = None
    try:
        from core import embeddings
        if embeddings.is_available():
            embed_text = f"{filename} {snippet}"[:512]
            embed_vec = embeddings.embed(embed_text)
    except Exception:
        pass

    # --- DB transaction: fast writes only, no slow I/O inside ---
    conn = _connect(username)
    try:
        cur = conn.cursor()

        # Check if already ingested — if so, recover entities in case they failed before
        existing = cur.execute(
            "SELECT id FROM knowledge WHERE source_type='file' AND source_id=?",
            (file_hash,)
        ).fetchone()
        if existing:
            knowledge_id = existing[0]
            if entities:
                tags = dict(context_tags or {})
                tags.setdefault("username", username)
                _upsert_entities(conn, knowledge_id, entities, context_tags=tags)
            conn.commit()
            return

        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        ring = get_ring(category, "file", filename)
        cur.execute(
            """INSERT OR IGNORE INTO knowledge
               (source_type, source_id, title, summary, content_snippet, category, ring, created_at)
               VALUES ('file', ?, ?, ?, ?, ?, ?, ?)""",
            (file_hash, filename, summary, snippet, category, ring, now)
        )
        knowledge_id = cur.lastrowid

        if knowledge_id:
            tags = dict(context_tags or {})
            tags.setdefault("username", username)
            _upsert_entities(conn, knowledge_id, entities, context_tags=tags)
            if embed_vec:
                conn.execute("UPDATE knowledge SET embedding=? WHERE id=?", (embed_vec, knowledge_id))

        conn.commit()
        logging.info(f"KNOWLEDGE: Ingested file '{filename}' (summary={'yes' if summary else 'backfill'})")
    except Exception as e:
        logging.warning(f"KNOWLEDGE: ingest_file_knowledge failed for '{filename}': {e}")
        raise
    finally:
        conn.close()


def ingest_conversation(
    username: str,
    persona: str,
    user_input: str,
    assistant_response: str,
    coherence_metrics: Optional[Dict] = None,
):
    """
    Ingest a conversation turn into the knowledge DB.

    - Creates knowledge atom for the exchange
    - Stores structured conversation_memory row
    - Extracts entities from both user input and response
    """
    init_db(username)
    conn = _connect(username)
    cur = conn.cursor()

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    source_id = f"conv_{now.replace(' ', '_').replace(':', '')}"

    # Title from first ~60 chars of user input
    title = user_input[:60].strip()
    if len(user_input) > 60:
        title += "..."

    # Snippet: user input + truncated response
    snippet = f"User: {user_input[:400]}\n{persona}: {assistant_response[:600]}"

    # Insert knowledge atom
    cur.execute(
        """INSERT OR IGNORE INTO knowledge
           (source_type, source_id, title, summary, content_snippet, category, created_at)
           VALUES ('conversation', ?, ?, NULL, ?, 'conversation', ?)""",
        (source_id, title, snippet, now)
    )
    knowledge_id = cur.lastrowid

    if not knowledge_id:
        conn.close()
        return

    # Coherence metrics
    ci = 0.0
    de = 0.0
    if coherence_metrics:
        ci = coherence_metrics.get("coherence_index", 0.0)
        de = coherence_metrics.get("delta_e", 0.0)

    # Extract topics from user input
    topics = _extract_topics_simple(user_input)

    # Insert conversation memory
    cur.execute(
        """INSERT INTO conversation_memory
           (knowledge_id, persona, user_input, assistant_response,
            coherence_index, delta_e, topics, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (knowledge_id, persona, user_input, assistant_response,
         ci, de, json.dumps(topics), now)
    )

    # Entity extraction from combined text
    combined = f"{user_input} {assistant_response}"
    entities = _extract_entities_regex(combined)
    _upsert_entities(conn, knowledge_id, entities)

    # Compute embedding (best-effort)
    try:
        from core import embeddings
        if embeddings.is_available():
            embed_text = f"{title} {user_input[:300]}"[:512]
            vec = embeddings.embed(embed_text)
            if vec:
                conn.execute("UPDATE knowledge SET embedding=? WHERE id=?", (vec, knowledge_id))
    except Exception:
        pass

    conn.commit()
    conn.close()
    logging.debug(f"KNOWLEDGE: Ingested conversation ({persona}, {len(user_input)}c)")


def _extract_topics_simple(text: str, max_topics: int = 5) -> List[str]:
    """Extract topic keywords from text (lightweight, no LLM)."""
    STOP = {
        "a", "an", "the", "is", "are", "was", "were", "be", "been",
        "have", "has", "had", "do", "does", "did", "will", "would",
        "could", "should", "may", "might", "can", "to", "of", "in",
        "for", "on", "with", "at", "by", "from", "as", "into",
        "and", "but", "if", "or", "not", "so", "just", "that",
        "this", "what", "which", "who", "how", "when", "where",
        "i", "me", "my", "we", "you", "your", "he", "she", "it",
        "they", "them", "their", "about", "like", "yeah", "yes",
        "no", "ok", "okay", "please", "thanks", "hi", "hello",
    }
    words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
    topics = []
    seen = set()
    for w in words:
        if w not in STOP and w not in seen:
            seen.add(w)
            topics.append(w)
            if len(topics) >= max_topics:
                break
    return topics


# =========================================================================
# Search
# =========================================================================

def search(username: str, query: str, max_results: int = 10) -> List[Dict]:
    """
    FTS5 BM25-ranked search over all loam.

    Returns list of dicts with: id, source_type, title, summary,
    content_snippet, category, rank, entities.
    """
    init_db(username)
    conn = _connect(username)
    cur = conn.cursor()

    # FTS5 match query — escape special chars for safety
    fts_query = re.sub(r'[^\w\s]', '', query).strip()
    if not fts_query:
        conn.close()
        return []

    # Split into terms and join with OR for broader matching
    terms = fts_query.split()
    fts_expr = " OR ".join(terms)

    from core.db import is_postgres as _is_pg
    if _is_pg():
        # PostgreSQL: use tsvector search_vector column (maintained by trigger in pg_schema.sql)
        try:
            rows = cur.execute("""
                SELECT id, source_type, title, summary,
                       content_snippet, category, created_at,
                       0 as rank
                FROM knowledge
                WHERE search_vector @@ plainto_tsquery('english', %s)
                ORDER BY ts_rank(search_vector, plainto_tsquery('english', %s)) DESC
                LIMIT %s
            """, (query, query, max_results)).fetchall()
        except Exception:
            conn._conn.rollback()
            rows = []

        # Fallback: if FTS returned nothing, try ILIKE on each term (handles nicknames, partial names)
        if not rows:
            _terms = [t for t in fts_query.split() if len(t) >= 3]
            if _terms:
                # Match any term in title/summary/content (OR logic)
                _clauses = []
                _params = []
                for t in _terms:
                    _clauses.append("(title ILIKE %s OR summary ILIKE %s OR content_snippet ILIKE %s)")
                    _params.extend([f"%{t}%", f"%{t}%", f"%{t}%"])
                try:
                    rows = cur.execute(f"""
                        SELECT id, source_type, title, summary,
                               content_snippet, category, created_at,
                               0 as rank
                        FROM knowledge
                        WHERE {' OR '.join(_clauses)}
                        ORDER BY created_at DESC
                        LIMIT %s
                    """, (*_params, max_results)).fetchall()
                except Exception:
                    conn._conn.rollback()
                    rows = []
    else:
        try:
            rows = cur.execute("""
                SELECT k.id, k.source_type, k.title, k.summary,
                       k.content_snippet, k.category, k.created_at,
                       rank
                FROM knowledge_fts
                JOIN knowledge k ON k.id = knowledge_fts.rowid
                WHERE knowledge_fts MATCH ?
                ORDER BY rank
                LIMIT ?
            """, (fts_expr, max_results)).fetchall()
        except Exception:
            # FTS match syntax error — fall back to simple LIKE
            rows = cur.execute("""
                SELECT id, source_type, title, summary,
                       content_snippet, category, created_at,
                       0 as rank
                FROM knowledge
                WHERE title LIKE ? OR summary LIKE ? OR content_snippet LIKE ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (f"%{query}%", f"%{query}%", f"%{query}%", max_results)).fetchall()

    results = []
    for row in rows:
        kid = row["id"]
        # Fetch linked entities
        ents = cur.execute("""
            SELECT e.name, e.entity_type
            FROM entities e
            JOIN knowledge_entities ke ON ke.entity_id = e.id
            WHERE ke.knowledge_id = ?
        """, (kid,)).fetchall()

        results.append({
            "id": kid,
            "source_type": row["source_type"],
            "title": row["title"],
            "summary": row["summary"],
            "content_snippet": row["content_snippet"],
            "category": row["category"],
            "created_at": row["created_at"],
            "rank": row["rank"],
            "entities": [{"name": e["name"], "type": e["entity_type"]} for e in ents],
        })

    conn.close()

    # Record gap if no results found
    if not results:
        record_gap(username, query, "search", "zero_results")

    return results


def build_knowledge_context(username: str, query: str, max_chars: int = 3000) -> str:
    """
    Build a formatted knowledge context block for system prompt injection.

    Combines:
    - FTS5 search results (ranked)
    - Entity mentions
    - Recent conversation memory

    Returns formatted string ready for prompt injection.
    Falls back to empty string if no results.
    """
    parts = []
    total_len = 0

    # 1. FTS5 search results (fall back to semantic if sparse)
    results = search(username, query, max_results=5)
    if len(results) < 2:
        sem_results = semantic_search(username, query, max_results=5)
        if sem_results:
            results = sem_results
    if results:
        parts.append("## RETRIEVED CONTEXT (from knowledge base)")
        for r in results:
            if total_len >= max_chars:
                break
            entry_parts = [f"\n**{r['title']}** ({r['source_type']}, {r['category']})"]
            if r["summary"]:
                entry_parts.append(f"Summary: {r['summary']}")
            elif r["content_snippet"]:
                entry_parts.append(r["content_snippet"][:300])
            if r["entities"]:
                ent_str = ", ".join(f"{e['name']} ({e['type']})" for e in r["entities"][:5])
                entry_parts.append(f"Entities: {ent_str}")
            entry = "\n".join(entry_parts)
            parts.append(entry)
            total_len += len(entry)

    # 2. Recent relevant conversations
    init_db(username)
    conn = _connect(username)
    # row_factory set in _connect() → RealDictCursor
    try:
        convos = conn.execute("""
            SELECT persona, user_input, assistant_response, delta_e, created_at
            FROM conversation_memory
            ORDER BY created_at DESC
            LIMIT 3
        """).fetchall()
        if convos and total_len < max_chars:
            parts.append("\n## RECENT CONVERSATIONS")
            for c in convos:
                if total_len >= max_chars:
                    break
                entry = (
                    f"\n[{c['created_at']}] {c['persona']}\n"
                    f"User: {c['user_input'][:150]}\n"
                    f"Response: {c['assistant_response'][:150]}"
                )
                parts.append(entry)
                total_len += len(entry)
    except Exception:
        pass
    finally:
        conn.close()

    # 3. Top entities by mention count
    if total_len < max_chars:
        conn = _connect(username)
        # row_factory set in _connect() → RealDictCursor
        try:
            top_ents = conn.execute("""
                SELECT name, entity_type, mention_count
                FROM entities
                ORDER BY mention_count DESC
                LIMIT 10
            """).fetchall()
            if top_ents:
                ent_line = ", ".join(f"{e['name']}({e['mention_count']})" for e in top_ents)
                parts.append(f"\n## KEY ENTITIES: {ent_line}")
        except Exception:
            pass
        finally:
            conn.close()

    return "\n".join(parts) if parts else ""


# =========================================================================
# Backfill
# =========================================================================

def backfill_summaries(username: str, batch_size: int = 5):
    """
    Fill NULL summaries via LLM fleet. Called periodically.
    Non-blocking — processes batch_size rows per call.
    """
    init_db(username)

    # Read rows — short-lived connection, close BEFORE fleet calls
    conn = _connect(username)
    rows = conn.execute(
        "SELECT id, title, content_snippet, category FROM knowledge WHERE summary IS NULL LIMIT ?",
        (batch_size,)
    ).fetchall()
    conn.close()

    if not rows:
        return

    # Fleet calls outside DB connection (each takes 10-60s)
    updates = []
    def _backfill_one(item):
        row_id, title, snippet, category = item
        if not snippet:
            return ""  # truthy-ish skip, not a fleet failure
        prompt = (
            f"Summarize this document in 2-3 sentences.\n\n"
            f"Title: {title}\nCategory: {category}\n\n"
            f"Content:\n{snippet}\n\nSummary:"
        )
        resp = llm_router.ask(prompt, preferred_tier="free")
        if resp and resp.content:
            return resp.content.strip()[:500]
        return None  # signals retry

    try:
        from core.fleet_retry import fleet_batch

        def _on_save(results):
            _updates = [(res, item[0]) for item, res in results if res]
            if _updates:
                c = _connect(username)
                c.executemany("UPDATE knowledge SET summary=? WHERE id=?", _updates)
                c.commit()
                c.close()

        completed = fleet_batch(
            list(rows), _backfill_one,
            max_retries=5, delay=1.5,
            save_every=25, on_save=_on_save,
        )
        updates = [(res, item[0]) for item, res in completed if res]
    except ImportError:
        for row_id, title, snippet, category in rows:
            if not snippet:
                continue
            try:
                prompt = (
                    f"Summarize this document in 2-3 sentences.\n\n"
                    f"Title: {title}\nCategory: {category}\n\n"
                    f"Content:\n{snippet}\n\nSummary:"
                )
                resp = llm_router.ask(prompt, preferred_tier="free")
                if resp and resp.content:
                    updates.append((resp.content.strip()[:500], row_id))
            except Exception as e:
                logging.info(f"KNOWLEDGE: Backfill failed for id={row_id}: {e}")
                continue  # keep going, don't break

    # Fast batch write — no slow I/O inside
    if updates:
        conn = _connect(username)
        conn.executemany("UPDATE knowledge SET summary=? WHERE id=?", updates)
        conn.commit()
        conn.close()
        logging.info(f"KNOWLEDGE: Backfilled {len(updates)}/{len(rows)} summaries for {username}")


# =========================================================================
# Gap Detection (the loss function)
# =========================================================================

def record_gap(username: str, query: str, source: str, gap_type: str, entity_name: str = None):
    """
    Record something the system doesn't know.
    Idempotent on (query, source) — increments times_hit on repeat.
    """
    init_db(username)
    conn = _connect(username)
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    # Normalize query for dedup
    norm_query = query.strip().lower()[:200]
    try:
        conn.execute(
            """INSERT INTO knowledge_gaps (query, source, gap_type, entity_name, first_seen, last_seen)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(query, source) DO UPDATE SET
                   times_hit = knowledge_gaps.times_hit + 1,
                   last_seen = ?""",
            (norm_query, source, gap_type, entity_name, now, now, now)
        )
        conn.commit()
    except Exception as e:
        logging.debug(f"KNOWLEDGE GAP: record failed: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
    finally:
        conn.close()
    logging.debug(f"KNOWLEDGE GAP: '{norm_query}' ({gap_type}) from {source}")


def get_top_gaps(username: str, limit: int = 10) -> List[Dict]:
    """Return the most frequently hit knowledge gaps."""
    init_db(username)
    conn = _connect(username)
    # row_factory set in _connect() → RealDictCursor
    rows = conn.execute(
        """SELECT query, source, gap_type, entity_name, times_hit, first_seen, last_seen
           FROM knowledge_gaps
           WHERE resolved = 0
           ORDER BY times_hit DESC
           LIMIT ?""",
        (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def resolve_gap(username: str, query: str, source: str, knowledge_id: int):
    """Mark a gap as resolved when knowledge is later ingested."""
    init_db(username)
    conn = _connect(username)
    norm_query = query.strip().lower()[:200]
    conn.execute(
        """UPDATE knowledge_gaps SET resolved = 1, resolved_by_knowledge_id = ?
           WHERE query = ? AND source = ?""",
        (knowledge_id, norm_query, source)
    )
    conn.commit()
    conn.close()


# =========================================================================
# ΔΣ Gap Layer — Acknowledged Unknowns as First-Class Data
# ΔΣ = Σ(Δᵢ) = 42 — the sum of what we know we don't know
# =========================================================================

def register_atom_gap(username: str, knowledge_id: int, gap_text: str,
                      gap_type: str, registered_by: str, specificity: float = 0.5) -> dict:
    """Register an acknowledged unknown on a knowledge atom. Crown-witnessed."""
    conn = _connect(username)
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    witness_id = None
    try:
        from core import crown
        witness_id = crown.witness_entity_event(
            "gap_registered", f"atom:{knowledge_id}",
            agent=registered_by, username=username,
            details={"gap_text": gap_text, "gap_type": gap_type,
                     "specificity": specificity, "target": "atom", "target_id": knowledge_id}
        )
    except Exception:
        pass
    try:
        conn.execute(
            """INSERT INTO atom_gaps (knowledge_id, gap_text, gap_type, specificity,
                   registered_by, registered_at, witness_id)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(knowledge_id, gap_text) DO UPDATE SET
                   specificity = EXCLUDED.specificity,
                   registered_at = EXCLUDED.registered_at""",
            (knowledge_id, gap_text.strip()[:500], gap_type, specificity,
             registered_by, now, witness_id)
        )
        conn.commit()
        return {"ok": True, "witness_id": witness_id}
    except Exception as e:
        conn.rollback()
        logging.warning(f"register_atom_gap failed: {e}")
        return {"ok": False, "error": str(e)}
    finally:
        conn.close()


def register_entity_gap(username: str, entity_id: int, gap_text: str,
                        gap_type: str, registered_by: str, specificity: float = 0.5) -> dict:
    """Register an acknowledged unknown on an entity. Crown-witnessed."""
    conn = _connect(username)
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    witness_id = None
    try:
        from core import crown
        witness_id = crown.witness_entity_event(
            "gap_registered", f"entity:{entity_id}",
            agent=registered_by, username=username,
            details={"gap_text": gap_text, "gap_type": gap_type,
                     "specificity": specificity, "target": "entity", "target_id": entity_id}
        )
    except Exception:
        pass
    try:
        conn.execute(
            """INSERT INTO entity_gaps (entity_id, gap_text, gap_type, specificity,
                   registered_by, registered_at, witness_id)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(entity_id, gap_text) DO UPDATE SET
                   specificity = EXCLUDED.specificity,
                   registered_at = EXCLUDED.registered_at""",
            (entity_id, gap_text.strip()[:500], gap_type, specificity,
             registered_by, now, witness_id)
        )
        conn.commit()
        return {"ok": True, "witness_id": witness_id}
    except Exception as e:
        conn.rollback()
        logging.warning(f"register_entity_gap failed: {e}")
        return {"ok": False, "error": str(e)}
    finally:
        conn.close()


def register_edge_gap(username: str, edge_id: int, gap_text: str,
                      gap_type: str, registered_by: str, specificity: float = 0.5) -> dict:
    """Register an acknowledged unknown on an edge. Crown-witnessed."""
    conn = _connect(username)
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    witness_id = None
    try:
        from core import crown
        witness_id = crown.witness_entity_event(
            "gap_registered", f"edge:{edge_id}",
            agent=registered_by, username=username,
            details={"gap_text": gap_text, "gap_type": gap_type,
                     "specificity": specificity, "target": "edge", "target_id": edge_id}
        )
    except Exception:
        pass
    try:
        conn.execute(
            """INSERT INTO edge_gaps (edge_id, gap_text, gap_type, specificity,
                   registered_by, registered_at, witness_id)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(edge_id, gap_text) DO UPDATE SET
                   specificity = EXCLUDED.specificity,
                   registered_at = EXCLUDED.registered_at""",
            (edge_id, gap_text.strip()[:500], gap_type, specificity,
             registered_by, now, witness_id)
        )
        conn.commit()
        return {"ok": True, "witness_id": witness_id}
    except Exception as e:
        conn.rollback()
        logging.warning(f"register_edge_gap failed: {e}")
        return {"ok": False, "error": str(e)}
    finally:
        conn.close()


def resolve_atom_gap(username: str, gap_id: int, resolved_by: str) -> dict:
    """Resolve an atom gap. Crown-witnessed."""
    conn = _connect(username)
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        from core import crown
        crown.witness_entity_event(
            "gap_resolved", f"atom_gap:{gap_id}",
            agent=resolved_by, username=username,
            details={"gap_id": gap_id, "target": "atom"}
        )
    except Exception:
        pass
    try:
        conn.execute(
            "UPDATE atom_gaps SET resolved = 1, resolved_at = ?, resolved_by = ? WHERE id = ?",
            (now, resolved_by, gap_id)
        )
        conn.commit()
        return {"ok": True}
    except Exception as e:
        conn.rollback()
        return {"ok": False, "error": str(e)}
    finally:
        conn.close()


def resolve_entity_gap(username: str, gap_id: int, resolved_by: str) -> dict:
    """Resolve an entity gap. Crown-witnessed."""
    conn = _connect(username)
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        from core import crown
        crown.witness_entity_event(
            "gap_resolved", f"entity_gap:{gap_id}",
            agent=resolved_by, username=username,
            details={"gap_id": gap_id, "target": "entity"}
        )
    except Exception:
        pass
    try:
        conn.execute(
            "UPDATE entity_gaps SET resolved = 1, resolved_at = ?, resolved_by = ? WHERE id = ?",
            (now, resolved_by, gap_id)
        )
        conn.commit()
        return {"ok": True}
    except Exception as e:
        conn.rollback()
        return {"ok": False, "error": str(e)}
    finally:
        conn.close()


def compute_delta_sigma(username: str) -> dict:
    """
    ΔΣ = Σ(Δᵢ) — the sum of acknowledged unknowns.
    The answer isn't a score. It's the sum of what you know you don't know.

    Health:
      ΔΣ=0 with real data → critical (system claims perfect knowledge — lying)
      ΔΣ>0, high specificity → healthy (system knows what it doesn't know)
      ΔΣ>0, low specificity → warning (gaps are vague)
    """
    conn = _connect(username)
    try:
        def _count(sql):
            row = conn.execute(sql).fetchone()
            if row is None:
                return 0
            if isinstance(row, dict):
                return list(row.values())[0] or 0
            return row[0] or 0

        system_gaps = _count("SELECT COUNT(*) as cnt FROM knowledge_gaps WHERE resolved = 0")
        atom_gaps = _count("SELECT COUNT(*) as cnt FROM atom_gaps WHERE resolved = 0")
        entity_gaps = _count("SELECT COUNT(*) as cnt FROM entity_gaps WHERE resolved = 0")
        edge_gaps = _count("SELECT COUNT(*) as cnt FROM edge_gaps WHERE resolved = 0")

        delta_sigma = system_gaps + atom_gaps + entity_gaps + edge_gaps

        # Average specificity across all gap tables
        spec_rows = conn.execute("""
            SELECT specificity FROM atom_gaps WHERE resolved = 0
            UNION ALL
            SELECT specificity FROM entity_gaps WHERE resolved = 0
            UNION ALL
            SELECT specificity FROM edge_gaps WHERE resolved = 0
        """).fetchall()

        def _val(r):
            if isinstance(r, dict):
                return list(r.values())[0] or 0.0
            return r[0] or 0.0

        avg_spec = sum(_val(r) for r in spec_rows) / max(len(spec_rows), 1) if spec_rows else 0.0

        total_atoms = _count("SELECT COUNT(*) as cnt FROM knowledge")

        # Health diagnosis
        if delta_sigma == 0 and total_atoms > 50:
            health = "critical"
            diagnosis = "System claims perfect knowledge. This is a lie."
        elif delta_sigma == 0:
            health = "nascent"
            diagnosis = "Too early to judge — not enough data yet."
        elif avg_spec >= 0.6:
            health = "healthy"
            diagnosis = f"System acknowledges {delta_sigma} unknowns with {avg_spec:.0%} specificity."
        elif avg_spec >= 0.3:
            health = "warning"
            diagnosis = f"System has {delta_sigma} gaps but specificity is low ({avg_spec:.0%}). Needs precision."
        else:
            health = "warning"
            diagnosis = f"System has {delta_sigma} vague gaps ({avg_spec:.0%} specificity). Quality over quantity."

        return {
            "delta_sigma": delta_sigma,
            "system_gaps": system_gaps,
            "atom_gaps": atom_gaps,
            "entity_gaps": entity_gaps,
            "edge_gaps": edge_gaps,
            "avg_specificity": round(avg_spec, 3),
            "total_atoms": total_atoms,
            "health": health,
            "diagnosis": diagnosis,
        }
    finally:
        conn.close()


# =========================================================================
# Semantic Search (embeddings)
# =========================================================================

def semantic_search(username: str, query: str, max_results: int = 5) -> List[Dict]:
    """
    Semantic similarity search using embeddings.
    Falls back to FTS5 if embeddings unavailable.
    """
    try:
        from core import embeddings
        if not embeddings.is_available():
            return search(username, query, max_results)
    except ImportError:
        return search(username, query, max_results)

    init_db(username)
    conn = _connect(username)
    # row_factory set in _connect() → RealDictCursor

    query_vec = embeddings.embed(query)
    if not query_vec:
        conn.close()
        return search(username, query, max_results)

    # Brute-force cosine — fine under 100k rows
    rows = conn.execute(
        "SELECT id, source_type, title, summary, content_snippet, category, created_at, embedding "
        "FROM knowledge WHERE embedding IS NOT NULL"
    ).fetchall()

    scored = []
    for row in rows:
        sim = embeddings.cosine_similarity(query_vec, row["embedding"])
        scored.append((sim, row))

    scored.sort(key=lambda x: x[0], reverse=True)
    results = []
    for sim, row in scored[:max_results]:
        results.append({
            "id": row["id"],
            "source_type": row["source_type"],
            "title": row["title"],
            "summary": row["summary"],
            "content_snippet": row["content_snippet"],
            "category": row["category"],
            "created_at": row["created_at"],
            "rank": -sim,
            "similarity": round(sim, 4),
            "entities": [],
        })
    conn.close()
    return results


def backfill_embeddings(username: str, batch_size: int = 20):
    """Compute embeddings for rows that don't have them. Mirrors backfill_summaries pattern."""
    try:
        from core import embeddings
        if not embeddings.is_available():
            return
    except ImportError:
        return

    init_db(username)

    # Read rows — short-lived connection, close BEFORE embedding
    conn = _connect(username)
    rows = conn.execute(
        "SELECT id, title, content_snippet FROM knowledge WHERE embedding IS NULL LIMIT ?",
        (batch_size,)
    ).fetchall()
    conn.close()

    if not rows:
        return

    # Compute embeddings outside DB (model load may take 10-30s on first call)
    updates = []
    for row_id, title, snippet in rows:
        text = f"{title or ''} {snippet or ''}"[:512]
        vec = embeddings.embed(text)
        if vec:
            updates.append((vec, row_id))

    # Fast batch write — no slow I/O inside
    if updates:
        conn = _connect(username)
        conn.executemany("UPDATE knowledge SET embedding=? WHERE id=?", updates)
        conn.commit()
        conn.close()
        logging.info(f"KNOWLEDGE: Backfilled {len(updates)}/{len(rows)} embeddings for {username}")

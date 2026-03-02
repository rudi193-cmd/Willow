-- Willow PostgreSQL Schema
-- Translated from SQLite willow_knowledge.db
-- Run: psql -U willow -d willow -p 5437 -f tools/pg_schema.sql

-- ── agents ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS agents (
    name          TEXT PRIMARY KEY,
    display_name  TEXT,
    trust_level   TEXT DEFAULT 'WORKER',
    agent_type    TEXT DEFAULT 'persona',
    profile_path  TEXT,
    registered_at TEXT,
    last_seen     TEXT
);

-- ── agent_mailbox ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS agent_mailbox (
    id         BIGSERIAL PRIMARY KEY,
    from_agent TEXT NOT NULL,
    to_agent   TEXT NOT NULL,
    subject    TEXT,
    body       TEXT NOT NULL,
    sent_at    TEXT,
    read_at    TEXT,
    thread_id  TEXT
);
CREATE INDEX IF NOT EXISTS idx_mailbox_to ON agent_mailbox(to_agent, read_at);

-- ── willow_state ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS willow_state (
    key    TEXT PRIMARY KEY,
    value  TEXT,
    set_at TEXT
);

-- ── schema_versions ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS schema_versions (
    id          BIGSERIAL PRIMARY KEY,
    version     TEXT NOT NULL,
    description TEXT,
    applied_at  TEXT NOT NULL
);

-- ── anonymous_mentions ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS anonymous_mentions (
    id        BIGSERIAL PRIMARY KEY,
    username  TEXT,
    category  TEXT,
    count     INTEGER DEFAULT 0,
    last_seen TEXT,
    UNIQUE(username, category)
);

-- ── knowledge ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS knowledge (
    id              BIGSERIAL PRIMARY KEY,
    source_type     TEXT NOT NULL,
    source_id       TEXT NOT NULL,
    title           TEXT NOT NULL,
    summary         TEXT,
    content_snippet TEXT,
    category        TEXT,
    created_at      TEXT NOT NULL,
    embedding       BYTEA,
    ring            TEXT DEFAULT 'bridge',
    ring_override   TEXT,
    lattice_domain  TEXT,
    lattice_type    TEXT,
    lattice_status  TEXT,
    search_vector   TSVECTOR,
    UNIQUE(source_type, source_id)
);
CREATE INDEX IF NOT EXISTS idx_knowledge_ring     ON knowledge(ring);
CREATE INDEX IF NOT EXISTS idx_knowledge_created  ON knowledge(created_at);
CREATE INDEX IF NOT EXISTS idx_knowledge_category ON knowledge(category);
CREATE INDEX IF NOT EXISTS idx_knowledge_fts      ON knowledge USING GIN(search_vector);

-- Trigger: keep search_vector current on insert/update
CREATE OR REPLACE FUNCTION knowledge_search_vector_update() RETURNS TRIGGER AS $$
BEGIN
    NEW.search_vector :=
        setweight(to_tsvector('english', coalesce(NEW.title, '')), 'A') ||
        setweight(to_tsvector('english', coalesce(NEW.summary, '')), 'B') ||
        setweight(to_tsvector('english', coalesce(NEW.content_snippet, '')), 'C') ||
        setweight(to_tsvector('english', coalesce(NEW.category, '')), 'D');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS knowledge_tsvector_update ON knowledge;
CREATE TRIGGER knowledge_tsvector_update
    BEFORE INSERT OR UPDATE ON knowledge
    FOR EACH ROW EXECUTE FUNCTION knowledge_search_vector_update();

-- ── entities ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS entities (
    id                BIGSERIAL PRIMARY KEY,
    name              TEXT NOT NULL UNIQUE,
    entity_type       TEXT NOT NULL,
    description       TEXT,
    mention_count     INTEGER DEFAULT 1,
    layer             TEXT DEFAULT '1',
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
);
CREATE INDEX IF NOT EXISTS idx_entities_username_domain ON entities(username, domain);
CREATE INDEX IF NOT EXISTS idx_entities_promotion       ON entities(promotion_status);

-- ── knowledge_entities ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS knowledge_entities (
    knowledge_id BIGINT REFERENCES knowledge(id) ON DELETE CASCADE,
    entity_id    BIGINT REFERENCES entities(id)  ON DELETE CASCADE,
    PRIMARY KEY (knowledge_id, entity_id)
);

-- ── entity_connections ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS entity_connections (
    id              BIGSERIAL PRIMARY KEY,
    entity_a_id     BIGINT,
    entity_b_id     BIGINT,
    connection_type TEXT,
    weight          REAL DEFAULT 1.0,
    source          TEXT,
    created_at      TEXT,
    confirmed       INTEGER DEFAULT 0,
    UNIQUE(entity_a_id, entity_b_id, connection_type)
);
CREATE INDEX IF NOT EXISTS idx_entity_connections_confirmed
    ON entity_connections(confirmed, entity_a_id);

-- ── knowledge_clusters ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS knowledge_clusters (
    cluster_id BIGSERIAL PRIMARY KEY,
    label      TEXT NOT NULL,
    method     TEXT NOT NULL,
    canonical  INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    atom_count INTEGER DEFAULT 0,
    centroid   BYTEA
);

-- ── cluster_members ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS cluster_members (
    cluster_id   BIGINT REFERENCES knowledge_clusters(cluster_id) ON DELETE CASCADE,
    knowledge_id BIGINT REFERENCES knowledge(id)                  ON DELETE CASCADE,
    distance     REAL,
    PRIMARY KEY (cluster_id, knowledge_id)
);
CREATE INDEX IF NOT EXISTS idx_cm_kid ON cluster_members(knowledge_id);

-- ── knowledge_edges ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS knowledge_edges (
    id         BIGSERIAL PRIMARY KEY,
    source_id  BIGINT REFERENCES knowledge(id) ON DELETE CASCADE,
    target_id  BIGINT REFERENCES knowledge(id) ON DELETE CASCADE,
    edge_type  TEXT NOT NULL,
    weight     REAL DEFAULT 1.0,
    canonical  INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    UNIQUE(source_id, target_id, edge_type)
);
CREATE INDEX IF NOT EXISTS idx_edges_source ON knowledge_edges(source_id, edge_type);
CREATE INDEX IF NOT EXISTS idx_edges_target ON knowledge_edges(target_id, edge_type);

-- ── knowledge_gaps ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS knowledge_gaps (
    id                       BIGSERIAL PRIMARY KEY,
    query                    TEXT NOT NULL,
    source                   TEXT NOT NULL,
    gap_type                 TEXT NOT NULL,
    entity_name              TEXT,
    times_hit                INTEGER DEFAULT 1,
    first_seen               TEXT NOT NULL,
    last_seen                TEXT NOT NULL,
    resolved                 INTEGER DEFAULT 0,
    resolved_by_knowledge_id BIGINT,
    UNIQUE(query, source)
);

-- ── conversation_memory ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS conversation_memory (
    id                 BIGSERIAL PRIMARY KEY,
    knowledge_id       BIGINT REFERENCES knowledge(id) ON DELETE SET NULL,
    persona            TEXT,
    user_input         TEXT,
    assistant_response TEXT,
    coherence_index    REAL,
    delta_e            REAL,
    topics             TEXT,
    created_at         TEXT NOT NULL
);

-- ── pigeon_droppings ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS pigeon_droppings (
    id            BIGSERIAL PRIMARY KEY,
    username      TEXT NOT NULL,
    filename      TEXT NOT NULL,
    original_path TEXT,
    filed_to      TEXT,
    category      TEXT,
    summary       TEXT,
    created_at    TEXT NOT NULL,
    file_hash     TEXT
);
CREATE INDEX IF NOT EXISTS idx_pigeon_username_cat
    ON pigeon_droppings(username, category, created_at);

-- ── pigeon_errors ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS pigeon_errors (
    id         BIGSERIAL PRIMARY KEY,
    username   TEXT NOT NULL,
    filename   TEXT NOT NULL,
    error      TEXT,
    created_at TEXT NOT NULL
);

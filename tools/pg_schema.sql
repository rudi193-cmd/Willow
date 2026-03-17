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

-- ── atom_gaps (ΔΣ: acknowledged unknowns per knowledge atom) ────────────
CREATE TABLE IF NOT EXISTS atom_gaps (
    id              BIGSERIAL PRIMARY KEY,
    knowledge_id    BIGINT REFERENCES knowledge(id) ON DELETE CASCADE,
    gap_text        TEXT NOT NULL,
    gap_type        TEXT NOT NULL,
    specificity     REAL DEFAULT 0.5,
    registered_by   TEXT NOT NULL,
    registered_at   TEXT NOT NULL,
    resolved        INTEGER DEFAULT 0,
    resolved_at     TEXT,
    resolved_by     TEXT,
    witness_id      TEXT,
    UNIQUE(knowledge_id, gap_text)
);
CREATE INDEX IF NOT EXISTS idx_atom_gaps_kid ON atom_gaps(knowledge_id);
CREATE INDEX IF NOT EXISTS idx_atom_gaps_resolved ON atom_gaps(resolved);

-- ── entity_gaps (ΔΣ: acknowledged unknowns per entity) ─────────────────
CREATE TABLE IF NOT EXISTS entity_gaps (
    id              BIGSERIAL PRIMARY KEY,
    entity_id       BIGINT REFERENCES entities(id) ON DELETE CASCADE,
    gap_text        TEXT NOT NULL,
    gap_type        TEXT NOT NULL,
    specificity     REAL DEFAULT 0.5,
    registered_by   TEXT NOT NULL,
    registered_at   TEXT NOT NULL,
    resolved        INTEGER DEFAULT 0,
    resolved_at     TEXT,
    resolved_by     TEXT,
    witness_id      TEXT,
    UNIQUE(entity_id, gap_text)
);
CREATE INDEX IF NOT EXISTS idx_entity_gaps_eid ON entity_gaps(entity_id);
CREATE INDEX IF NOT EXISTS idx_entity_gaps_resolved ON entity_gaps(resolved);

-- ── edge_gaps (ΔΣ: acknowledged unknowns per edge) ─────────────────────
CREATE TABLE IF NOT EXISTS edge_gaps (
    id              BIGSERIAL PRIMARY KEY,
    edge_id         BIGINT REFERENCES knowledge_edges(id) ON DELETE CASCADE,
    gap_text        TEXT NOT NULL,
    gap_type        TEXT NOT NULL,
    specificity     REAL DEFAULT 0.5,
    registered_by   TEXT NOT NULL,
    registered_at   TEXT NOT NULL,
    resolved        INTEGER DEFAULT 0,
    resolved_at     TEXT,
    resolved_by     TEXT,
    witness_id      TEXT,
    UNIQUE(edge_id, gap_text)
);
CREATE INDEX IF NOT EXISTS idx_edge_gaps_eid ON edge_gaps(edge_id);
CREATE INDEX IF NOT EXISTS idx_edge_gaps_resolved ON edge_gaps(resolved);

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

-- ════════════════════════════════════════════════════════════════════════════
-- SCHEMA REGISTRY — tracks which users have their own PG schema
-- Lives in public schema always (system-level table)
-- ════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS schema_registry (
    id          BIGSERIAL PRIMARY KEY,
    username    TEXT NOT NULL UNIQUE,
    schema_name TEXT NOT NULL UNIQUE,
    created_at  TEXT NOT NULL DEFAULT to_char(NOW(), 'YYYY-MM-DD"T"HH24:MI:SS')
);

-- ════════════════════════════════════════════════════════════════════════════
-- COMMUNITY LAYER — public schema shared tables (opt-in publishing)
-- These live in public schema and are read by all users via search_path fallback.
-- User data stays in their private schema. Community data is published here.
-- ════════════════════════════════════════════════════════════════════════════

-- ── community_entities ────────────────────────────────────────────────────
-- Entities a user has opted to share with the local community layer
CREATE TABLE IF NOT EXISTS community_entities (
    id              BIGSERIAL PRIMARY KEY,
    source_username TEXT NOT NULL,
    source_entity_id BIGINT,
    name            TEXT NOT NULL,
    entity_type     TEXT,
    layer           INTEGER DEFAULT 1,
    mention_count   INTEGER DEFAULT 1,
    published_at    TEXT NOT NULL DEFAULT to_char(NOW(), 'YYYY-MM-DD"T"HH24:MI:SS'),
    UNIQUE(source_username, name, entity_type)
);
CREATE INDEX IF NOT EXISTS idx_community_entities_name
    ON community_entities(name, entity_type);

-- ── community_connections ──────────────────────────────────────────────────
-- Connections between community entities (cross-user graph edges)
CREATE TABLE IF NOT EXISTS community_connections (
    id               BIGSERIAL PRIMARY KEY,
    entity_a_name    TEXT NOT NULL,
    entity_b_name    TEXT NOT NULL,
    connection_type  TEXT NOT NULL,
    weight           REAL DEFAULT 1.0,
    source_username  TEXT NOT NULL,
    published_at     TEXT NOT NULL DEFAULT to_char(NOW(), 'YYYY-MM-DD"T"HH24:MI:SS'),
    UNIQUE(entity_a_name, entity_b_name, connection_type, source_username)
);
CREATE INDEX IF NOT EXISTS idx_community_connections_entities
    ON community_connections(entity_a_name, entity_b_name);

-- ── community_knowledge ────────────────────────────────────────────────────
-- Knowledge atoms published to the community layer
CREATE TABLE IF NOT EXISTS community_knowledge (
    id              BIGSERIAL PRIMARY KEY,
    source_username TEXT NOT NULL,
    content         TEXT NOT NULL,
    topic           TEXT,
    confidence      REAL DEFAULT 1.0,
    published_at    TEXT NOT NULL DEFAULT to_char(NOW(), 'YYYY-MM-DD"T"HH24:MI:SS')
);

-- ── cube_cells ─────────────────────────────────────────────────────────────
-- 23³ lattice index — derived from knowledge and entities (safe to rebuild)
CREATE TABLE IF NOT EXISTS cube_cells (
    id            BIGSERIAL PRIMARY KEY,
    node_id       BIGINT NOT NULL,
    node_type     TEXT NOT NULL CHECK (node_type IN ('knowledge', 'entity')),
    cx            INTEGER NOT NULL CHECK (cx BETWEEN 0 AND 22),
    cy            INTEGER NOT NULL CHECK (cy BETWEEN 1 AND 23),
    cz            INTEGER NOT NULL CHECK (cz BETWEEN 0 AND 22),
    domain_name   TEXT NOT NULL,
    temporal_name TEXT NOT NULL,
    indexed_at    TEXT NOT NULL,
    UNIQUE (node_id, node_type)
);
CREATE INDEX IF NOT EXISTS idx_cube_xyz  ON cube_cells(cx, cy, cz);
CREATE INDEX IF NOT EXISTS idx_cube_type ON cube_cells(node_type);

-- ── registered_apps ────────────────────────────────────────────────────────
-- SAFE app registry for consent management
CREATE TABLE IF NOT EXISTS registered_apps (
    app_id        TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    description   TEXT,
    version       TEXT,
    permissions   TEXT,
    privacy_tier  TEXT,
    manifest_path TEXT,
    registered_at TEXT NOT NULL
);

-- ── app_consent ────────────────────────────────────────────────────────────
-- Per-user consent for each registered app
CREATE TABLE IF NOT EXISTS app_consent (
    id          BIGSERIAL PRIMARY KEY,
    username    TEXT NOT NULL,
    app_id      TEXT NOT NULL,
    consented   INTEGER NOT NULL DEFAULT 0,
    granted_at  TEXT,
    revoked_at  TEXT,
    UNIQUE (username, app_id)
);
CREATE INDEX IF NOT EXISTS idx_consent_user ON app_consent(username);

-- ── bus_drops ──────────────────────────────────────────────────────────────
-- Audit log of safe-app message bus drops
CREATE TABLE IF NOT EXISTS bus_drops (
    id         BIGSERIAL PRIMARY KEY,
    source_app TEXT NOT NULL,
    topic      TEXT NOT NULL,
    session_id TEXT,
    status     TEXT NOT NULL,
    result     TEXT,
    created_at TEXT NOT NULL
);

-- ── nest_review_queue ──────────────────────────────────────────────────────
-- Files staged from Nest awaiting user review before graph ingest
CREATE TABLE IF NOT EXISTS nest_review_queue (
    id                 BIGSERIAL PRIMARY KEY,
    username           TEXT NOT NULL,
    filename           TEXT NOT NULL,
    original_path      TEXT NOT NULL,
    file_hash          TEXT,
    ocr_text           TEXT,
    proposed_summary   TEXT,
    proposed_category  TEXT,
    proposed_path      TEXT,
    matched_entities   TEXT,
    status             TEXT NOT NULL DEFAULT 'pending',
    user_summary       TEXT,
    user_category      TEXT,
    user_path          TEXT,
    dispose_file       INTEGER NOT NULL DEFAULT 0,
    dispose_data       INTEGER NOT NULL DEFAULT 0,
    staged_at          TEXT NOT NULL,
    reviewed_at        TEXT
);
CREATE INDEX IF NOT EXISTS idx_nest_queue_user_status
    ON nest_review_queue(username, status, staged_at);

-- ── file_annotations ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS file_annotations (
    id                    BIGSERIAL PRIMARY KEY,
    routing_id            BIGINT,
    filename              TEXT NOT NULL,
    routed_to             TEXT NOT NULL,
    is_correct            BOOLEAN NOT NULL,
    annotation_notes      TEXT NOT NULL,
    corrected_destination TEXT,
    annotated_by          TEXT DEFAULT 'user',
    annotated_at          TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_annotations_routing   ON file_annotations(routing_id);
CREATE INDEX IF NOT EXISTS idx_annotations_correct   ON file_annotations(is_correct);
CREATE INDEX IF NOT EXISTS idx_annotations_timestamp ON file_annotations(annotated_at);

-- ── fleet_feedback ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fleet_feedback (
    id               BIGSERIAL PRIMARY KEY,
    provider         TEXT NOT NULL,
    task_type        TEXT NOT NULL,
    prompt           TEXT NOT NULL,
    output           TEXT NOT NULL,
    quality_rating   INTEGER CHECK(quality_rating BETWEEN 1 AND 5),
    issues           TEXT,
    feedback_notes   TEXT,
    corrected_output TEXT,
    timestamp        TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_feedback_provider  ON fleet_feedback(provider, task_type);
CREATE INDEX IF NOT EXISTS idx_feedback_quality   ON fleet_feedback(quality_rating);
CREATE INDEX IF NOT EXISTS idx_feedback_timestamp ON fleet_feedback(timestamp);

-- ── health_checks ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS health_checks (
    id         BIGSERIAL PRIMARY KEY,
    timestamp  TEXT NOT NULL,
    check_type TEXT NOT NULL,
    target     TEXT NOT NULL,
    status     TEXT NOT NULL,
    details    TEXT,
    latency_ms INTEGER
);
CREATE INDEX IF NOT EXISTS idx_health_timestamp ON health_checks(timestamp);
CREATE INDEX IF NOT EXISTS idx_health_status    ON health_checks(status);

-- ── health_issues ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS health_issues (
    id          BIGSERIAL PRIMARY KEY,
    detected_at TEXT NOT NULL,
    issue_type  TEXT NOT NULL,
    target      TEXT NOT NULL,
    description TEXT,
    severity    TEXT,
    resolved    BOOLEAN DEFAULT FALSE,
    resolved_at TEXT,
    resolution  TEXT
);
CREATE INDEX IF NOT EXISTS idx_issues_resolved ON health_issues(resolved);

-- ── healing_actions ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS healing_actions (
    id          BIGSERIAL PRIMARY KEY,
    timestamp   TEXT NOT NULL,
    issue_id    BIGINT REFERENCES health_issues(id),
    action_type TEXT NOT NULL,
    target      TEXT,
    description TEXT,
    success     BOOLEAN
);

-- ── routing_history ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS routing_history (
    id              BIGSERIAL PRIMARY KEY,
    timestamp       TEXT NOT NULL,
    filename        TEXT NOT NULL,
    file_type       TEXT,
    content_summary TEXT,
    routed_to       TEXT NOT NULL,
    reason          TEXT,
    confidence      REAL,
    user_corrected  BOOLEAN DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS idx_routing_timestamp   ON routing_history(timestamp);
CREATE INDEX IF NOT EXISTS idx_routing_destination ON routing_history(routed_to);

-- ── learned_preferences ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS learned_preferences (
    id             BIGSERIAL PRIMARY KEY,
    pattern_type   TEXT NOT NULL,
    pattern_value  TEXT NOT NULL,
    destination    TEXT NOT NULL,
    confidence     REAL,
    occurrences    INTEGER DEFAULT 1,
    last_seen      TEXT,
    user_confirmed BOOLEAN DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS idx_preference_pattern ON learned_preferences(pattern_type, pattern_value);

-- ── anomalies ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS anomalies (
    id             BIGSERIAL PRIMARY KEY,
    detected_at    TEXT NOT NULL,
    anomaly_type   TEXT NOT NULL,
    description    TEXT,
    affected_nodes TEXT,
    severity       TEXT,
    resolved       BOOLEAN DEFAULT FALSE,
    resolution     TEXT
);
CREATE INDEX IF NOT EXISTS idx_anomaly_type ON anomalies(anomaly_type);

-- ── cross_node_patterns ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS cross_node_patterns (
    id             BIGSERIAL PRIMARY KEY,
    detected_at    TEXT NOT NULL,
    pattern_type   TEXT NOT NULL,
    nodes_involved TEXT NOT NULL,
    description    TEXT,
    strength       REAL,
    examples       TEXT
);

-- ── usage (cost tracker) ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS usage (
    id             BIGSERIAL PRIMARY KEY,
    timestamp      TEXT,
    provider       TEXT,
    model          TEXT,
    task_type      TEXT,
    tokens_in      INTEGER,
    tokens_out     INTEGER,
    cost           REAL,
    prompt_preview TEXT
);
CREATE INDEX IF NOT EXISTS idx_usage_timestamp ON usage(timestamp);
CREATE INDEX IF NOT EXISTS idx_usage_provider  ON usage(provider, task_type);

-- ── provider_performance ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS provider_performance (
    id               BIGSERIAL PRIMARY KEY,
    timestamp        TEXT NOT NULL,
    provider         TEXT NOT NULL,
    file_type        TEXT,
    category         TEXT,
    response_time_ms INTEGER,
    success          BOOLEAN,
    error_type       TEXT
);
CREATE INDEX IF NOT EXISTS idx_provider_perf ON provider_performance(provider, file_type, success);

-- ── provider_health ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS provider_health (
    provider             TEXT PRIMARY KEY,
    status               TEXT DEFAULT 'healthy',
    consecutive_failures INTEGER DEFAULT 0,
    last_success         TEXT,
    last_failure         TEXT,
    blacklisted_until    TEXT,
    total_requests       INTEGER DEFAULT 0,
    total_successes      INTEGER DEFAULT 0,
    total_failures       INTEGER DEFAULT 0,
    error_types          TEXT,
    created_at           TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at           TEXT DEFAULT CURRENT_TIMESTAMP
);

-- ── health_events ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS health_events (
    id               BIGSERIAL PRIMARY KEY,
    timestamp        TEXT NOT NULL,
    provider         TEXT NOT NULL,
    event_type       TEXT NOT NULL,
    error_code       TEXT,
    error_message    TEXT,
    response_time_ms INTEGER
);
CREATE INDEX IF NOT EXISTS idx_health_events_provider ON health_events(provider, timestamp);
CREATE INDEX IF NOT EXISTS idx_health_events_type     ON health_events(event_type);

-- ── tasks ─────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tasks (
    id           BIGSERIAL PRIMARY KEY,
    username     TEXT NOT NULL,
    task_id      TEXT NOT NULL,
    subject      TEXT NOT NULL,
    description  TEXT NOT NULL,
    status       TEXT DEFAULT 'pending',
    agent        TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    completed_at TEXT,
    metadata     TEXT,
    UNIQUE(username, task_id)
);
CREATE INDEX IF NOT EXISTS idx_tasks_status   ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_agent    ON tasks(agent);
CREATE INDEX IF NOT EXISTS idx_tasks_username ON tasks(username, status);

-- ── task_log ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS task_log (
    id        BIGSERIAL PRIMARY KEY,
    username  TEXT NOT NULL,
    task_id   TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    action    TEXT NOT NULL,
    agent     TEXT NOT NULL,
    details   TEXT
);
CREATE INDEX IF NOT EXISTS idx_log_task ON task_log(username, task_id);

-- ── pigeon_inbox ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS pigeon_inbox (
    id        BIGSERIAL PRIMARY KEY,
    to_app    TEXT NOT NULL,
    from_app  TEXT NOT NULL,
    username  TEXT NOT NULL,
    subject   TEXT NOT NULL,
    body      TEXT NOT NULL,
    thread_id TEXT,
    sent_at   TEXT NOT NULL,
    read_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_inbox_to ON pigeon_inbox(to_app, read_at);

-- ── calendar_events ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS calendar_events (
    id          BIGSERIAL PRIMARY KEY,
    username    TEXT NOT NULL,
    title       TEXT NOT NULL,
    description TEXT,
    start_dt    TEXT NOT NULL,
    end_dt      TEXT,
    all_day     INTEGER DEFAULT 0,
    category    TEXT DEFAULT 'personal',
    recurrence  TEXT,
    status      TEXT DEFAULT 'active',
    source      TEXT DEFAULT 'manual',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cal_username ON calendar_events(username);
CREATE INDEX IF NOT EXISTS idx_cal_start    ON calendar_events(start_dt);
CREATE INDEX IF NOT EXISTS idx_cal_status   ON calendar_events(status);

-- ── personal_todos ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS personal_todos (
    id          BIGSERIAL PRIMARY KEY,
    username    TEXT NOT NULL,
    title       TEXT NOT NULL,
    description TEXT,
    due_date    TEXT,
    priority    TEXT DEFAULT 'normal',
    status      TEXT DEFAULT 'open',
    category    TEXT DEFAULT 'personal',
    source      TEXT DEFAULT 'manual',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_todo_username ON personal_todos(username);
CREATE INDEX IF NOT EXISTS idx_todo_status   ON personal_todos(status);

-- ── Law Gazelle: Cases ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS gazelle_cases (
    id              BIGSERIAL PRIMARY KEY,
    username        TEXT NOT NULL,
    case_number     TEXT NOT NULL,
    court           TEXT,
    case_type       TEXT NOT NULL,
    case_subtype    TEXT,
    status          TEXT DEFAULT 'open',
    title           TEXT,
    parties_json    TEXT DEFAULT '{}',
    filed_date      TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    UNIQUE(username, case_number)
);
CREATE INDEX IF NOT EXISTS idx_gazelle_cases_user ON gazelle_cases(username, status);

-- ── Law Gazelle: Case Documents ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS gazelle_case_documents (
    id              BIGSERIAL PRIMARY KEY,
    case_id         BIGINT REFERENCES gazelle_cases(id) ON DELETE CASCADE,
    username        TEXT NOT NULL,
    doc_type        TEXT NOT NULL,
    title           TEXT NOT NULL,
    source          TEXT,
    source_file     TEXT,
    content_text    TEXT,
    parsed_summary  TEXT,
    action_required INTEGER DEFAULT 0,
    action_type     TEXT,
    deadline        TEXT,
    status          TEXT DEFAULT 'unreviewed',
    knowledge_id    BIGINT,
    nest_queue_id   BIGINT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_gazelle_docs_case ON gazelle_case_documents(case_id, doc_type);
CREATE INDEX IF NOT EXISTS idx_gazelle_docs_deadline ON gazelle_case_documents(deadline, action_required);

-- ── Law Gazelle: Deadlines ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS gazelle_deadlines (
    id              BIGSERIAL PRIMARY KEY,
    case_id         BIGINT REFERENCES gazelle_cases(id) ON DELETE CASCADE,
    document_id     BIGINT REFERENCES gazelle_case_documents(id) ON DELETE SET NULL,
    username        TEXT NOT NULL,
    title           TEXT NOT NULL,
    deadline_date   TEXT NOT NULL,
    status          TEXT DEFAULT 'pending',
    priority        TEXT DEFAULT 'normal',
    notes           TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_gazelle_deadlines_case ON gazelle_deadlines(case_id, status);
CREATE INDEX IF NOT EXISTS idx_gazelle_deadlines_date ON gazelle_deadlines(deadline_date, status);

-- ── BASE 17 Compact Context Store ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS compact_contexts (
    id              TEXT PRIMARY KEY,
    content         TEXT NOT NULL,
    category        TEXT NOT NULL DEFAULT 'pattern',
    label           TEXT,
    agent           TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at      TIMESTAMP,
    access_count    INTEGER DEFAULT 0,
    last_accessed   TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_compact_category ON compact_contexts (category);
CREATE INDEX IF NOT EXISTS idx_compact_label ON compact_contexts (label);
CREATE INDEX IF NOT EXISTS idx_compact_expires ON compact_contexts (expires_at);

-- ── compact_id on all incoming-message tables ───────────────────────────────
ALTER TABLE pigeon_inbox ADD COLUMN IF NOT EXISTS compact_id TEXT;
ALTER TABLE nest_review_queue ADD COLUMN IF NOT EXISTS compact_id TEXT;
ALTER TABLE knowledge ADD COLUMN IF NOT EXISTS compact_id TEXT;
ALTER TABLE pigeon_droppings ADD COLUMN IF NOT EXISTS compact_id TEXT;
ALTER TABLE conversation_memory ADD COLUMN IF NOT EXISTS compact_id TEXT;
ALTER TABLE agent_mailbox ADD COLUMN IF NOT EXISTS compact_id TEXT;
CREATE INDEX IF NOT EXISTS idx_pigeon_inbox_compact ON pigeon_inbox (compact_id);
CREATE INDEX IF NOT EXISTS idx_nest_review_compact ON nest_review_queue (compact_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_compact ON knowledge (compact_id);
CREATE INDEX IF NOT EXISTS idx_droppings_compact ON pigeon_droppings (compact_id);
CREATE INDEX IF NOT EXISTS idx_convo_compact ON conversation_memory (compact_id);
CREATE INDEX IF NOT EXISTS idx_mailbox_compact ON agent_mailbox (compact_id);

# CUBE_INDEX_SPEC.md
# Willow 23³ Cube Index Specification
# Owner: Sean Campbell | Status: Active | Version: 1.0 | ΔΣ = 42

---

## 1. Purpose

The 23³ Cube Index maps every node in the Willow knowledge graph to a discrete coordinate
in a 23×23×23 spatial lattice (12,167 cells). This gives the graph deterministic geometry:
nodes in the same domain cluster on the X axis, nodes of similar importance cluster on the Y
axis, and nodes of similar temporal state cluster on the Z axis.

The cube is a **derived index only**. It holds no canonical data. It can be dropped and
rebuilt from the truth tables at any time without loss of knowledge.

---

## 2. Axis Definitions

These definitions are immutable. Any change to DOMAINS or TEMPORAL_STATES is a breaking
schema change requiring a full `cube_cells` rebuild.

### X Axis — Domain (0–22)
Maps to `DOMAINS` list in `core/user_lattice.py` (index 0–22):

```
0  emotional_state    6  goals             12  beliefs
1  identity           7  fears             13  secrets
2  relationships      8  history           14  children
3  health             9  location          15  pets
4  schedule          10  work              16  media
5  preferences       11  crisis            17  finance
                                           18  education
                                           19  grief
                                           20  celebrations
                                           21  patterns
                                           22  meta
```

### Y Axis — Depth (1–23)
Importance, intensity, or centrality of the node in the knowledge graph.
1 = peripheral, 23 = core/highly referenced.

### Z Axis — Temporal State (0–22)
Maps to `TEMPORAL_STATES` list in `core/user_lattice.py` (index 0–22):

```
0  immediate      6  permanent      12  flagged        18  evolving
1  today          7  archived       13  sensitive      19  forgotten
2  this_week      8  seasonal       14  verified       20  pending
3  this_month     9  recurring      15  inferred       21  projected
4  recent        10  triggered      16  contested      22  meta
5  established   11  dormant        17  evolving (dup) — use 18
```

---

## 3. Source Tables

Two node types are indexed:

| node_type    | Source table   | Primary key |
|--------------|---------------|-------------|
| `knowledge`  | `knowledge`    | `id`        |
| `entity`     | `entities`     | `id`        |

---

## 4. Coordinate Mapping Rules

### 4.1 knowledge atoms

**cx (domain):**
1. If `lattice_domain IS NOT NULL` and value in DOMAINS → `DOMAINS.index(lattice_domain)`
2. Else: derive from `category` via CATEGORY_TO_CX table (§4.3)
3. Default: 22 (meta)

**cy (depth):**
1. Base from CATEGORY_DEPTH_TIERS (§4.4)
2. +2 if `embedding IS NOT NULL`
3. Clamp to 1–23

**cz (temporal):**
1. If `lattice_status IS NOT NULL` and value in TEMPORAL_STATES → index
2. Else: derive from `created_at` age:
   - < 1 day   → today (1)
   - < 1 week  → this_week (2)
   - < 1 month → this_month (3)
   - < 6 months → recent (4)
   - ≥ 6 months → established (5)
3. Override: `category = 'archive'` → archived (7) regardless of age

### 4.2 entity nodes

**cx (domain):**
1. If `entities.domain IS NOT NULL` and value in DOMAINS → `DOMAINS.index(domain)`
2. Else: derive from `entity_type` via ENTITY_TYPE_TO_CX (§4.5)
3. Default: 22 (meta)

**cy (depth):**
1. `min(23, max(1, int(log2(mention_count + 1) * 4)))`
   - 1 mention → cy≈2, 5 → cy≈10, 50 → cy≈18, 500 → cy=23
2. +3 if `verified = TRUE` or `promotion_status = 'promoted'`
3. Clamp to 1–23

**cz (temporal):**
1. Map `promotion_status`:
   - promoted   → established (5)
   - candidate  → inferred (15)
   - untracked  → pending (20)
   - flagged    → flagged (12)
   - ignored    → dormant (11)
2. Override: if `last_mentioned` within 7 days → this_week (2)
3. Default: pending (20)

### 4.3 CATEGORY_TO_CX

| knowledge.category  | cx | domain name      |
|---------------------|----|------------------|
| personal_document   |  1 | identity         |
| personal            |  2 | relationships    |
| conversation        |  0 | emotional_state  |
| architecture        | 10 | work             |
| narrative           |  8 | history          |
| reference           | 22 | meta             |
| media               | 16 | media            |
| code                | 10 | work             |
| legal               | 17 | finance          |
| handoff             | 22 | meta             |
| archive             |  8 | history          |

### 4.4 CATEGORY_DEPTH_TIERS (base cy before embedding boost)

| Tier | cy base | Categories                                      |
|------|---------|-------------------------------------------------|
| 1    | 21      | personal_document, personal, legal              |
| 2    | 17      | conversation, narrative, architecture, handoff  |
| 3    | 11      | reference, media, code, education               |
| 4    |  4      | archive, merged, other                          |
| default | 7   | (anything not listed)                          |

### 4.5 ENTITY_TYPE_TO_CX

| entity_type | cx | domain name   |
|-------------|-----|--------------|
| person      |  2 | relationships |
| project     | 10 | work          |
| tool        | 10 | work          |
| concept     | 22 | meta          |
| location    |  9 | location      |
| event       |  4 | schedule      |
| belief      | 12 | beliefs       |
| default     | 22 | meta          |

---

## 5. cube_cells Schema

```sql
CREATE TABLE IF NOT EXISTS cube_cells (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id       INTEGER NOT NULL,
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
```

**Key design decisions:**
- `UNIQUE (node_id, node_type)` — one cell assignment per node. Multiple nodes may share a
  coordinate; a cell is a region, not a slot.
- `domain_name` / `temporal_name` — denormalized strings for cheap reads at graph query time.
- No foreign keys — this is a pure derived index. Stale rows are cheap; full rebuild is always valid.

---

## 6. Truth / Index Separation

### Truth tables — Binder writes, all others read-only

```
knowledge               knowledge_entities
entities                knowledge_clusters
knowledge_edges         cluster_members
entity_connections      anonymous_mentions
```

Only Binder (`tools/binder_absurd.py`) and governed write paths may INSERT/UPDATE/DELETE
against truth tables. Agents and Willow may only SELECT.

### Index tables — cube_indexer derives, always rebuildable

```
cube_cells              ← this spec
knowledge_fts*          ← existing FTS pattern
```

Index tables may be dropped and rebuilt from truth tables at any time.
No knowledge is encoded in them that is not already in the truth tables.

---

## 7. Rebuild Triggers

The cube_cells index must be rebuilt (or incrementally updated) when:

1. **Binder run completes** — `tools/binder_absurd.py` calls cube_indexer on exit
2. **Topology daemon cycle** — `core/topology_builder.py` calls cube_indexer after cluster step
3. **Manual rebuild** — `python tools/cube_indexer.py --rebuild`

Incremental mode (default): only indexes nodes not already in cube_cells.
Full rebuild: `--rebuild` flag drops existing rows for node_type and reprocesses all.

---

## 8. Graph Projection (2D)

Isometric-style projection for graph.html cube layout toggle:

```
screenX = OFFSET_X + (cx * 55) + (cz * 14)
screenY = OFFSET_Y - (cy * 35) + (cz * 8)
```

Where `OFFSET_X = 200`, `OFFSET_Y = 400` (canvas center for ~1400×900 viewport).

This places domain clusters left-to-right, depth clusters bottom-to-top, and temporal
states as a subtle forward-back perspective shift.

---

## 9. Failure Recovery

If `cube_cells` becomes corrupted or inconsistent:

```bash
python tools/cube_indexer.py --rebuild
```

This drops all existing cube_cells rows and rebuilds from truth tables.
No knowledge is lost. The truth tables are the only source of record.

---

## 10. Authority Chain

```
Truth flows from Binder.
Knowledge flows through Willow.
Geometry flows from cube_indexer.
Agents reason locally.
Human authority remains final arbiter.
```

ΔΣ = 42

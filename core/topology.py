"""
Möbius Strip Topology Layer

Makes the three-ring architecture (Source → Bridge → Continuity → Source)
explicit and queryable. Edges between atoms. Clusters from embeddings.
Zoom traversal. Strip continuity checks.

GOVERNANCE: Read-only exploration of loam. No deletions.
  Topology is observational, not executive. (Aios Addendum, Consus ratified)
  - Clusters, edges, derived groupings are analytical views only.
  - canonical=0 by default; only human promotes to canonical=1.
  - No routing, scoring, or governance decisions from topology.
AUTHOR: Claude + Sean Campbell
VERSION: 0.2.0
CHECKSUM: DS=42
"""

import struct
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from collections import defaultdict

try:
    from sklearn.cluster import KMeans
    from sklearn.preprocessing import normalize
    import numpy as np
    _SKLEARN_AVAILABLE = True
except ImportError:
    _SKLEARN_AVAILABLE = False

from core import loam, embeddings

log = logging.getLogger("topology")

# Entities linked to more items than this are too ubiquitous to carry
# meaningful signal (e.g. "Sean", "Willow").  Skip them to avoid N*(N-1)/2
# edge explosion.  Adjustable per deployment.
MAX_ENTITY_FANOUT = 500


# =========================================================================
# TABLE INIT
# =========================================================================

def _init_tables(conn):
    """No-op — schema managed by pg_schema.sql."""
    return
    cur = conn.cursor()

    cur.execute("""CREATE TABLE IF NOT EXISTS knowledge_edges (
        id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        source_id INTEGER REFERENCES knowledge(id),
        target_id INTEGER REFERENCES knowledge(id),
        edge_type TEXT NOT NULL,
        weight REAL DEFAULT 1.0,
        canonical BOOLEAN DEFAULT 0,
        created_at TEXT NOT NULL,
        UNIQUE(source_id, target_id, edge_type)
    )""")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_edges_source ON knowledge_edges(source_id, edge_type)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_edges_target ON knowledge_edges(target_id, edge_type)")

    cur.execute("""CREATE TABLE IF NOT EXISTS knowledge_clusters (
        cluster_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        label TEXT NOT NULL,
        method TEXT NOT NULL,
        canonical BOOLEAN DEFAULT 0,
        created_at TEXT NOT NULL,
        atom_count INTEGER DEFAULT 0,
        centroid BLOB
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS cluster_members (
        cluster_id INTEGER REFERENCES knowledge_clusters(cluster_id),
        knowledge_id INTEGER REFERENCES knowledge(id),
        distance REAL,
        PRIMARY KEY (cluster_id, knowledge_id)
    )""")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_cm_kid ON cluster_members(knowledge_id)")

    # Add canonical column to existing tables (idempotent)
    for table in ("knowledge_edges", "knowledge_clusters"):
        try:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN canonical BOOLEAN DEFAULT 0")
        except Exception:
            pass  # Column already exists

    conn.commit()


# =========================================================================
# EDGE BUILDING
# =========================================================================

def build_edges(username: str, batch_size: int = 50) -> int:
    """
    Compute edges between knowledge atoms. Incremental.
    Returns number of new edges created.
    """
    loam.init_db(username)
    conn = loam._connect(username)
    try:
        _init_tables(conn)
        cur = conn.cursor()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        created = 0

        # Log mega-entities being skipped by the fanout guard
        mega = cur.execute("""
            SELECT e.name, COUNT(*) as cnt FROM entities e
            JOIN knowledge_entities ke ON ke.entity_id = e.id
            GROUP BY e.name HAVING COUNT(*) > ?
            ORDER BY cnt DESC
        """, (MAX_ENTITY_FANOUT,)).fetchall()
        for ename, ecnt in mega:
            log.info(f"Skipping entity {ename} (linked to {ecnt} items, exceeds fanout limit {MAX_ENTITY_FANOUT})")

        # Get atoms without edges yet
        atoms = cur.execute("""
            SELECT k.id, k.category, k.created_at, k.embedding, k.ring, k.title, k.content_snippet
            FROM knowledge k
            WHERE NOT EXISTS (SELECT 1 FROM knowledge_edges e WHERE e.source_id = k.id)
            LIMIT ?
        """, (batch_size,)).fetchall()

        if not atoms:
            return 0

        for atom_id, category, created_at, emb, ring, title, snippet in atoms:

            # 1. Shared entity edges — JOIN to knowledge guards against orphaned knowledge_entities rows
            #    Cardinality guard: exclude entities linked to > MAX_ENTITY_FANOUT items
            #    to prevent quadratic edge explosion on mega-entities.
            shared = cur.execute("""
                SELECT ke2.knowledge_id, COUNT(*) as cnt
                FROM knowledge_entities ke1
                JOIN knowledge_entities ke2 ON ke1.entity_id = ke2.entity_id
                JOIN knowledge k ON k.id = ke2.knowledge_id
                JOIN entities e ON e.id = ke1.entity_id
                WHERE ke1.knowledge_id = ? AND ke2.knowledge_id != ?
                  AND e.never_promote = 0
                  AND ke1.entity_id NOT IN (
                      SELECT entity_id FROM knowledge_entities
                      GROUP BY entity_id HAVING COUNT(*) > ?
                  )
                GROUP BY ke2.knowledge_id HAVING COUNT(*) >= 2
            """, (atom_id, atom_id, MAX_ENTITY_FANOUT)).fetchall()

            for target_id, cnt in shared:
                w = min(1.0, cnt / 5.0)
                cur.execute(
                    "INSERT OR IGNORE INTO knowledge_edges (source_id, target_id, edge_type, weight, created_at) VALUES (?,?,?,?,?)",
                    (atom_id, target_id, "shared_entity", w, now)
                )
                created += 1

            # 2. Semantic similarity edges
            if emb and embeddings.is_available():
                others = cur.execute(
                    "SELECT id, embedding FROM knowledge WHERE id != ? AND embedding IS NOT NULL", (atom_id,)
                ).fetchall()
                for tid, temb in others:
                    sim = embeddings.cosine_similarity(emb, temb)
                    if sim >= 0.75:
                        cur.execute(
                            "INSERT OR IGNORE INTO knowledge_edges (source_id, target_id, edge_type, weight, created_at) VALUES (?,?,?,?,?)",
                            (atom_id, tid, "semantic_similar", round(sim, 4), now)
                        )
                        created += 1

            # 3. Temporal edges (same day)
            try:
                dt = datetime.strptime(created_at, '%Y-%m-%d %H:%M:%S')
                day_start = dt.strftime('%Y-%m-%d 00:00:00')
                day_end = (dt + timedelta(days=1)).strftime('%Y-%m-%d 00:00:00')
                temporal = cur.execute(
                    "SELECT id FROM knowledge WHERE id != ? AND created_at >= ? AND created_at < ? LIMIT 10",
                    (atom_id, day_start, day_end)
                ).fetchall()
                for (tid,) in temporal:
                    cur.execute(
                        "INSERT OR IGNORE INTO knowledge_edges (source_id, target_id, edge_type, weight, created_at) VALUES (?,?,?,?,?)",
                        (atom_id, tid, "temporal", 0.5, now)
                    )
                    created += 1
            except ValueError:
                pass

            # 4. Ring flow edges
            next_ring = {"source": "bridge", "bridge": "continuity", "continuity": "source"}.get(ring)
            if next_ring:
                # Get this atom's entity names (excluding mega-entities)
                ent_names = [r[0] for r in cur.execute("""
                    SELECT e.name FROM entities e
                    JOIN knowledge_entities ke ON ke.entity_id = e.id
                    WHERE ke.knowledge_id = ?
                      AND e.never_promote = 0
                      AND ke.entity_id NOT IN (
                          SELECT entity_id FROM knowledge_entities
                          GROUP BY entity_id HAVING COUNT(*) > ?
                      )
                """, (atom_id, MAX_ENTITY_FANOUT)).fetchall()]

                if ent_names:
                    candidates = cur.execute(
                        "SELECT id, content_snippet FROM knowledge WHERE ring = ? AND id != ?",
                        (next_ring, atom_id)
                    ).fetchall()
                    for tid, tsnippet in candidates:
                        tsnippet_lower = (tsnippet or "").lower()
                        if any(en.lower() in tsnippet_lower for en in ent_names):
                            cur.execute(
                                "INSERT OR IGNORE INTO knowledge_edges (source_id, target_id, edge_type, weight, created_at) VALUES (?,?,?,?,?)",
                                (atom_id, tid, "ring_flow", 0.8, now)
                            )
                            created += 1

        conn.commit()
        log.info(f"Built {created} edges for {len(atoms)} atoms")

        # ΔΣ: Register gaps for weak edges (post-commit, best-effort)
        try:
            _register_edge_gaps(conn, username, now)
        except Exception as e:
            log.warning(f"Edge gap registration failed (non-fatal): {e}")

        return created
    finally:
        conn.close()


def _register_edge_gaps(conn, username: str, now: str):
    """Register acknowledged unknowns on weak edges. ΔΣ = Σ(Δᵢ)."""
    cur = conn.cursor()

    # Temporal edges (weight 0.5) — co-occurrence only, no semantic link
    temporal_edges = cur.execute("""
        SELECT id FROM knowledge_edges
        WHERE edge_type = 'temporal' AND weight <= 0.5
        AND id NOT IN (SELECT edge_id FROM edge_gaps)
        LIMIT 100
    """).fetchall()
    for (eid,) in temporal_edges:
        try:
            cur.execute(
                """INSERT INTO edge_gaps (edge_id, gap_text, gap_type, specificity,
                       registered_by, registered_at)
                   VALUES (?, 'Temporal co-occurrence only — no entity or semantic link',
                           'temporal_only', 0.7, 'topology_builder', ?)
                   ON CONFLICT(edge_id, gap_text) DO NOTHING""",
                (eid, now)
            )
        except Exception:
            pass

    # Semantic edges below high-confidence threshold
    weak_semantic = cur.execute("""
        SELECT id, weight FROM knowledge_edges
        WHERE edge_type = 'semantic_similar' AND weight < 0.80
        AND id NOT IN (SELECT edge_id FROM edge_gaps)
        LIMIT 100
    """).fetchall()
    for eid, w in weak_semantic:
        try:
            cur.execute(
                """INSERT INTO edge_gaps (edge_id, gap_text, gap_type, specificity,
                       registered_by, registered_at)
                   VALUES (?, ?, 'weak_evidence', 0.8, 'topology_builder', ?)
                   ON CONFLICT(edge_id, gap_text) DO NOTHING""",
                (eid, f'Similarity score {w:.3f} — below high-confidence threshold (0.80)', now)
            )
        except Exception:
            pass

    # Ring flow edges — inferred from text mention, not structural link
    inferred_flow = cur.execute("""
        SELECT id FROM knowledge_edges
        WHERE edge_type = 'ring_flow'
        AND id NOT IN (SELECT edge_id FROM edge_gaps)
        LIMIT 100
    """).fetchall()
    for (eid,) in inferred_flow:
        try:
            cur.execute(
                """INSERT INTO edge_gaps (edge_id, gap_text, gap_type, specificity,
                       registered_by, registered_at)
                   VALUES (?, 'Flow inferred from text mention, not structural link',
                           'inferred_not_stated', 0.6, 'topology_builder', ?)
                   ON CONFLICT(edge_id, gap_text) DO NOTHING""",
                (eid, now)
            )
        except Exception:
            pass

    conn.commit()
    gap_count = len(temporal_edges) + len(weak_semantic) + len(inferred_flow)
    if gap_count > 0:
        log.info(f"ΔΣ: Registered {gap_count} edge gaps (temporal={len(temporal_edges)}, weak_semantic={len(weak_semantic)}, flow={len(inferred_flow)})")


# =========================================================================
# CLUSTERING
# =========================================================================

def cluster_atoms(username: str, n_clusters: int = 10, method: str = "kmeans") -> List[int]:
    """Cluster atoms by embeddings. Returns list of cluster IDs created."""
    if not _SKLEARN_AVAILABLE:
        return []
    if not embeddings.is_available():
        return []

    loam.init_db(username)
    conn = loam._connect(username)
    try:
        _init_tables(conn)
        cur = conn.cursor()

        # Clear old clusters
        cur.execute("DELETE FROM cluster_members")
        cur.execute("DELETE FROM knowledge_clusters")

        rows = cur.execute(
            "SELECT id, embedding, title FROM knowledge WHERE embedding IS NOT NULL ORDER BY id"
        ).fetchall()

        if len(rows) < 3:
            return []

        n_clusters = min(n_clusters, len(rows) // 2)
        atom_ids = [r[0] for r in rows]

        # Unpack embeddings
        vecs = []
        for r in rows:
            dim = len(r[1]) // 4
            vecs.append(list(struct.unpack(f'{dim}f', r[1])))
        X = normalize(np.array(vecs))

        km = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        labels = km.fit_predict(X)

        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cluster_ids = []

        for label in range(n_clusters):
            member_ids = [atom_ids[i] for i in range(len(atom_ids)) if labels[i] == label]
            if not member_ids:
                continue

            # Label from top entities
            placeholders = ",".join(["?"] * len(member_ids))
            top_ents = cur.execute(f"""
                SELECT e.name, COUNT(*) as cnt FROM entities e
                JOIN knowledge_entities ke ON ke.entity_id = e.id
                WHERE ke.knowledge_id IN ({placeholders})
                GROUP BY e.name ORDER BY cnt DESC LIMIT 3
            """, member_ids).fetchall()

            cluster_label = ", ".join(e[0] for e in top_ents) if top_ents else f"Cluster {label}"

            # Centroid
            mask = labels == label
            centroid = X[mask].mean(axis=0)
            centroid_blob = struct.pack(f'{len(centroid)}f', *centroid)

            cur.execute(
                "INSERT INTO knowledge_clusters (label, method, created_at, atom_count, centroid) VALUES (?,?,?,?,?)",
                (cluster_label, method, now, len(member_ids), centroid_blob)
            )
            cid = cur.lastrowid
            cluster_ids.append(cid)

            for i, aid in enumerate(atom_ids):
                if labels[i] == label:
                    dist = float(np.linalg.norm(X[i] - centroid))
                    cur.execute(
                        "INSERT OR REPLACE INTO cluster_members (cluster_id, knowledge_id, distance) VALUES (?,?,?)",
                        (cid, aid, round(dist, 4))
                    )

        conn.commit()
        log.info(f"Created {len(cluster_ids)} clusters")
        return cluster_ids
    finally:
        conn.close()


# =========================================================================
# TRAVERSAL
# =========================================================================

def zoom(username: str, node_id: int, depth: int = 1) -> Dict:
    """Traverse the topology from a single atom."""
    loam.init_db(username)
    conn = loam._connect(username)
    # row_factory handled by db.py
    cur = conn.cursor()

    atom = cur.execute(
        "SELECT id, source_type, title, summary, category, ring, created_at FROM knowledge WHERE id=?",
        (node_id,)
    ).fetchone()
    if not atom:
        conn.close()
        return {"error": "Atom not found"}

    # Cluster
    cluster = cur.execute("""
        SELECT c.cluster_id, c.label, c.atom_count
        FROM knowledge_clusters c JOIN cluster_members cm ON cm.cluster_id = c.cluster_id
        WHERE cm.knowledge_id = ?
    """, (node_id,)).fetchone()

    # Edges grouped by type
    edges_by_type = defaultdict(list)
    for row in cur.execute("""
        SELECT e.target_id, e.edge_type, e.weight, k.title, k.ring
        FROM knowledge_edges e JOIN knowledge k ON k.id = e.target_id
        WHERE e.source_id = ? ORDER BY e.weight DESC
    """, (node_id,)):
        edges_by_type[row["edge_type"]].append({
            "id": row["target_id"], "title": row["title"],
            "ring": row["ring"], "weight": round(row["weight"], 3)
        })

    # Entities
    entities = [{"name": r["name"], "type": r["entity_type"]} for r in cur.execute("""
        SELECT e.name, e.entity_type FROM entities e
        JOIN knowledge_entities ke ON ke.entity_id = e.id WHERE ke.knowledge_id = ?
    """, (node_id,))]

    result = {
        "atom": dict(atom),
        "ring": atom["ring"],
        "cluster": dict(cluster) if cluster else None,
        "edges": dict(edges_by_type),
        "entities": entities,
    }

    if depth > 1:
        children = []
        for etype, elist in edges_by_type.items():
            for edge in elist[:3]:
                children.append(zoom(username, edge["id"], depth - 1))
        result["children"] = children

    conn.close()
    return result


# =========================================================================
# STRIP CONTINUITY CHECK
# =========================================================================

def check_strip_continuity(username: str) -> Dict:
    """Find atoms stuck in one ring — gaps in the Möbius strip."""
    loam.init_db(username)
    conn = loam._connect(username)
    # row_factory handled by db.py
    cur = conn.cursor()
    _init_tables(conn)

    total = cur.execute("SELECT COUNT(*) AS cnt FROM knowledge").fetchone()["cnt"]
    by_ring = {}
    for ring in ("source", "bridge", "continuity"):
        by_ring[ring] = cur.execute("SELECT COUNT(*) AS cnt FROM knowledge WHERE ring=?", (ring,)).fetchone()["cnt"]

    # Source atoms with no flow to bridge
    stuck_source = cur.execute("""
        SELECT COUNT(*) AS cnt FROM knowledge k WHERE k.ring = 'source'
        AND NOT EXISTS (SELECT 1 FROM knowledge_edges e WHERE e.source_id = k.id AND e.edge_type = 'ring_flow')
    """).fetchone()["cnt"]

    # Bridge atoms with no edges at all (isolated)
    stuck_bridge = cur.execute("""
        SELECT COUNT(*) AS cnt FROM knowledge k WHERE k.ring = 'bridge'
        AND NOT EXISTS (SELECT 1 FROM knowledge_edges e WHERE e.source_id = k.id)
    """).fetchone()["cnt"]

    # Example gaps
    gaps = []
    for row in cur.execute("""
        SELECT id, title, ring FROM knowledge k WHERE k.ring = 'source'
        AND NOT EXISTS (SELECT 1 FROM knowledge_edges e WHERE e.source_id = k.id AND e.edge_type = 'ring_flow')
        LIMIT 5
    """):
        gaps.append({"id": row["id"], "title": row["title"], "ring": "source", "reason": "No flow to bridge"})

    for row in cur.execute("""
        SELECT id, title, ring FROM knowledge k WHERE k.ring = 'bridge'
        AND NOT EXISTS (SELECT 1 FROM knowledge_edges e WHERE e.source_id = k.id)
        LIMIT 5
    """):
        gaps.append({"id": row["id"], "title": row["title"], "ring": "bridge", "reason": "Isolated (no edges)"})

    conn.close()
    return {
        "total_atoms": total,
        "by_ring": by_ring,
        "stuck_in_source": stuck_source,
        "stuck_in_bridge": stuck_bridge,
        "gaps": gaps,
    }


# =========================================================================
# RING FLOW GRAPH
# =========================================================================

def get_ring_flow_graph(username: str) -> Dict:
    """Sankey-style: nodes with counts, links with flow values."""
    loam.init_db(username)
    conn = loam._connect(username)
    cur = conn.cursor()
    _init_tables(conn)

    nodes = []
    for ring in ("source", "bridge", "continuity"):
        _row = cur.execute("SELECT COUNT(*) AS cnt FROM knowledge WHERE ring=?", (ring,)).fetchone(); cnt = _row["cnt"] if hasattr(_row, "__getitem__") and not isinstance(_row, tuple) else _row[0]
        nodes.append({"id": ring, "count": cnt})

    links = []
    for src, tgt in [("source", "bridge"), ("bridge", "continuity"), ("continuity", "source")]:
        _row = cur.execute("""
            SELECT COUNT(*) AS cnt FROM knowledge_edges e
            JOIN knowledge ks ON ks.id = e.source_id
            JOIN knowledge kt ON kt.id = e.target_id
            WHERE ks.ring = ? AND kt.ring = ? AND e.edge_type = 'ring_flow'
        """, (src, tgt)).fetchone(); cnt = _row["cnt"] if hasattr(_row, "__getitem__") and not isinstance(_row, tuple) else _row[0]
        links.append({"source": src, "target": tgt, "value": cnt})

    conn.close()
    return {"nodes": nodes, "links": links}


def get_ring_distribution(username: str) -> Dict:
    """Simple ring counts."""
    loam.init_db(username)
    conn = loam._connect(username)
    result = {}
    for ring in ("source", "bridge", "continuity"):
        _row = conn.execute("SELECT COUNT(*) AS cnt FROM knowledge WHERE ring=?", (ring,)).fetchone(); result[ring] = _row["cnt"] if hasattr(_row, "__getitem__") and not isinstance(_row, tuple) else _row[0]
    conn.close()
    return result

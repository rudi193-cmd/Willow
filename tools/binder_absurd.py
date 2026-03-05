"""
Binder: Connect the Absurd
===========================
Finds non-obvious cross-category connections in the knowledge graph.

Step 1: Entity bridges — entities that appear in 3+ different categories
Step 2: Embedding proximity — atoms from different categories with high cosine similarity
Step 3: Generate proposed knowledge_edges for human review

Run: python tools/binder_absurd.py [--dry-run]
"""

import sqlite3, struct, math, sys, json, io
from pathlib import Path
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DB = Path(__file__).parent.parent / "artifacts" / "Sweet-Pea-Rudi19" / "willow_knowledge.db"
DRY_RUN = "--dry-run" in sys.argv


def connect():
    conn = sqlite3.connect(str(DB))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.row_factory = sqlite3.Row
    return conn


def cosine(a: bytes, b: bytes) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dim = len(a) // 4
    va = struct.unpack(f'{dim}f', a)
    vb = struct.unpack(f'{dim}f', b)
    dot = sum(x * y for x, y in zip(va, vb))
    na = math.sqrt(sum(x * x for x in va))
    nb = math.sqrt(sum(x * x for x in vb))
    return dot / (na * nb) if na and nb else 0.0


# ── Step 1: Entity bridges ────────────────────────────────────────────────────

def find_entity_bridges(conn) -> list[dict]:
    """Entities that span 3+ distinct categories, connecting otherwise separate domains."""
    rows = conn.execute("""
        SELECT e.id, e.name, e.entity_type,
               COUNT(DISTINCT k.category) as cat_count,
               GROUP_CONCAT(DISTINCT k.category) as categories,
               GROUP_CONCAT(DISTINCT k.id) as atom_ids
        FROM entities e
        JOIN knowledge_entities ke ON e.id = ke.entity_id
        JOIN knowledge k ON ke.knowledge_id = k.id
        WHERE k.category NOT IN ('merged')
          AND e.name NOT IN ('Willow', 'Sean', 'Claude', 'Ganesha', 'system', 'file')
        GROUP BY e.id
        HAVING cat_count >= 3
        ORDER BY cat_count DESC, COUNT(DISTINCT k.id) DESC
        LIMIT 40
    """).fetchall()

    bridges = []
    for r in rows:
        atom_ids = [int(x) for x in r['atom_ids'].split(',')]
        cats = r['categories'].split(',')
        bridges.append({
            'entity_id': r['id'],
            'entity_name': r['name'],
            'entity_type': r['entity_type'],
            'cat_count': r['cat_count'],
            'categories': cats,
            'atom_ids': atom_ids,
        })
    return bridges


# ── Step 2: Embedding proximity across categories ─────────────────────────────

def find_cross_category_similar(conn, sample_per_cat=50, threshold=0.65) -> list[dict]:
    """
    Finds pairs of atoms from DIFFERENT categories with embedding similarity > threshold.
    Focuses on the most surprising category pairings (narrative↔code, personal↔governance, etc.)
    """
    # Load atoms with embeddings, one sample per category
    atoms_by_cat = {}
    cats = [r[0] for r in conn.execute(
        "SELECT DISTINCT category FROM knowledge WHERE category NOT IN ('merged') AND embedding IS NOT NULL"
    ).fetchall()]

    for cat in cats:
        rows = conn.execute(
            "SELECT id, title, category, embedding FROM knowledge "
            "WHERE category=? AND embedding IS NOT NULL AND category NOT IN ('merged') LIMIT ?",
            (cat, sample_per_cat)
        ).fetchall()
        atoms_by_cat[cat] = [(r['id'], r['title'], r['category'], r['embedding']) for r in rows]

    # Find surprising cross-category pairs
    # Limited to categories with high embedding coverage (>75%)
    # These are the absurd pairings: code↔personal, legal↔personal, media↔code, etc.
    ABSURD_PAIRS = [
        ('code', 'personal'),
        ('code', 'legal'),
        ('code', 'personal_document'),
        ('personal', 'legal'),
        ('personal', 'media'),
        ('personal', 'reference'),
        ('legal', 'media'),
        ('legal', 'reference'),
        ('media', 'reference'),
        ('personal_document', 'media'),
    ]

    results = []
    seen = set()
    for cat_a, cat_b in ABSURD_PAIRS:
        if cat_a not in atoms_by_cat or cat_b not in atoms_by_cat:
            continue
        for id_a, title_a, _, emb_a in atoms_by_cat[cat_a]:
            for id_b, title_b, _, emb_b in atoms_by_cat[cat_b]:
                if id_a == id_b:
                    continue
                pair_key = (min(id_a, id_b), max(id_a, id_b))
                if pair_key in seen:
                    continue
                seen.add(pair_key)
                sim = cosine(emb_a, emb_b)
                if sim >= threshold:
                    results.append({
                        'id_a': id_a, 'title_a': title_a, 'cat_a': cat_a,
                        'id_b': id_b, 'title_b': title_b, 'cat_b': cat_b,
                        'similarity': round(sim, 4),
                    })

    results.sort(key=lambda x: x['similarity'], reverse=True)
    return results[:50]


# ── Step 3: Propose edges ─────────────────────────────────────────────────────

def edge_exists(conn, src: int, tgt: int, etype: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM knowledge_edges WHERE source_id=? AND target_id=? AND edge_type=?",
        (src, tgt, etype)
    ).fetchone() is not None


def propose_edges(conn, bridges: list, similar_pairs: list) -> list[dict]:
    """Build list of new edges to create."""
    proposals = []

    # From entity bridges: connect atom pairs via shared entity
    for bridge in bridges[:15]:  # top 15 bridges
        atom_ids = bridge['atom_ids']
        cats = bridge['categories']
        # Only propose edges between atoms from different categories
        atoms_by_cat = {}
        for aid in atom_ids:
            row = conn.execute("SELECT id, category, title FROM knowledge WHERE id=?", (aid,)).fetchone()
            if row:
                atoms_by_cat.setdefault(row['category'], []).append((row['id'], row['title']))

        cat_list = [c for c in cats if c in atoms_by_cat]
        for i, cat_a in enumerate(cat_list):
            for cat_b in cat_list[i+1:]:
                # Connect the first atom from each category (representative)
                a_id, a_title = atoms_by_cat[cat_a][0]
                b_id, b_title = atoms_by_cat[cat_b][0]
                if not edge_exists(conn, a_id, b_id, 'bridge'):
                    proposals.append({
                        'source_id': a_id, 'target_id': b_id,
                        'edge_type': 'bridge',
                        'weight': 0.7,
                        'reason': f"shared entity: '{bridge['entity_name']}' ({bridge['entity_type']})",
                        'source_title': a_title, 'target_title': b_title,
                        'source_cat': cat_a, 'target_cat': cat_b,
                    })

    # From embedding similarity
    for pair in similar_pairs:
        if not edge_exists(conn, pair['id_a'], pair['id_b'], 'similar'):
            proposals.append({
                'source_id': pair['id_a'], 'target_id': pair['id_b'],
                'edge_type': 'similar',
                'weight': pair['similarity'],
                'reason': f"embedding similarity {pair['similarity']:.3f} across {pair['cat_a']}/{pair['cat_b']}",
                'source_title': pair['title_a'], 'target_title': pair['title_b'],
                'source_cat': pair['cat_a'], 'target_cat': pair['cat_b'],
            })

    return proposals


def apply_edges(conn, proposals: list) -> int:
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    applied = 0
    for p in proposals:
        try:
            conn.execute(
                "INSERT OR IGNORE INTO knowledge_edges "
                "(source_id, target_id, edge_type, weight, canonical, created_at) VALUES (?,?,?,?,0,?)",
                (p['source_id'], p['target_id'], p['edge_type'], p['weight'], now)
            )
            applied += 1
        except Exception as e:
            print(f"  SKIP {p['source_id']}→{p['target_id']}: {e}")
    conn.commit()
    return applied


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    conn = connect()

    print("=== BINDER: CONNECT THE ABSURD ===\n")

    print("Step 1: Entity bridges (3+ categories)...")
    bridges = find_entity_bridges(conn)
    print(f"  Found {len(bridges)} bridging entities\n")
    for b in bridges[:10]:
        cats = ', '.join(b['categories'])
        print(f"  '{b['entity_name']}' ({b['entity_type']}) — {b['cat_count']} cats: [{cats}]")

    print(f"\nStep 2: Cross-category embedding proximity (threshold=0.75)...")
    similar = find_cross_category_similar(conn)
    print(f"  Found {len(similar)} cross-category similar pairs\n")
    for s in similar[:10]:
        print(f"  {s['similarity']:.3f}  [{s['cat_a']}] '{s['title_a'][:35]}'")
        print(f"         [{s['cat_b']}] '{s['title_b'][:35]}'")

    print(f"\nStep 3: Generating edge proposals...")
    proposals = propose_edges(conn, bridges, similar)
    print(f"  {len(proposals)} new edges proposed\n")

    for p in proposals[:20]:
        print(f"  {p['edge_type']:8s} [{p['source_cat']}→{p['target_cat']}] "
              f"'{p['source_title'][:30]}' → '{p['target_title'][:30]}'")
        print(f"           reason: {p['reason']}")

    if DRY_RUN:
        print(f"\n[DRY RUN] Would create {len(proposals)} edges. Re-run without --dry-run to apply.")
    else:
        applied = apply_edges(conn, proposals)
        total_edges = conn.execute("SELECT COUNT(*) FROM knowledge_edges").fetchone()[0]
        print(f"\nApplied {applied} new edges. Total knowledge_edges: {total_edges:,}")

        # Update cube index after writing new edges
        try:
            from cube_indexer import index_knowledge, index_entities
            k = index_knowledge(conn)
            e = index_entities(conn)
            print(f"Cube index updated: +{k} knowledge, +{e} entities")
        except Exception as _ci_err:
            print(f"[cube_indexer] skipped: {_ci_err}")

    conn.close()


if __name__ == "__main__":
    main()

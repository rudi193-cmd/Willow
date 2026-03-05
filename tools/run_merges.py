"""
Clean entity merges — knowledge graph deduplication.
Based on dup_audit_report.md, 2026-03-03.

Merge strategy:
1. Repoint entity_connections (both sides) to canonical id, ON CONFLICT DO NOTHING
2. Repoint knowledge_entities to canonical id, ON CONFLICT DO NOTHING
3. Add old mention_count to canonical
4. Delete old entity row

SKIPPED (judgment calls / false positives):
- Ada (id 259) — NOT merged into Douglas Adams
- Gemini Willow (id 3789) — NOT merged into Willow
- Steve (id 228) / Robert Louis Stevenson — different people
- SAFE OS (id 815) — distinct concept from SAFE (id 25)
- Git (id 327) — distinct from GitHub (id 18)
- Rudi193/Kart-Llama (id 2176) — distinct model from Kart agent
- Jane Austen (id 3946) — distinct from Jane agent (id 1001)
- Briggs family (ids 1159, 1677, 1910) — different people from Riggs
- ali (id 3464) — deleted as noise entity
"""
import psycopg2
import sys

DB_URL = "postgresql://willow:willow@localhost:5437/willow"
SCHEMA = "sweet_pea_rudi19"

# canonical_id -> [old_ids to merge in]
MERGES = {
    2:    [3668, 5808, 5815, 4317, 4722, 4297, 4637],       # Sean
    19:   [3650, 3690, 3794, 3799, 4473, 4873],             # Willow
    3:    [924, 5064, 4737, 1948],                           # Die-Namic
    5:    [2051, 2725, 2788, 4503],                          # Claude (tool)
    109:  [1233, 310, 3185, 3232, 3233, 3654, 3752, 3896, 4849],  # Kart
    168:  [590, 2462, 1946, 5110, 5150],                    # UTETY
    1779: [3274, 5723, 3214],                               # Kartikeya
    1013: [603, 2475, 2860, 2887, 5151, 4988, 4701, 2476],  # Riggs
    155:  [85, 1541, 5181, 5265, 5156, 5218, 1892, 2063,    # Aionic
           3793, 3805, 4483, 4993, 4994, 5183, 538, 48,
           1559, 1558, 5005, 2065, 5169, 5171, 5296],
    959:  [183, 3523],                                       # DispatchesFromReality
    316:  [5132, 1806, 2660],                               # Python
    18:   [2980],                                            # GitHub (github.com)
    342:  [3772],                                            # Gemini (Google Gemini)
    31:   [3365],                                            # NASA
    179:  [1299, 2125, 2136, 3547, 4356],                  # LLMPhysics
    184:  [2940, 1822, 1021, 2527, 3462, 3848],            # Pharaohs MC
    2578: [5601, 3263, 5592],                               # Huggingface
    164:  [2009],                                            # Trader Joe's
    1232: [3609, 3610],                                      # Kaggle
    3131: [3133],                                            # Oracle Cloud
    198:  [5035],                                            # Ruby
    907:  [1394],                                            # ChatGPT
    25:   [2160, 2171, 2987],                               # SAFE (obvious aliases only)
}

# Pure noise — delete without merging
DELETE_NOISE = [3464]  # 'ali' — appears as false positive across many groups


def merge_entity(cur, canonical_id, old_id):
    # Get old mention count
    cur.execute("SELECT mention_count FROM entities WHERE id = %s", (old_id,))
    row = cur.fetchone()
    if not row:
        return 0  # already gone
    old_mentions = row[0]

    # Repoint entity_connections (entity_a side)
    cur.execute("""
        INSERT INTO entity_connections (entity_a_id, entity_b_id, connection_type, weight, source, created_at, confirmed)
        SELECT %s, entity_b_id, connection_type, weight, source, created_at, confirmed
        FROM entity_connections WHERE entity_a_id = %s
        ON CONFLICT DO NOTHING
    """, (canonical_id, old_id))
    cur.execute("DELETE FROM entity_connections WHERE entity_a_id = %s", (old_id,))

    # Repoint entity_connections (entity_b side)
    cur.execute("""
        INSERT INTO entity_connections (entity_a_id, entity_b_id, connection_type, weight, source, created_at, confirmed)
        SELECT entity_a_id, %s, connection_type, weight, source, created_at, confirmed
        FROM entity_connections WHERE entity_b_id = %s
        ON CONFLICT DO NOTHING
    """, (canonical_id, old_id))
    cur.execute("DELETE FROM entity_connections WHERE entity_b_id = %s", (old_id,))

    # Repoint knowledge_entities
    cur.execute("""
        INSERT INTO knowledge_entities (knowledge_id, entity_id)
        SELECT knowledge_id, %s FROM knowledge_entities WHERE entity_id = %s
        ON CONFLICT DO NOTHING
    """, (canonical_id, old_id))
    cur.execute("DELETE FROM knowledge_entities WHERE entity_id = %s", (old_id,))

    # Add mention count to canonical
    cur.execute("UPDATE entities SET mention_count = mention_count + %s WHERE id = %s",
                (old_mentions, canonical_id))

    # Delete old entity
    cur.execute("DELETE FROM entities WHERE id = %s", (old_id,))

    return old_mentions


def main():
    conn = psycopg2.connect(DB_URL)
    conn.autocommit = False
    cur = conn.cursor()
    cur.execute(f"SET search_path = {SCHEMA}, public")

    # Verify canonicals exist
    all_canonicals = list(MERGES.keys())
    cur.execute("SELECT id, name FROM entities WHERE id = ANY(%s)", (all_canonicals,))
    found = {r[0]: r[1] for r in cur.fetchall()}
    missing = [c for c in all_canonicals if c not in found]
    if missing:
        print(f"ERROR: canonical ids not found: {missing}", file=sys.stderr)
        conn.close()
        sys.exit(1)

    total_merged = 0
    total_mentions_absorbed = 0

    for canonical_id, old_ids in MERGES.items():
        canonical_name = found[canonical_id]
        group_merged = 0
        group_mentions = 0
        for old_id in old_ids:
            mentions = merge_entity(cur, canonical_id, old_id)
            group_merged += 1
            group_mentions += mentions
        total_merged += group_merged
        total_mentions_absorbed += group_mentions
        print(f"  [{canonical_id}] {canonical_name:40} <- {group_merged} merged, +{group_mentions} mentions")

    # Delete noise entities
    for noise_id in DELETE_NOISE:
        cur.execute("DELETE FROM entity_connections WHERE entity_a_id = %s OR entity_b_id = %s", (noise_id, noise_id))
        cur.execute("DELETE FROM knowledge_entities WHERE entity_id = %s", (noise_id,))
        cur.execute("DELETE FROM entities WHERE id = %s", (noise_id,))
        print(f"  [DELETED] noise entity id={noise_id}")

    conn.commit()
    conn.close()

    print(f"\n=== Merge complete ===")
    print(f"  Entities merged:    {total_merged}")
    print(f"  Mentions absorbed:  {total_mentions_absorbed}")
    print(f"  Noise deleted:      {len(DELETE_NOISE)}")
    print(f"  Net reduction:      {total_merged + len(DELETE_NOISE)} rows removed")


if __name__ == "__main__":
    main()

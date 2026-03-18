#!/usr/bin/env python3
"""
Shell 1 Backfill — Extract Relationship Edges from Corpus
==========================================================
The Source Ring (shell 1) should be the densest shell — it's Sean's corpus.
Currently 5,880 edges against a budget of 21,286 (e per atom).

The ingestion pipeline extracts ENTITIES but not RELATIONSHIPS between them.
This tool reads atoms with 2+ legitimate entities, asks the fleet to identify
relationships, and creates typed edges.

Usage:
    python tools/shell1_backfill.py                    # dry-run, show candidates
    python tools/shell1_backfill.py --extract          # extract relationships via fleet
    python tools/shell1_backfill.py --extract --apply  # extract AND create edges
    python tools/shell1_backfill.py --status           # current shell 1 state

Hydrogen Orbital Model:
    Shell 1 (Source Ring): e ≈ 2.718 connections per atom → budget ~21,286 edges
    Edge types: supports, owner, bridge, part_of, authored, creator, etc.
    These are the load-bearing connections — direct semantic relationships.

Authority: Sean Campbell
System: Willow
ΔΣ=42
"""

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "core"))
from db import get_connection

log = logging.getLogger("willow.shell1")

# Shell 1 budget from hydrogen orbital model
SHELL_1_BUDGET = 21_286

# Valid relationship types for shell 1 edges
VALID_RELATIONSHIP_TYPES = {
    "created", "creator", "created_by", "authored", "authored_by", "author_of",
    "owns", "owner", "owned_by",
    "part_of", "contains", "member_of", "component_of",
    "supports", "supported_by", "enables",
    "uses", "used_by", "powered_by", "powers",
    "builds", "built_by", "built_on",
    "serves", "served_by",
    "teaches", "teaches_at", "taught_by",
    "parent_of", "child_of", "sibling_of", "family_of",
    "friend_of", "colleague_of", "companion_of",
    "governs", "governed_by", "enforces",
    "manages", "managed_by", "administers",
    "routes_to", "connects", "bridges",
    "documents", "documented_in", "describes",
    "inspired_by", "derives_from", "extends",
    "hosts", "hosted_on", "runs_on", "deployed_in",
    "associated_with", "related_to",
    "persona_of", "voice_for", "agent_in",
    "faculty_of", "dean_of",
}

# Noise entity filter
_NOISE_ENTITY_QUERY = """
    SELECT id FROM entities
    WHERE name IN ('Sean', 'Willow')
    OR never_promote = 1
    OR id IN (SELECT entity_id FROM knowledge_entities GROUP BY entity_id HAVING count(*) > 500)
"""

# Existing shell 1 edge types (NOT these bulk types)
_BULK_EDGE_TYPES = {'shared_entity', 'ring_flow', 'semantic_similar', 'temporal'}


def get_shell1_status() -> dict:
    """Current state of shell 1 edges."""
    conn = get_connection()

    total = conn.execute(f"""
        SELECT count(*) FROM knowledge_edges
        WHERE edge_type NOT IN ('shared_entity', 'ring_flow', 'semantic_similar', 'temporal')
    """).fetchone()[0]

    by_type = conn.execute(f"""
        SELECT edge_type, count(*) FROM knowledge_edges
        WHERE edge_type NOT IN ('shared_entity', 'ring_flow', 'semantic_similar', 'temporal')
        GROUP BY edge_type ORDER BY count(*) DESC
    """).fetchall()

    atoms_with_edges = conn.execute("""
        SELECT count(DISTINCT x.atom_id) FROM (
            SELECT source_id as atom_id FROM knowledge_edges
            WHERE edge_type NOT IN ('shared_entity', 'ring_flow', 'semantic_similar', 'temporal')
            UNION
            SELECT target_id as atom_id FROM knowledge_edges
            WHERE edge_type NOT IN ('shared_entity', 'ring_flow', 'semantic_similar', 'temporal')
        ) x
    """).fetchone()[0]

    total_atoms = conn.execute("SELECT count(*) FROM knowledge").fetchone()[0]

    conn.close()
    return {
        "total_shell1_edges": total,
        "budget": SHELL_1_BUDGET,
        "gap": SHELL_1_BUDGET - total,
        "fill_pct": round(total / SHELL_1_BUDGET * 100, 1),
        "atoms_with_edges": atoms_with_edges,
        "total_atoms": total_atoms,
        "by_type": {r[0]: r[1] for r in by_type},
    }


def get_backfill_candidates(min_entities: int = 2, limit: int = 500, offset: int = 0) -> list:
    """
    Find atoms with 2+ legitimate entities that could yield relationship edges.
    Returns [(knowledge_id, title, category, summary, snippet, [(entity_name, entity_type), ...]), ...]
    """
    conn = get_connection()

    # Atoms with 2+ legit entities
    rows = conn.execute(f"""
        SELECT sub.knowledge_id, k.title, k.category, k.summary, k.content_snippet, sub.ent_count
        FROM (
            SELECT ke.knowledge_id, count(*) as ent_count
            FROM knowledge_entities ke
            WHERE ke.entity_id NOT IN ({_NOISE_ENTITY_QUERY})
            GROUP BY ke.knowledge_id
            HAVING count(*) >= ?
        ) sub
        JOIN knowledge k ON k.id = sub.knowledge_id
        ORDER BY sub.ent_count DESC
        LIMIT ?
        OFFSET ?
    """, (min_entities, limit, offset)).fetchall()

    candidates = []
    for r in rows:
        kid, title, cat, summary, snippet, ent_count = r[0], r[1], r[2], r[3], r[4], r[5]

        # Get the legitimate entities for this atom
        ents = conn.execute(f"""
            SELECT e.name, e.entity_type FROM entities e
            JOIN knowledge_entities ke ON ke.entity_id = e.id
            WHERE ke.knowledge_id = ?
            AND e.id NOT IN ({_NOISE_ENTITY_QUERY})
            ORDER BY e.mention_count DESC
        """, (kid,)).fetchall()

        candidates.append({
            "knowledge_id": kid,
            "title": title,
            "category": cat,
            "summary": summary,
            "snippet": snippet,
            "entity_count": ent_count,
            "entities": [(e[0], e[1]) for e in ents],
        })

    conn.close()
    return candidates


_fleet_initialized = False

def _init_fleet():
    global _fleet_initialized
    if not _fleet_initialized:
        import llm_router
        llm_router.load_keys_from_json()
        _fleet_initialized = True


def _extract_relationships_fleet(text: str, entities: list) -> list:
    """
    Ask fleet to identify relationships between entities in text.
    Returns [{source, target, relationship}] or empty list.
    """
    _init_fleet()
    import llm_router

    entity_list = ", ".join(f"{name} ({etype})" for name, etype in entities)

    prompt = (
        "Given this text and the entities found in it, identify the relationships between the entities.\n"
        "Return ONLY a JSON array of objects with 'source', 'target', and 'relationship' fields.\n"
        "Use simple relationship types: created, part_of, uses, teaches, parent_of, supports, manages, etc.\n"
        "Only include relationships that are clearly stated or strongly implied in the text.\n"
        "If no clear relationships exist, return [].\n\n"
        f"Entities: {entity_list}\n\n"
        f"Text: {text[:1200]}\n\n"
        "JSON:"
    )

    try:
        resp = llm_router.ask(prompt, preferred_tier="free", task_type="text_summarization")
        if resp and resp.content:
            content = resp.content.strip()
            # Handle markdown code blocks
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
                content = content.strip()
            rels = json.loads(content)
            if isinstance(rels, list):
                valid = []
                for r in rels:
                    if isinstance(r, dict) and "source" in r and "target" in r and "relationship" in r:
                        rel_type = r["relationship"].lower().strip().replace(" ", "_")
                        # Normalize to valid types
                        if rel_type not in VALID_RELATIONSHIP_TYPES:
                            # Try close matches
                            if rel_type in ("creator_of", "creates"):
                                rel_type = "created"
                            elif rel_type in ("belongs_to", "included_in"):
                                rel_type = "part_of"
                            elif rel_type in ("employs", "uses_tool"):
                                rel_type = "uses"
                            else:
                                rel_type = "associated_with"
                        valid.append({
                            "source": r["source"],
                            "target": r["target"],
                            "relationship": rel_type,
                        })
                return valid
    except (json.JSONDecodeError, Exception) as e:
        log.debug(f"Fleet relationship extraction failed: {e}")
    return []


def _find_atom_for_entity(conn, entity_name) -> int:
    """Find the entity ID for a given name. Handles bad fleet responses."""
    if not isinstance(entity_name, str):
        return None
    entity_name = entity_name.strip()
    if not entity_name or len(entity_name) > 200:
        return None
    row = conn.execute(
        "SELECT id FROM entities WHERE name = ?", (entity_name,)
    ).fetchone()
    return row[0] if row else None


def _get_atoms_for_entity(conn, entity_id: int) -> set:
    """Get all knowledge atom IDs linked to an entity."""
    rows = conn.execute(
        "SELECT knowledge_id FROM knowledge_entities WHERE entity_id = ?",
        (entity_id,)
    ).fetchall()
    return {r[0] for r in rows}


def _fresh_conn():
    """Get a fresh DB connection. Reconnects if stale."""
    conn = get_connection()
    try:
        conn.execute("SELECT 1")
    except Exception:
        conn = get_connection()
    return conn


def extract_and_create(candidates: list, apply: bool = False, max_fleet_calls: int = 200) -> dict:
    """
    Extract relationships from candidate atoms and optionally create edges.

    For each relationship found, creates an edge between a pair of atoms
    that share the source and target entities.
    """
    conn = _fresh_conn()
    now = datetime.now(timezone.utc).isoformat()

    total_relationships = 0
    total_edges_created = 0
    total_edges_existed = 0
    fleet_calls = 0
    errors = 0
    all_relationships = []

    t0 = time.time()

    for cand in candidates:
        if fleet_calls >= max_fleet_calls:
            log.info(f"Fleet call limit reached ({max_fleet_calls})")
            break

        # Build text for fleet
        text_parts = []
        if cand["title"]:
            text_parts.append(cand["title"])
        if cand["summary"]:
            text_parts.append(cand["summary"])
        if cand["snippet"]:
            text_parts.append(cand["snippet"][:500])
        text = "\n".join(text_parts)

        if len(text) < 20:
            continue

        rels = _extract_relationships_fleet(text, cand["entities"])
        fleet_calls += 1

        if fleet_calls % 20 == 0:
            elapsed = time.time() - t0
            log.info(f"  {fleet_calls} fleet calls, {total_relationships} relationships, {total_edges_created} edges ({elapsed:.0f}s)")

        for rel in rels:
            total_relationships += 1
            all_relationships.append({
                "atom_id": cand["knowledge_id"],
                "source_entity": rel["source"],
                "target_entity": rel["target"],
                "relationship": rel["relationship"],
            })

            if apply:
                # Find entity IDs for source and target
                try:
                    src_eid = _find_atom_for_entity(conn, rel["source"])
                    tgt_eid = _find_atom_for_entity(conn, rel["target"])
                except Exception:
                    conn = _fresh_conn()
                    src_eid = _find_atom_for_entity(conn, rel["source"])
                    tgt_eid = _find_atom_for_entity(conn, rel["target"])

                if not src_eid or not tgt_eid:
                    continue

                # Get atoms that contain each entity
                src_atoms = _get_atoms_for_entity(conn, src_eid)
                tgt_atoms = _get_atoms_for_entity(conn, tgt_eid)

                # Find atoms that contain the TARGET entity but NOT the source entity.
                # These are the atoms that the candidate atom "reaches" via the relationship.
                # Skip mega-entities (>500 atoms) to prevent hub creation.
                if len(tgt_atoms) > 500 or len(src_atoms) > 500:
                    continue  # mega-entity fan-out protection

                # Create at most 3 edges per relationship (closest targets first)
                # The candidate atom describes the relationship — connect it to the
                # closest target atoms (those that also contain the target entity).
                created_for_rel = 0
                MAX_EDGES_PER_REL = 3

                for tgt_atom in tgt_atoms:
                    if created_for_rel >= MAX_EDGES_PER_REL:
                        break
                    if tgt_atom == cand["knowledge_id"]:
                        continue  # no self-loops

                    # Check if edge already exists
                    existing = conn.execute(
                        "SELECT id FROM knowledge_edges WHERE source_id = ? AND target_id = ? AND edge_type = ?",
                        (cand["knowledge_id"], tgt_atom, rel["relationship"])
                    ).fetchone()

                    if existing:
                        total_edges_existed += 1
                        continue

                    try:
                        conn.execute(
                            """INSERT INTO knowledge_edges
                               (source_id, target_id, edge_type, weight, canonical, created_at)
                               VALUES (?, ?, ?, ?, 1, ?)""",
                            (cand["knowledge_id"], tgt_atom, rel["relationship"], 0.8, now)
                        )
                        total_edges_created += 1
                        created_for_rel += 1
                    except Exception as e:
                        errors += 1
                        log.debug(f"Edge creation failed: {e}")

                # Periodic budget check (every 50 edges, not every edge)
                if total_edges_created > 0 and total_edges_created % 50 == 0:
                    current_total = conn.execute("""
                        SELECT count(*) FROM knowledge_edges
                        WHERE edge_type NOT IN ('shared_entity', 'ring_flow', 'semantic_similar', 'temporal')
                    """).fetchone()[0]
                    if current_total >= SHELL_1_BUDGET:
                        log.info(f"Shell 1 budget reached ({SHELL_1_BUDGET})")
                        conn.commit()
                        conn.close()
                        return {
                            "fleet_calls": fleet_calls,
                            "relationships_found": total_relationships,
                            "edges_created": total_edges_created,
                            "edges_existed": total_edges_existed,
                            "errors": errors,
                            "budget_reached": True,
                            "elapsed": round(time.time() - t0, 1),
                        }

        # Commit every 10 atoms + refresh connection every 50
        if apply and fleet_calls % 10 == 0:
            try:
                conn.commit()
            except Exception:
                conn = _fresh_conn()
        if fleet_calls % 50 == 0:
            try:
                conn.execute("SELECT 1")
            except Exception:
                log.info("Reconnecting to DB...")
                conn = _fresh_conn()

    if apply:
        conn.commit()
    conn.close()

    elapsed = round(time.time() - t0, 1)
    log.info(f"Done: {fleet_calls} calls, {total_relationships} rels, {total_edges_created} edges, {elapsed}s")

    return {
        "fleet_calls": fleet_calls,
        "relationships_found": total_relationships,
        "edges_created": total_edges_created,
        "edges_existed": total_edges_existed,
        "errors": errors,
        "budget_reached": False,
        "elapsed": elapsed,
        "sample_relationships": all_relationships[:30],
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(description="Shell 1 backfill — extract relationship edges from corpus")
    parser.add_argument("--status", action="store_true", help="Current shell 1 state")
    parser.add_argument("--extract", action="store_true", help="Extract relationships via fleet")
    parser.add_argument("--apply", action="store_true", help="Actually create edges (default is dry-run)")
    parser.add_argument("--min-entities", type=int, default=2, help="Minimum entities per atom (default 2)")
    parser.add_argument("--limit", type=int, default=500, help="Max candidate atoms to process")
    parser.add_argument("--max-fleet", type=int, default=200, help="Max fleet calls")
    parser.add_argument("--offset", type=int, default=0, help="Skip first N candidates")
    args = parser.parse_args()

    if args.status:
        status = get_shell1_status()
        print(f"\n=== SHELL 1 STATUS ===")
        print(f"  Current edges:  {status['total_shell1_edges']:,}")
        print(f"  Budget (e×N/2): {status['budget']:,}")
        print(f"  Gap:            {status['gap']:,}")
        print(f"  Fill:           {status['fill_pct']}%")
        print(f"  Atoms with edges: {status['atoms_with_edges']:,} / {status['total_atoms']:,}")
        print(f"\n  By type:")
        for etype, count in sorted(status["by_type"].items(), key=lambda x: -x[1])[:20]:
            print(f"    {etype:25} {count:>6,}")

    elif args.extract:
        print(f"=== SHELL 1 BACKFILL {'(DRY-RUN)' if not args.apply else '(APPLYING)'} ===")

        # Get current status
        status = get_shell1_status()
        print(f"  Current: {status['total_shell1_edges']:,} / {status['budget']:,} ({status['fill_pct']}%)")
        print(f"  Gap: {status['gap']:,} edges needed\n")

        # Find candidates
        print(f"Finding atoms with {args.min_entities}+ legitimate entities...")
        candidates = get_backfill_candidates(min_entities=args.min_entities, limit=args.limit, offset=args.offset)
        print(f"  Found {len(candidates)} candidate atoms (offset={args.offset})\n")

        if not candidates:
            print("No candidates found.")
            sys.exit(0)

        # Show sample
        print("  Top candidates:")
        for c in candidates[:10]:
            ent_names = [e[0] for e in c["entities"][:5]]
            print(f"    #{c['knowledge_id']} [{c['category']}] ents={c['entity_count']} | {', '.join(ent_names)}")
        print()

        # Extract
        result = extract_and_create(candidates, apply=args.apply, max_fleet_calls=args.max_fleet)

        mode = "APPLIED" if args.apply else "DRY-RUN"
        print(f"\n=== [{mode}] RESULTS ===")
        print(f"  Fleet calls:         {result['fleet_calls']}")
        print(f"  Relationships found: {result['relationships_found']}")
        print(f"  Edges created:       {result['edges_created']}")
        print(f"  Edges existed:       {result['edges_existed']}")
        print(f"  Errors:              {result['errors']}")
        print(f"  Budget reached:      {result['budget_reached']}")
        print(f"  Time:                {result['elapsed']}s")

        if result.get("sample_relationships"):
            print(f"\n  Sample relationships:")
            for r in result["sample_relationships"][:15]:
                print(f"    atom #{r['atom_id']}: {r['source_entity']} --[{r['relationship']}]--> {r['target_entity']}")

    else:
        # Default: show candidates
        print("=== SHELL 1 BACKFILL CANDIDATES ===\n")
        candidates = get_backfill_candidates(min_entities=args.min_entities, limit=20)
        print(f"Found {len(candidates)} atoms with {args.min_entities}+ legitimate entities\n")
        for c in candidates:
            ent_names = [f"{e[0]} ({e[1]})" for e in c["entities"][:6]]
            print(f"  #{c['knowledge_id']} [{c['category']}] {c['entity_count']} entities")
            print(f"    {(c['title'] or '')[:70]}")
            print(f"    Entities: {', '.join(ent_names)}")
            print()
        print("Use --extract to run fleet extraction, --extract --apply to create edges")

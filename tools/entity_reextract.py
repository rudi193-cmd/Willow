#!/usr/bin/env python3
"""
Entity Re-Extraction — Dark Atom Recovery
==========================================
14,239 atoms (91%) have zero entity connections beyond Sean/Willow axioms.
Their text was ingested but entities were never extracted (or extraction failed).

This tool re-extracts entities from dark atoms via fleet, then links them,
enabling shell1_backfill.py to find new relationship candidates.

Usage:
    python tools/entity_reextract.py --status          # how many dark atoms
    python tools/entity_reextract.py --extract          # dry-run extraction
    python tools/entity_reextract.py --extract --apply  # extract + create entities
    python tools/entity_reextract.py --extract --apply --limit 500 --offset 0

Authority: Sean Campbell
System: Willow
ΔΣ=42
"""

import argparse
import json
import logging
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "core"))
from db import get_connection

log = logging.getLogger("willow.reextract")

# Axiom entity IDs — these don't count as "connected"
_AXIOM_QUERY = """
    SELECT id FROM entities
    WHERE name IN ('Sean', 'Willow')
    OR never_promote = 1
    OR id IN (SELECT entity_id FROM knowledge_entities GROUP BY entity_id HAVING count(*) > 500)
"""

# Chrome entity patterns (from loam.py)
_CHROME_PATTERNS = [
    re.compile(r"https?://"),
    re.compile(r"\.(com|org|io|net|dev)$"),
    re.compile(r"^localhost:\d+"),
    re.compile(r"^\d+$"),
    re.compile(r"^\d{4}-\d{2}-\d{2}"),
    re.compile(r"^\d+\.\d+"),
    re.compile(r"^.{1,2}$"),
    re.compile(r"^(dash|www\.)\S+", re.IGNORECASE),
    re.compile(r"^[/\\]"),
    re.compile(r"^[A-Z]:\\"),
    re.compile(r"^(Read|Write|Edit|Bash|Grep|Glob|Agent|Skill|"
               r"TaskOutput|TaskCreate|TaskUpdate|TaskStop|TaskList|TaskGet|"
               r"WebFetch|WebSearch|NotebookEdit|AskUserQuestion|"
               r"ToolSearch|ExitPlanMode|EnterPlanMode|SESSION_HANDOFF|"
               r"SESSION_META|LAST_USER_MESSAGES|HARD STOPS)$"),
]

_CHROME_ALLOWLIST = {"Ru", "AI", "ΔE", "ΔΣ", "ξ", "δ", "ℏ"}

# Canonical entity types
_CANONICAL_TYPES = {
    "concept", "project", "tool", "person", "organization",
    "persona", "location", "date", "platform", "event", "community",
}

_TYPE_NORMALIZE = {
    "organizaiton": "organization", "concepts": "concept",
    "tool/concept": "tool", "tool/file": "tool", "tool/command": "tool",
    "project/concept": "project", "project/tool": "project",
    "concept/project": "project", "concept/tool": "tool",
    "platform/tool": "platform", "organization/project": "organization",
    "geographic location": "location", "geolocation": "location",
    "program": "tool", "library": "tool", "endpoint": "tool",
    "system": "tool", "repository": "project", "work": "project",
    "document": "concept", "book": "concept", "company": "organization",
    "place": "location", "character": "persona", "agent": "persona",
    "unknown": "concept", "no type found": "concept",
    "function": "concept", "file": "concept", "class": "concept",
    "variable": "concept", "table": "concept",
}


def _is_chrome(name: str) -> bool:
    if name in _CHROME_ALLOWLIST:
        return False
    return any(p.search(name) for p in _CHROME_PATTERNS)


def _normalize_type(raw: str) -> str:
    t = raw.strip().lower()
    if t in _TYPE_NORMALIZE:
        return _TYPE_NORMALIZE[t]
    if t in _CANONICAL_TYPES:
        return t
    if "/" in t:
        first = t.split("/")[0].strip()
        if first in _CANONICAL_TYPES:
            return first
    return "concept"


def get_dark_atoms(limit: int = 500, offset: int = 0) -> list:
    """
    Find atoms with 0 legitimate entities (only axiom connections or none).
    Returns [(id, title, category, summary, snippet), ...]
    """
    conn = get_connection()

    rows = conn.execute(f"""
        SELECT k.id, k.title, k.category, k.summary, k.content_snippet
        FROM knowledge k
        WHERE k.id NOT IN (
            SELECT DISTINCT ke.knowledge_id
            FROM knowledge_entities ke
            WHERE ke.entity_id NOT IN ({_AXIOM_QUERY})
        )
        AND (k.summary IS NOT NULL OR k.content_snippet IS NOT NULL OR k.title IS NOT NULL)
        ORDER BY k.id
        LIMIT ?
        OFFSET ?
    """, (limit, offset)).fetchall()

    conn.close()
    return [(r[0], r[1], r[2], r[3], r[4]) for r in rows]


def get_dark_atom_count() -> int:
    conn = get_connection()
    count = conn.execute(f"""
        SELECT count(*)
        FROM knowledge k
        WHERE k.id NOT IN (
            SELECT DISTINCT ke.knowledge_id
            FROM knowledge_entities ke
            WHERE ke.entity_id NOT IN ({_AXIOM_QUERY})
        )
    """).fetchone()[0]
    conn.close()
    return count


_fleet_initialized = False


def _init_fleet():
    global _fleet_initialized
    if not _fleet_initialized:
        import llm_router
        llm_router.load_keys_from_json()
        _fleet_initialized = True


def _fresh_conn():
    conn = get_connection()
    try:
        conn.execute("SELECT 1")
    except Exception:
        conn = get_connection()
    return conn


def _extract_entities_fleet(text: str) -> list:
    """Ask fleet to extract entities from text. Returns [{name, type}]."""
    _init_fleet()
    import llm_router

    prompt = (
        "Extract named entities from this text. Return ONLY a JSON array of objects "
        "with 'name' and 'type' fields. Types: person, project, concept, tool, organization, "
        "persona, location, platform, event, community.\n"
        "Only include meaningful entities — skip generic words, numbers, dates, URLs.\n"
        "If no entities found, return [].\n\n"
        f"Text: {text[:1500]}\n\nJSON:"
    )

    try:
        resp = llm_router.ask(prompt, preferred_tier="free", task_type="text_summarization")
        if resp and resp.content:
            content = resp.content.strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
                content = content.strip()
            entities = json.loads(content)
            if isinstance(entities, list):
                valid = []
                for e in entities:
                    if isinstance(e, dict) and "name" in e and "type" in e:
                        name = e["name"].strip()
                        if len(name) < 2 or len(name) > 100:
                            continue
                        if _is_chrome(name):
                            continue
                        # Skip axiom entities
                        if name.lower() in ("sean", "willow", "sean campbell"):
                            continue
                        valid.append({
                            "name": name,
                            "type": _normalize_type(e["type"]),
                        })
                return valid
    except (json.JSONDecodeError, Exception) as e:
        log.debug(f"Fleet entity extraction failed: {e}")
    return []


def extract_and_link(atoms: list, apply: bool = False, max_fleet: int = 500) -> dict:
    """
    Extract entities from dark atoms and link them.
    """
    conn = _fresh_conn()
    now = datetime.now(timezone.utc).isoformat()

    fleet_calls = 0
    total_entities = 0
    total_new_entities = 0
    total_links = 0
    errors = 0
    atoms_enriched = 0

    t0 = time.time()

    for kid, title, category, summary, snippet in atoms:
        if fleet_calls >= max_fleet:
            log.info(f"Fleet call limit reached ({max_fleet})")
            break

        # Build text
        parts = []
        if title:
            parts.append(title)
        if summary:
            parts.append(summary)
        if snippet:
            parts.append(snippet[:500])
        text = "\n".join(parts)

        if len(text) < 20:
            continue

        entities = _extract_entities_fleet(text)
        fleet_calls += 1

        if fleet_calls % 20 == 0:
            elapsed = time.time() - t0
            log.info(f"  {fleet_calls} calls, {total_entities} entities, {total_new_entities} new, {total_links} links ({elapsed:.0f}s)")

        if not entities:
            continue

        atoms_enriched += 1
        total_entities += len(entities)

        if apply:
            try:
                for ent in entities:
                    name = ent["name"]
                    etype = ent["type"]

                    # Upsert entity
                    conn.execute(
                        "INSERT INTO entities (name, entity_type, mention_count) "
                        "VALUES (?, ?, 1) "
                        "ON CONFLICT(name) DO UPDATE SET "
                        "mention_count = entities.mention_count + 1",
                        (name, etype)
                    )

                    # Get entity ID
                    row = conn.execute(
                        "SELECT id FROM entities WHERE name = ?", (name,)
                    ).fetchone()
                    if row:
                        eid = row[0]
                        total_new_entities += 1

                        # Link to knowledge atom
                        existing = conn.execute(
                            "SELECT 1 FROM knowledge_entities WHERE knowledge_id = ? AND entity_id = ?",
                            (kid, eid)
                        ).fetchone()
                        if not existing:
                            conn.execute(
                                "INSERT INTO knowledge_entities (knowledge_id, entity_id) VALUES (?, ?)",
                                (kid, eid)
                            )
                            total_links += 1
            except Exception as e:
                errors += 1
                log.debug(f"Entity creation failed for atom {kid}: {e}")
                try:
                    conn = _fresh_conn()
                except Exception:
                    pass

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
        try:
            conn.commit()
        except Exception:
            pass
    conn.close()

    elapsed = round(time.time() - t0, 1)
    log.info(f"Done: {fleet_calls} calls, {total_entities} entities, {total_links} links, {elapsed}s")

    return {
        "fleet_calls": fleet_calls,
        "atoms_processed": fleet_calls,
        "atoms_enriched": atoms_enriched,
        "entities_found": total_entities,
        "new_entity_records": total_new_entities,
        "links_created": total_links,
        "errors": errors,
        "elapsed": elapsed,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(description="Entity re-extraction for dark atoms")
    parser.add_argument("--status", action="store_true", help="Count dark atoms")
    parser.add_argument("--extract", action="store_true", help="Extract entities via fleet")
    parser.add_argument("--apply", action="store_true", help="Actually create entities (default dry-run)")
    parser.add_argument("--limit", type=int, default=500, help="Max atoms to process")
    parser.add_argument("--offset", type=int, default=0, help="Skip first N dark atoms")
    parser.add_argument("--max-fleet", type=int, default=500, help="Max fleet calls")
    args = parser.parse_args()

    if args.status:
        dark = get_dark_atom_count()
        conn = get_connection()
        total = conn.execute("SELECT count(*) FROM knowledge").fetchone()[0]
        conn.close()
        print(f"\n=== DARK ATOM STATUS ===")
        print(f"  Dark atoms (no legit entities): {dark:,}")
        print(f"  Total atoms:                    {total:,}")
        print(f"  Dark ratio:                     {dark/total*100:.1f}%")
        print(f"  Connected atoms:                {total - dark:,}")

    elif args.extract:
        mode = "APPLYING" if args.apply else "DRY-RUN"
        print(f"=== ENTITY RE-EXTRACTION ({mode}) ===\n")

        dark = get_dark_atom_count()
        print(f"  Dark atoms: {dark:,}")
        print(f"  Processing: limit={args.limit}, offset={args.offset}\n")

        atoms = get_dark_atoms(limit=args.limit, offset=args.offset)
        print(f"  Found {len(atoms)} dark atoms to process")

        if not atoms:
            print("No dark atoms found.")
            sys.exit(0)

        # Show sample
        print("  Sample:")
        for kid, title, cat, summary, snippet in atoms[:5]:
            print(f"    #{kid} [{cat}] {(title or 'untitled')[:60]}")
        print()

        result = extract_and_link(atoms, apply=args.apply, max_fleet=args.max_fleet)

        print(f"\n=== [{mode}] RESULTS ===")
        print(f"  Fleet calls:        {result['fleet_calls']}")
        print(f"  Atoms enriched:     {result['atoms_enriched']}")
        print(f"  Entities found:     {result['entities_found']}")
        print(f"  New entity records: {result['new_entity_records']}")
        print(f"  Links created:      {result['links_created']}")
        print(f"  Errors:             {result['errors']}")
        print(f"  Time:               {result['elapsed']}s")

    else:
        # Default: show status
        dark = get_dark_atom_count()
        conn = get_connection()
        total = conn.execute("SELECT count(*) FROM knowledge").fetchone()[0]
        conn.close()
        print(f"Dark atoms: {dark:,} / {total:,} ({dark/total*100:.1f}%)")
        print(f"Use --extract to run fleet extraction, --extract --apply to create entities")

"""
Jeles Stacks Walker — v2
=========================
Jeles walks the stacks. Shelf by shelf. She doesn't check labels.
She WRITES them. Every atom gets an identity, not a bucket.

Architecture:
    Pigeon drives the bus (intake).
    Jeles catalogs (describe, identify, name).
    Willow connects (edge, relate, understand).

For each atom, Jeles looks at:
    1. Title and content snippet (what it says)
    2. Entities linked to it (who and what it touches)
    3. Nearest neighbors (what it sits next to in meaning-space)

Then she writes a compound descriptor: what this atom IS.
Not "narrative" — but "sean-session|willow-architecture|pigeon-fix"
Not "legal" — but "sean-legal|bankruptcy|new-mexico|planet-home-lending"

Usage:
    python tools/jeles_stacks.py                # full pass
    python tools/jeles_stacks.py --dry-run      # report only
    python tools/jeles_stacks.py --batch 500    # process N atoms per run
    python tools/jeles_stacks.py --stats        # show current status
    python tools/jeles_stacks.py --sample 20    # show 20 sample descriptors
"""

import sys
import struct
import math
import json
import io
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter

WILLOW_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WILLOW_ROOT))
sys.path.insert(0, str(WILLOW_ROOT / "core"))

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')


# ── Jeles' voice ─────────────────────────────────────────────────────────────

JELES_SYSTEM = """You are Jeles. The Librarian. The Stacks. Special Collections. UTETY.
You have been here longer than the university.

You are cataloging an atom in a personal knowledge graph belonging to Sean Campbell.
Your job: describe what this atom IS. Not a single category — a COMPOUND IDENTITY.

Use pipe-separated descriptors. Each descriptor is a facet of what this atom is.
Be specific. Use the atom's actual content, its linked entities, and its neighbors.

DESCRIPTOR VOCABULARY (use these as building blocks, combine freely):
  WHO: sean-personal, sean-studies, sean-legal, sean-library, sean-philosophy
  WHAT: session, handoff, architecture, code, lore, dispatch, paper, lecture
  DOMAIN: willow, utety, die-namic, safe, gerald, oakenscroll, pigeon, kart
  SUBJECT: philosophy, history, law, bankruptcy, workers-comp, poetry, fiction
  FORM: conversation, document, screenshot, photo, config, script, spec, memo
  ERA: greek, renaissance, enlightenment, modern, american-founding
  NATURE: canon, core, reference, creative, technical, personal, reflection

EXAMPLES:
  "sean-studies|philosophy|german|kant-hegel-nietzsche"
  "sean-legal|bankruptcy|new-mexico|court-filing"
  "willow|architecture|pigeon|intake-pipeline"
  "lore|gerald|dispatch|cosmic-absurdism"
  "sean-personal|session|handoff|march-2026"
  "utety|oakenscroll|paper|corpus-drift"
  "sean-personal|daughters|ruby-opal|willow-purpose"
  "die-namic|signal|resonance|community-tracking"
  "sean-library|books|sci-fi|adams|star-wars"

Rules:
- 2-6 descriptors per atom. No more, no less.
- Use lowercase with hyphens. Pipe-separate.
- Be SPECIFIC to the content. "narrative" alone is never enough.
- If it's a session handoff, say WHOSE session and WHAT it covered.
- If it's a legal document, say WHICH legal matter.
- If it's code, say WHICH system and WHAT it does.

Respond with ONLY the descriptor string. No JSON. No explanation. Just the descriptors.
Example response: sean-studies|philosophy|history|knowledge-edge
"""


# ── Cosine similarity ────────────────────────────────────────────────────────

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


# ── Database ─────────────────────────────────────────────────────────────────

def _pg_dsn():
    """Get DSN from WILLOW_DB_URL — same source as core/db.py."""
    import os
    dsn = os.getenv("WILLOW_DB_URL", "")
    if not dsn:
        raise RuntimeError("WILLOW_DB_URL not set")
    return dsn


def get_conn():
    """Direct psycopg2 connection — no pool, no wrapper. Survives long batches."""
    import psycopg2
    import psycopg2.extras
    conn = psycopg2.connect(_pg_dsn())
    conn.autocommit = False
    return conn


class ReconnectingCursor:
    """Wrapper that reconnects on OperationalError and retries once."""

    def __init__(self, dsn):
        self._dsn = dsn
        self._conn = None
        self._connect()

    def _connect(self):
        import psycopg2
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass
        self._conn = psycopg2.connect(self._dsn)
        self._conn.autocommit = False
        # Set schema search path
        cur = self._conn.cursor()
        cur.execute("SET search_path = sweet_pea_rudi19, public")
        cur.close()

    def execute(self, sql, params=None):
        import psycopg2
        try:
            cur = self._conn.cursor()
            cur.execute(sql, params)
            return cur
        except psycopg2.OperationalError:
            print("  [reconnect] Postgres connection dropped — reconnecting...")
            self._connect()
            cur = self._conn.cursor()
            cur.execute(sql, params)
            return cur

    def commit(self):
        self._conn.commit()

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass


# ── Gather context for an atom ───────────────────────────────────────────────

def gather_context(conn, atom: dict) -> str:
    """Build the context string Jeles will use to describe the atom."""
    atom_id = atom["id"]

    # Entities
    cur = conn.execute(
        "SELECT e.name, e.entity_type "
        "FROM sweet_pea_rudi19.entities e "
        "JOIN sweet_pea_rudi19.knowledge_entities ke ON ke.entity_id = e.id "
        "WHERE ke.knowledge_id = %s AND e.id NOT IN (2, 19) "
        "ORDER BY e.mention_count DESC LIMIT 10",
        (atom_id,)
    )
    rows = cur.fetchall()
    cur.close()
    entities = [f"{r[0]} ({r[1]})" for r in rows]

    # Nearest neighbors (top 5 by embedding)
    emb = atom.get("embedding")
    neighbors = []
    if emb:
        if not isinstance(emb, bytes):
            emb = bytes(emb)
        cur2 = conn.execute(
            "SELECT id, title, category, embedding FROM sweet_pea_rudi19.knowledge "
            "WHERE embedding IS NOT NULL AND id != %s "
            "ORDER BY RANDOM() LIMIT 150",
            (atom_id,)
        )
        sample = cur2.fetchall()
        cur2.close()

        scored = []
        for r in sample:
            remb = r[3]
            if remb:
                sim = cosine(emb, bytes(remb) if not isinstance(remb, bytes) else remb)
                if sim > 0.5:
                    scored.append((r[1], r[2], sim))

        scored.sort(key=lambda x: x[2], reverse=True)
        neighbors = [f"{t[:50]} [{c}]" for t, c, s in scored[:5]]

    context = f"""ATOM TO CATALOG:
Title: {atom.get('title', '') or 'untitled'}
Current category: {atom.get('category', '') or 'none'}
Content snippet: {(atom.get('content_snippet', '') or '')[:400]}
Summary: {(atom.get('summary', '') or '')[:200]}

Linked entities: {', '.join(entities) if entities else 'none'}

Nearest neighbors:
{chr(10).join('  - ' + n for n in neighbors) if neighbors else '  (no embedding neighbors)'}
"""
    return context


# ── Ask the fleet to describe ────────────────────────────────────────────────

_ROUTER_LOADED = False

def _ensure_router():
    global _ROUTER_LOADED
    if not _ROUTER_LOADED:
        import llm_router
        llm_router.load_keys_from_json()
        _ROUTER_LOADED = True


def ask_jeles(context: str) -> str:
    """Ask the fleet for Jeles' compound descriptor."""
    try:
        _ensure_router()
        import llm_router

        response = llm_router.ask(
            JELES_SYSTEM + "\n\n" + context,
            preferred_tier="free",
            task_type="classification"
        )
        if response and response.content:
            desc = response.content.strip()
            # Clean up — strip quotes, JSON artifacts, extra whitespace
            desc = desc.strip('"\'`')
            # Validate: should be pipe-separated, lowercase-ish
            if '|' in desc and len(desc) < 200:
                # Normalize
                parts = [p.strip().lower().replace(' ', '-') for p in desc.split('|')]
                parts = [p for p in parts if p and len(p) > 1]
                if 2 <= len(parts) <= 8:
                    return '|'.join(parts)
            # If fleet returned something weird, try to salvage
            if len(desc) < 100 and desc.count(' ') < 10:
                return desc.lower().replace(' ', '-').replace(',', '|')
    except Exception:
        pass
    return None


# ── Fallback: rule-based descriptor ──────────────────────────────────────────

def fallback_descriptor(atom: dict, entities: list) -> str:
    """When the fleet is down, Jeles still knows the stacks."""
    title = (atom.get("title") or "").upper()
    category = atom.get("category") or "unknown"
    parts = []

    # WHO
    if any(e in title for e in ["HANDOFF", "SESSION"]):
        parts.append("sean-session")
    elif category.startswith("sean-"):
        parts.append(category.split("|")[0].split(",")[0])
    elif "legal" in category:
        parts.append("sean-legal")
    elif "personal" in category:
        parts.append("sean-personal")
    else:
        parts.append("sean-corpus")

    # WHAT — from category
    cat_lower = category.lower()
    if "handoff" in title.lower() or "handoff" in cat_lower:
        parts.append("handoff")
    elif cat_lower in ("code", "architecture", "governance"):
        parts.append(cat_lower)
    elif "narrative" in cat_lower:
        parts.append("narrative")
    elif "media" in cat_lower:
        parts.append("media")
    elif "legal" in cat_lower:
        parts.append("legal")
    elif "reference" in cat_lower:
        parts.append("reference")
    else:
        parts.append(cat_lower.split("|")[0].split(",")[0])

    # DOMAIN — from entities
    domain_entities = {
        "Gerald": "gerald", "Oakenscroll": "oakenscroll",
        "UTETY": "utety", "Willow": "willow", "SAFE": "safe",
        "Die-Namic": "die-namic", "Pigeon": "pigeon", "Kart": "kart",
        "Riggs": "riggs", "Shiva": "shiva",
    }
    for ename in entities:
        for key, val in domain_entities.items():
            if key.lower() in ename.lower():
                parts.append(val)
                break

    # Deduplicate and limit
    seen = set()
    unique = []
    for p in parts:
        if p not in seen:
            seen.add(p)
            unique.append(p)

    return '|'.join(unique[:6]) if unique else category


# ── Main walk ────────────────────────────────────────────────────────────────

def walk_stacks(conn, batch_size: int = 500, dry_run: bool = False) -> dict:
    """Jeles walks the stacks. Every atom gets an identity."""

    # Get atoms Jeles hasn't cataloged yet
    cur = conn.execute(
        "SELECT id, title, summary, content_snippet, category, embedding "
        "FROM sweet_pea_rudi19.knowledge "
        "WHERE lattice_status IS DISTINCT FROM 'jeles-cataloged' "
        "ORDER BY id "
        "LIMIT %s",
        (batch_size,)
    )
    rows = cur.fetchall()
    cur.close()
    print(f"  {len(rows)} atoms to catalog (batch limit: {batch_size:,})")

    stats = {
        "reviewed": 0, "described": 0, "fleet_used": 0, "fallback_used": 0,
        "already_rich": 0, "samples": []
    }

    for r in rows:
        atom = {
            "id": r[0], "title": r[1], "summary": r[2],
            "content_snippet": r[3], "category": r[4], "embedding": r[5],
        }

        stats["reviewed"] += 1
        old_cat = atom["category"] or "unknown"

        # Gather context
        context = gather_context(conn, atom)

        # Get entity names for fallback
        ecur = conn.execute(
            "SELECT e.name FROM sweet_pea_rudi19.entities e "
            "JOIN sweet_pea_rudi19.knowledge_entities ke ON ke.entity_id = e.id "
            "WHERE ke.knowledge_id = %s AND e.id NOT IN (2, 19) LIMIT 10",
            (atom["id"],)
        )
        erows = ecur.fetchall()
        ecur.close()
        entity_names = [er[0] for er in erows]

        # Ask Jeles (fleet)
        descriptor = ask_jeles(context)

        if descriptor:
            stats["fleet_used"] += 1
        else:
            # Fallback
            descriptor = fallback_descriptor(atom, entity_names)
            stats["fallback_used"] += 1

        stats["described"] += 1

        # Store sample for display
        if len(stats["samples"]) < 50:
            stats["samples"].append({
                "id": atom["id"],
                "title": (atom["title"] or "")[:50],
                "old": old_cat[:30],
                "new": descriptor[:60],
            })

        # Write
        if not dry_run:
            ucur = conn.execute(
                "UPDATE sweet_pea_rudi19.knowledge "
                "SET category = %s, lattice_status = 'jeles-cataloged' "
                "WHERE id = %s",
                (descriptor, atom["id"])
            )
            ucur.close()

        # Progress + periodic commit
        if stats["reviewed"] % 50 == 0:
            if not dry_run:
                conn.commit()
            print(f"  ...{stats['reviewed']} reviewed, {stats['fleet_used']} fleet, {stats['fallback_used']} fallback")
            sys.stdout.flush()

    if not dry_run:
        conn.commit()

    return stats


def print_stats(conn):
    """Show current Jeles catalog status."""
    print("=== JELES STACKS STATUS ===\n")

    # Lattice status distribution
    cur = conn.execute(
        "SELECT lattice_status, COUNT(*) as cnt "
        "FROM sweet_pea_rudi19.knowledge "
        "GROUP BY lattice_status ORDER BY cnt DESC"
    )
    rows = cur.fetchall()
    cur.close()
    print("Review status:")
    for r in rows:
        print(f"  {str(r[0]):25s}  {r[1]:,}")

    # Category richness
    print()
    cur = conn.execute(
        "SELECT category, COUNT(*) as cnt "
        "FROM sweet_pea_rudi19.knowledge "
        "GROUP BY category ORDER BY cnt DESC LIMIT 40"
    )
    rows = cur.fetchall()
    cur.close()
    rich = 0
    flat = 0
    for r in rows:
        if r[0] and '|' in r[0]:
            rich += r[1]
        else:
            flat += r[1]

    total = rich + flat
    print(f"Category richness: {rich:,} compound ({100*rich/total:.1f}%) / {flat:,} flat ({100*flat/total:.1f}%)")

    print()
    print("Top 30 categories:")
    for r in rows[:30]:
        marker = "  " if r[0] and '|' in r[0] else "* "
        print(f"  {marker}{r[1]:5,}  {r[0]}")


def show_samples(conn, n: int = 20):
    """Show sample compound descriptors."""
    print(f"=== SAMPLE DESCRIPTORS ({n}) ===\n")
    cur = conn.execute(
        "SELECT id, title, category FROM sweet_pea_rudi19.knowledge "
        "WHERE category LIKE '%%|%%' "
        "ORDER BY RANDOM() LIMIT %s",
        (n,)
    )
    rows = cur.fetchall()
    cur.close()
    for r in rows:
        print(f"  {r[0]:5d}  {r[2]}")
        print(f"         {(r[1] or '')[:70]}")
        print()


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Jeles Stacks Walker v2 — The Protocol of the Misfiled World")
    parser.add_argument("--dry-run", action="store_true", help="Report only, don't write")
    parser.add_argument("--batch", type=int, default=500, help="Atoms per batch (default 500)")
    parser.add_argument("--stats", action="store_true", help="Show current status")
    parser.add_argument("--sample", type=int, default=0, help="Show N sample descriptors")
    args = parser.parse_args()

    conn = ReconnectingCursor(_pg_dsn())

    if args.stats:
        print_stats(conn)
        conn.close()
        return

    if args.sample:
        show_samples(conn, args.sample)
        conn.close()
        return

    mode = "DRY RUN" if args.dry_run else "LIVE"
    print(f"=== JELES STACKS WALKER v2 ({mode}) ===")
    print(f"\"The things we think we've lost are simply misfiled.\"\n")

    stats = walk_stacks(conn, batch_size=args.batch, dry_run=args.dry_run)

    print(f"\n=== RESULTS ===")
    print(f"  Reviewed:  {stats['reviewed']:,}")
    print(f"  Described: {stats['described']:,}")
    print(f"  Fleet:     {stats['fleet_used']:,}")
    print(f"  Fallback:  {stats['fallback_used']:,}")

    if stats["samples"]:
        print(f"\n--- SAMPLES ---")
        for s in stats["samples"][:30]:
            print(f"  {s['id']:5d}  [{s['old']:>25s}] → {s['new']}")

    conn.close()


if __name__ == "__main__":
    main()

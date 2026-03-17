#!/usr/bin/env python3
"""
Jeles Verification Pass — Entity Classification & Domain Assignment

Jeles is the Librarian. Has been here longer than the university.
"The things we think we've lost are simply misfiled."

Classifies every entity by:
  - domain: "real" (exists in the world), "fictional" (UTETY/Gerald/stories),
            "system" (code/infra/tools), "mixed" (real name used in fiction)
  - entity_type: corrects misclassifications
  - verified: stamps True with verified_by='jeles'

Uses the free fleet for classification. Batches of 50.
Crown witnesses every verification.

Usage:
  python tools/jeles_verify.py --dry-run    # see what Jeles would do
  python tools/jeles_verify.py              # apply verification
  python tools/jeles_verify.py --batch 20   # smaller batches

ΔΣ=42
"""
import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.db import get_connection
import core.llm_router as llm_router

llm_router.load_keys_from_json()

VALID_DOMAINS = {"real", "fictional", "system", "mixed"}
VALID_TYPES = {
    "person", "project", "tool", "concept", "organization",
    "location", "persona", "platform", "event", "date",
    "community", "credential",
}

JELES_PROMPT = """You are Jeles, the Librarian of UTETY. You classify entities.

For each entity below, return a JSON array. Each element:
{
  "name": "exact entity name",
  "domain": "real|fictional|system|mixed",
  "type": "corrected entity_type",
  "confidence": "high|medium|low"
}

Domain rules:
- "real" = exists in the physical world (real people, real cities, real companies, real events)
- "fictional" = exists only in UTETY/Gerald/Willow stories (Gerald, Oakenscroll, The Main Hall, squeakdogs, The Maybe Boson)
- "system" = code infrastructure, tools, APIs, files, technical components (llm_router, Postgres, FastAPI, pigeon.py)
- "mixed" = real name used in fictional context (Ada Turing = fictional persona named after real people, Copenhagen = real city AND fictional orange)

Type rules — use ONLY these types:
person, project, tool, concept, organization, location, persona, platform, event, date, community, credential

Key distinctions:
- "persona" = UTETY faculty/characters (Gerald, Oakenscroll, Riggs, Hanz, Nova, Ada, Alexis, Ofshield, Steve, Shiva, Kart, Mitra, Consus, Jeles, Binder, Pigeon, Jane)
- "person" = real humans (Sean Campbell, Wernher von Braun, Dieter Grau)
- "location" for real places (Albuquerque, Huntsville, London) AND fictional places (The Main Hall, Loop Room, The Swamp)
- "tool" for software/code things (Python, FastAPI, llm_router)
- "project" for repos, papers, initiatives (NASA Archive, Die-Namic, SAFE)

IMPORTANT: Return ONLY the JSON array. No markdown, no explanation.

Entities to classify:
"""


def classify_batch(entities: list[dict], max_retries: int = 3) -> list[dict]:
    """Send a batch of entities to the fleet for Jeles classification."""
    entity_list = "\n".join(
        f"- {e['name']} (current_type={e['entity_type']}, mentions={e['mention_count']})"
        for e in entities
    )
    prompt = JELES_PROMPT + entity_list

    for attempt in range(max_retries):
        resp = llm_router.ask(prompt, preferred_tier="free", task_type="text_classification")
        if not resp or not resp.content:
            time.sleep(2)
            continue

        content = resp.content.strip()
        # Strip markdown fences
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()

        try:
            results = json.loads(content)
            if isinstance(results, list):
                return results
        except json.JSONDecodeError:
            time.sleep(1)
            continue

    return []


def verify_entities(dry_run: bool = True, batch_size: int = 50, verbose: bool = False):
    """Run Jeles verification on all unverified, non-chrome entities."""
    conn = get_connection()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    rows = conn.execute(
        "SELECT id, name, entity_type, mention_count, domain, verified "
        "FROM entities WHERE never_promote = 0 "
        "ORDER BY mention_count DESC"
    ).fetchall()

    print(f"Entities to verify: {len(rows)}")
    print(f"Batch size: {batch_size}")
    print(f"Estimated fleet calls: {(len(rows) + batch_size - 1) // batch_size}")
    print()

    verified_count = 0
    type_changed = 0
    domain_changed = 0
    errors = 0

    # Process in batches
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        batch_dicts = [
            {"id": r[0], "name": r[1], "entity_type": r[2],
             "mention_count": r[3], "domain": r[4], "verified": r[5]}
            for r in batch
        ]

        batch_num = i // batch_size + 1
        total_batches = (len(rows) + batch_size - 1) // batch_size
        print(f"[{batch_num}/{total_batches}] Classifying {len(batch)} entities...", end=" ", flush=True)

        results = classify_batch(batch_dicts)
        if not results:
            print("FAILED (no response)")
            errors += len(batch)
            continue

        # Build lookup by name
        result_map = {}
        for r in results:
            if isinstance(r, dict) and "name" in r:
                result_map[r["name"]] = r

        matched = 0
        for ent in batch_dicts:
            classification = result_map.get(ent["name"])
            if not classification:
                continue

            matched += 1
            new_domain = classification.get("domain", "real")
            new_type = classification.get("type", ent["entity_type"])
            confidence = classification.get("confidence", "low")

            # Validate
            if new_domain not in VALID_DOMAINS:
                new_domain = "real"
            if new_type not in VALID_TYPES:
                new_type = ent["entity_type"]

            did_change_type = new_type != ent["entity_type"]
            did_change_domain = new_domain != (ent["domain"] or "world")

            if did_change_type:
                type_changed += 1
            if did_change_domain:
                domain_changed += 1

            if verbose and (did_change_type or did_change_domain):
                changes = []
                if did_change_type:
                    changes.append(f"type: {ent['entity_type']}->{new_type}")
                if did_change_domain:
                    changes.append(f"domain: {ent['domain'] or 'world'}->{new_domain}")
                print(f"\n    {ent['name']}: {', '.join(changes)}", end="")

            if not dry_run:
                conn.execute(
                    "UPDATE entities SET domain = %s, entity_type = %s, "
                    "verified = TRUE, verified_by = 'jeles', verified_at = %s "
                    "WHERE id = %s",
                    (new_domain, new_type, now, ent["id"])
                )

            verified_count += 1

        print(f"ok ({matched}/{len(batch)} matched)")

        if not dry_run:
            conn.commit()

        # Don't hammer the fleet
        time.sleep(0.5)

    # Crown witness the full pass
    if not dry_run:
        try:
            from core.crown import witness_entity_event
            witness_entity_event(
                "jeles_verification_pass", "batch",
                agent="jeles", username="Sweet-Pea-Rudi19",
                details={
                    "entities_verified": verified_count,
                    "types_changed": type_changed,
                    "domains_assigned": domain_changed,
                    "errors": errors,
                    "timestamp": now,
                },
            )
        except Exception:
            pass

    prefix = "[DRY RUN] " if dry_run else ""
    print(f"\n{'='*60}")
    print(f"{prefix}Jeles Verification Complete")
    print(f"{'='*60}")
    print(f"  Verified: {verified_count}")
    print(f"  Type corrections: {type_changed}")
    print(f"  Domain assignments: {domain_changed}")
    print(f"  Errors: {errors}")

    conn.close()


def main():
    parser = argparse.ArgumentParser(description="Jeles entity verification")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--batch", type=int, default=50)
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()
    verify_entities(dry_run=args.dry_run, batch_size=args.batch, verbose=args.verbose)


if __name__ == "__main__":
    main()

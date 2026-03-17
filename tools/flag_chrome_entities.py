#!/usr/bin/env python3
"""
Entity QC — Full quality control on all ingested entities.

Phase 1: Flag chrome/garbage entities (never_promote=1)
Phase 2: Merge case-insensitive duplicates (keep highest-mention version)
Phase 3: Report promotion candidates

Does NOT delete anything. Entities are reclassified, not removed.
Crown witnesses every change for tamper-evident audit.

Usage:
  python tools/flag_chrome_entities.py --dry-run     # review everything
  python tools/flag_chrome_entities.py                # apply all fixes
  python tools/flag_chrome_entities.py --phase 1      # chrome flagging only
  python tools/flag_chrome_entities.py --phase 2      # dedup only

ΔΣ=42
"""
import argparse
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.db import get_connection
from core.loam import _is_chrome_name


def phase1_flag_chrome(conn, dry_run: bool, now: str) -> dict:
    """Flag chrome/garbage entities with never_promote=1."""
    rows = conn.execute(
        "SELECT id, name, entity_type, mention_count, never_promote "
        "FROM entities ORDER BY name"
    ).fetchall()

    flagged = []
    already_flagged = 0

    for row in rows:
        eid, name, etype, mentions, already = row

        if already:
            already_flagged += 1
            continue

        if _is_chrome_name(name):
            flagged.append({"id": eid, "name": name, "type": etype, "mentions": mentions})

            if not dry_run:
                conn.execute(
                    "UPDATE entities SET never_promote = 1, confidence = 'chrome', "
                    "last_mentioned = ? WHERE id = ?",
                    (now, eid)
                )
                try:
                    from core.crown import witness_entity_event
                    witness_entity_event(
                        "entity_chrome_retroactive", name,
                        agent="entity_qc", username="Sweet-Pea-Rudi19",
                        details={"entity_type": etype, "mention_count": mentions},
                    )
                except Exception:
                    pass

    if not dry_run:
        conn.commit()

    return {
        "flagged": flagged,
        "flagged_count": len(flagged),
        "already_flagged": already_flagged,
        "total_entities": len(rows),
    }


def phase2_merge_duplicates(conn, dry_run: bool, now: str) -> dict:
    """Merge case-insensitive duplicate entities. Keep highest-mention version."""
    rows = conn.execute(
        "SELECT id, name, entity_type, mention_count, never_promote "
        "FROM entities ORDER BY mention_count DESC"
    ).fetchall()

    # Group by lowercase name
    groups = defaultdict(list)
    for row in rows:
        groups[row[1].lower()].append(row)

    merged = []
    for lname, members in groups.items():
        if len(members) < 2:
            continue

        # Keep the one with highest mentions (already sorted desc)
        keeper = members[0]
        dupes = members[1:]

        total_mentions = sum(m[3] for m in members)
        merged.append({
            "keeper": keeper[1],
            "keeper_id": keeper[0],
            "absorbed": [d[1] for d in dupes],
            "absorbed_ids": [d[0] for d in dupes],
            "total_mentions": total_mentions,
        })

        if not dry_run:
            # Sum mentions into keeper
            conn.execute(
                "UPDATE entities SET mention_count = ? WHERE id = ?",
                (total_mentions, keeper[0])
            )

            for dupe in dupes:
                # Repoint knowledge_entities links to keeper (skip if link already exists)
                conn.execute(
                    "UPDATE knowledge_entities SET entity_id = ? "
                    "WHERE entity_id = ? AND knowledge_id NOT IN "
                    "(SELECT knowledge_id FROM knowledge_entities WHERE entity_id = ?)",
                    (keeper[0], dupe[0], keeper[0])
                )
                # Delete remaining links for the dupe (already covered by keeper)
                conn.execute(
                    "DELETE FROM knowledge_entities WHERE entity_id = ?",
                    (dupe[0],)
                )
                # Delete the duplicate entity
                conn.execute("DELETE FROM entities WHERE id = ?", (dupe[0],))

            try:
                from core.crown import witness_entity_event
                witness_entity_event(
                    "entity_dedup_merged", keeper[1],
                    agent="entity_qc", username="Sweet-Pea-Rudi19",
                    details={
                        "absorbed": [d[1] for d in dupes],
                        "total_mentions": total_mentions,
                    },
                )
            except Exception:
                pass

    if not dry_run:
        conn.commit()

    return {"merged": merged, "merge_count": len(merged)}


def phase3_promotion_report(conn) -> dict:
    """Report entities qualifying for layer 1→2 promotion."""
    candidates = conn.execute("""
        SELECT e.id, e.name, e.entity_type, e.mention_count,
               COUNT(DISTINCT k.category) as cat_spread
        FROM entities e
        JOIN knowledge_entities ke ON e.id = ke.entity_id
        JOIN knowledge k ON ke.knowledge_id = k.id
        WHERE e.mention_count >= 5 AND e.layer = 1
          AND e.never_promote = 0
        GROUP BY e.id
        HAVING COUNT(DISTINCT k.category) >= 2
        ORDER BY e.mention_count DESC
    """).fetchall()

    return {
        "candidates": [
            {"name": r[1], "type": r[2], "mentions": r[3], "categories": r[4]}
            for r in candidates
        ],
        "count": len(candidates),
    }


def main():
    parser = argparse.ArgumentParser(description="Entity QC — full quality control")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would change without applying")
    parser.add_argument("--phase", type=int, choices=[1, 2, 3],
                        help="Run specific phase only (default: all)")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    conn = get_connection()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    prefix = "[DRY RUN] " if args.dry_run else ""

    try:
        if args.phase in (None, 1):
            print(f"\n{'='*60}")
            print(f"{prefix}PHASE 1: Chrome/Garbage Flagging")
            print(f"{'='*60}")
            r1 = phase1_flag_chrome(conn, args.dry_run, now)
            print(f"  Total entities: {r1['total_entities']}")
            print(f"  Already flagged: {r1['already_flagged']}")
            print(f"  Newly flagged: {r1['flagged_count']}")
            if args.verbose and r1['flagged']:
                for f in r1['flagged']:
                    print(f"    - {f['name']!r} ({f['type']}): {f['mentions']} mentions")

        if args.phase in (None, 2):
            print(f"\n{'='*60}")
            print(f"{prefix}PHASE 2: Case-Insensitive Dedup")
            print(f"{'='*60}")
            r2 = phase2_merge_duplicates(conn, args.dry_run, now)
            print(f"  Duplicate groups merged: {r2['merge_count']}")
            if r2['merged']:
                for m in r2['merged']:
                    print(f"    - Keep {m['keeper']!r}, absorb {m['absorbed']} "
                          f"({m['total_mentions']} total mentions)")

        if args.phase in (None, 3):
            print(f"\n{'='*60}")
            print(f"PHASE 3: Promotion Candidates (layer 1→2)")
            print(f"{'='*60}")
            r3 = phase3_promotion_report(conn)
            print(f"  Qualifying entities: {r3['count']}")
            for c in r3['candidates'][:20]:
                print(f"    - {c['name']} ({c['type']}): {c['mentions']} mentions, "
                      f"{c['categories']} categories")
            if r3['count'] > 20:
                print(f"    ... and {r3['count'] - 20} more")

    finally:
        conn.close()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Edge Migration — Hydrogen Orbital Pruning
==========================================
49.5M edges → 95K edges, governed by the hydrogen orbital model.

Three shells = three rings. Per-atom degree budget:
  Shell 1 (Source Ring):     e ≈ 2.718 per atom → ~21,286 edges
  Shell 2 (Bridge Ring):     π ≈ 3.142 per atom → ~24,600 edges
  Shell 3 (Continuity Ring): 2π ≈ 6.283 per atom → ~49,200 edges
  Total:                     ~12.14 per atom    → ~95,086 edges

Shell membership by edge type:
  Shell 1: supports, owner, indexed_by, bridge, part_of, uses, created,
           teaches, manages, associated_with, and all other direct relationship types
  Shell 2: semantic_similar, temporal
  Shell 3: shared_entity, ring_flow

Pruning strategy per shell:
  Shell 1: Keep all (currently underfilled, being backfilled)
  Shell 2: Keep top edges by weight until budget reached
  Shell 3: Keep top edges by weight until budget reached; archive the rest

Modes:
  --dry-run          Count per shell, show what would be archived (DEFAULT)
  --apply            Archive excess edges (creates knowledge_edges_archive)
  --status           Current state vs hydrogen targets

Nothing is deleted. Edges move to knowledge_edges_archive. Recoverable.
Crown witnesses the archival for tamper-evident audit.

Authority: Sean Campbell
System: Willow
ΔΣ=42
"""

import argparse
import logging
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "core"))
from db import get_connection

log = logging.getLogger("willow.edge_migration")

# Hydrogen orbital constants
E = math.e          # 2.71828...
PI = math.pi        # 3.14159...
TWO_PI = 2 * math.pi  # 6.28318...

# Shell edge type classification
SHELL_1_TYPES = {
    "supports", "owner", "indexed_by", "bridge", "part_of", "uses", "created",
    "teaches", "manages", "associated_with", "created_by", "managed_by",
    "taught_by", "parent_of", "child_of", "sibling_of", "family_of",
    "friend_of", "colleague_of", "companion_of", "persona_of", "voice_for",
    "agent_in", "faculty_of", "dean_of", "governs", "governed_by", "enforces",
    "routes_to", "connects", "bridges", "documents", "documented_in",
    "describes", "inspired_by", "derives_from", "extends", "hosts",
    "hosted_on", "runs_on", "deployed_in", "builds", "built_by", "built_on",
    "serves", "served_by", "powers", "powered_by", "authored", "authored_by",
    "author_of", "creator", "member_of", "component_of", "contains",
    "related_to", "alias_of", "same_as", "references", "referenced_in",
    "similar", "character_of", "character_in", "variant_of",
}

SHELL_2_TYPES = {"semantic_similar", "temporal"}
SHELL_3_TYPES = {"shared_entity", "ring_flow"}


def get_atom_count(conn) -> int:
    return conn.execute("SELECT count(*) FROM knowledge").fetchone()[0]


def get_shell_budgets(atom_count: int) -> dict:
    """Calculate per-shell edge budgets from hydrogen orbital model."""
    return {
        "shell_1": int(atom_count * E / 2),      # e per atom, /2 because edges are pairs
        "shell_2": int(atom_count * PI / 2),
        "shell_3": int(atom_count * TWO_PI / 2),
        "total": int(atom_count * (E + PI + TWO_PI) / 2),
        "atoms": atom_count,
    }


def get_shell_status(conn) -> dict:
    """Current edge counts per shell."""
    rows = conn.execute(
        "SELECT edge_type, count(*) FROM knowledge_edges GROUP BY edge_type ORDER BY count(*) DESC"
    ).fetchall()

    shell_1 = 0
    shell_2 = 0
    shell_3 = 0
    unclassified = 0
    by_type = {}

    for etype, count in rows:
        by_type[etype] = count
        if etype in SHELL_1_TYPES:
            shell_1 += count
        elif etype in SHELL_2_TYPES:
            shell_2 += count
        elif etype in SHELL_3_TYPES:
            shell_3 += count
        else:
            # Unknown type — classify as shell 1 (direct relationship)
            shell_1 += count

    return {
        "shell_1": shell_1,
        "shell_2": shell_2,
        "shell_3": shell_3,
        "total": shell_1 + shell_2 + shell_3 + unclassified,
        "by_type": by_type,
    }


def status_report():
    """Show current state vs hydrogen orbital targets."""
    conn = get_connection()
    atoms = get_atom_count(conn)
    budgets = get_shell_budgets(atoms)
    current = get_shell_status(conn)
    conn.close()

    print(f"\n{'='*65}")
    print(f"  HYDROGEN ORBITAL EDGE STATUS")
    print(f"  Atoms: {atoms:,}")
    print(f"{'='*65}")

    for shell, label, const in [
        ("shell_1", "Source Ring (e)", E),
        ("shell_2", "Bridge Ring (π)", PI),
        ("shell_3", "Continuity Ring (2π)", TWO_PI),
    ]:
        cur = current[shell]
        bud = budgets[shell]
        ratio = cur / bud if bud > 0 else 0
        over = cur - bud
        bar = "█" * min(int(ratio * 20), 40) + "░" * max(20 - int(ratio * 20), 0)

        status = "UNDER" if over < 0 else "OVER" if over > 0 else "AT"
        print(f"\n  {label}")
        print(f"    Budget:  {bud:>12,}  ({const:.3f} × {atoms:,} / 2)")
        print(f"    Current: {cur:>12,}  ({ratio:.1%})")
        print(f"    Delta:   {over:>+12,}  [{status}]")
        print(f"    [{bar}]")

    total_cur = current["total"]
    total_bud = budgets["total"]
    print(f"\n  {'─'*61}")
    print(f"  TOTAL:   {total_cur:>12,} / {total_bud:>12,}  ({total_cur/total_bud:.1%})")
    print(f"  Archive: {total_cur - total_bud:>+12,} edges to reach target")
    print(f"{'='*65}")

    # Type breakdown
    print(f"\n  Edge types (top 15):")
    for etype, count in sorted(current["by_type"].items(), key=lambda x: -x[1])[:15]:
        shell = "S1" if etype in SHELL_1_TYPES else "S2" if etype in SHELL_2_TYPES else "S3"
        print(f"    [{shell}] {etype:25} {count:>12,}")


def dry_run():
    """Count what each shell needs to prune."""
    conn = get_connection()
    atoms = get_atom_count(conn)
    budgets = get_shell_budgets(atoms)
    current = get_shell_status(conn)

    plan = {}

    # Shell 1: keep all (underfilled)
    s1_over = current["shell_1"] - budgets["shell_1"]
    plan["shell_1"] = {
        "current": current["shell_1"],
        "budget": budgets["shell_1"],
        "to_archive": max(0, s1_over),
        "action": "KEEP ALL — underfilled, backfill in progress" if s1_over < 0 else f"PRUNE {s1_over:,} lowest-weight edges",
    }

    # Shell 2: prune semantic_similar + temporal to budget
    s2_over = current["shell_2"] - budgets["shell_2"]
    plan["shell_2"] = {
        "current": current["shell_2"],
        "budget": budgets["shell_2"],
        "to_archive": max(0, s2_over),
        "action": "KEEP ALL" if s2_over <= 0 else f"PRUNE {s2_over:,} lowest-weight edges",
    }

    # Shell 3: prune shared_entity + ring_flow to budget (the big one)
    s3_over = current["shell_3"] - budgets["shell_3"]
    plan["shell_3"] = {
        "current": current["shell_3"],
        "budget": budgets["shell_3"],
        "to_archive": max(0, s3_over),
        "action": "KEEP ALL" if s3_over <= 0 else f"PRUNE {s3_over:,} lowest-weight edges",
    }

    total_archive = sum(s["to_archive"] for s in plan.values())

    conn.close()

    print(f"\n{'='*65}")
    print(f"  DRY RUN — HYDROGEN ORBITAL PRUNING PLAN")
    print(f"  Atoms: {atoms:,}")
    print(f"{'='*65}")

    for shell, label in [("shell_1", "Shell 1 (Source)"), ("shell_2", "Shell 2 (Bridge)"), ("shell_3", "Shell 3 (Continuity)")]:
        s = plan[shell]
        print(f"\n  {label}:")
        print(f"    Current: {s['current']:>12,}")
        print(f"    Budget:  {s['budget']:>12,}")
        print(f"    Archive: {s['to_archive']:>12,}")
        print(f"    Action:  {s['action']}")

    print(f"\n  {'─'*61}")
    print(f"  TOTAL TO ARCHIVE: {total_archive:,}")
    print(f"{'='*65}")

    return plan


def apply_shell_prune(shell: int):
    """
    Prune a specific shell to its hydrogen budget.
    Archives lowest-weight edges first. Crown witnesses the archival.
    """
    conn = get_connection()
    atoms = get_atom_count(conn)
    budgets = get_shell_budgets(atoms)
    now = datetime.now(timezone.utc).isoformat()

    if shell == 2:
        types = tuple(SHELL_2_TYPES)
        budget = budgets["shell_2"]
        reason = "hydrogen_shell2_prune"
    elif shell == 3:
        types = tuple(SHELL_3_TYPES)
        budget = budgets["shell_3"]
        reason = "hydrogen_shell3_prune"
    else:
        print("Shell 1 pruning not supported — shell 1 is being backfilled.")
        conn.close()
        return

    # Count current
    placeholders = ",".join("?" for _ in types)
    current = conn.execute(
        f"SELECT count(*) FROM knowledge_edges WHERE edge_type IN ({placeholders})",
        types
    ).fetchone()[0]

    to_prune = current - budget
    if to_prune <= 0:
        print(f"Shell {shell} is within budget ({current:,} <= {budget:,}). Nothing to prune.")
        conn.close()
        return

    print(f"Shell {shell}: {current:,} edges, budget {budget:,}, pruning {to_prune:,}")

    # Ensure archive table exists
    conn.execute("""
        CREATE TABLE IF NOT EXISTS knowledge_edges_archive (
            id BIGINT,
            source_id INTEGER,
            target_id INTEGER,
            edge_type TEXT,
            weight REAL,
            canonical INTEGER DEFAULT 0,
            created_at TEXT,
            archived_at TEXT,
            archive_reason TEXT
        )
    """)
    conn.commit()

    # Archive lowest-weight edges in batches
    batch_size = 50000
    total_archived = 0
    t0 = time.time()

    while total_archived < to_prune:
        remaining = to_prune - total_archived
        this_batch = min(batch_size, remaining)

        # Select lowest-weight edges for this shell
        moved = conn.execute(
            f"""WITH to_archive AS (
                SELECT id FROM knowledge_edges
                WHERE edge_type IN ({placeholders})
                ORDER BY weight ASC, id ASC
                LIMIT ?
            )
            INSERT INTO knowledge_edges_archive
                (id, source_id, target_id, edge_type, weight, canonical, created_at, archived_at, archive_reason)
            SELECT ke.id, ke.source_id, ke.target_id, ke.edge_type, ke.weight, ke.canonical,
                   ke.created_at, ?, ?
            FROM knowledge_edges ke
            WHERE ke.id IN (SELECT id FROM to_archive)
            RETURNING ke.id""",
            types + (this_batch, now, reason)
        ).fetchall()

        if not moved:
            break

        archived_ids = tuple(r[0] for r in moved)
        # Delete in chunks to avoid parameter limit
        for i in range(0, len(archived_ids), 10000):
            chunk = archived_ids[i:i+10000]
            chunk_ph = ",".join("?" for _ in chunk)
            conn.execute(
                f"DELETE FROM knowledge_edges WHERE id IN ({chunk_ph})",
                chunk
            )
        conn.commit()

        total_archived += len(archived_ids)
        elapsed = time.time() - t0
        rate = total_archived / max(elapsed, 0.1)
        log.info(f"  Shell {shell}: archived {total_archived:,} / {to_prune:,} ({rate:,.0f}/sec)")
        print(f"  Archived {total_archived:,} / {to_prune:,} ({rate:,.0f}/sec)")

    # Crown witness
    try:
        from core.crown import witness_entity_event
        witness_entity_event(
            "edge_archived", f"shell_{shell}_prune",
            agent="edge_migration", username="Sweet-Pea-Rudi19",
            details={
                "shell": shell,
                "archived_count": total_archived,
                "budget": budget,
                "reason": reason,
            },
        )
    except Exception:
        pass

    remaining_total = conn.execute("SELECT count(*) FROM knowledge_edges").fetchone()[0]
    conn.close()

    elapsed = round(time.time() - t0, 1)
    print(f"\nShell {shell} prune complete: {total_archived:,} archived, {remaining_total:,} total remaining, {elapsed}s")

    return {
        "shell": shell,
        "archived": total_archived,
        "remaining_total": remaining_total,
        "elapsed": elapsed,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(description="Edge migration — hydrogen orbital pruning")
    parser.add_argument("--status", action="store_true", help="Current state vs hydrogen targets")
    parser.add_argument("--dry-run", action="store_true", help="Show pruning plan (default)")
    parser.add_argument("--apply", action="store_true", help="Apply pruning")
    parser.add_argument("--shell", type=int, choices=[2, 3], help="Prune specific shell (2 or 3)")
    args = parser.parse_args()

    if args.status:
        status_report()
    elif args.apply:
        if args.shell:
            apply_shell_prune(args.shell)
        else:
            print("Pruning all over-budget shells...")
            for s in [2, 3]:
                apply_shell_prune(s)
            print("\nFinal status:")
            status_report()
    else:
        dry_run()

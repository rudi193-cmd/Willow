#!/usr/bin/env python3
"""
Governance Precedent Lookup

Queries the settled governance ledger (.applied files) before halting for
human ratification. If the proposed action matches a prior ratified decision
by type, trust level, and pattern similarity, returns AUTO_APPROVE.

Only novel proposals — outside the established envelope — trigger a HALT.

Decision flow:
    1. Exact match (type + trust + summary hash)  → AUTO_APPROVE (confidence 1.0)
    2. Pattern match (type + trust + word overlap) → AUTO_APPROVE if above threshold
    3. Distributed match (neighboring node ledger) → DISTRIBUTED
    4. No match                                    → HALT

Usage:
    from governance.precedent import check_precedent

    result = check_precedent(
        proposal_type="Agent Registration",
        trust_level="WORKER",
        summary="Register new agent for domain: scooter rally archive",
        proposer="agent_builder"
    )

    if result["decision"] == "AUTO_APPROVE":
        # proceed without halting
    elif result["decision"] == "HALT":
        # write .pending, wait for Sean
"""

import re
import hashlib
from pathlib import Path
from typing import Optional

COMMITS_DIR = Path(__file__).parent / "commits"

# Known neighbor ring ledgers for distributed ratification.
# Source Ring (die-namic-system) is the canonical upstream neighbor.
NEIGHBOR_LEDGERS: list[Path] = [
    p for p in [
        Path(__file__).parent.parent.parent / "die-namic-system" / "governance" / "commits",
    ]
    if p.exists()
]

# Word-overlap threshold for pattern match auto-approval.
# 0.6 = 60% of significant words must overlap with a prior ratified summary.
PATTERN_MATCH_THRESHOLD = 0.6

# Stop words excluded from similarity comparison.
_STOP = {
    "a", "an", "the", "and", "or", "for", "to", "of", "in", "on",
    "with", "is", "are", "was", "be", "by", "at", "from", "this",
    "that", "new", "add", "adds", "update", "updates", "fix", "fixes",
}


def _tokens(text: str) -> set:
    words = re.sub(r"[^a-z0-9]", " ", text.lower()).split()
    return {w for w in words if w not in _STOP and len(w) > 2}


def _summary_hash(proposal_type: str, trust_level: str, summary: str) -> str:
    key = f"{proposal_type}|{trust_level}|{summary}".lower().strip()
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def _word_overlap(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / min(len(ta), len(tb))


def _load_applied_ledger() -> list[dict]:
    """Read all .applied and .commit files from the commits directory."""
    ledger = []
    if not COMMITS_DIR.exists():
        return ledger

    for path in list(COMMITS_DIR.glob("*.applied")) + list(COMMITS_DIR.glob("*.commit")):
        try:
            content = path.read_text(encoding="utf-8")
        except Exception:
            continue

        entry = {"commit_id": path.stem, "file": str(path)}

        m = re.search(r"\*\*Type:\*\*\s*(.+)", content)
        entry["type"] = m.group(1).strip() if m else ""

        m = re.search(r"\*\*Trust Level:\*\*\s*(.+)", content)
        entry["trust_level"] = m.group(1).strip() if m else ""

        m = re.search(r"## Summary\n+(.+)", content)
        entry["summary"] = m.group(1).strip() if m else ""

        m = re.search(r"\*\*Proposer:\*\*\s*(.+)", content)
        entry["proposer"] = m.group(1).strip() if m else ""

        ledger.append(entry)

    return ledger


def check_precedent(
    proposal_type: str,
    trust_level: str,
    summary: str,
    proposer: str = "",
    neighbor_ledgers: Optional[list[Path]] = None,
) -> dict:
    """
    Check whether a proposed action has prior ratified precedent.

    Args:
        proposal_type:   e.g. "Agent Registration", "Code Enhancement"
        trust_level:     e.g. "WORKER", "OPERATOR", "ENGINEER"
        summary:         One-paragraph description of the proposed change.
        proposer:        Agent name proposing the action.
        neighbor_ledgers: Optional paths to .applied dirs from other nodes/rings.

    Returns:
        {
            "decision":       "AUTO_APPROVE" | "HALT" | "DISTRIBUTED",
            "matched_commit": str | None,   # commit_id of the matching prior decision
            "confidence":     float,        # 0.0 – 1.0
            "reason":         str,
        }
    """
    candidate_hash = _summary_hash(proposal_type, trust_level, summary)
    ledger = _load_applied_ledger()

    # --- 1. Exact hash match (same type + trust + summary text) ---------------
    for entry in ledger:
        prior_hash = _summary_hash(entry["type"], entry["trust_level"], entry["summary"])
        if prior_hash == candidate_hash:
            return {
                "decision": "AUTO_APPROVE",
                "matched_commit": entry["commit_id"],
                "confidence": 1.0,
                "reason": f"Exact match: {entry['commit_id']} (hash {candidate_hash})",
            }

    # --- 2. Pattern match (same type + trust + high word overlap) -------------
    type_norm = proposal_type.strip().lower()
    trust_norm = trust_level.strip().upper()

    best_overlap = 0.0
    best_commit = None

    for entry in ledger:
        if entry["type"].lower() != type_norm:
            continue
        # Trust level must match or proposer must be same/higher tier
        entry_trust = entry["trust_level"].upper().split()[0]  # "ENGINEER (3)" → "ENGINEER"
        if entry_trust != trust_norm:
            continue

        overlap = _word_overlap(summary, entry["summary"])
        if overlap > best_overlap:
            best_overlap = overlap
            best_commit = entry["commit_id"]

    if best_overlap >= PATTERN_MATCH_THRESHOLD:
        return {
            "decision": "AUTO_APPROVE",
            "matched_commit": best_commit,
            "confidence": round(best_overlap, 3),
            "reason": (
                f"Pattern match: {best_commit} "
                f"(type={proposal_type}, trust={trust_level}, "
                f"overlap={best_overlap:.1%})"
            ),
        }

    # --- 3. Distributed ratification (neighboring node ledgers) ---------------
    if neighbor_ledgers:
        for ledger_dir in neighbor_ledgers:
            neighbor_entries = []
            for path in Path(ledger_dir).glob("*.applied"):
                try:
                    content = path.read_text(encoding="utf-8")
                    m_type = re.search(r"\*\*Type:\*\*\s*(.+)", content)
                    m_trust = re.search(r"\*\*Trust Level:\*\*\s*(.+)", content)
                    m_sum = re.search(r"## Summary\n+(.+)", content)
                    if m_type and m_trust and m_sum:
                        neighbor_entries.append({
                            "commit_id": path.stem,
                            "type": m_type.group(1).strip(),
                            "trust_level": m_trust.group(1).strip(),
                            "summary": m_sum.group(1).strip(),
                        })
                except Exception:
                    continue

            for entry in neighbor_entries:
                prior_hash = _summary_hash(entry["type"], entry["trust_level"], entry["summary"])
                if prior_hash == candidate_hash:
                    return {
                        "decision": "DISTRIBUTED",
                        "matched_commit": entry["commit_id"],
                        "confidence": 0.95,
                        "reason": (
                            f"Distributed ratification: {entry['commit_id']} "
                            f"from {ledger_dir}"
                        ),
                    }

    # --- 4. Novel — halt for human ratification --------------------------------
    return {
        "decision": "HALT",
        "matched_commit": None,
        "confidence": 0.0,
        "reason": (
            f"No precedent found for type='{proposal_type}', "
            f"trust='{trust_level}'. Dual Commit required. "
            f"Write proposal to governance/commits/ and await ratification."
        ),
    }


if __name__ == "__main__":
    # Quick smoke test against the live ledger
    import sys

    tests = [
        {
            "proposal_type": "Agent Registration",
            "trust_level": "WORKER",
            "summary": "Register new agent for domain: scooter rally archive hooks and memory",
            "proposer": "agent_builder",
        },
        {
            "proposal_type": "Code Enhancement",
            "trust_level": "ENGINEER",
            "summary": "Add precedent lookup function to governance module",
            "proposer": "ganesha",
        },
        {
            "proposal_type": "Experimental New Thing",
            "trust_level": "OPERATOR",
            "summary": "Introduce a completely novel architectural pattern never seen before",
            "proposer": "ganesha",
        },
    ]

    for t in tests:
        result = check_precedent(**t)
        print(f"\n[{result['decision']}] {t['summary'][:60]}...")
        print(f"  confidence: {result['confidence']}")
        print(f"  matched:    {result['matched_commit']}")
        print(f"  reason:     {result['reason']}")

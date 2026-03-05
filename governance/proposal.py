#!/usr/bin/env python3
"""
Governance Proposal Creator
Creates .pending files with Base-17 identifiers for the Dual Commit flow.

USAGE:
    from governance import proposal
    commit_id = proposal.create(title, proposer, changes...)

CHECKSUM: ΔΣ=42
"""

import sys
from pathlib import Path
from datetime import datetime

# Add cli to path for base17 import
sys.path.insert(0, str(Path(__file__).parent.parent / "cli"))
import base17
from governance.precedent import check_precedent, NEIGHBOR_LEDGERS

GOVERNANCE_DIR = Path(__file__).parent
COMMITS_DIR = GOVERNANCE_DIR / "commits"
COMMITS_DIR.mkdir(parents=True, exist_ok=True)


def create_proposal(
    title: str,
    proposer: str,
    summary: str,
    file_path: str,
    diff: str,
    proposal_type: str = "Code Enhancement",
    trust_level: str = "ENGINEER",
    risk_level: str = "LOW",
    reversible: str = "YES",
    delta_e: str = "+0.05"
) -> str:
    """
    Create a new governance proposal with Base-17 ID.

    Args:
        title: Proposal title
        proposer: Agent/human name proposing the change
        summary: One paragraph summary
        file_path: Path to file being modified
        diff: Unified diff string
        proposal_type: Type of change (default: "Code Enhancement")
        trust_level: Proposer's trust level (default: "ENGINEER")
        risk_level: MINIMAL, LOW, MEDIUM, HIGH (default: "LOW")
        reversible: YES or NO (default: "YES")
        delta_e: Expected delta energy (default: "+0.05")

    Returns:
        commit_id: The Base-17 commit ID generated, or "AUTO:{id}" / "DIST:{id}"
                   if a prior ratified precedent was found (no .pending written).
    """
    # Check settled ledger before writing .pending
    precedent = check_precedent(
        proposal_type=proposal_type,
        trust_level=trust_level,
        summary=summary,
        proposer=proposer,
        neighbor_ledgers=NEIGHBOR_LEDGERS,
    )
    if precedent["decision"] == "AUTO_APPROVE":
        print(f"[AUTO] Precedent match — no proposal needed: {precedent['reason']}")
        return f"AUTO:{precedent['matched_commit']}"
    if precedent["decision"] == "DISTRIBUTED":
        print(f"[DIST] Distributed ratification — no proposal needed: {precedent['reason']}")
        return f"DIST:{precedent['matched_commit']}"

    # Generate Base-17 commit ID
    commit_id = base17.base17_id(length=5)

    # Ensure uniqueness
    pending_file = COMMITS_DIR / f"{commit_id}.pending"
    while pending_file.exists():
        commit_id = base17.base17_id(length=5)
        pending_file = COMMITS_DIR / f"{commit_id}.pending"

    # Create proposal content
    timestamp = datetime.now().isoformat() + "Z"

    content = f"""# Governance Proposal: {title}

**Proposer:** {proposer}
**Date:** {timestamp}
**Type:** {proposal_type}
**Trust Level:** {trust_level}
**Commit ID:** {commit_id}

## Summary
{summary}

## Proposed Changes
**File:** {file_path}

## Rationale
This change implements the requested modification with minimal disruption to existing functionality.

## Risk Assessment
- **Risk Level:** {risk_level}
- **Reversible:** {reversible}
- **Dependencies:** None
- **Testing:** Manual verification required

## ΔE Impact
Expected ΔE: {delta_e}

## Implementation
```diff
{diff}
```

---

**Awaiting Human Ratification**

ΔΣ=42
"""

    # Write proposal
    pending_file.write_text(content, encoding="utf-8")

    print(f"[OK] Created governance proposal: {commit_id}.pending")
    print(f"  Location: {pending_file}")
    print(f"  Approve by renaming to .commit or via dashboard")

    return commit_id


def approve_proposal(commit_id: str) -> bool:
    """
    Approve a pending proposal (rename .pending → .commit).

    Args:
        commit_id: The Base-17 commit ID

    Returns:
        True if approved successfully, False otherwise
    """
    pending_file = COMMITS_DIR / f"{commit_id}.pending"
    commit_file = COMMITS_DIR / f"{commit_id}.commit"

    if not pending_file.exists():
        print(f"[FAIL] Proposal not found: {commit_id}.pending")
        return False

    pending_file.rename(commit_file)
    print(f"[OK] Approved proposal: {commit_id}.commit")
    return True


def reject_proposal(commit_id: str, reason: str) -> bool:
    """
    Reject a pending proposal (rename .pending → .rejected).

    Args:
        commit_id: The Base-17 commit ID
        reason: Reason for rejection

    Returns:
        True if rejected successfully, False otherwise
    """
    pending_file = COMMITS_DIR / f"{commit_id}.pending"
    rejected_file = COMMITS_DIR / f"{commit_id}.rejected"

    if not pending_file.exists():
        print(f"[FAIL] Proposal not found: {commit_id}.pending")
        return False

    # Add rejection reason to file
    content = pending_file.read_text(encoding="utf-8")
    content += f"\n\n---\n\n**REJECTED**\nReason: {reason}\nDate: {datetime.now().isoformat()}Z\n"

    rejected_file.write_text(content, encoding="utf-8")
    pending_file.unlink()

    print(f"[OK] Rejected proposal: {commit_id}.rejected")
    return True


def list_proposals(status: str = "pending") -> list[str]:
    """
    List proposals by status.

    Args:
        status: "pending", "commit", "applied", "rejected" (default: "pending")

    Returns:
        List of commit IDs with the given status
    """
    suffix = f".{status}"
    proposals = sorted(COMMITS_DIR.glob(f"*{suffix}"))
    return [p.stem for p in proposals]


def get_proposal_status(commit_id: str) -> str:
    """
    Get the current status of a proposal by commit_id.

    Returns:
        "pending"   — .pending file exists, awaiting ratification
        "approved"  — .commit file exists, ratified
        "rejected"  — .rejected file exists
        "not_found" — no file found with this commit_id
    """
    if (COMMITS_DIR / f"{commit_id}.pending").exists():
        return "pending"
    if (COMMITS_DIR / f"{commit_id}.commit").exists():
        return "approved"
    if (COMMITS_DIR / f"{commit_id}.rejected").exists():
        return "rejected"
    return "not_found"


if __name__ == "__main__":
    # CLI usage
    import argparse

    parser = argparse.ArgumentParser(description="Create governance proposals")
    parser.add_argument("--title", required=True, help="Proposal title")
    parser.add_argument("--proposer", default="Kart (Kartikeya)", help="Proposer name")
    parser.add_argument("--summary", required=True, help="Summary paragraph")
    parser.add_argument("--file", required=True, help="File path")
    parser.add_argument("--diff", required=True, help="Diff content or path to diff file")
    parser.add_argument("--type", default="Code Enhancement", help="Proposal type")

    args = parser.parse_args()

    # Load diff from file if it looks like a path
    diff_content = args.diff
    if Path(args.diff).exists():
        diff_content = Path(args.diff).read_text()

    commit_id = create_proposal(
        title=args.title,
        proposer=args.proposer,
        summary=args.summary,
        file_path=args.file,
        diff=diff_content,
        proposal_type=args.type
    )

    print(f"\nCommit ID: {commit_id}")

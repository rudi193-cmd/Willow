#!/usr/bin/env python3
"""Doc-integrity gate for the charter repo.

The checker itself is `tools/check_docs.py`, **vendored byte-for-byte** from
`willow-grove/tools/check_docs.py`. It is not edited here — the fleet's standard
for cross-repo shared code (2026-07-27 handoff, "Patterns / decisions carried
forward") is a vendored copy plus a two-sided drift-guard: an in-repo body-hash
pin catching local edits (`tests/test_doc_gate.py`) and a CI diff against
canonical catching the upstream advancing (`doc-integrity.yml`). Copying it and
then editing it would fork the canonical implementation, which is box-scan theme
① and the reason `friction_floor` shipped a known-defective detector for weeks.

This file is the willow-local layer the vendored checker deliberately has no
opinion about: which existing breaks are known.

WHY A REGISTRY INSTEAD OF JUST FIXING THEM
------------------------------------------
Three references were already broken when this gate landed. Two point at files
that do not exist anywhere in the repo (`LAST-RUN.md`, `MAINTAINER.md`) and one
at a section anchor that was renamed. Guessing at their intended targets would
put invented content in the charter repo, so they are recorded rather than
silently skipped or silently fixed — absence is a recorded value.

The registry is not a mute list. It fails in **both** directions:

  * a new broken reference fails the gate, which is the point;
  * a registered break that no longer fires ALSO fails, because a registry that
    outlives its entries rots into a list nobody can read as current. Fix the
    doc, delete the line.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_docs import ROOT, _md_files, check  # noqa: E402

# Broken when the gate landed (2026-08-04). Each entry is the exact message
# check() produces, plus why it is not simply fixed.
KNOWN_BROKEN: dict[str, str] = {
    "design/architecture/sandbox/AGENT-RUN.md: link target 'LAST-RUN.md' does not exist":
        "LAST-RUN.md is not in the repo and never was; the run log it refers to was "
        "presumably local to a sandbox session. Owner call whether to write one or drop the link.",
    "design/architecture/sandbox/SANDBOX-LAYOUTS.md: anchor '#l2--vault-full-user-data-vault' not found in this file":
        "The L2 section was retitled; the correct anchor depends on which heading is "
        "now meant, and picking one would be a guess about intent.",
    "seed/canon/README.md: link target '../MAINTAINER.md' does not exist":
        "No MAINTAINER.md exists at seed/ or repo root. Either it was never written or "
        "it moved; both are owner decisions, not inferences.",
}


def evaluate(root: Path = ROOT) -> tuple[list[str], list[str]]:
    """Return (new breaks, registry entries that no longer fire)."""
    current = set(check(root))
    new = sorted(current - set(KNOWN_BROKEN))
    stale = sorted(set(KNOWN_BROKEN) - current)
    return new, stale


def main() -> int:
    root = ROOT
    new, stale = evaluate(root)
    n_docs = len(_md_files(root))

    if new:
        print("Doc-integrity gate FAILED — new broken reference(s):\n")
        for e in new:
            print(f"  ✗ {e}")
    if stale:
        print("\nDoc-integrity gate FAILED — KNOWN_BROKEN entries that no longer fire:\n")
        for e in stale:
            print(f"  ✗ {e}")
        print("\n  These are fixed. Delete them from KNOWN_BROKEN in tools/doc_gate.py")
        print("  so the registry keeps meaning what it says.")
    if new or stale:
        return 1

    print(
        f"Doc-integrity gate passed: {n_docs} doc(s) scanned, no new broken references. "
        f"{len(KNOWN_BROKEN)} known break(s) still registered — see tools/doc_gate.py."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

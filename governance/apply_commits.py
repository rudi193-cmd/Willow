#!/usr/bin/env python3
import io as _io, sys as _sys
_sys.stdout = _io.TextIOWrapper(_sys.stdout.buffer, encoding='utf-8', errors='replace')
_sys.stderr = _io.TextIOWrapper(_sys.stderr.buffer, encoding='utf-8', errors='replace')
"""
Governance Commit Applicator
Processes approved .commit files and applies them to the repository.

Usage:
    python apply_commits.py                    # Apply all pending .commit files
    python apply_commits.py <commit_id>        # Apply specific commit
"""

import os
import sys
import subprocess
import re
from pathlib import Path
from datetime import datetime

GOVERNANCE_DIR = Path(__file__).parent
COMMITS_DIR = GOVERNANCE_DIR / "commits"
REPO_ROOT = GOVERNANCE_DIR.parent

def extract_diff(commit_file):
    """Extract and normalize diff content from a commit proposal.

    Handles:
    - Multiple diff blocks in one proposal (multi-file changes)
    - Formatting corruption where --- and +++ land on the same line
    """
    import re
    content = commit_file.read_text(encoding="utf-8")

    # Collect ALL diff blocks (multi-file proposals have one per file)
    diffs = re.findall(r'```diff\n(.*?)\n```', content, re.DOTALL)
    if not diffs:
        return None

    combined = '\n'.join(diffs)

    # Fix common agent formatting corruption:
    # "--- a/foo.py+++ b/foo.py" on one line -> split to two lines
    combined = re.sub(r'(--- a/\S+)\s*(\+\+\+ b/)', r'\1\n\2', combined)

    if not combined.endswith('\n'):
        combined += '\n'

    return combined
def extract_metadata(commit_file: Path) -> dict:
    """Extract metadata from commit proposal."""
    content = commit_file.read_text(encoding="utf-8")

    metadata = {}

    # Extract proposer
    proposer_match = re.search(r'\*\*Proposer:\*\* (.+)', content)
    if proposer_match:
        metadata['proposer'] = proposer_match.group(1)

    # Extract summary (first line after ## Summary)
    summary_match = re.search(r'## Summary\n\n(.+)', content)
    if summary_match:
        metadata['summary'] = summary_match.group(1).strip()

    # Extract type
    type_match = re.search(r'\*\*Type:\*\* (.+)', content)
    if type_match:
        metadata['type'] = type_match.group(1)

    return metadata

def apply_commit(commit_file: Path, dry_run: bool = False) -> bool:
    """Apply a single approved commit."""
    commit_id = commit_file.stem

    print(f"\n{'[DRY RUN] ' if dry_run else ''}Processing: {commit_id}")
    print("=" * 60)

    # Extract diff
    diff = extract_diff(commit_file)
    if not diff:
        print("[FAIL] No diff found in commit file")
        return False

    # Extract metadata
    meta = extract_metadata(commit_file)
    proposer = meta.get('proposer', 'Unknown')
    summary = meta.get('summary', 'Governance change')

    print(f"Proposer: {proposer}")
    print(f"Summary: {summary}")
    print(f"\nDiff preview:")
    print(diff[:200] + "..." if len(diff) > 200 else diff)

    if dry_run:
        print("\n[OK] Dry run - would apply this commit")
        return True

    # Apply the diff as a patch
    try:
        # Write diff to temp file
        patch_file = GOVERNANCE_DIR / f".temp_{commit_id}.patch"
        patch_file.write_text(diff + '\n', newline='\n')

        # Apply patch
        result = subprocess.run(
            ["git", "apply", "--check", str(patch_file)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            print(f"[FAIL] Patch validation failed: {result.stderr}")
            patch_file.unlink()
            return False

        # Actually apply
        result = subprocess.run(
            ["git", "apply", str(patch_file)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True
        )

        patch_file.unlink()

        if result.returncode != 0:
            print(f"[FAIL] Patch application failed: {result.stderr}")
            return False

        # Commit the change
        commit_msg = f"{summary}\n\nProposed by: {proposer}\nCommit ID: {commit_id}\n\nCo-Authored-By: Kart (Kartikeya) <kart@die-namic.system>"

        # Stage all changes
        subprocess.run(["git", "add", "-A"], cwd=REPO_ROOT, check=True)

        # Commit
        result = subprocess.run(
            ["git", "commit", "-m", commit_msg],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            print(f"[FAIL] Git commit failed: {result.stderr}")
            return False

        print(f"[OK] Applied and committed: {commit_id}")

        # Move to .applied
        applied_file = commit_file.with_suffix('.applied')
        commit_file.rename(applied_file)

        return True

    except Exception as e:
        print(f"[FAIL] Error: {e}")
        return False

def main():
    """Main entry point."""
    dry_run = "--dry-run" in sys.argv

    if len(sys.argv) > 1 and sys.argv[1] != "--dry-run":
        # Apply specific commit
        commit_id = sys.argv[1]
        commit_file = COMMITS_DIR / f"{commit_id}.commit"

        if not commit_file.exists():
            print(f"[FAIL] Commit not found: {commit_file}")
            sys.exit(1)

        success = apply_commit(commit_file, dry_run)
        sys.exit(0 if success else 1)

    # Apply all pending .commit files
    commit_files = sorted(COMMITS_DIR.glob("*.commit"))

    if not commit_files:
        print("No pending commits to apply.")
        sys.exit(0)

    print(f"Found {len(commit_files)} pending commit(s)")

    applied = 0
    failed = 0

    for commit_file in commit_files:
        if apply_commit(commit_file, dry_run):
            applied += 1
        else:
            failed += 1

    print(f"\n{'[DRY RUN] ' if dry_run else ''}Summary:")
    print(f"  [OK] Applied: {applied}")
    print(f"  [FAIL] Failed: {failed}")

if __name__ == "__main__":
    main()

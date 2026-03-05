#!/usr/bin/env python3
"""
Test the full governance flow:
1. Check pending proposal
2. Approve it (simulate human approval)
3. Apply the commit
4. Verify the change
"""

import requests
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent
COMMITS_DIR = REPO_ROOT / "governance" / "commits"
SERVER_URL = "http://localhost:8420"  # Willow server
COMMIT_ID = "kart_test_2026-02-06_19-15"

def step(num, desc):
    print(f"\n{'='*60}")
    print(f"STEP {num}: {desc}")
    print('='*60)

def check_server():
    """Check if Willow server is running."""
    try:
        resp = requests.get(f"{SERVER_URL}/api/status", timeout=2)
        return resp.status_code == 200
    except:
        return False

def main():
    step(1, "Check pending proposal exists")
    pending_file = COMMITS_DIR / f"{COMMIT_ID}.pending"
    if not pending_file.exists():
        print(f"[FAIL] Proposal not found: {pending_file}")
        sys.exit(1)
    print(f"[OK] Proposal exists: {pending_file}")

    step(2, "Approve the proposal (simulate human)")
    # Move .pending -> .commit (simulating the approval endpoint)
    commit_file = COMMITS_DIR / f"{COMMIT_ID}.commit"
    pending_file.rename(commit_file)
    print(f"[OK] Moved {pending_file.name} -> {commit_file.name}")

    step(3, "Apply the commit (dry run)")
    result = subprocess.run(
        [sys.executable, "governance/apply_commits.py", COMMIT_ID, "--dry-run"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True
    )
    print(result.stdout)
    if result.returncode != 0:
        print(f"[FAIL] Dry run failed:\n{result.stderr}")
        sys.exit(1)

    step(4, "Apply the commit (real)")
    result = subprocess.run(
        [sys.executable, "governance/apply_commits.py", COMMIT_ID],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True
    )
    print(result.stdout)
    if result.returncode != 0:
        print(f"[FAIL] Application failed:\n{result.stderr}")
        sys.exit(1)

    step(5, "Verify the change")
    # Check if the function was added
    llm_router = REPO_ROOT / "core" / "llm_router.py"
    content = llm_router.read_text()
    if "def get_provider_count()" in content:
        print("[OK] Function get_provider_count() found in llm_router.py")
    else:
        print("[FAIL] Function not found - apply may have failed")
        sys.exit(1)

    step(6, "Check git status")
    result = subprocess.run(
        ["git", "log", "-1", "--oneline"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True
    )
    print(f"Latest commit: {result.stdout.strip()}")

    # Check if commit has the governance metadata
    result = subprocess.run(
        ["git", "log", "-1"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True
    )
    if "Proposed by: Kart" in result.stdout and "Commit ID:" in result.stdout:
        print("[OK] Commit has governance metadata")
    else:
        print("[WARN] Commit may be missing governance metadata")

    print(f"\n{'='*60}")
    print("[SUCCESS] GOVERNANCE FLOW TEST COMPLETE")
    print('='*60)
    print("\nThe proposal was:")
    print("  1. Created (.pending)")
    print("  2. Approved (.pending -> .commit)")
    print("  3. Applied (patch + git commit)")
    print("  4. Verified (code change present)")
    print("\nThe change is now in git history with Dual Commit metadata.")

if __name__ == "__main__":
    main()

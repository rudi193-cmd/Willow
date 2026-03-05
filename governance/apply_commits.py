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
    python apply_commits.py <commit_id> --dry-run
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
    """Extract unified diff block(s) from proposal, if present.

    Returns the combined diff text, or None if no ```diff blocks found.
    Handles git-extended headers (diff --git, index lines) by passing them
    through — git apply understands them, and we strip them for patch fallback.
    """
    content = commit_file.read_text(encoding="utf-8")
    diffs = re.findall(r'```diff\n(.*?)\n```', content, re.DOTALL)
    if not diffs:
        return None
    combined = '\n'.join(diffs)
    # Ensure --- a/ and +++ b/ headers are on separate lines
    combined = re.sub(r'(--- a/\S+)\s*(\+\+\+ b/)', r'\1\n\2', combined)
    if not combined.endswith('\n'):
        combined += '\n'
    return combined


def _strip_git_headers(diff_text):
    """Strip git-extended headers, keeping only the unified diff lines.

    Removes lines like:
        diff --git a/foo b/foo
        index abc123..def456 100644
        new file mode 100644
        deleted file mode 100644
        old mode / new mode

    Leaves intact: --- a/..., +++ b/..., @@ ... @@, context, +/- lines.
    Used as fallback for `patch` which doesn't understand git headers.
    """
    output_lines = []
    for line in diff_text.splitlines(keepends=True):
        if re.match(r'^(diff --git|index [0-9a-f]+\.\.|new file mode|deleted file mode|old mode|new mode)\b', line):
            continue
        output_lines.append(line)
    return ''.join(output_lines)


def _try_git_apply(patch_file, dry_run, cwd):
    """Try git apply with progressively looser flags.

    Returns True if the patch was applied (or would apply in dry-run).
    Returns False if git apply cannot handle this patch at all.
    """
    base_flags = [
        "--recount",          # don't trust line counts in hunk headers
        "--whitespace=nowarn",  # don't fail on trailing whitespace
        "--ignore-whitespace",  # ignore whitespace differences in context
    ]

    # First try: strict check
    check_result = subprocess.run(
        ["git", "apply", "--check"] + base_flags + [str(patch_file)],
        cwd=cwd, capture_output=True, text=True
    )
    if check_result.returncode == 0:
        if not dry_run:
            subprocess.run(
                ["git", "apply"] + base_flags + [str(patch_file)],
                cwd=cwd, check=True
            )
        return True

    # Second try: with --unidiff-zero (zero context lines in hunk)
    check_result2 = subprocess.run(
        ["git", "apply", "--check", "--unidiff-zero"] + base_flags + [str(patch_file)],
        cwd=cwd, capture_output=True, text=True
    )
    if check_result2.returncode == 0:
        if not dry_run:
            subprocess.run(
                ["git", "apply", "--unidiff-zero"] + base_flags + [str(patch_file)],
                cwd=cwd, check=True
            )
        return True

    # Report the actual git error for diagnostics
    err = (check_result2.stderr or check_result.stderr).strip()
    print(f"  [WARN] git apply failed: {err}")
    return False


def _try_patch_command(patch_file, dry_run, cwd):
    """Fall back to GNU patch -p1.

    patch is more tolerant than git apply for non-git diffs and
    diffs with unusual hunk headers. Strips git-extended headers first
    since patch doesn't understand them.
    """
    raw = patch_file.read_text(encoding="utf-8", errors="replace")
    stripped = _strip_git_headers(raw)

    stripped_file = patch_file.parent / (patch_file.name + ".stripped")
    stripped_file.write_text(stripped, encoding="utf-8", newline='\n')

    flags = ["-p1", "--batch", "--ignore-whitespace"]
    if dry_run:
        flags.append("--dry-run")

    try:
        result = subprocess.run(
            ["patch"] + flags + ["-i", str(stripped_file)],
            cwd=cwd, capture_output=True, text=True
        )
        stripped_file.unlink(missing_ok=True)
        if result.returncode == 0:
            return True
        print(f"  [WARN] patch command failed: {result.stderr.strip() or result.stdout.strip()}")
        return False
    except FileNotFoundError:
        stripped_file.unlink(missing_ok=True)
        print("  [WARN] patch command not found — skipping GNU patch fallback")
        return False


def extract_prose_patches(commit_file):
    """Parse prose-format proposals.

    Looks for blocks like:
        ### File: path/to/file.py
        ...
        Change from:
        ```python
        <old code>
        ```

        To:
        ```python
        <new code>
        ```

    Returns list of (filepath, old_str, new_str) tuples.
    """
    content = commit_file.read_text(encoding="utf-8")
    patches = []

    # Find all ### File: sections
    file_sections = re.split(r'### File:\s*', content)[1:]

    for section in file_sections:
        # First line is the file path
        lines = section.split('\n')
        rel_path = lines[0].strip()
        section_body = '\n'.join(lines[1:])

        # Extract Change from / To blocks (any code fence language)
        change_match = re.search(
            r'Change from:\s*```\w*\n(.*?)\n```\s*\nTo:\s*```\w*\n(.*?)\n```',
            section_body, re.DOTALL
        )
        if change_match:
            old_str = change_match.group(1)
            new_str = change_match.group(2)
            patches.append((rel_path, old_str, new_str))

    return patches


def apply_prose_patch(rel_path, old_str, new_str, dry_run=False):
    """Apply a single string replacement to a file."""
    target = REPO_ROOT / rel_path
    if not target.exists():
        print(f"  [FAIL] File not found: {target}")
        return False

    content = target.read_text(encoding="utf-8")
    if old_str not in content:
        print(f"  [FAIL] Old string not found in {rel_path}")
        print(f"  Expected: {repr(old_str[:80])}...")
        return False

    if dry_run:
        print(f"  [DRY] Would replace in {rel_path}")
        print(f"    - {repr(old_str[:60])}...")
        print(f"    + {repr(new_str[:60])}...")
        return True

    new_content = content.replace(old_str, new_str, 1)
    target.write_text(new_content, encoding="utf-8")
    print(f"  [OK] Patched: {rel_path}")
    return True


def extract_python_block(commit_file: Path):
    """Extract Python code from the ## Implementation section.

    Looks for:
        ## Implementation
        ```python
        ...code...
        ```

    Returns the code string, or None if not found.
    """
    content = commit_file.read_text(encoding="utf-8")
    m = re.search(r'## Implementation\s*\n.*?```python\n(.*?)```', content, re.DOTALL)
    if m:
        return m.group(1)
    return None


def apply_python_block(code: str, commit_id: str, dry_run: bool = False) -> bool:
    """Execute a Python implementation block from a temp file.

    Returns True on success (or dry-run), False on failure.
    """
    if dry_run:
        first = code.strip().splitlines()[0] if code.strip() else '(empty)'
        print(f"  [DRY] Would execute Python block ({len(code)} chars): {first}")
        return True

    tmp = GOVERNANCE_DIR / f".temp_{commit_id}_impl.py"
    try:
        tmp.write_text(code, encoding="utf-8")
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        result = subprocess.run(
            [sys.executable, str(tmp)],
            capture_output=True, text=True, encoding="utf-8", cwd=str(REPO_ROOT), env=env
        )
        if result.stdout.strip():
            for line in result.stdout.strip().splitlines():
                print(f"  [OUT] {line}")
        if result.returncode != 0:
            err = result.stderr.strip() or result.stdout.strip()
            print(f"  [FAIL] Python block exited {result.returncode}: {err}")
            return False
        print("  [OK] Python implementation block executed")
        return True
    except Exception as exc:
        print(f"  [FAIL] Python block execution error: {exc}")
        return False
    finally:
        tmp.unlink(missing_ok=True)


def extract_metadata(commit_file: Path) -> dict:
    """Extract metadata from commit proposal."""
    content = commit_file.read_text(encoding="utf-8")
    metadata = {}
    proposer_match = re.search(r'\*\*Proposer:\*\* (.+)', content)
    if proposer_match:
        metadata['proposer'] = proposer_match.group(1)
    summary_match = re.search(r'## Summary\n\n(.+)', content)
    if summary_match:
        metadata['summary'] = summary_match.group(1).strip()
    type_match = re.search(r'\*\*Type:\*\* (.+)', content)
    if type_match:
        metadata['type'] = type_match.group(1)
    return metadata


def cleanup_context_store(commit_id):
    """Remove stale governance approval entry from context_store."""
    try:
        sys.path.insert(0, str(REPO_ROOT.parent / ".claude"))
        import context_store as cs
        cs.delete(f"governance:pending_apply:{commit_id}")
        cs.delete(f"governance_approval:{commit_id}")
    except Exception:
        pass  # context_store unavailable — not critical


def apply_commit(commit_file: Path, dry_run: bool = False) -> bool:
    """Apply a single approved commit using diff or prose fallback.

    Strategy order:
      1. Unified diff via git apply (with --recount --ignore-whitespace fallbacks)
      2. Unified diff via GNU patch -p1 (more tolerant, strips git headers)
      3. Prose Change from/To string replacements
      4. No applicable change found — warn and skip cleanly (not a crash)

    Never raises an exception for unknown/unparseable proposal formats.
    Returns True on success or clean skip; False only if a known patch
    strategy was found but failed to apply (real failure, worth retrying).
    """
    commit_id = commit_file.stem

    print(f"\n{'[DRY RUN] ' if dry_run else ''}Processing: {commit_id}")
    print("=" * 60)

    meta = extract_metadata(commit_file)
    proposer = meta.get('proposer', 'Unknown')
    summary = meta.get('summary', 'Governance change')
    print(f"Proposer: {proposer}")
    print(f"Summary: {summary}")

    applied = False
    patch_attempted = False  # track whether we tried a real strategy

    # --- Strategy 1 & 2: unified diff (git apply, then GNU patch) ---
    diff = extract_diff(commit_file)
    if diff:
        patch_attempted = True
        print("\nApplying unified diff...")
        patch_file = GOVERNANCE_DIR / f".temp_{commit_id}.patch"
        try:
            patch_file.write_text(diff + '\n', encoding="utf-8", newline='\n')

            # Strategy 1: git apply
            if _try_git_apply(patch_file, dry_run, REPO_ROOT):
                applied = True
            else:
                # Strategy 2: GNU patch -p1 fallback
                print("  Trying GNU patch fallback...")
                if _try_patch_command(patch_file, dry_run, REPO_ROOT):
                    applied = True
                else:
                    print("  [WARN] Both git apply and patch failed for this diff.")
        except Exception as exc:
            print(f"  [WARN] Unexpected error during diff apply: {exc}")
        finally:
            patch_file.unlink(missing_ok=True)

    # --- Strategy 3: prose Change from/To blocks ---
    if not applied:
        patches = extract_prose_patches(commit_file)
        if patches:
            patch_attempted = True
            print(f"\nApplying {len(patches)} prose patch(es)...")
            all_ok = True
            for rel_path, old_str, new_str in patches:
                if not apply_prose_patch(rel_path, old_str, new_str, dry_run):
                    all_ok = False
            if all_ok:
                applied = True

    # --- Strategy 4: Python implementation block ---
    if not applied:
        python_code = extract_python_block(commit_file)
        if python_code:
            patch_attempted = True
            print("\nExecuting Python implementation block...")
            if apply_python_block(python_code, commit_id, dry_run):
                applied = True

    # --- No applicable change found ---
    if not applied:
        if not patch_attempted:
            # Proposal is prose-only (no diff block, no Change from/To).
            # This is not an error — it may be documentation, approval-only, etc.
            print("[WARN] No diff block or prose patches found — nothing to apply.")
            print("       If manual changes are needed, apply them, then rename to .applied")
            # Mark as applied so the pipeline doesn't block
            if not dry_run:
                applied_file = commit_file.with_suffix('.applied')
                commit_file.rename(applied_file)
                print(f"[OK] Marked as applied (no-op): {applied_file.name}")
                cleanup_context_store(commit_id)
            else:
                print("[OK] Dry run: would mark as applied (no-op)")
            return True
        else:
            # We found a diff or prose patch but couldn't apply it — real failure
            print("[FAIL] Patch strategy found but failed to apply.")
            print("       Apply manually, then rename to .applied")
            return False

    if dry_run:
        print("\n[OK] Dry run complete")
        return True

    # Move to .applied
    applied_file = commit_file.with_suffix('.applied')
    commit_file.rename(applied_file)
    print(f"[OK] Marked as applied: {applied_file.name}")

    # Clean up context_store notification
    cleanup_context_store(commit_id)

    return True


def main():
    """Main entry point."""
    dry_run = "--dry-run" in sys.argv

    if len(sys.argv) > 1 and sys.argv[1] != "--dry-run":
        commit_id = sys.argv[1]
        # Accept .commit or .pending (for emergency manual applies)
        commit_file = COMMITS_DIR / f"{commit_id}.commit"
        if not commit_file.exists():
            commit_file = COMMITS_DIR / f"{commit_id}.pending"
        if not commit_file.exists():
            print(f"[FAIL] Commit not found: {commit_id}")
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

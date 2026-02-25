"""File Registry Ingest — Willow Post-Commit Hook Handler

Called by .git/hooks/post-commit in watched repos.
Writes two atom types to willow_knowledge.db:
  - file_location: one atom per committed file (5 W's)
  - behavioral_pattern: one atom per commit (cognitive fingerprint)

Never raises. Never blocks commits. Silent on failure.

Usage:
  python file_registry_ingest.py --repo <name> --commit <hash> --message <msg>

DS=42
"""

import sys
import os
import argparse
import sqlite3
import subprocess
import json
import re
from datetime import datetime
from statistics import mean
from typing import Optional, List

os.chdir(r"C:\Users\Sean\Documents\GitHub\Willow")
sys.path.insert(0, r"C:\Users\Sean\Documents\GitHub\Willow\core")
import llm_router

DB_PATH = r"C:\Users\Sean\Documents\GitHub\Willow\artifacts\Sweet-Pea-Rudi19\willow_knowledge.db"

REPO_ROOTS = {
    "die-namic-system": r"C:\Users\Sean\Documents\GitHub\die-namic-system",
    "Willow": r"C:\Users\Sean\Documents\GitHub\Willow",
    "safe-app-utety-chat": r"C:\Users\Sean\Documents\GitHub\safe-app-utety-chat",
    "nasa-archive": r"C:\Users\Sean\Documents\GitHub\safe-app-nasa-archive",
    "SAFE": r"C:\Users\Sean\Documents\GitHub\SAFE",
}

def infer_category(filepath: str) -> str:
    parts = filepath.lower().replace("\\", "/").split("/")
    if "governance" in parts: return "governance"
    if "creative_works" in parts: return "creative"
    if "utety" in parts: return "utety"
    if "core" in parts: return "core"
    if "docs" in parts: return "documentation"
    if "tests" in parts: return "test"
    if "apps" in parts: return "application"
    if "tools" in parts: return "tools"
    return "general"

def detect_naming_style(filenames: List[str]) -> str:
    screaming = sum(1 for f in filenames if re.match(r'^[A-Z][A-Z0-9_]+\.[a-z]+$', f))
    camel = sum(1 for f in filenames if re.search(r'[a-z][A-Z]', f))
    kebab = sum(1 for f in filenames if '-' in f and '_' not in f.split('.')[0])
    total = len(filenames) or 1
    if screaming / total > 0.6: return "SCREAMING_SNAKE"
    if camel / total > 0.4: return "camelCase"
    if kebab / total > 0.4: return "kebab-case"
    return "mixed"

def get_committed_files(repo_root: str, commit_hash: str) -> List[str]:
    try:
        result = subprocess.run(
            ["git", "diff-tree", "--no-commit-id", "-r", "--name-only", commit_hash],
            capture_output=True, text=True, cwd=repo_root, timeout=10
        )
        return [f.strip() for f in result.stdout.splitlines() if f.strip()]
    except Exception:
        return []

def generate_summary(filename: str, filepath: str, repo: str, commit_msg: str) -> Optional[str]:
    try:
        prompt = (
            f"One sentence only. No prefix. What is this file about?\n"
            f"Filename: {filename}\nPath: {filepath}\nRepo: {repo}\n"
            f"Commit: {commit_msg}\nAnswer:"
        )
        resp = llm_router.ask(prompt, preferred_tier="free")
        if resp and resp.content:
            return resp.content.strip()[:300]
    except Exception:
        pass
    return None

def write_file_atom(conn: sqlite3.Connection, repo: str, filepath: str,
                    commit_hash: str, commit_msg: str, summary: Optional[str]):
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    source_id = f"{repo}:{filepath}"
    title = os.path.basename(filepath)
    category = infer_category(filepath)
    content_snippet = (
        f"repo={repo} | path={filepath} | commit={commit_hash[:8]} | "
        f"filed={now[:10]} | msg={commit_msg[:120]}"
    )
    ring_keywords = ["governance", "creative_works", "utety"]
    ring = "source" if any(k in filepath.lower() for k in ring_keywords) else "bridge"
    conn.execute(
        """INSERT OR REPLACE INTO knowledge
           (source_type, source_id, title, summary, content_snippet, category, ring, created_at)
           VALUES ('file_location', ?, ?, ?, ?, ?, ?, ?)""",
        (source_id, title, summary, content_snippet, category, ring, now)
    )

def write_pattern_atom(conn: sqlite3.Connection, repo: str, files: List[str],
                       commit_hash: str, commit_msg: str):
    if not files:
        return
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    basenames = [os.path.basename(f) for f in files]
    naming_style = detect_naming_style(basenames)
    depths = [f.replace("\\", "/").count("/") for f in files]
    avg_depth = round(mean(depths), 1) if depths else 0
    categories = list(dict.fromkeys(infer_category(f) for f in files))
    dirnames = [os.path.dirname(f).replace("\\", "/") for f in files]
    cluster = max(set(dirnames), key=dirnames.count) if dirnames else repo
    pattern = {
        "naming_style": naming_style,
        "avg_depth": avg_depth,
        "categories": categories,
        "cluster": cluster,
        "file_count": len(files),
    }
    source_id = f"pattern:{repo}:{commit_hash[:8]}"
    summary = (
        f"{len(files)} files committed to {repo}. "
        f"Style: {naming_style}. Cluster: {cluster}. "
        f"Categories: {','.join(categories)}."
    )
    conn.execute(
        """INSERT OR REPLACE INTO knowledge
           (source_type, source_id, title, summary, content_snippet, category, ring, created_at)
           VALUES ('behavioral_pattern', ?, ?, ?, ?, 'user_cognition', 'continuity', ?)""",
        (source_id, f"Filing pattern: {repo}", summary, json.dumps(pattern), now)
    )

def main():
    try:
        parser = argparse.ArgumentParser(description="Willow file registry ingest")
        parser.add_argument("--repo", required=True)
        parser.add_argument("--commit", required=True)
        parser.add_argument("--message", default="")
        args = parser.parse_args()

        repo_root = REPO_ROOTS.get(args.repo)
        if not repo_root:
            sys.exit(0)

        files = get_committed_files(repo_root, args.commit)
        if not files:
            sys.exit(0)

        llm_router.load_keys_from_json()

        conn = sqlite3.connect(DB_PATH, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")

        for filepath in files:
            filename = os.path.basename(filepath)
            summary = generate_summary(filename, filepath, args.repo, args.message)
            write_file_atom(conn, args.repo, filepath, args.commit, args.message, summary)

        write_pattern_atom(conn, args.repo, files, args.commit, args.message)

        conn.commit()
        conn.close()
        print(f"Registry: {len(files)} atoms filed from {args.repo}")

    except Exception as e:
        # Never block a commit
        pass

if __name__ == "__main__":
    main()
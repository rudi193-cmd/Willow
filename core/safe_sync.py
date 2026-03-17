#!/usr/bin/env python3
import argparse
import json
import logging
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

# Ensure Willow root is on sys.path for core.db imports
_WILLOW_ROOT = str(Path(__file__).parent.parent)
if _WILLOW_ROOT not in sys.path:
    sys.path.insert(0, _WILLOW_ROOT)
from typing import Optional

try:
    import git
    from git import Repo, GitCommandError
    _GIT_AVAILABLE = True
except ImportError:
    _GIT_AVAILABLE = False
    Repo = None
    GitCommandError = OSError

DEFAULT_INTERVAL = 300
LOG_FILE = Path(__file__).parent.parent / "core" / "safe_sync.log"
SAFE_REPO_DEFAULT = Path(__file__).parent.parent.parent / "SAFE"
WILLOW_ROOT = Path(__file__).parent.parent
STATE_FILE = Path(__file__).parent / "safe_sync_state.json"
KB_PATH = WILLOW_ROOT / "artifacts" / "Sweet-Pea-Rudi19" / "willow_knowledge.db"

CONTINUITY_SOURCE_TYPES = {"session_handoff", "context_store", "narrative", "governance", "ocr_image"}
CONTINUITY_CATEGORIES = {"history", "analysis", "narrative", "governance"}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def _load_state() -> dict:
    """Load persistent sync state (last sync timestamp)."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"last_sync_at": "2000-01-01T00:00:00"}


def _save_state(state: dict) -> None:
    """Persist sync state."""
    try:
        STATE_FILE.write_text(json.dumps(state, indent=2))
    except Exception as e:
        logger.error(f"Could not save sync state: {e}")


class SafeSyncDaemon:
    def __init__(self, safe_path: Path, interval: int):
        self.safe_path = safe_path
        self.interval = interval
        self.running = False
        self.repo: Optional[Repo] = None

    def initialize_repo(self) -> None:
        if not _GIT_AVAILABLE:
            logger.warning("GitPython not installed — git operations disabled")
            return
        try:
            self.repo = Repo(self.safe_path)
            logger.info(f"Initialized SAFE repo at {self.safe_path}")
        except git.InvalidGitRepositoryError:
            logger.error(f"Invalid git repository at {self.safe_path}")
            raise

    def query_new_continuity_entries(self) -> list:
        """Query willow_knowledge.db for entries since last sync."""
        state = _load_state()
        last_sync = state["last_sync_at"]

        if not KB_PATH.exists():
            logger.warning(f"Knowledge DB not found: {KB_PATH}")
            return []

        try:
            from core.db import get_connection as _gc
            conn = _gc()
            placeholders = ','.join('?' for _ in CONTINUITY_SOURCE_TYPES)
            cat_placeholders = ','.join('?' for _ in CONTINUITY_CATEGORIES)
            params = list(CONTINUITY_SOURCE_TYPES) + list(CONTINUITY_CATEGORIES) + [last_sync]
            rows = conn.execute(f"""
                SELECT id, source_type, source_id, title, summary, content_snippet,
                       category, ring, created_at, lattice_domain, lattice_type, lattice_status
                FROM knowledge
                WHERE (source_type IN ({placeholders}) OR category IN ({cat_placeholders}))
                  AND created_at > ?
                ORDER BY created_at ASC
                LIMIT 100
            """, params).fetchall()
            conn.close()
            entries = [dict(r) for r in rows]
            logger.info(f"Found {len(entries)} new entries since {last_sync}")
            return entries
        except Exception as e:
            logger.error(f"DB query failed: {e}")
            return []

    def format_as_markdown(self, entries: list) -> str:
        """Format knowledge entries as markdown continuity record."""
        lines = []
        for entry in entries:
            title = entry.get("title") or entry.get("source_id") or "Untitled"
            lines.append(f"## {title}")
            lines.append("")
            lines.append(f"- **Source:** {entry.get('source_type', 'unknown')} / {entry.get('category', '')}")
            lines.append(f"- **Ring:** {entry.get('ring', '')}")
            lines.append(f"- **Lattice:** {entry.get('lattice_domain', '')} / {entry.get('lattice_type', '')} / {entry.get('lattice_status', '')}")
            lines.append(f"- **Created:** {entry.get('created_at', '')}")
            if entry.get("summary"):
                lines.append("")
                lines.append(entry["summary"])
            lines.append("")
            lines.append("---")
            lines.append("")
        return "\n".join(lines)

    def append_to_safe_repo(self, markdown_content: str, entries: list) -> Path:
        """Write formatted entries to monthly continuity file in SAFE repo."""
        month = datetime.now().strftime("%Y-%m")
        continuity_dir = self.safe_path / "continuity"
        continuity_dir.mkdir(exist_ok=True)
        continuity_file = continuity_dir / f"{month}.md"

        header = ""
        if not continuity_file.exists():
            header = f"# Continuity Log - {month}\n\nGenerated by safe_sync.py\n\n---\n\n"

        with open(continuity_file, "a", encoding="utf-8") as f:
            if header:
                f.write(header)
            f.write(f"*Synced: {datetime.now().isoformat()} - {len(entries)} entries*\n\n")
            f.write(markdown_content)

        logger.info(f"Wrote {len(entries)} entries to {continuity_file}")
        return continuity_file

    def git_commit_changes(self, entry_count: int) -> str:
        if not _GIT_AVAILABLE or self.repo is None:
            logger.warning("Git unavailable — skipping commit")
            return "no-git"
        try:
            self.repo.git.add(A=True)
            msg = f"safe_sync: {entry_count} continuity entries [{datetime.now().strftime('%Y-%m-%d %H:%M')}]"
            commit = self.repo.index.commit(msg)
            logger.info(f"Committed: {commit.hexsha}")
            return commit.hexsha
        except GitCommandError as e:
            logger.error(f"Git operation failed: {e}")
            raise

    def sync(self) -> None:
        """Sync new continuity entries to SAFE repo.

        Governance: writes markdown to continuity/ dir but does NOT auto-commit.
        A .safe_sync_approve trigger file must exist for git commit to proceed.
        This ensures a human has reviewed what's being exported to the public repo.
        """
        try:
            if self.repo is None:
                self.initialize_repo()

            entries = self.query_new_continuity_entries()
            if not entries:
                logger.info("No new entries to sync")
                return

            markdown_content = self.format_as_markdown(entries)
            self.append_to_safe_repo(markdown_content, entries)

            # Governance gate: only commit if approval trigger exists
            approve_trigger = self.safe_path / ".safe_sync_approve"
            if approve_trigger.exists():
                self.git_commit_changes(len(entries))
                approve_trigger.unlink()
                logger.info(f"SAFE sync: committed {len(entries)} entries (approved)")
            else:
                logger.info(f"SAFE sync: staged {len(entries)} entries to continuity/ — awaiting .safe_sync_approve to commit")

            # Advance last_sync_at to latest entry
            latest = max(e["created_at"] for e in entries if e.get("created_at"))
            state = _load_state()
            state["last_sync_at"] = latest
            _save_state(state)

            logger.info(f"Sync complete. {len(entries)} entries. Last sync: {latest}")
        except Exception as e:
            logger.error(f"Sync failed: {e}")

    def run(self) -> None:
        self.running = True
        logger.info(f"Starting SAFE sync daemon (interval: {self.interval}s)")
        try:
            while self.running:
                self.sync()
                time.sleep(self.interval)
        except KeyboardInterrupt:
            logger.info("Shutting down gracefully...")
        finally:
            self.running = False
            logger.info("Daemon stopped")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SAFE Continuity Sync Daemon")
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL)
    parser.add_argument("--safe-path", type=Path, default=SAFE_REPO_DEFAULT)
    parser.add_argument("--daemon", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    daemon = SafeSyncDaemon(args.safe_path, args.interval)
    if args.daemon:
        daemon.run()
    else:
        daemon.sync()


if __name__ == "__main__":
    main()


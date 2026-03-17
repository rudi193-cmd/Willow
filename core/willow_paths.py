"""
willow_paths.py — Canonical path definitions for Willow.

Two roots:

  WILLOW_HOME  — user-visible folder, lives in the OS home directory.
                 Windows: C:\\Users\\{name}\\Willow\\
                 Mac/Linux: ~/Willow/
                 Easy to find in File Explorer / Finder.
                 Cloud sync: just move it into Google Drive / iCloud / Dropbox.
                 Willow doesn't manage the sync — the OS does.

  WILLOW_CONFIG — hidden machine config. Never browsed by the user.
                  Always: ~/.willow/

Everything that a user would want to find goes under WILLOW_HOME.
Everything that is machine-level config goes under WILLOW_CONFIG.

Usage:
    from core.willow_paths import willow_home, willow_config, user_dir, nest_dir
"""

import os
import sys
from pathlib import Path


# ── Root resolution ────────────────────────────────────────────────────────────

def _find_home_root() -> Path:
    """
    Resolve the OS home directory.
    On WSL, prefer the Windows user home over the Linux home.
    Override with WILLOW_HOME env var.
    """
    override = os.getenv("WILLOW_HOME", "").strip()
    if override:
        return Path(override)

    # WSL: use the Windows home so the folder appears in Windows Explorer
    if sys.platform == "linux" and Path("/mnt/c/Users").exists():
        win_user = os.getenv("WSLENV", "")
        # Try to find the Windows username from the mounted path
        win_home_candidates = list(Path("/mnt/c/Users").iterdir())
        # Filter out system accounts
        skip = {"All Users", "Default", "Default User", "Public", "desktop.ini"}
        real_users = [p for p in win_home_candidates
                      if p.is_dir() and p.name not in skip]
        if len(real_users) == 1:
            return real_users[0] / "Willow"
        # Multiple users — fall back to matching the Linux username
        linux_user = os.getenv("USER", "")
        for p in real_users:
            if p.name.lower() == linux_user.lower():
                return p / "Willow"

    # Standard: ~/Willow
    return Path.home() / "Willow"


def _find_config_root() -> Path:
    """
    ~/.willow — hidden machine config directory.
    Override with WILLOW_CONFIG env var.
    """
    override = os.getenv("WILLOW_CONFIG", "").strip()
    if override:
        return Path(override)
    return Path.home() / ".willow"


# ── Module-level roots ─────────────────────────────────────────────────────────

def willow_home() -> Path:
    """
    User-visible Willow folder. Created on first access.
    Windows: C:\\Users\\{name}\\Willow\\
    Mac/Linux: ~/Willow/
    """
    p = _find_home_root()
    p.mkdir(parents=True, exist_ok=True)
    return p


def willow_config() -> Path:
    """
    Hidden machine config directory. Created on first access.
    Always: ~/.willow/
    """
    p = _find_config_root()
    p.mkdir(parents=True, exist_ok=True)
    return p


# ── User paths (under WILLOW_HOME) ────────────────────────────────────────────

def user_dir(username: str) -> Path:
    """
    Per-user directory. Created on first access.
    {willow_home}/users/{username}/
    """
    p = willow_home() / "users" / username
    p.mkdir(parents=True, exist_ok=True)
    return p


def user_pickup(username: str) -> Path:
    """
    Willow writes outputs here — handoffs, reports, agent responses.
    {willow_home}/users/{username}/pickup/
    """
    p = user_dir(username) / "pickup"
    p.mkdir(parents=True, exist_ok=True)
    return p


def user_drop(username: str) -> Path:
    """
    User drops files here for Willow to intake.
    {willow_home}/users/{username}/drop/
    """
    p = user_dir(username) / "drop"
    p.mkdir(parents=True, exist_ok=True)
    return p


def user_journal(username: str) -> Path:
    """
    Journal exports — human-readable, browsable.
    {willow_home}/users/{username}/journal/
    """
    p = user_dir(username) / "journal"
    p.mkdir(parents=True, exist_ok=True)
    return p


def user_profile(username: str) -> Path:
    """
    User profile documents — ECOSYSTEM.md, PREFERENCES.md, etc.
    {willow_home}/users/{username}/profile/
    """
    p = user_dir(username) / "profile"
    p.mkdir(parents=True, exist_ok=True)
    return p


# ── Nest (Pigeon inbox) ────────────────────────────────────────────────────────

def nest_dir() -> Path:
    """
    Pigeon message drop zone. Cloud apps write here; Willow reads and routes.
    {willow_home}/Nest/
    """
    p = willow_home() / "Nest"
    p.mkdir(parents=True, exist_ok=True)
    return p


def nest_inbox(app_id: str) -> Path:
    """
    Inbox for a specific app.
    {willow_home}/Nest/inbox/{app_id}/
    """
    p = nest_dir() / "inbox" / app_id
    p.mkdir(parents=True, exist_ok=True)
    return p


# ── Config paths (under ~/.willow) ────────────────────────────────────────────

def config_file() -> Path:
    """~/.willow/config.json"""
    return willow_config() / "config.json"


def logs_dir() -> Path:
    """~/.willow/logs/"""
    p = willow_config() / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def sessions_dir() -> Path:
    """~/.willow/sessions/"""
    p = willow_config() / "sessions"
    p.mkdir(parents=True, exist_ok=True)
    return p


def seeds_dir() -> Path:
    """~/.willow/seeds/"""
    p = willow_config() / "seeds"
    p.mkdir(parents=True, exist_ok=True)
    return p


# ── Repo paths (for server-side code that needs to find the repo) ──────────────

def _find_repo_root() -> Path:
    """Walk up from this file until we find server.py."""
    override = os.getenv("WILLOW_ROOT", "").strip()
    if override and Path(override).exists():
        return Path(override).resolve()
    candidate = Path(__file__).resolve()
    for parent in [candidate, *candidate.parents]:
        if (parent / "server.py").exists():
            return parent
    raise RuntimeError(
        "Cannot locate Willow repo root. Set WILLOW_ROOT env var to override."
    )


def repo_root() -> Path:
    """The Willow repository root (contains server.py)."""
    return _find_repo_root()


def artifacts_dir(username: str) -> Path:
    """
    Server-side artifacts — DBs, agent profiles, etc.
    {repo_root}/artifacts/{username}/
    NOT user-visible. Not synced to cloud.
    """
    p = repo_root() / "artifacts" / username
    p.mkdir(parents=True, exist_ok=True)
    return p


def knowledge_db(username: str) -> Path:
    """Path to user's SQLite knowledge DB (server-side)."""
    return artifacts_dir(username) / "willow_knowledge.db"


# ── Diagnostics ────────────────────────────────────────────────────────────────

def report(username: str = "Sweet-Pea-Rudi19") -> dict:
    """Return all resolved paths. Useful for debugging."""
    return {
        "willow_home":    str(willow_home()),
        "willow_config":  str(willow_config()),
        "user_dir":       str(user_dir(username)),
        "user_pickup":    str(user_pickup(username)),
        "user_drop":      str(user_drop(username)),
        "user_journal":   str(user_journal(username)),
        "user_profile":   str(user_profile(username)),
        "nest_dir":       str(nest_dir()),
        "nest_inbox":     str(nest_inbox("example-app")),
        "repo_root":      str(repo_root()),
        "artifacts_dir":  str(artifacts_dir(username)),
        "knowledge_db":   str(knowledge_db(username)),
    }


if __name__ == "__main__":
    import json
    print(json.dumps(report(), indent=2))

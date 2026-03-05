import sys
import sqlite3
import argparse
import json
from pathlib import Path

REGISTRY_PATH = Path("C:/Users/Sean/Documents/GitHub/die-namic-system/bridge_ring")
WILLOW_ROOT = Path("C:/Users/Sean/Documents/GitHub/Willow")
# No GDRIVE_BASE here — connectors are set by the user via OpAuth, not hardcoded

sys.path.insert(0, str(REGISTRY_PATH))

from instance_registry import register_instance


def create_user_dirs(username: str) -> None:
    """Create local artifact dir and one default local Drop folder."""
    user_artifacts = WILLOW_ROOT / "artifacts" / username
    user_artifacts.mkdir(parents=True, exist_ok=True)
    (user_artifacts / "Drop").mkdir(exist_ok=True)  # local default watch folder


def init_user_knowledge_db(username: str) -> None:
    """Create willow_knowledge.db with the production schema (lattice columns included)."""
    db_path = WILLOW_ROOT / "artifacts" / username / "willow_knowledge.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS knowledge (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            source_type     TEXT NOT NULL,
            source_id       TEXT NOT NULL UNIQUE,
            title           TEXT,
            summary         TEXT,
            content_snippet TEXT,
            category        TEXT DEFAULT 'reference',
            ring            TEXT DEFAULT 'bridge',
            created_at      TEXT,
            lattice_domain  TEXT,
            lattice_type    TEXT,
            lattice_status  TEXT
        )
    """)
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts
        USING fts5(title, summary, content_snippet, content='knowledge', content_rowid='id')
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_source_id ON knowledge(source_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_lattice ON knowledge(lattice_domain, lattice_type, lattice_status)")
    conn.commit()
    conn.close()


def create_user_config(username: str, display_name: str, trust_level: int) -> dict:
    """
    Write user_config.json with local-first watch_paths and empty connectors.
    Connectors (GDrive, Apple, GitHub, etc.) are added later by the user via OpAuth.
    """
    trust_names = {0: "OBSERVER", 1: "WORKER", 2: "OPERATOR", 3: "ENGINEER", 4: "ARCHITECT"}
    local_drop = str(WILLOW_ROOT / "artifacts" / username / "Drop")
    config = {
        "username": username,
        "display_name": display_name,
        "trust_level": trust_level,
        "trust_name": trust_names.get(trust_level, "WORKER"),
        "knowledge_db": str(WILLOW_ROOT / "artifacts" / username / "willow_knowledge.db"),
        "watch_paths": [local_drop],   # user controls this list — connectors add to it via OpAuth
        "connectors": {},              # populated by OpAuth: {"gdrive": {...}, "apple": {...}, ...}
    }
    config_path = WILLOW_ROOT / "artifacts" / username / "user_config.json"
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return config


def register_user(username: str, display_name: str, trust_level: int = 1) -> None:
    create_user_dirs(username)
    init_user_knowledge_db(username)
    config = create_user_config(username, display_name, trust_level)
    register_instance(
        instance_id=username, name=display_name,
        instance_type="user", trust_level=trust_level,
        escalates_to="human-chief", metadata={"admin": trust_level >= 4}
    )
    print(f"Registered: {username} ({display_name}) trust={trust_level}")
    print(f"  DB:         {config['knowledge_db']}")
    print(f"  Local Drop: {config['watch_paths'][0]}")
    print(f"  Connectors: none (add via OpAuth)")


def main():
    parser = argparse.ArgumentParser(description="Register a Willow user")
    parser.add_argument("--username", required=True)
    parser.add_argument("--display-name", required=True)
    parser.add_argument("--trust-level", type=int, default=1, choices=[0,1,2,3,4])
    args = parser.parse_args()
    register_user(args.username, args.display_name, args.trust_level)


if __name__ == "__main__":
    main()

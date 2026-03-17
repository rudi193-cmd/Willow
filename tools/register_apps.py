"""
Register SAFE Apps
==================
Scans for safe-app-manifest.json files in ../safe-app-* directories and
populates the registered_apps table. Idempotent — safe to re-run.

Usage:
    python tools/register_apps.py              # scan manifests
    python tools/register_apps.py --list       # show registered apps
    python tools/register_apps.py --db PATH    # custom DB path
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.db import get_connection

WILLOW_ROOT = Path(__file__).resolve().parent.parent
GITHUB_ROOT = WILLOW_ROOT.parent
DEFAULT_DB = WILLOW_ROOT / "artifacts" / "Sweet-Pea-Rudi19" / "willow_knowledge.db"

# Fallback if a manifest isn't found on disk
FALLBACK_APPS = [
    {"app_id": "ask-jeles",       "name": "AskJeles",        "description": "Verified-source librarian. Smithsonian, LoC, NASA, NIH."},
    {"app_id": "law-gazelle",     "name": "Law Gazelle",     "description": "Legal research. Case summaries, statute analysis."},
    {"app_id": "nasa-archive",    "name": "NASA Archive",    "description": "Space history and rally documentation."},
    {"app_id": "the-binder",      "name": "The Binder",      "description": "Knowledge graph tools and cross-domain linking."},
    {"app_id": "utety-chat",      "name": "UTETY Chat",      "description": "Applied reality engineering courses."},
    {"app_id": "source-trail",    "name": "Source Trail",    "description": "Citation and provenance tracking."},
    {"app_id": "field-notes",     "name": "Field Notes",     "description": "Field observations and structured notes."},
    {"app_id": "public-ledger",   "name": "Public Ledger",   "description": "Public governance and financial records."},
    {"app_id": "private-ledger",  "name": "Private Ledger",  "description": "Personal finance and private records."},
    {"app_id": "grove",           "name": "Grove",           "description": "Community knowledge garden."},
    {"app_id": "the-squirrel",    "name": "The Squirrel",    "description": "Bookmark and resource collection."},
    {"app_id": "dating-wellbeing","name": "Dating & Wellbeing", "description": "Relationship and wellbeing tracking."},
    {"app_id": "game",            "name": "Game",            "description": "Interactive game and narrative."},
    {"app_id": "ganesha-cli",     "name": "Ganesha (Claude Code)", "description": "Claude Code CLI — session handoffs and engineering drops."},
]


def connect(db_path=None):
    return get_connection()


def scan_manifests() -> list[dict]:
    """Find all safe-app-manifest.json files in sibling safe-app-* dirs."""
    manifests = []
    for manifest_path in sorted(GITHUB_ROOT.glob("safe-app-*/safe-app-manifest.json")):
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            data["_manifest_path"] = str(manifest_path)
            manifests.append(data)
        except Exception as e:
            print(f"  WARN: could not parse {manifest_path}: {e}")
    return manifests


def build_app_record(data: dict, manifest_path: str = "") -> dict:
    # Strip safe-app- prefix from manifest app_ids (some manifests use it, the registry doesn't)
    raw_id = data.get("app_id", "")
    app_id = raw_id.removeprefix("safe-app-") if raw_id else raw_id
    return {
        "app_id":        app_id,
        "name":          data.get("name", data.get("app_id", "")),
        "description":   data.get("description", ""),
        "version":       data.get("version", ""),
        "permissions":   json.dumps(data.get("permissions", [])),
        "privacy_tier":  data.get("privacy_tier", ""),
        "manifest_path": manifest_path or data.get("_manifest_path", ""),
        "registered_at": datetime.now(timezone.utc).isoformat(),
    }


def upsert_app(conn, record: dict) -> str:
    """Insert or update an app. Returns 'inserted' or 'updated'."""
    existing = conn.execute(
        "SELECT app_id FROM registered_apps WHERE app_id=?", (record["app_id"],)
    ).fetchone()

    if existing:
        conn.execute("""
            UPDATE registered_apps
            SET name=?, description=?, version=?, permissions=?, privacy_tier=?, manifest_path=?
            WHERE app_id=?
        """, (record["name"], record["description"], record["version"],
              record["permissions"], record["privacy_tier"], record["manifest_path"],
              record["app_id"]))
        return "updated"
    else:
        conn.execute("""
            INSERT INTO registered_apps
            (app_id, name, description, version, permissions, privacy_tier, manifest_path, registered_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (record["app_id"], record["name"], record["description"], record["version"],
              record["permissions"], record["privacy_tier"], record["manifest_path"],
              record["registered_at"]))
        return "inserted"


def register_from_manifests(conn) -> tuple[int, int]:
    """Scan disk manifests. Returns (inserted, updated)."""
    manifests = scan_manifests()
    inserted = updated = 0
    for data in manifests:
        record = build_app_record(data, data.get("_manifest_path", ""))
        action = upsert_app(conn, record)
        print(f"  {action:8s}  {record['app_id']}  ({record['name']})")
        if action == "inserted":
            inserted += 1
        else:
            updated += 1
    return inserted, updated


def register_fallbacks(conn) -> tuple[int, int]:
    """Register fallback apps not already in DB."""
    existing_ids = {r[0] for r in conn.execute("SELECT app_id FROM registered_apps")}
    inserted = 0
    for app in FALLBACK_APPS:
        if app["app_id"] not in existing_ids:
            record = build_app_record(app)
            upsert_app(conn, record)
            print(f"  inserted  {app['app_id']}  ({app['name']})  [fallback]")
            inserted += 1
    return inserted, 0


def list_apps(conn):
    rows = conn.execute(
        "SELECT app_id, name, description, version, privacy_tier FROM registered_apps ORDER BY app_id"
    ).fetchall()
    print(f"\n{'APP_ID':<25} {'NAME':<25} {'TIER':<12} {'VER'}")
    print("-" * 80)
    for r in rows:
        print(f"  {r['app_id']:<23} {r['name']:<23} {r['privacy_tier'] or '—':<12} {r['version'] or '—'}")
    print(f"\nTotal: {len(rows)} apps")


def main():
    parser = argparse.ArgumentParser(description="Register SAFE apps in Willow")
    parser.add_argument("--list", action="store_true", help="List registered apps")
    parser.add_argument("--db",   default=None,        help="Path to knowledge DB")
    args = parser.parse_args()

    conn = connect()

    # Ensure tables exist (in case init_db hasn't been called with new schema yet)
    conn.execute("""CREATE TABLE IF NOT EXISTS registered_apps (
        app_id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT,
        version TEXT, permissions TEXT, privacy_tier TEXT,
        manifest_path TEXT, registered_at TEXT NOT NULL
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS app_consent (
        id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
        username TEXT NOT NULL, app_id TEXT NOT NULL,
        consented INTEGER NOT NULL DEFAULT 0,
        granted_at TEXT, revoked_at TEXT,
        UNIQUE (username, app_id)
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_consent_user ON app_consent(username)")
    conn.commit()

    if args.list:
        list_apps(conn)
        conn.close()
        return

    print("=== REGISTER SAFE APPS ===\n")
    print("Scanning manifests...")
    ins, upd = register_from_manifests(conn)

    print("\nChecking fallbacks...")
    fins, _ = register_fallbacks(conn)

    conn.commit()
    total = conn.execute("SELECT COUNT(*) FROM registered_apps").fetchone()[0]
    print(f"\nDone: {ins} inserted, {upd} updated, {fins} fallbacks added")
    print(f"Total registered apps: {total}")
    conn.close()


if __name__ == "__main__":
    main()

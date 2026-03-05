"""
MIGRATION: Move flat artifacts/ into per-user artifacts/{username}/ structure.

One-time script. Safe to run multiple times (idempotent — skips if already migrated).

Run from Willow repo root:
    python migrate_to_per_user.py
"""

import os
import shutil
import sqlite3

EARTH_PATH = os.path.dirname(os.path.abspath(__file__))
ARTIFACTS_PATH = os.path.join(EARTH_PATH, "artifacts")
USERNAME = "Sweet-Pea-Rudi19"
USER_PATH = os.path.join(ARTIFACTS_PATH, USERNAME)
OLD_MASTER_DB = os.path.join(EARTH_PATH, "willow_index.db")
NEW_MASTER_DB = os.path.join(USER_PATH, "willow_index.db")


def migrate():
    # Check if already migrated
    if os.path.exists(USER_PATH) and os.listdir(USER_PATH):
        print(f"[SKIP] {USER_PATH} already exists and has content.")
        print("       If you need to re-migrate, remove it first.")
        return

    os.makedirs(USER_PATH, exist_ok=True)

    # Move category folders (everything except 'pending' and user folders)
    moved = 0
    skipped = []
    for item in os.listdir(ARTIFACTS_PATH):
        item_path = os.path.join(ARTIFACTS_PATH, item)
        if not os.path.isdir(item_path):
            continue
        # Skip the new user folder itself and any other user folders
        if item == USERNAME:
            continue
        # Move category folder into user folder
        dest = os.path.join(USER_PATH, item)
        print(f"  MOVE: artifacts/{item}/ -> artifacts/{USERNAME}/{item}/")
        shutil.move(item_path, dest)
        moved += 1

    print(f"\n[OK] Moved {moved} category folders into {USERNAME}/")

    # Move master DB
    if os.path.exists(OLD_MASTER_DB):
        print(f"  MOVE: willow_index.db -> artifacts/{USERNAME}/willow_index.db")
        shutil.move(OLD_MASTER_DB, NEW_MASTER_DB)

        # Upgrade schema: add new columns if missing
        try:
            conn = sqlite3.connect(NEW_MASTER_DB)
            existing = [row[1] for row in conn.execute("PRAGMA table_info(file_registry)").fetchall()]
            new_cols = {
                'archive_date': 'TEXT',
                'archive_path': 'TEXT',
                'deleted_date': 'TEXT',
                'flagged_reason': 'TEXT',
                'retain_context': 'INTEGER DEFAULT 1',
            }
            # Update status default from 'SORTED' to 'active'
            if 'status' in existing:
                conn.execute("UPDATE file_registry SET status='active' WHERE status='SORTED'")

            for col, col_type in new_cols.items():
                if col not in existing:
                    conn.execute(f"ALTER TABLE file_registry ADD COLUMN {col} {col_type}")
                    print(f"  ADD COLUMN: file_registry.{col}")

            conn.commit()
            conn.close()
            print(f"[OK] Master DB migrated and schema upgraded.")
        except Exception as e:
            print(f"[WARN] DB schema upgrade: {e}")
    else:
        print(f"[SKIP] No willow_index.db to migrate.")

    # Upgrade per-folder catalog.db schemas
    for root, dirs, files in os.walk(USER_PATH):
        for f in files:
            if f == "catalog.db":
                db_path = os.path.join(root, f)
                try:
                    conn = sqlite3.connect(db_path)
                    existing = [row[1] for row in conn.execute("PRAGMA table_info(file_registry)").fetchall()]
                    new_cols = {
                        'archive_date': 'TEXT',
                        'archive_path': 'TEXT',
                        'deleted_date': 'TEXT',
                        'flagged_reason': 'TEXT',
                        'retain_context': 'INTEGER DEFAULT 1',
                    }
                    if 'status' in existing:
                        conn.execute("UPDATE file_registry SET status='active' WHERE status='SORTED'")

                    for col, col_type in new_cols.items():
                        if col not in existing:
                            conn.execute(f"ALTER TABLE file_registry ADD COLUMN {col} {col_type}")

                    conn.commit()
                    conn.close()
                    rel = os.path.relpath(db_path, ARTIFACTS_PATH)
                    print(f"  UPGRADED: {rel}")
                except Exception as e:
                    print(f"  [WARN] {db_path}: {e}")

    # Create pending dir for user
    pending = os.path.join(USER_PATH, "pending")
    os.makedirs(pending, exist_ok=True)
    print(f"\n[DONE] Migration complete. User '{USERNAME}' is ready.")


if __name__ == "__main__":
    print(f"=== WILLOW MIGRATION: Flat -> Per-User ===")
    print(f"Source: {ARTIFACTS_PATH}")
    print(f"Target: {USER_PATH}")
    print()
    migrate()

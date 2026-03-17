"""
Roots Config — Willow File System Roots
========================================
Manages the configured filesystem roots: directories Willow watches and indexes
so it can answer questions about local file structure beyond the Drop folder.

Stored per-user at: artifacts/{username}/roots.json

CHECKSUM: ΔΣ=42
"""

import json
from datetime import datetime
from pathlib import Path

ARTIFACTS_BASE = Path(r"C:\Users\Sean\Documents\GitHub\Willow\artifacts")


def _roots_path(username: str) -> Path:
    p = ARTIFACTS_BASE / username
    p.mkdir(parents=True, exist_ok=True)
    return p / "roots.json"


def load_roots(username: str) -> list:
    """Load configured roots for user. Returns list of root dicts."""
    p = _roots_path(username)
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_roots(username: str, roots: list):
    """Save roots list to disk."""
    _roots_path(username).write_text(
        json.dumps(roots, indent=2), encoding="utf-8"
    )


def add_root(username: str, path: str, label: str = "", recursive: bool = True) -> dict:
    """Add a root path. Returns the root entry."""
    roots = load_roots(username)
    # Deduplicate
    if any(r["path"] == path for r in roots):
        return next(r for r in roots if r["path"] == path)
    entry = {
        "path": path,
        "label": label or Path(path).name,
        "recursive": recursive,
        "added_at": datetime.now().isoformat(),
        "last_scanned": None,
    }
    roots.append(entry)
    save_roots(username, roots)
    return entry


def remove_root(username: str, path: str) -> bool:
    """Remove a root path. Returns True if removed."""
    roots = load_roots(username)
    new_roots = [r for r in roots if r["path"] != path]
    if len(new_roots) == len(roots):
        return False
    save_roots(username, new_roots)
    return True


def scan_roots(username: str, db_path: Path) -> dict:
    """
    Scan all configured roots and index file metadata into willow_knowledge.db.
    
    Adds entries with:
        source_type = "filesystem_root"
        category    = "files"
        title       = relative path from root
        summary     = size + modified date
        content_snippet = absolute path
    
    Returns {"indexed": int, "skipped": int, "roots_scanned": int}
    """
    roots = load_roots(username)
    if not roots:
        return {"indexed": 0, "skipped": 0, "roots_scanned": 0}

    # File types worth indexing
    TEXT_EXTS = {
        ".md", ".txt", ".py", ".js", ".ts", ".json", ".yaml", ".yml",
        ".html", ".css", ".csv", ".rst", ".toml", ".ini", ".cfg",
        ".bat", ".sh", ".ps1", ".sql",
    }

    from core.db import get_connection
    conn = get_connection()

    # Ensure filesystem columns exist (no-op if already present)
    for col in ("file_path", "file_ext"):
        try:
            conn.execute(f"ALTER TABLE knowledge ADD COLUMN {col} TEXT")
            conn.commit()
        except Exception:
            pass  # column already exists

    indexed = 0
    skipped = 0

    for root_entry in roots:
        root_path = Path(root_entry["path"])
        if not root_path.exists():
            skipped += 1
            continue

        pattern = "**/*" if root_entry.get("recursive", True) else "*"
        for file_path in root_path.glob(pattern):
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in TEXT_EXTS:
                continue

            try:
                stat = file_path.stat()
                rel = str(file_path.relative_to(root_path))
                title = rel
                summary = f"{_human_size(stat.st_size)} — modified {datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d')}"
                snippet = str(file_path)
                label = root_entry.get("label", root_path.name)
                now = datetime.now().isoformat()

                # Upsert by file_path
                existing = conn.execute(
                    "SELECT id FROM knowledge WHERE file_path=?", (snippet,)
                ).fetchone()

                if existing:
                    conn.execute(
                        """UPDATE knowledge SET title=?, summary=?, content_snippet=?,
                           source_type=?, category=?, created_at=?, file_ext=?
                           WHERE file_path=?""",
                        (title, summary, snippet, "filesystem_root", "files",
                         now, file_path.suffix.lower(), snippet)
                    )
                else:
                    conn.execute(
                        """INSERT INTO knowledge
                           (title, summary, content_snippet, source_type, category,
                            ring, created_at, file_path, file_ext)
                           VALUES (?,?,?,?,?,?,?,?,?)""",
                        (title, summary, snippet, "filesystem_root", "files",
                         "bridge", now, snippet, file_path.suffix.lower())
                    )
                indexed += 1

            except Exception:
                skipped += 1
                continue

    conn.commit()
    conn.close()

    # Update last_scanned timestamps
    now_str = datetime.now().isoformat()
    roots_updated = load_roots(username)
    for r in roots_updated:
        if Path(r["path"]).exists():
            r["last_scanned"] = now_str
    save_roots(username, roots_updated)

    return {"indexed": indexed, "skipped": skipped, "roots_scanned": len(roots)}


def _human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"

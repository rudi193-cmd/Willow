"""
Bulk Repo + Google Drive Ingestion — Get Willow Swoll

Walks repos and Google Drive, inserts knowledge atoms directly.
NO LLM calls — fast, safe, won't flood the fleet.
Summaries left NULL; topology/coherence fill them in later.

Usage:
    python scripts/bulk_ingest.py           # dry run
    python scripts/bulk_ingest.py --ingest  # actually ingest
    python scripts/bulk_ingest.py --ingest --verbose
"""
import sys
import hashlib
import argparse
import re
import time
from pathlib import Path
from datetime import datetime

WILLOW_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(WILLOW_ROOT))

from core.loam import init_db, _connect, _extract_entities_regex, get_ring
from core.db import get_connection

USERNAME = "Sweet-Pea-Rudi19"
GDRIVE = Path("C:/Users/Sean/My Drive")
GITHUB = WILLOW_ROOT.parent

# (path, ring, category)
SOURCES = [
    # Source Ring — repos
    (GITHUB / "die-namic-system" / "governance",       "source",      "governance"),
    (GITHUB / "die-namic-system" / "source_ring",      "source",      "code"),
    (GITHUB / "die-namic-system" / "docs",             "source",      "narrative"),
    (GITHUB / "die-namic-system" / "continuity_ring",  "continuity",  "narrative"),
    (GITHUB / "die-namic-system" / "scripts",          "source",      "code"),
    (GITHUB / "die-namic-system" / "tools",            "source",      "code"),
    (GITHUB / "SAFE" / "governance",                   "source",      "governance"),
    (GITHUB / "SAFE" / "schemas",                      "source",      "specs"),
    (GITHUB / "SAFE" / "docs",                         "source",      "narrative"),
    # Bridge Ring — Willow code
    (WILLOW_ROOT / "core",                             "bridge",      "code"),
    (WILLOW_ROOT / "apps",                             "bridge",      "code"),
    (WILLOW_ROOT / "scripts",                          "bridge",      "code"),
    (WILLOW_ROOT / "schema",                           "bridge",      "specs"),
    (WILLOW_ROOT / "governance",                       "bridge",      "governance"),
    (WILLOW_ROOT / "neocities",                        "bridge",      "code"),
    (GITHUB / "vision-board" / "backend",              "bridge",      "code"),
    (GITHUB / "vision-board" / "frontend" / "src",     "bridge",      "code"),
    # Google Drive — Source/Continuity material
    (GDRIVE / "die-namic-system" / "training_data",    "source",      "data"),
    (GDRIVE / "die-namic-system" / "origin_materials", "source",      "narrative"),
    (GDRIVE / "die-namic-system" / "awa",              "source",      "specs"),
    (GDRIVE / "die-namic-system" / "canvas",           "source",      "narrative"),
    (GDRIVE / "die-namic-system" / "docs",             "source",      "narrative"),
    (GDRIVE / "die-namic-system" / "governance",       "source",      "governance"),
    (GDRIVE / "die-namic-system" / "continuity_ring",  "continuity",  "narrative"),
    (GDRIVE / "Captures",                              "bridge",      "screenshots"),
    (GDRIVE / "Archive",                               "continuity",  "documents"),
    (GDRIVE / "Career",                                "continuity",  "documents"),
    (GDRIVE / "Creative",                              "source",      "narrative"),
    (GDRIVE / "Data",                                  "bridge",      "data"),
    (GDRIVE / "Journal",                               "continuity",  "narrative"),
    (GDRIVE / "Media",                                 "bridge",      "photos"),
    (GDRIVE / "Personal",                              "continuity",  "narrative"),
    (GDRIVE / "Projects",                              "source",      "narrative"),
    (GDRIVE / "System",                                "source",      "specs"),
    (GDRIVE / "Transcripts",                           "continuity",  "narrative"),
    (GDRIVE / "Campbell_WCA_25-01325_Mediation_Notebook_2026-02-06", "continuity", "documents"),
]

TEXT_EXTS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css",
    ".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".csv",
    ".sh", ".bat", ".ps1", ".sql", ".xml", ".rst",
}

SKIP_DIRS = {
    "node_modules", "__pycache__", ".git", ".venv", "venv",
    "dist", "build", ".next", ".nuxt", ".tmp.drivedownload",
    ".tmp.driveupload", "$RECYCLE.BIN", ".pytest_cache",
}

SKIP_FILES = {"desktop.ini", ".DS_Store", "Thumbs.db",
              "package-lock.json", "yarn.lock"}

MAX_FILE_SIZE = 200_000  # 200KB


def should_skip(path: Path) -> bool:
    if path.name in SKIP_FILES:
        return True
    if path.suffix.lower() not in TEXT_EXTS:
        return True
    try:
        if path.stat().st_size > MAX_FILE_SIZE:
            return True
    except Exception:
        return True
    return False


def infer_category(path: Path, default: str) -> str:
    parts = {p.lower() for p in path.parts}
    name = path.name.lower()
    if "governance" in parts:
        return "governance"
    if "continuity_ring" in parts or "journal" in parts or "transcripts" in parts:
        return "narrative"
    if "schemas" in parts or "schema" in parts or "specs" in parts or "awa" in parts:
        return "specs"
    if "training_data" in parts or "data" in parts:
        return "data"
    if "captures" in parts or "screenshots" in parts:
        return "screenshots"
    if path.suffix in (".py", ".js", ".ts", ".sh", ".bat"):
        return "code"
    if path.suffix in (".json", ".csv", ".yaml", ".yml"):
        return "data"
    if path.suffix == ".md":
        return "narrative"
    return default


def file_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()[:32]


def direct_insert(db_path: str, filename: str, fhash: str, category: str,
                  ring: str, snippet: str, now: str, retries: int = 8):
    """Insert knowledge atom directly, no LLM. Opens fresh connection per insert."""
    for attempt in range(retries):
        try:
            conn = get_connection()
            cur = conn.cursor()

            if cur.execute("SELECT id FROM knowledge WHERE source_type='file' AND source_id=?",
                           (fhash,)).fetchone():
                conn.close()
                return False

            entities = _extract_entities_regex(f"{filename} {snippet}")

            cur.execute(
                """INSERT OR IGNORE INTO knowledge
                   (source_type, source_id, title, summary, content_snippet,
                    category, ring, created_at)
                   VALUES ('file', ?, ?, NULL, ?, ?, ?, ?)""",
                (fhash, filename, snippet[:1000], category, ring, now)
            )
            kid = cur.lastrowid
            if kid and entities:
                cur.executemany(
                    """INSERT OR IGNORE INTO knowledge_entities
                       (knowledge_id, entity_name, entity_type)
                       VALUES (?, ?, ?)""",
                    [(kid, e["name"], e.get("type", "unknown")) for e in entities]
                )
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            if "locked" in str(e) and attempt < retries - 1:
                time.sleep(0.1)
                continue
            raise


def walk_source(base: Path, ring: str, default_cat: str):
    if not base.exists():
        return
    for path in base.rglob("*"):
        if not path.is_file():
            continue
        if any(s in path.parts for s in SKIP_DIRS):
            continue
        if should_skip(path):
            continue
        yield path, ring, infer_category(path, default_cat)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ingest", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    init_db(USERNAME)
    from core.loam import _db_path
    db_path = _db_path(USERNAME)

    total = skipped = ingested = errors = 0
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    print(f"{'DRY RUN' if not args.ingest else 'INGESTING'} - {now}")
    print(f"Target: {USERNAME}\n")

    for base, ring, default_cat in SOURCES:
        count = 0
        print(f"  scanning {base.name}...", flush=True)
        for path, r, cat in walk_source(base, ring, default_cat):
            total += 1
            count += 1
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                skipped += 1
                continue

            if len(content.strip()) < 20:
                skipped += 1
                continue

            fhash = file_hash(content)

            if args.ingest:
                try:
                    ok = direct_insert(db_path, str(path), fhash, cat, r,
                                       content[:1000], now)
                    if ok:
                        ingested += 1
                        if args.verbose:
                            print(f"  OK  [{r:11s}] {path.name}")
                    else:
                        skipped += 1
                except Exception as e:
                    errors += 1
                    if args.verbose:
                        print(f"  ERR {path.name}: {e}")

        if count > 0:
            label = str(base).replace(str(GITHUB), "").replace(str(GDRIVE), "[G]").replace(str(WILLOW_ROOT), "[W]")
            print(f"  {label:65s} {count:4d} files")

    print(f"\n{'-'*50}")
    if args.ingest:
        print(f"Ingested: {ingested}  Skipped: {skipped}  Errors: {errors}  Total: {total}")
    else:
        print(f"Would process: {total} files")
        print("Run with --ingest to apply.")


if __name__ == "__main__":
    main()

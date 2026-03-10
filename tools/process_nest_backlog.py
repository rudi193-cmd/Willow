#!/usr/bin/env python3
"""
Willow Nest Backlog Processor
Processes all files from Nest subdirectories that Pigeon never scans.
Run from WSL: python3 tools/process_nest_backlog.py [--dry-run] [--photos-only]

TASK 1: Walk category subdirs in Nest (legal/, personal/, media/, code/, reference/, narrative/)
        and process each file through pigeon._process_one().
TASK 2: Create pigeon_dropping + knowledge records for photos already filed to
        Filed/media/photos/ that have no DB record.
TASK 3: Queue all photo files (new + existing) for Windows-side OCR via Pickup folder.
"""

import os
import sys
import json
import hashlib
import argparse
import logging
from datetime import datetime, UTC
from pathlib import Path

# Ensure Willow repo is on the path
REPO = "/mnt/c/Users/Sean/Documents/GitHub/Willow"
sys.path.insert(0, REPO)

from core.db import get_connection
from core import pigeon

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("backlog")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

USERNAME = "Sweet-Pea-Rudi19"
NEST_ROOT = "/mnt/c/Users/Sean/Willow/Nest"
FILED_ROOT = "/mnt/c/Users/Sean/Willow/Filed"
PHOTOS_DIR = os.path.join(FILED_ROOT, "media", "photos")
PICKUP_DIR = "/mnt/c/Users/Sean/My Drive/Willow/Auth Users/Sweet-Pea-Rudi19/Pickup"
DB_PATH = os.path.join(REPO, "artifacts", "Sweet-Pea-Rudi19", "willow_knowledge.db")

# Category subdirs Pigeon does NOT scan (it only scans root + agent-named subdirs)
CATEGORY_SUBDIRS = {"legal", "personal", "media", "code", "reference", "narrative"}

# Extensions to skip entirely (binary / large / non-text formats)
SKIP_EXTENSIONS = {
    ".exe", ".dll", ".gguf", ".bin", ".iso", ".msi",
    ".app", ".dmg", ".step", ".stl", ".obj", ".scad",
    ".dxf", ".fbx",
    # Key/cert files
    ".key", ".pem", ".p12", ".pfx", ".cer", ".crt", ".der",
}

# Sensitive path fragments — skip any file/dir containing these
SENSITIVE_FRAGMENTS = {
    "api-key", "api-keys", "credentials", "secret", "token",
    "auth-key", "auth-keys", "private-key", "ssh-key",
}

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB

PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif", ".webp", ".heic"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _wsl_to_win(wsl_path: str) -> str:
    """Convert /mnt/c/... WSL path to C:\\... Windows path."""
    if wsl_path.startswith("/mnt/c/"):
        return "C:\\" + wsl_path[7:].replace("/", "\\")
    return wsl_path.replace("/", "\\")


def _file_hash(path: Path) -> str:
    """MD5 of first 64 KB + file size (matches pigeon._file_hash)."""
    h = hashlib.md5()
    try:
        with open(path, "rb") as f:
            h.update(f.read(65536))
        h.update(str(path.stat().st_size).encode())
    except Exception:
        h.update(path.name.encode())
    return h.hexdigest()


def _should_skip(path: Path) -> tuple[bool, str]:
    """Return (True, reason) if the file should be skipped."""
    path_str = str(path).lower()

    # Hidden files
    if path.name.startswith("."):
        return True, "hidden file"

    # .gitkeep
    if path.name == ".gitkeep":
        return True, ".gitkeep"

    # Sensitive path fragments
    for frag in SENSITIVE_FRAGMENTS:
        if frag in path_str:
            return True, f"sensitive path fragment '{frag}'"

    # Extension check
    if path.suffix.lower() in SKIP_EXTENSIONS:
        return True, f"skipped extension {path.suffix}"

    # Size check
    try:
        if path.stat().st_size > MAX_FILE_SIZE:
            return True, f"file too large ({path.stat().st_size / 1024 / 1024:.1f} MB)"
    except OSError:
        return True, "unreadable (stat failed)"

    return False, ""


def _dropping_exists_for_filename(filename: str) -> bool:
    """Check pigeon_droppings for an existing record by filename."""
    try:
        conn = get_connection()
        row = conn.execute(
            "SELECT id FROM pigeon_droppings WHERE filename=? AND username=? LIMIT 1",
            (filename, USERNAME),
        ).fetchone()
        conn.close()
        return row is not None
    except Exception as e:
        log.warning(f"DB check failed for {filename}: {e}")
        return False


def _knowledge_exists_for_hash(file_hash: str) -> bool:
    """Check knowledge table for an existing record by file_hash (source_id)."""
    try:
        conn = get_connection()
        row = conn.execute(
            "SELECT id FROM knowledge WHERE source_type='file' AND source_id=? LIMIT 1",
            (file_hash,),
        ).fetchone()
        conn.close()
        return row is not None
    except Exception as e:
        log.warning(f"Knowledge DB check failed for hash {file_hash}: {e}")
        return False


# ---------------------------------------------------------------------------
# Task 1 — Process files in category subdirs of Nest
# ---------------------------------------------------------------------------

def collect_nest_backlog() -> list[Path]:
    """Walk category subdirs under Nest and return all processable files."""
    candidates = []
    nest = Path(NEST_ROOT)
    if not nest.exists():
        log.warning(f"Nest root not found: {NEST_ROOT}")
        return candidates

    for subdir_name in CATEGORY_SUBDIRS:
        subdir = nest / subdir_name
        if not subdir.exists():
            continue
        for item in subdir.rglob("*"):
            if not item.is_file():
                continue
            skip, reason = _should_skip(item)
            if skip:
                log.debug(f"SKIP {item.relative_to(nest)}: {reason}")
                continue
            candidates.append(item)

    return sorted(candidates)


def process_nest_backlog(dry_run: bool = False) -> list[dict]:
    """Task 1: Process all unscanned category subdir files."""
    files = collect_nest_backlog()
    total = len(files)
    results = []

    if total == 0:
        log.info("TASK 1: No files found in Nest category subdirs.")
        return results

    log.info(f"TASK 1: Found {total} file(s) in Nest category subdirs.")

    for i, item in enumerate(files, start=1):
        rel = item.relative_to(Path(NEST_ROOT))
        label = f"[{i}/{total}] Filing: {rel}"

        if dry_run:
            print(f"  [DRY-RUN] {label}")
            results.append({"path": str(item), "action": "would_file"})
            continue

        print(f"  {label}")
        try:
            fh = _file_hash(item)
            result = pigeon._process_one(item, USERNAME, fh)
            if result:
                log.info(f"  -> {result.get('category')}/{result.get('filename')}")
                results.append(result)
            else:
                log.warning(f"  _process_one returned None for {item.name}")
        except Exception as e:
            log.error(f"  ERROR processing {item}: {e}")

    return results


# ---------------------------------------------------------------------------
# Task 2 — Create records for already-filed-but-unrecorded photos
# ---------------------------------------------------------------------------

def collect_unrecorded_photos() -> list[Path]:
    """Return photo files in Filed/media/photos/ that have no pigeon_dropping record."""
    photos_path = Path(PHOTOS_DIR)
    if not photos_path.exists():
        log.warning(f"Photos dir not found: {PHOTOS_DIR}")
        return []

    unrecorded = []
    for item in sorted(photos_path.iterdir()):
        if not item.is_file():
            continue
        if item.suffix.lower() not in PHOTO_EXTENSIONS:
            continue
        if item.name.startswith("."):
            continue
        if not _dropping_exists_for_filename(item.name):
            unrecorded.append(item)

    return unrecorded


def process_unrecorded_photos(dry_run: bool = False) -> list[Path]:
    """Task 2: Create pigeon_dropping + knowledge records for already-filed photos."""
    photos = collect_unrecorded_photos()
    total = len(photos)
    processed = []

    if total == 0:
        log.info("TASK 2: No unrecorded photos found in Filed/media/photos/.")
        return processed

    log.info(f"TASK 2: Found {total} unrecorded photo(s) to record.")

    # Ensure DB tables exist before writing
    pigeon.init_droppings_table()

    for i, item in enumerate(photos, start=1):
        label = f"[{i}/{total}] Recording: {item.name}"

        if dry_run:
            print(f"  [DRY-RUN] {label}")
            processed.append(item)
            continue

        print(f"  {label}")
        try:
            fh = _file_hash(item)
            filed_to = str(item)
            summary = f"Photo: {item.name}"

            # Pigeon dropping record
            pigeon.create_dropping(
                username=USERNAME,
                filename=item.name,
                original_path=filed_to,
                filed_to=filed_to,
                category="media",
                summary=summary,
                file_hash=fh,
            )

            # Knowledge record (skip if already present)
            if not _knowledge_exists_for_hash(fh):
                try:
                    import core.knowledge as kmod
                    kmod.ingest_file_knowledge(
                        username=USERNAME,
                        filename=item.name,
                        file_hash=fh,
                        category="media",
                        content_text=f"IMAGE: {item.name}",
                        provider="backlog_processor",
                    )
                except Exception as ke:
                    log.warning(f"  Knowledge ingest failed for {item.name}: {ke}")

            log.info(f"  Recorded: {item.name}")
            processed.append(item)
        except Exception as e:
            log.error(f"  ERROR recording {item.name}: {e}")

    return processed


# ---------------------------------------------------------------------------
# Task 3 — Queue photos for OCR
# ---------------------------------------------------------------------------

def queue_photos_for_ocr(photo_paths: list[Path], dry_run: bool = False) -> int:
    """Task 3: Write OCR queue files to Pickup folder for Windows-side processing."""
    if not photo_paths:
        log.info("TASK 3: No photos to queue for OCR.")
        return 0

    pickup = Path(PICKUP_DIR)
    if not dry_run:
        pickup.mkdir(parents=True, exist_ok=True)

    total = len(photo_paths)
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    queued = 0

    log.info(f"TASK 3: Queuing {total} photo(s) for OCR in Pickup folder.")

    for i, item in enumerate(photo_paths, start=1):
        win_path = _wsl_to_win(str(item))
        payload = {
            "source_file": win_path,
            "username": USERNAME,
            "category": "media",
            "subcategory": "photos",
            "created_at": datetime.now(UTC).isoformat(),
        }
        queue_filename = f"ocr_queue_{ts}_{i}.json"
        queue_path = pickup / queue_filename
        label = f"[{i}/{total}] OCR queue: {item.name} -> {queue_filename}"

        if dry_run:
            print(f"  [DRY-RUN] {label}")
            queued += 1
            continue

        print(f"  {label}")
        try:
            with open(queue_path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2)
            queued += 1
        except Exception as e:
            log.error(f"  ERROR writing OCR queue for {item.name}: {e}")

    return queued


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Willow Nest Backlog Processor — ingests files Pigeon never scanned."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List what would be processed without making any changes.",
    )
    parser.add_argument(
        "--photos-only",
        action="store_true",
        help="Skip Task 1 (Nest walk); only run Task 2 (record photos) + Task 3 (OCR queue).",
    )
    args = parser.parse_args()

    if args.dry_run:
        print("=== DRY-RUN MODE — no files will be moved or written ===\n")

    # Track all photo paths that need OCR queuing (Tasks 2 and potentially Task 1 photos)
    all_ocr_photos: list[Path] = []

    # ------------------------------------------------------------------
    # TASK 1 — Process Nest category subdirs
    # ------------------------------------------------------------------
    if not args.photos_only:
        print("=" * 60)
        print("TASK 1: Processing Nest category subdirs")
        print("=" * 60)
        nest_results = process_nest_backlog(dry_run=args.dry_run)

        # Collect any newly filed photos from Task 1 for OCR
        for r in nest_results:
            if isinstance(r, dict) and r.get("filed_to"):
                filed_path = Path(r["filed_to"])
                if filed_path.suffix.lower() in PHOTO_EXTENSIONS:
                    all_ocr_photos.append(filed_path)

        print()

    # ------------------------------------------------------------------
    # TASK 2 — Record already-filed photos with no DB entry
    # ------------------------------------------------------------------
    print("=" * 60)
    print("TASK 2: Recording untracked photos in Filed/media/photos/")
    print("=" * 60)
    newly_recorded = process_unrecorded_photos(dry_run=args.dry_run)

    # All photos from Task 2 also need OCR queueing
    all_ocr_photos.extend(newly_recorded)

    # Deduplicate (in case Task 1 and Task 2 overlap)
    seen = set()
    deduped_ocr: list[Path] = []
    for p in all_ocr_photos:
        key = str(p)
        if key not in seen:
            seen.add(key)
            deduped_ocr.append(p)

    # ------------------------------------------------------------------
    # TASK 3 — OCR queue
    # ------------------------------------------------------------------
    print()
    print("=" * 60)
    print("TASK 3: Queuing photos for OCR")
    print("=" * 60)
    queued = queue_photos_for_ocr(deduped_ocr, dry_run=args.dry_run)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    if not args.photos_only:
        print(f"  Task 1 (Nest filing):        {len(nest_results)} file(s) processed")
    print(f"  Task 2 (Photo records):      {len(newly_recorded)} photo(s) recorded")
    print(f"  Task 3 (OCR queue):          {queued} queue file(s) written")
    if args.dry_run:
        print()
        print("  [DRY-RUN] No changes were made.")


if __name__ == "__main__":
    main()

"""
Drive Scanner + Classifier + Deduplicator

Walks a Google Drive mount (local filesystem), classifies every file,
detects duplicates, and builds a catalog for the organizer.

Read-only — no side effects. All mutations happen in drive_organize.py.

AUTHOR: Claude + Sean Campbell
VERSION: 0.1.0
CHECKSUM: DS=42
"""

import os
import re
import hashlib
import logging
from pathlib import Path
from typing import Optional, Dict, List

log = logging.getLogger("pa.scan")

# Near-duplicate detection via MinHash
try:
    from datasketch import MinHash, MinHashLSH
    _MINHASH_AVAILABLE = True
except ImportError:
    _MINHASH_AVAILABLE = False

# --- Classification rules (ordered, first match wins) ---

CACHE_EXTENSIONS = {".pyc", ".pyo", ".tmp"}
CACHE_DIRS = {"__pycache__", ".git", "node_modules", ".pytest_cache"}

CODE_EXTENSIONS = {".py", ".js", ".ts", ".jsx", ".tsx", ".bat", ".sh", ".ps1", ".cmd"}
PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff"}
OCR_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"}
PDF_EXTENSION = ".pdf"
MEDIA_EXTENSIONS = {".mp4", ".m4a", ".mp3", ".wav", ".mov", ".avi", ".mkv", ".flac"}
AUDIO_EXTENSIONS = {".mp3", ".m4a", ".wav", ".flac"}  # Vosk can transcribe these
DATA_EXTENSIONS = {".json", ".jsonl", ".csv", ".xml", ".yaml", ".yml"}
TRAINING_EXTENSIONS = {".safetensors", ".pt", ".pth", ".onnx", ".gguf"}

# Date pattern: YYYY-MM-DD.md
DATE_FILE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})\.md$")

# OCR screenshot: OCR_Screenshot_YYYYMMDD_HHMMSS_{App}.md
OCR_RE = re.compile(r"^OCR_Screenshot_\d{8}_\d{6}_(.+)\.md$", re.IGNORECASE)

# Duplicate suffix: filename (1).ext, filename (2).ext
DUPE_RE = re.compile(r"^(.+?)\s*\((\d+)\)(\.[^.]+)$")

# Category prefixes for filename matching
PREFIX_RULES = [
    (["HANDOFF_", "_SIG-"], "handoff", "System/Handoffs/"),
    (["GOVERNANCE_", "HARD_STOPS", "HARD_STOP", "CHARTER"], "governance", "System/Governance/"),
    (["SEED_PACKET_", "_seed."], "seed", "System/Seeds/"),
    (["ENTRY_", "MOMENT_", "JOURNAL"], "journal", "Journal/"),
    (["CAMPAIGN_", "CHARACTER_", "GM_", "DRILL_", "ITEM_REGISTRY"], "ttrpg", "Projects/TTRPG/"),
    (["LECTURE_", "CURRICULUM", "BIO_", "PERSONA_"], "utety", "Projects/UTETY/"),
    (["ESSAY", "BOOK_OF", "FRENCH_TOAST", "POETRY", "TREATMENT"], "creative", "Creative/"),
    (["BIOGRAPHICAL", "DATING", "MANN_FAMILY", "BOOK_OF_THE_DEAD"], "personal", "Personal/"),
    (["COVER_LETTER", "EXECUTIVE_SUMMARY", "BUDGET", "MEETING_PREP", "JOB_SEARCH"], "career", "Career/"),
    (["BOOTSTRAP", "CONTINUITY", "DELTA_SYSTEM", "FORMAL_SYSTEM", "AIONIC", "AIOS"], "architecture", "System/Architecture/"),
    (["DEBATE_FRAMEWORK", "GEOGRAPHIC_REACH", "HUMANITARIAN", "CIVIC"], "civic", "Projects/Civic/"),
]

# Known OCR source apps
OCR_APPS = {"Reddit", "Gmail", "LinkedIn", "Facebook", "Chrome", "GitHub", "Claude", "Messages", "Safari"}

# Minimum size (bytes) for a date-named .md to be classified as transcript
TRANSCRIPT_MIN_SIZE = 50_000  # 50KB


def _file_hash(path: Path, chunk_size: int = 8192) -> str:
    """MD5 hash of file contents."""
    h = hashlib.md5()
    try:
        with open(path, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                h.update(chunk)
    except (OSError, PermissionError):
        return "ERROR"
    return h.hexdigest()


def _detect_project(path: Path, category: str) -> str:
    """Guess a project name from path components or category."""
    parts = [p.lower() for p in path.parts]
    if any("ttrpg" in p or "campaign" in p for p in parts):
        return "ttrpg"
    if any("utety" in p for p in parts):
        return "utety"
    if any("pitch" in p for p in parts):
        return "pitches"
    if any("origin_material" in p for p in parts):
        return "ttrpg"
    if category in ("transcript", "ocr_capture"):
        return "daily"
    return category


def _classify_file(path: Path, name: str, ext: str, size: int, rel_path: str) -> Dict:
    """Classify a single file. Returns catalog entry dict."""
    name_upper = name.upper()

    entry = {
        "path": rel_path,
        "name": name,
        "ext": ext,
        "size_bytes": size,
        "category": "uncategorized",
        "project": "",
        "action": "keep",
        "destination": None,
        "ingestable": False,
        "duplicate_of": None,
    }

    # 1. Cache files
    if ext in CACHE_EXTENSIONS:
        entry.update(category="cache", action="delete")
        return entry

    # 2. DB files (not knowledge DB)
    if ext == ".db" and "knowledge" not in name.lower():
        entry.update(category="cache", action="delete")
        return entry

    # 3. Check if inside a cache directory
    for part in path.parts:
        if part in CACHE_DIRS:
            entry.update(category="cache", action="delete")
            return entry

    # 4. Date-named markdown (transcript)
    date_match = DATE_FILE_RE.match(name)
    if date_match and size >= TRANSCRIPT_MIN_SIZE:
        year, month = date_match.group(1), date_match.group(2)
        entry.update(
            category="transcript",
            action="ingest_and_move",
            destination=f"Transcripts/{year}-{month}/",
            ingestable=True,
            project="daily",
        )
        return entry

    # 5. OCR screenshots
    ocr_match = OCR_RE.match(name)
    if ocr_match:
        app_name = ocr_match.group(1).strip()
        # Normalize app name
        for known in OCR_APPS:
            if known.lower() in app_name.lower():
                app_name = known
                break
        entry.update(
            category="ocr_capture",
            action="ingest_and_move",
            destination=f"Captures/{app_name}/",
            ingestable=True,
            project="daily",
        )
        return entry

    # 6. Prefix-based rules
    for prefixes, category, dest in PREFIX_RULES:
        if any(name_upper.startswith(p.upper()) or p.upper() in name_upper for p in prefixes):
            entry.update(
                category=category,
                action="ingest_and_move" if ext == ".md" else "move",
                destination=dest,
                ingestable=(ext in {".md", ".txt", ".html", ".htm"}),
                project=_detect_project(path, category),
            )
            return entry

    # 7. Small date-named .md (not big enough for transcript, still ingestable)
    if date_match and ext == ".md":
        year, month = date_match.group(1), date_match.group(2)
        entry.update(
            category="note",
            action="ingest_and_move",
            destination=f"Transcripts/{year}-{month}/",
            ingestable=True,
            project="daily",
        )
        return entry

    # 8. PDFs — OCR-ingestable
    if ext == PDF_EXTENSION:
        project = _detect_project(path, "document")
        entry.update(
            category="document",
            action="ingest_and_move",
            destination=f"Archive/Documents/",
            ingestable=True,
            project=project,
        )
        return entry

    # 9. Photos — OCR-ingestable if image format Tesseract can read
    if ext in PHOTO_EXTENSIONS:
        project = _detect_project(path, "photo")
        entry.update(
            category="photo",
            action="ingest_and_move" if ext in OCR_IMAGE_EXTENSIONS else "move",
            destination=f"Media/{project}/",
            ingestable=(ext in OCR_IMAGE_EXTENSIONS),
        )
        return entry

    # 10. Audio — transcribable via Vosk
    if ext in AUDIO_EXTENSIONS:
        project = _detect_project(path, "media")
        entry.update(
            category="audio",
            action="ingest_and_move",
            destination=f"Media/{project}/",
            ingestable=True,
        )
        return entry

    # 10b. Video/other media — not transcribable
    if ext in MEDIA_EXTENSIONS:
        project = _detect_project(path, "media")
        entry.update(category="media", action="move", destination=f"Media/{project}/")
        return entry

    # 11. Code
    if ext in CODE_EXTENSIONS:
        entry.update(category="code", action="skip")
        return entry

    # 12. Data files
    if ext in DATA_EXTENSIONS:
        project = _detect_project(path, "data")
        entry.update(category="data", action="move", destination=f"Data/{project}/")
        return entry

    # 13. Training weights
    if ext in TRAINING_EXTENSIONS:
        entry.update(category="training", action="move", destination="Archive/Training/")
        return entry

    # 14. Generic .md — ingest and move based on location
    if ext in {".md", ".txt"}:
        entry.update(
            category="document",
            action="ingest_and_move",
            destination="Archive/Documents/",
            ingestable=True,
        )
        return entry

    # 15. Everything else
    return entry


def scan(drive_root: str, progress_callback=None) -> List[Dict]:
    """
    Walk the entire Drive and classify every file.

    Args:
        drive_root: Path to Google Drive mount (e.g. "C:\\Users\\Sean\\My Drive")
        progress_callback: Optional callable(files_processed, current_file) for progress

    Returns:
        List of catalog entry dicts.
    """
    root = Path(drive_root)
    if not root.exists():
        raise FileNotFoundError(f"Drive root not found: {drive_root}")

    catalog = []
    count = 0

    for dirpath, dirnames, filenames in os.walk(root):
        # Skip Willow operational dirs (keep those in place)
        rel_dir = os.path.relpath(dirpath, root)
        if rel_dir.startswith("Willow") and ("Auth Users" not in rel_dir or "Pickup" not in rel_dir):
            # Keep Willow structure except Pickup (which we're organizing)
            if "Pickup" not in rel_dir and "Notes" not in rel_dir:
                continue

        for fname in filenames:
            fpath = Path(dirpath) / fname
            try:
                size = fpath.stat().st_size
            except (OSError, PermissionError):
                continue

            ext = fpath.suffix.lower()
            rel_path = os.path.relpath(fpath, root)

            entry = _classify_file(fpath, fname, ext, size, rel_path)
            entry["project"] = entry["project"] or _detect_project(fpath, entry["category"])
            catalog.append(entry)

            count += 1
            if progress_callback and count % 50 == 0:
                progress_callback(count, fname)

    log.info(f"Scan complete: {len(catalog)} files cataloged")
    return catalog


def find_duplicates(catalog: List[Dict], drive_root: str) -> List[Dict]:
    """
    Detect duplicate files (filename with (1), (2), (3) suffixes).
    Hash-compares with the base file.

    Mutates catalog entries in-place: sets action='dedupe' and duplicate_of.
    Returns only the entries marked as duplicates.
    """
    root = Path(drive_root)
    duplicates = []

    # Build map of base filenames to entries
    base_map = {}  # base_name -> list of entries
    for entry in catalog:
        name = entry["name"]
        match = DUPE_RE.match(name)
        if match:
            base_name = match.group(1) + match.group(3)
            if base_name not in base_map:
                base_map[base_name] = {"original": None, "copies": []}
            base_map[base_name]["copies"].append(entry)
        else:
            if name not in base_map:
                base_map[name] = {"original": None, "copies": []}
            base_map[name]["original"] = entry

    # Compare hashes
    for base_name, group in base_map.items():
        if not group["copies"] or not group["original"]:
            continue

        orig_path = root / group["original"]["path"]
        orig_hash = _file_hash(orig_path)
        if orig_hash == "ERROR":
            continue

        for copy_entry in group["copies"]:
            copy_path = root / copy_entry["path"]
            copy_hash = _file_hash(copy_path)

            if copy_hash == orig_hash:
                # Identical — mark for deletion
                copy_entry["action"] = "dedupe"
                copy_entry["duplicate_of"] = group["original"]["path"]
                copy_entry["category"] = "duplicate"
                duplicates.append(copy_entry)
            else:
                # Different content — keep both, but if copy is larger, swap
                if copy_entry["size_bytes"] > group["original"]["size_bytes"]:
                    log.info(f"Duplicate variant larger than original: {copy_entry['name']}")

    log.info(f"Deduplication: {len(duplicates)} identical duplicates found")
    return duplicates


def find_near_duplicates(catalog: List[Dict], drive_root: str, threshold: float = 0.7) -> List[Dict]:
    """
    Detect near-duplicate text files using MinHash LSH.
    Files that are similar but not identical (edits, rewording).
    Only runs on ingestable text files. Does NOT mark for deletion —
    flags them for human review.

    Returns list of {path, similar_to, similarity} dicts.
    """
    if not _MINHASH_AVAILABLE:
        log.info("datasketch not available, skipping near-duplicate detection")
        return []

    root = Path(drive_root)
    text_entries = [e for e in catalog if e.get("ingestable") and e["ext"] in {".md", ".txt"}]

    if len(text_entries) < 2:
        return []

    lsh = MinHashLSH(threshold=threshold, num_perm=128)
    minhashes = {}

    for entry in text_entries:
        fpath = root / entry["path"]
        try:
            text = fpath.read_text(encoding="utf-8", errors="ignore")[:8000]
            words = text.lower().split()
            if len(words) < 10:
                continue
            mh = MinHash(num_perm=128)
            for w in words:
                mh.update(w.encode("utf-8"))
            minhashes[entry["path"]] = (mh, entry)
            lsh.insert(entry["path"], mh)
        except (OSError, PermissionError):
            continue

    near_dupes = []
    seen_pairs = set()

    for path_key, (mh, entry) in minhashes.items():
        results = lsh.query(mh)
        for match_key in results:
            if match_key == path_key:
                continue
            pair = tuple(sorted([path_key, match_key]))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            similarity = mh.jaccard(minhashes[match_key][0])
            near_dupes.append({
                "path": path_key,
                "similar_to": match_key,
                "similarity": round(similarity, 3),
            })

    log.info(f"Near-duplicate detection: {len(near_dupes)} similar pairs found")
    return near_dupes


def catalog_summary(catalog: List[Dict]) -> Dict:
    """Generate a human-readable summary of the catalog."""
    by_category = {}
    by_action = {}
    total_size = 0
    ingestable_count = 0

    for entry in catalog:
        cat = entry["category"]
        act = entry["action"]
        by_category[cat] = by_category.get(cat, 0) + 1
        by_action[act] = by_action.get(act, 0) + 1
        total_size += entry["size_bytes"]
        if entry["ingestable"]:
            ingestable_count += 1

    return {
        "total_files": len(catalog),
        "total_size_mb": round(total_size / (1024 * 1024), 1),
        "by_category": dict(sorted(by_category.items(), key=lambda x: -x[1])),
        "by_action": dict(sorted(by_action.items(), key=lambda x: -x[1])),
        "ingestable_count": ingestable_count,
        "duplicate_count": by_category.get("duplicate", 0),
    }

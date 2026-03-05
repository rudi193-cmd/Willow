"""
file_organizer.py — Willow file organization module.

Organizes files from a GDrive Pickup inbox using OCR-extracted text and
LLM-generated rename suggestions. Part of the Willow personal OS core.

Paths:
    GDrive Pickup:  C:/Users/Sean/My Drive/Willow/Auth Users/{username}/Pickup/
    Local Pickup:   C:/Users/Sean/Documents/GitHub/Willow/artifacts/willow/Auth Users/{username}/Pickup/
    Filed dest:     {pickup_root}/Filed/{category}/
"""

import hashlib
import logging
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

GDRIVE_BASE = Path("C:/Users/Sean/My Drive/Willow/Auth Users")
LOCAL_BASE = Path(
    "C:/Users/Sean/Documents/GitHub/Willow/artifacts/willow/Auth Users"
)

_SKIP_PREFIXES = ("ocr_done_", "ocr_skip_", "ocr_queue_")
_SKIP_EXTENSIONS = {".json", ".md"}

_FOLDER_MAP = {
    "legal_document": "legal",
    "property_record": "property",
    "screenshot": "screenshots",
    "personal_document": "personal",
    "document": "documents",
}


# ---------------------------------------------------------------------------
# 1. scan_pickup
# ---------------------------------------------------------------------------

def scan_pickup(username: str) -> list[dict]:
    """List all organizable files in the GDrive Pickup folder for *username*.

    Skips:
    - Hidden files (name starts with '.')
    - Files with prefixes: ocr_done_, ocr_skip_, ocr_queue_
    - Files with extensions: .json, .md
    - Any subdirectory (including Filed/)

    Returns:
        list of dicts: {path, filename, size_bytes, modified (ISO 8601), status}
    """
    pickup = GDRIVE_BASE / username / "Pickup"
    if not pickup.exists():
        logger.warning("scan_pickup: Pickup folder not found: %s", pickup)
        return []

    results: list[dict] = []
    for p in pickup.iterdir():
        if p.is_dir():
            continue
        if p.name.startswith("."):
            continue
        if any(p.name.startswith(px) for px in _SKIP_PREFIXES):
            continue
        if p.suffix.lower() in _SKIP_EXTENSIONS:
            continue
        try:
            stat = p.stat()
            results.append(
                {
                    "path": str(p),
                    "filename": p.name,
                    "size_bytes": stat.st_size,
                    "modified": datetime.fromtimestamp(
                        stat.st_mtime, tz=timezone.utc
                    ).isoformat(),
                    "status": "pending",
                }
            )
        except OSError as e:
            logger.warning("scan_pickup: could not stat %s: %s", p.name, e)

    logger.info("scan_pickup: found %d file(s) for %s", len(results), username)
    return results


# ---------------------------------------------------------------------------
# 2. suggest_rename
# ---------------------------------------------------------------------------

def suggest_rename(
    file_path: Path, extracted_text: str, category: str
) -> str:
    """Ask the free-tier fleet for a clean snake_case rename stem.

    Prompt format: YYYY-MM-DD_type_subject, max 60 chars, no extension.
    Falls back to sanitize_filename(file_path.stem) if the fleet fails or
    returns an empty response.

    Args:
        file_path:      Original file path (used for extension-less fallback).
        extracted_text: OCR or raw text from the file.
        category:       Classifier category string (e.g. 'legal_document').

    Returns:
        Suggested filename stem (no extension), max 60 chars.
    """
    from core.filename_sanitizer import sanitize_filename  # sibling import

    fallback = sanitize_filename(Path(file_path).stem)

    try:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from core import llm_router as _lr

        _lr.load_keys_from_json()

        snippet = extracted_text[:800]
        prompt = (
            "Return ONLY a snake_case filename stem. "
            "Max 60 characters. "
            "Format: YYYY-MM-DD_type_subject. "
            "No file extension. No explanation. No punctuation other than underscores and hyphens. "
            f"Category: {category}. "
            f"File text: {snippet}"
        )

        resp = _lr.ask(prompt, preferred_tier="free")
        if resp and resp.content.strip():
            stem = (
                resp.content.strip()
                .strip('"')
                .strip("'")
                .split()[0]
            )
            if stem:
                cleaned = stem[:60]
                logger.info(
                    "suggest_rename: fleet (%s) -> %s", resp.provider, cleaned
                )
                return cleaned

    except Exception as e:
        logger.warning("suggest_rename: fleet error: %s", e)

    logger.info("suggest_rename: using fallback -> %s", fallback)
    return fallback


# ---------------------------------------------------------------------------
# 3. suggest_folder
# ---------------------------------------------------------------------------

def suggest_folder(category: str) -> str:
    """Map a classifier category string to a Filed/ subfolder name.

    Mapping:
        legal_document    -> legal
        property_record   -> property
        screenshot        -> screenshots
        personal_document -> personal
        document          -> documents
        <anything else>   -> documents

    Args:
        category: Category string from classifier.

    Returns:
        Folder name string.
    """
    return _FOLDER_MAP.get(category, "documents")


# ---------------------------------------------------------------------------
# 4. apply_rename
# ---------------------------------------------------------------------------

def apply_rename(
    file_path: Path, new_stem: str, dry_run: bool = True
) -> Path:
    """Rename a file to new_stem + original extension.

    If the target path already exists, appends _2, _3, ... until unique.
    In dry_run mode the rename is not performed — only the computed path
    is returned.

    Args:
        file_path: Current file path.
        new_stem:  Desired stem (no extension).
        dry_run:   If True, return proposed path without touching disk.

    Returns:
        Resulting Path (whether or not it was applied).
    """
    file_path = Path(file_path)
    candidate = file_path.parent / (new_stem + file_path.suffix)

    counter = 2
    while candidate.exists() and candidate != file_path:
        candidate = file_path.parent / (
            new_stem + "_" + str(counter) + file_path.suffix
        )
        counter += 1

    if not dry_run:
        file_path.rename(candidate)
        logger.info("apply_rename: %s -> %s", file_path.name, candidate.name)
    else:
        logger.debug(
            "apply_rename [dry_run]: %s -> %s", file_path.name, candidate.name
        )

    return candidate


# ---------------------------------------------------------------------------
# 5. move_to_filed
# ---------------------------------------------------------------------------

def move_to_filed(
    file_path: Path, category: str, username: str, dry_run: bool = True
) -> Path:
    """Move a file into the Filed/{folder}/ hierarchy inside the GDrive Pickup.

    Destination: GDRIVE_BASE / username / Pickup / Filed / <folder> / <filename>

    In dry_run mode the directory is not created and the file is not moved.

    Args:
        file_path: Current (post-rename) file path.
        category:  Classifier category string (used to determine subfolder).
        username:  Willow username (e.g. 'Sweet-Pea-Rudi19').
        dry_run:   If True, return destination path without touching disk.

    Returns:
        Destination Path.
    """
    file_path = Path(file_path)
    folder = suggest_folder(category)
    dest_dir = GDRIVE_BASE / username / "Pickup" / "Filed" / folder
    dest = dest_dir / file_path.name

    if not dry_run:
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(file_path), str(dest))
        logger.info("move_to_filed: %s -> %s", file_path.name, dest)
    else:
        logger.debug(
            "move_to_filed [dry_run]: %s -> %s", file_path.name, dest
        )

    return dest


# ---------------------------------------------------------------------------
# 6. find_duplicates
# ---------------------------------------------------------------------------

def find_duplicates(username: str) -> list[list[dict]]:
    """Find duplicate files in the GDrive Pickup folder by MD5 content hash.

    Uses the same skip rules as scan_pickup (hidden files, ocr_* prefixes,
    .json/.md extensions, subdirectories excluded).

    Args:
        username: Willow username.

    Returns:
        List of duplicate groups. Each group is a list of dicts:
        {path, filename, size_bytes}. Only groups with >1 file are returned.
    """
    pickup = GDRIVE_BASE / username / "Pickup"
    if not pickup.exists():
        logger.warning("find_duplicates: Pickup folder not found: %s", pickup)
        return []

    hashes: dict[str, list[dict]] = {}

    for p in pickup.iterdir():
        if p.is_dir():
            continue
        if p.name.startswith("."):
            continue
        if any(p.name.startswith(px) for px in _SKIP_PREFIXES):
            continue
        if p.suffix.lower() in _SKIP_EXTENSIONS:
            continue

        try:
            md5 = hashlib.md5(p.read_bytes()).hexdigest()
            stat = p.stat()
            entry = {
                "path": str(p),
                "filename": p.name,
                "size_bytes": stat.st_size,
            }
            hashes.setdefault(md5, []).append(entry)
        except Exception as e:
            logger.warning("find_duplicates: skipping %s: %s", p.name, e)

    groups = [g for g in hashes.values() if len(g) > 1]
    logger.info(
        "find_duplicates: found %d duplicate group(s) for %s",
        len(groups),
        username,
    )
    return groups


# ---------------------------------------------------------------------------
# 7. batch_organize
# ---------------------------------------------------------------------------

def batch_organize(username: str, auto_apply: bool = False) -> list[dict]:
    """Run the full organize pipeline over the GDrive Pickup for *username*.

    Pipeline per file:
        1. Extract text via ocr_consumer (process_single_file or extract_text).
           Falls back to reading the first 1000 bytes as UTF-8 text.
        2. suggest_rename  — fleet LLM or sanitize_filename fallback.
        3. suggest_folder  — category -> folder name mapping.
        4. If auto_apply:  apply_rename + move_to_filed (dry_run=False).

    Note: ocr_consumer is imported INSIDE this function to avoid circular
    imports at module load time.

    Args:
        username:   Willow username.
        auto_apply: If True, actually rename and move files.

    Returns:
        List of result dicts:
            {original_path, suggested_name, suggested_folder, applied, error}
    """
    _ocr = None
    try:
        import core.ocr_consumer as _ocr_mod
        _ocr = _ocr_mod
    except ImportError:
        logger.info("batch_organize: ocr_consumer not available; using raw bytes fallback")

    files = scan_pickup(username)
    logger.info(
        "batch_organize: processing %d file(s) for %s (auto_apply=%s)",
        len(files),
        username,
        auto_apply,
    )

    results: list[dict] = []

    for entry in files:
        file_path = Path(entry["path"])
        result: dict = {
            "original_path": str(file_path),
            "suggested_name": "",
            "suggested_folder": "",
            "applied": False,
            "error": None,
        }

        try:
            extracted = ""
            if _ocr is not None:
                try:
                    if hasattr(_ocr, "process_single_file"):
                        extracted = _ocr.process_single_file(file_path) or ""
                    elif hasattr(_ocr, "extract_text"):
                        extracted = _ocr.extract_text(file_path) or ""
                except Exception as ocr_err:
                    logger.warning(
                        "batch_organize: OCR failed for %s: %s",
                        file_path.name,
                        ocr_err,
                    )

            if not extracted:
                try:
                    extracted = file_path.read_bytes()[:1000].decode(
                        "utf-8", errors="replace"
                    )
                except Exception as read_err:
                    logger.warning(
                        "batch_organize: raw read failed for %s: %s",
                        file_path.name,
                        read_err,
                    )
                    extracted = ""

            category = "document"

            new_stem = suggest_rename(file_path, extracted, category)
            folder = suggest_folder(category)

            result["suggested_name"] = new_stem
            result["suggested_folder"] = folder

            if auto_apply:
                renamed_path = apply_rename(file_path, new_stem, dry_run=False)
                move_to_filed(renamed_path, category, username, dry_run=False)
                result["applied"] = True

        except Exception as e:
            logger.error(
                "batch_organize: unhandled error for %s: %s",
                file_path.name,
                e,
            )
            result["error"] = str(e)

        results.append(result)

    applied_count = sum(1 for r in results if r["applied"])
    error_count = sum(1 for r in results if r["error"])
    logger.info(
        "batch_organize: done. applied=%d, errors=%d, total=%d",
        applied_count,
        error_count,
        len(results),
    )
    return results

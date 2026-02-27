"""
file_organizer.py — Smart file rename and sort for the Willow Pickup inbox.

Scans the Pickup folder, uses OCR-extracted text + LLM to suggest clean
filenames and destination folders, then applies renames/moves on approval.
Feeds Willow: after organizing, callers should update ECOSYSTEM.md via
ecosystem_writer.update_section().
"""

import hashlib
import logging
import os
import re
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

GDRIVE_PICKUP = Path(
    r"C:\Users\Sean\My Drive\Willow\Auth Users\Sweet-Pea-Rudi19\Pickup"
)
LOCAL_PICKUP = Path(
    r"C:\Users\Sean\Documents\GitHub\Willow\artifacts\willow\Auth Users\Sweet-Pea-Rudi19\Pickup"
)

# Files to skip during scan
_SKIP_PREFIXES = ("ocr_done_", "ocr_skip_", "ocr_queue_", ".")
_SKIP_SUFFIXES = (".json", ".md")
_SKIP_DIRS = {"Filed", "__pycache__"}

# Category → folder name mapping
CATEGORY_FOLDERS = {
    "legal_document": "legal",
    "property_record": "property",
    "screenshot": "screenshots",
    "personal_document": "personal",
    "document": "documents",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pickup_root(username: str) -> Path:
    """Return GDrive Pickup path for username (falls back to local)."""
    p = GDRIVE_PICKUP
    if not p.exists():
        p = LOCAL_PICKUP
    return p


def _should_skip(path: Path) -> bool:
    if path.is_dir():
        return True
    name = path.name
    if any(name.startswith(pfx) for pfx in _SKIP_PREFIXES):
        return True
    if any(name.endswith(sfx) for sfx in _SKIP_SUFFIXES):
        return True
    if path.parent.name in _SKIP_DIRS:
        return True
    return False


def _md5(path: Path) -> str:
    h = hashlib.md5()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
    except OSError:
        return ""
    return h.hexdigest()


def _fleet_ask(prompt: str) -> str:
    """Ask the free LLM fleet. Returns response text or empty string."""
    try:
        core_dir = str(Path(__file__).parent.parent)
        if core_dir not in sys.path:
            sys.path.insert(0, core_dir)
        from core import llm_router
        llm_router.load_keys_from_json()
        response = llm_router.ask(prompt, preferred_tier="free")
        if response:
            return response.content.strip()
    except Exception as e:
        logger.warning("Fleet unavailable: %s", e)
    return ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def scan_pickup(username: str) -> list:
    """List files in Pickup that are ready for organization.

    Returns list of dicts: {path, filename, size_bytes, modified, status}
    """
    root = _pickup_root(username)
    if not root.exists():
        logger.warning("Pickup not found: %s", root)
        return []

    results = []
    for p in root.iterdir():
        if _should_skip(p):
            continue
        try:
            stat = p.stat()
            results.append({
                "path": str(p),
                "filename": p.name,
                "size_bytes": stat.st_size,
                "modified": stat.st_mtime,
                "status": "pending",
            })
        except OSError as e:
            logger.warning("Cannot stat %s: %s", p, e)
    return results


def suggest_rename(file_path: Path, extracted_text: str, category: str) -> str:
    """Ask the fleet for a clean filename stem.

    Format: YYYY-MM-DD_type_subject (snake_case, max 60 chars, no extension).
    Falls back to sanitized original stem if fleet unavailable.
    """
    snippet = extracted_text[:800].strip() if extracted_text else ""
    prompt = (
        f"You are a document filing assistant. Given the document content and category below, "
        f"suggest a clean filename (no extension) in snake_case, max 60 characters, "
        f"format: YYYY-MM-DD_type_subject (use today's date if no date is apparent).\n"
        f"Category: {category}\n"
        f"Content snippet:\n{snippet}\n\n"
        f"Reply with ONLY the filename, nothing else."
    )
    result = _fleet_ask(prompt)
    if result:
        # Strip any extension the LLM may have added, sanitize
        stem = Path(result).stem if "." in result else result
        stem = re.sub(r"[^\w\-]", "_", stem)[:60].strip("_")
        if stem:
            return stem

    # Fallback: sanitize original stem
    try:
        core_dir = str(Path(__file__).parent.parent)
        if core_dir not in sys.path:
            sys.path.insert(0, core_dir)
        from core.filename_sanitizer import sanitize_filename
        return sanitize_filename(file_path.stem)
    except Exception:
        return re.sub(r"[^\w\-]", "_", file_path.stem)[:60]


def suggest_folder(category: str) -> str:
    """Map a content category to a Filed/ subfolder name."""
    return CATEGORY_FOLDERS.get(category, "documents")


def apply_rename(file_path: Path, new_stem: str, dry_run: bool = True) -> Path:
    """Rename file_path to new_stem + original extension.

    If dry_run=True, returns the would-be new path without touching disk.
    Deduplicates by appending _2, _3, etc. if destination exists.
    """
    new_name = new_stem + file_path.suffix
    new_path = file_path.parent / new_name

    # Deduplicate
    counter = 2
    while new_path.exists() and new_path != file_path:
        new_path = file_path.parent / f"{new_stem}_{counter}{file_path.suffix}"
        counter += 1

    if not dry_run:
        try:
            file_path.rename(new_path)
            logger.info("Renamed: %s → %s", file_path.name, new_path.name)
        except OSError as e:
            logger.error("Rename failed: %s", e)
            return file_path

    return new_path


def move_to_filed(file_path: Path, category: str, username: str, dry_run: bool = True) -> Path:
    """Move file_path to Pickup/Filed/{category}/ for username.

    Creates directory if needed (only when not dry_run).
    Returns destination path.
    """
    root = _pickup_root(username)
    folder = suggest_folder(category)
    dest_dir = root / "Filed" / folder
    dest = dest_dir / file_path.name

    # Deduplicate destination
    counter = 2
    while dest.exists():
        dest = dest_dir / f"{file_path.stem}_{counter}{file_path.suffix}"
        counter += 1

    if not dry_run:
        dest_dir.mkdir(parents=True, exist_ok=True)
        try:
            file_path.rename(dest)
            logger.info("Moved: %s → %s", file_path.name, dest)
        except OSError as e:
            logger.error("Move failed: %s", e)
            return file_path

    return dest


def find_duplicates(username: str) -> list:
    """Find files in Pickup with identical content (by MD5 hash).

    Returns list of groups (each group is a list of dicts) where len > 1.
    """
    root = _pickup_root(username)
    if not root.exists():
        return []

    hash_map: dict = {}
    for p in root.rglob("*"):
        if _should_skip(p):
            continue
        h = _md5(p)
        if not h:
            continue
        try:
            stat = p.stat()
            entry = {"path": str(p), "filename": p.name, "size_bytes": stat.st_size}
        except OSError:
            continue
        hash_map.setdefault(h, []).append(entry)

    return [group for group in hash_map.values() if len(group) > 1]


def batch_organize(username: str, auto_apply: bool = False) -> list:
    """Run the full organize pipeline on the Pickup folder.

    For each file: extract text → suggest rename + folder → optionally apply.

    Returns list of result dicts:
        {original_path, original_name, suggested_name, suggested_folder,
         category, applied, error}
    """
    # Import OCR consumer inside function to avoid circular imports
    try:
        core_dir = str(Path(__file__).parent.parent)
        if core_dir not in sys.path:
            sys.path.insert(0, core_dir)
        from core import ocr_consumer
        _has_ocr = True
    except ImportError:
        _has_ocr = False
        logger.warning("ocr_consumer not available — using raw text fallback")

    files = scan_pickup(username)
    results = []

    for file_info in files:
        file_path = Path(file_info["path"])
        result = {
            "original_path": str(file_path),
            "original_name": file_path.name,
            "suggested_name": None,
            "suggested_folder": None,
            "category": "document",
            "applied": False,
            "error": None,
        }

        try:
            # Extract text
            extracted_text = ""
            category = "document"

            if _has_ocr:
                try:
                    ocr_result = ocr_consumer.extract_text(file_path)
                    if isinstance(ocr_result, dict):
                        extracted_text = ocr_result.get("text", "")
                        category = ocr_result.get("category", "document")
                    elif isinstance(ocr_result, str):
                        extracted_text = ocr_result
                except Exception as e:
                    logger.warning("OCR failed for %s: %s", file_path.name, e)

            # Fallback: read first 1000 bytes as text
            if not extracted_text:
                try:
                    extracted_text = file_path.read_bytes()[:1000].decode(
                        "utf-8", errors="replace"
                    )
                except OSError:
                    pass

            # Suggest rename and folder
            new_stem = suggest_rename(file_path, extracted_text, category)
            folder = suggest_folder(category)
            result["suggested_name"] = new_stem + file_path.suffix
            result["suggested_folder"] = folder
            result["category"] = category

            # Apply if requested
            if auto_apply:
                renamed = apply_rename(file_path, new_stem, dry_run=False)
                moved = move_to_filed(renamed, category, username, dry_run=False)
                result["applied"] = True
                result["final_path"] = str(moved)

        except Exception as e:
            result["error"] = str(e)
            logger.error("Error organizing %s: %s", file_path.name, e)

        results.append(result)

    return results


if __name__ == "__main__":
    import json
    print("Scanning Pickup...")
    files = scan_pickup("Sweet-Pea-Rudi19")
    print(f"Found {len(files)} files")
    for f in files[:5]:
        print(f"  {f['filename']} ({f['size_bytes']} bytes)")
    dupes = find_duplicates("Sweet-Pea-Rudi19")
    print(f"Duplicate groups: {len(dupes)}")

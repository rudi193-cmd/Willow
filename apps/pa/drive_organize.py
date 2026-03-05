"""
Drive Organizer + Executor + Cleanup

Takes a catalog from drive_scan.py and:
1. Generates a move plan (read-only)
2. Executes moves with consent (consent_gate)
3. Ingests text content into knowledge DB during moves
4. Cleans up empty directories
5. Logs every action to ~/.willow/pa_moves.log

AUTHOR: Claude + Sean Campbell
VERSION: 0.1.0
CHECKSUM: DS=42
"""

import os
import sys
import shutil
import logging
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Callable

log = logging.getLogger("pa.organize")

# --- OCR support (Tesseract + PyMuPDF) ---
TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

try:
    import pytesseract
    from PIL import Image
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
    _OCR_AVAILABLE = True
except ImportError:
    _OCR_AVAILABLE = False
    log.warning("pytesseract/Pillow not available — OCR disabled")

try:
    import fitz  # PyMuPDF
    _PDF_AVAILABLE = True
except ImportError:
    _PDF_AVAILABLE = False
    log.warning("PyMuPDF not available — PDF OCR disabled")

OCR_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"}
AUDIO_EXTENSIONS = {".mp3", ".m4a", ".wav", ".flac"}

# --- Speech-to-text (Vosk) ---
VOSK_MODEL_PATH = str(Path.home() / ".willow" / "models" / "vosk-model-small-en-us-0.15")

try:
    from vosk import Model as VoskModel, KaldiRecognizer
    import wave
    import json as _json
    _VOSK_AVAILABLE = os.path.exists(VOSK_MODEL_PATH)
    if _VOSK_AVAILABLE:
        _vosk_model = VoskModel(VOSK_MODEL_PATH)
    else:
        _vosk_model = None
        log.warning(f"Vosk model not found at {VOSK_MODEL_PATH}")
except ImportError:
    _VOSK_AVAILABLE = False
    _vosk_model = None
    log.warning("vosk not available — audio transcription disabled")

# --- Semantic chunking (semchunk) ---
try:
    import semchunk
    _CHUNKER_AVAILABLE = True
except ImportError:
    _CHUNKER_AVAILABLE = False

# --- Structured extraction (dateparser + phonenumbers) ---
try:
    import dateparser
    _DATEPARSER_AVAILABLE = True
except ImportError:
    _DATEPARSER_AVAILABLE = False

try:
    import phonenumbers as _phonenumbers
    _PHONENUMBERS_AVAILABLE = True
except ImportError:
    _PHONENUMBERS_AVAILABLE = False

# Ensure core is importable
_willow_root = Path(__file__).parent.parent.parent
if str(_willow_root) not in sys.path:
    sys.path.insert(0, str(_willow_root))

from core import loam

# Audit log path
LOG_DIR = Path.home() / ".willow"
MOVE_LOG = LOG_DIR / "pa_moves.log"

# Consent scopes
SCOPE_ORGANIZE = "pa.organize"
SCOPE_DEDUPE = "pa.dedupe"
SCOPE_CLEANUP = "pa.cleanup"

# Progress state (module-level for API polling)
_progress = {
    "phase": "idle",
    "files_processed": 0,
    "files_total": 0,
    "current_file": "",
}


def get_progress() -> Dict:
    return dict(_progress)


def _log_action(action: str, source: str, dest: str = "", detail: str = ""):
    """Append to audit log."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().isoformat(timespec="seconds")
    line = f"{ts} | {action:12s} | {source}"
    if dest:
        line += f" -> {dest}"
    if detail:
        line += f" | {detail}"
    with open(MOVE_LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def generate_plan(catalog: List[Dict]) -> Dict:
    """
    Generate a move plan from the catalog. Read-only, no side effects.

    Returns:
        {
            "moves": [{source, destination, action, category}, ...],
            "folders_to_create": [path, ...],
            "deletes": [{source, reason}, ...],
            "skips": [{source, reason}, ...],
            "summary": {by_destination: {dest: count}, ...}
        }
    """
    moves = []
    deletes = []
    skips = []
    folders_needed = set()

    for entry in catalog:
        action = entry["action"]

        if action == "skip":
            skips.append({"source": entry["path"], "reason": f"code file ({entry['ext']})"})
        elif action == "keep":
            skips.append({"source": entry["path"], "reason": "uncategorized, kept in place"})
        elif action == "delete":
            deletes.append({"source": entry["path"], "reason": f"cache ({entry['category']})"})
        elif action == "dedupe":
            deletes.append({
                "source": entry["path"],
                "reason": f"duplicate of {entry.get('duplicate_of', 'unknown')}",
            })
        elif action in ("move", "ingest_and_move"):
            dest = entry.get("destination")
            if dest:
                folders_needed.add(dest.rstrip("/"))
                moves.append({
                    "source": entry["path"],
                    "destination": dest + entry["name"],
                    "action": action,
                    "category": entry["category"],
                    "size_bytes": entry["size_bytes"],
                    "ingestable": entry.get("ingestable", False),
                })

    # Summary by destination folder
    by_dest = {}
    for m in moves:
        dest_folder = str(Path(m["destination"]).parent)
        by_dest[dest_folder] = by_dest.get(dest_folder, 0) + 1

    return {
        "moves": moves,
        "folders_to_create": sorted(folders_needed),
        "deletes": deletes,
        "skips": skips,
        "summary": {
            "files_to_move": len(moves),
            "files_to_delete": len(deletes),
            "files_to_skip": len(skips),
            "folders_to_create": len(folders_needed),
            "by_destination": dict(sorted(by_dest.items())),
        },
    }


def review(plan: Dict) -> str:
    """Generate human-readable summary of the plan."""
    s = plan["summary"]
    lines = [
        f"PA Drive Organizer Plan",
        f"=======================",
        f"Files to move:   {s['files_to_move']}",
        f"Files to delete: {s['files_to_delete']}",
        f"Files to skip:   {s['files_to_skip']}",
        f"Folders to create: {s['folders_to_create']}",
        f"",
        f"Destination breakdown:",
    ]
    for dest, count in s["by_destination"].items():
        lines.append(f"  {dest}: {count} files")

    if plan["deletes"]:
        lines.append(f"\nDeletions ({len(plan['deletes'])}):")
        # Show first 10
        for d in plan["deletes"][:10]:
            lines.append(f"  {d['source']} — {d['reason']}")
        if len(plan["deletes"]) > 10:
            lines.append(f"  ... and {len(plan['deletes']) - 10} more")

    return "\n".join(lines)


def _transcribe_audio(filepath: Path) -> str:
    """Transcribe audio file to text via Vosk. Converts to WAV first if needed."""
    if not _VOSK_AVAILABLE:
        return ""
    try:
        import subprocess
        wav_path = filepath.with_suffix(".tmp.wav")
        needs_convert = filepath.suffix.lower() != ".wav"

        if needs_convert:
            # Use ffmpeg to convert to 16kHz mono WAV (Vosk requirement)
            result = subprocess.run(
                ["ffmpeg", "-y", "-i", str(filepath), "-ar", "16000", "-ac", "1", "-f", "wav", str(wav_path)],
                capture_output=True, timeout=120,
            )
            if result.returncode != 0:
                log.warning(f"ffmpeg conversion failed for {filepath.name}")
                return ""
            audio_path = wav_path
        else:
            audio_path = filepath

        wf = wave.open(str(audio_path), "rb")
        rec = KaldiRecognizer(_vosk_model, wf.getframerate())
        rec.SetWords(False)

        text_parts = []
        while True:
            data = wf.readframes(4000)
            if len(data) == 0:
                break
            if rec.AcceptWaveform(data):
                result = _json.loads(rec.Result())
                if result.get("text"):
                    text_parts.append(result["text"])
        final = _json.loads(rec.FinalResult())
        if final.get("text"):
            text_parts.append(final["text"])
        wf.close()

        if needs_convert and wav_path.exists():
            wav_path.unlink()

        return " ".join(text_parts)
    except Exception as e:
        log.warning(f"Audio transcription failed for {filepath.name}: {e}")
        return ""


def _extract_structured_metadata(text: str) -> Dict:
    """Extract dates and phone numbers from OCR/text output."""
    metadata = {"dates": [], "phones": []}

    if _DATEPARSER_AVAILABLE and len(text) < 50000:
        import re
        # Look for date-like patterns and parse them
        date_patterns = re.findall(
            r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{1,2},?\s*\d{2,4}\b',
            text, re.IGNORECASE
        )
        for dp in date_patterns[:20]:  # cap at 20
            parsed = dateparser.parse(dp)
            if parsed:
                metadata["dates"].append(parsed.isoformat()[:10])
        metadata["dates"] = list(set(metadata["dates"]))

    if _PHONENUMBERS_AVAILABLE:
        for match in _phonenumbers.PhoneNumberMatcher(text, "US"):
            formatted = _phonenumbers.format_number(match.number, _phonenumbers.PhoneNumberFormat.E164)
            metadata["phones"].append(formatted)
            if len(metadata["phones"]) >= 10:
                break

    return metadata


def _chunk_text(text: str, max_chunk: int = 4000) -> List[str]:
    """Split text into semantic chunks instead of hard truncation."""
    if not _CHUNKER_AVAILABLE or len(text) <= max_chunk:
        return [text[:max_chunk]]

    try:
        chunks = semchunk.chunk(text, chunk_size=max_chunk, token_counter=len)
        return chunks if chunks else [text[:max_chunk]]
    except Exception:
        return [text[:max_chunk]]


def _ocr_image(filepath: Path) -> str:
    """Extract text from an image file via Tesseract."""
    if not _OCR_AVAILABLE:
        return ""
    try:
        img = Image.open(filepath)
        text = pytesseract.image_to_string(img)
        return text.strip()
    except Exception as e:
        log.warning(f"OCR failed for {filepath.name}: {e}")
        return ""


def _ocr_pdf(filepath: Path, max_pages: int = 5) -> str:
    """Extract text from a PDF — tries native text first, falls back to OCR."""
    if not _PDF_AVAILABLE:
        return ""
    try:
        doc = fitz.open(filepath)
        pages_text = []
        for i, page in enumerate(doc):
            if i >= max_pages:
                break
            # Try native text extraction first (fast, no OCR needed)
            text = page.get_text().strip()
            if text:
                pages_text.append(text)
            elif _OCR_AVAILABLE:
                # No embedded text — render to image and OCR
                pix = page.get_pixmap(dpi=200)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                ocr_text = pytesseract.image_to_string(img).strip()
                if ocr_text:
                    pages_text.append(ocr_text)
        doc.close()
        return "\n\n".join(pages_text)
    except Exception as e:
        log.warning(f"PDF extraction failed for {filepath.name}: {e}")
        return ""


def _extract_text(filepath: Path) -> str:
    """Extract text from any supported file type."""
    ext = filepath.suffix.lower()

    # PDF — native text or OCR
    if ext == ".pdf":
        return _ocr_pdf(filepath)

    # Image — OCR
    if ext in OCR_IMAGE_EXTENSIONS:
        return _ocr_image(filepath)

    # Audio — speech-to-text
    if ext in AUDIO_EXTENSIONS:
        return _transcribe_audio(filepath)

    # Text-based files — direct read
    try:
        return filepath.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _ingest_text(filepath: Path, entry: Dict, username: str):
    """
    Extract and ingest content into knowledge DB.
    Handles text, images, PDFs, audio.
    Uses semantic chunking for large documents (multiple atoms).
    Extracts structured metadata (dates, phones) from OCR output.
    """
    try:
        text = _extract_text(filepath)
        if not text or len(text) < 10:
            return False

        filename = entry.get("source", filepath.name)
        category = entry.get("category", "document")

        # Semantic chunking — split large docs into meaningful pieces
        chunks = _chunk_text(text, max_chunk=4000)

        for i, chunk in enumerate(chunks):
            chunk_id = f"{filename}#chunk{i}" if len(chunks) > 1 else filename
            file_hash = hashlib.md5(chunk.encode()).hexdigest()
            loam.ingest_file_knowledge(
                username=username,
                filename=chunk_id,
                file_hash=file_hash,
                category=category,
                content_text=chunk,
                provider="pa",
            )

        # Extract structured metadata from first chunk (dates, phones)
        metadata = _extract_structured_metadata(chunks[0])
        if metadata["dates"] or metadata["phones"]:
            _log_action("METADATA", filename,
                        detail=f"dates={metadata['dates'][:5]} phones={metadata['phones'][:3]}")

        return True
    except Exception as e:
        log.warning(f"Ingest failed for {filepath}: {e}")
        return False


def execute_moves(
    plan: Dict,
    drive_root: str,
    username: str = "Sweet-Pea-Rudi19",
    progress_callback: Optional[Callable] = None,
) -> Dict:
    """
    Execute file moves from the plan. Creates destination folders, moves files,
    ingests text content along the way.

    Returns: {moved: int, ingested: int, errors: [str]}
    """
    global _progress
    root = Path(drive_root)
    moved = 0
    ingested = 0
    errors = []

    moves = plan["moves"]
    _progress.update(phase="organizing", files_total=len(moves), files_processed=0, current_file="")

    # Create destination folders
    for folder in plan["folders_to_create"]:
        dest_dir = root / folder
        dest_dir.mkdir(parents=True, exist_ok=True)
        _log_action("MKDIR", folder)

    # Move files
    for i, move in enumerate(moves):
        src = root / move["source"]
        dst = root / move["destination"]
        _progress.update(files_processed=i, current_file=move["source"])

        if not src.exists():
            errors.append(f"Source missing: {move['source']}")
            continue

        # Ensure destination parent exists
        dst.parent.mkdir(parents=True, exist_ok=True)

        # Handle name collision at destination
        if dst.exists():
            stem = dst.stem
            suffix = dst.suffix
            counter = 1
            while dst.exists():
                dst = dst.parent / f"{stem}_{counter}{suffix}"
                counter += 1

        # Ingest before move (file is still at source)
        if move.get("ingestable") and move["action"] == "ingest_and_move":
            if _ingest_text(src, move, username):
                ingested += 1

        # Move
        try:
            shutil.move(str(src), str(dst))
            moved += 1
            _log_action("MOVE", move["source"], move["destination"])
        except (OSError, PermissionError) as e:
            errors.append(f"Move failed: {move['source']} — {e}")
            _log_action("ERROR", move["source"], detail=str(e))

        if progress_callback and i % 10 == 0:
            progress_callback(i + 1, move["source"])

    _progress.update(phase="done", files_processed=len(moves))
    log.info(f"Organize complete: {moved} moved, {ingested} ingested, {len(errors)} errors")
    return {"moved": moved, "ingested": ingested, "errors": errors}


def execute_deletes(
    plan: Dict,
    drive_root: str,
    scope: str = "dedupe",
) -> Dict:
    """
    Execute deletions from the plan.
    scope: "dedupe" (only duplicates) or "cleanup" (cache files too)
    """
    global _progress
    root = Path(drive_root)
    deleted = 0
    errors = []
    targets = plan["deletes"]

    if scope == "dedupe":
        targets = [d for d in targets if "duplicate" in d["reason"]]
    elif scope == "cleanup":
        targets = [d for d in targets if "cache" in d["reason"]]

    _progress.update(phase=f"deleting ({scope})", files_total=len(targets), files_processed=0)

    for i, item in enumerate(targets):
        fpath = root / item["source"]
        _progress.update(files_processed=i, current_file=item["source"])

        if not fpath.exists():
            continue

        try:
            fpath.unlink()
            deleted += 1
            _log_action("DELETE", item["source"], detail=item["reason"])
        except (OSError, PermissionError) as e:
            errors.append(f"Delete failed: {item['source']} — {e}")

    _progress.update(phase="done", files_processed=len(targets))
    log.info(f"Delete ({scope}): {deleted} removed, {len(errors)} errors")
    return {"deleted": deleted, "errors": errors}


def correct_file(
    drive_root: str,
    current_path: str,
    new_destination: Optional[str] = None,
    corrected_text: Optional[str] = None,
    new_category: Optional[str] = None,
    username: str = "Sweet-Pea-Rudi19",
) -> Dict:
    """
    Correct a misrouted file or mis-transcribed content.

    - new_destination: move file to a different folder (relative to drive root)
    - corrected_text: re-ingest with corrected text (appends new knowledge atom)
    - new_category: update the category tag on the new knowledge atom

    Returns: {moved: bool, re_ingested: bool, details: str}
    """
    root = Path(drive_root)
    src = root / current_path
    result = {"moved": False, "re_ingested": False, "details": ""}

    if not src.exists():
        result["details"] = f"File not found: {current_path}"
        return result

    # Move to correct location
    if new_destination:
        dst = root / new_destination / src.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            stem, suffix = dst.stem, dst.suffix
            counter = 1
            while dst.exists():
                dst = dst.parent / f"{stem}_{counter}{suffix}"
                counter += 1
        try:
            shutil.move(str(src), str(dst))
            result["moved"] = True
            _log_action("CORRECT_MOVE", current_path, str(dst.relative_to(root)))
        except (OSError, PermissionError) as e:
            result["details"] += f"Move failed: {e}. "

    # Re-ingest with corrected text
    if corrected_text and len(corrected_text) >= 10:
        file_hash = hashlib.md5(corrected_text.encode()).hexdigest()
        category = new_category or "corrected"
        loam.ingest_file_knowledge(
            username=username,
            filename=f"{src.name}#corrected",
            file_hash=file_hash,
            category=category,
            content_text=corrected_text[:4000],
            provider="pa_correction",
        )
        result["re_ingested"] = True
        _log_action("CORRECT_INGEST", current_path, detail=f"category={category}, chars={len(corrected_text)}")
    elif corrected_text:
        result["details"] += "Corrected text too short (min 10 chars). "

    if not result["details"]:
        result["details"] = "ok"
    return result


def cleanup_empty_dirs(drive_root: str) -> int:
    """Remove empty directories after moves. Returns count removed."""
    root = Path(drive_root)
    removed = 0

    # Walk bottom-up to catch nested empties
    for dirpath, dirnames, filenames in os.walk(root, topdown=False):
        if not dirnames and not filenames:
            rel = os.path.relpath(dirpath, root)
            # Don't remove Willow operational dirs
            if rel.startswith("Willow"):
                continue
            try:
                os.rmdir(dirpath)
                removed += 1
                _log_action("RMDIR", rel)
            except OSError:
                pass

    log.info(f"Cleanup: {removed} empty directories removed")
    return removed

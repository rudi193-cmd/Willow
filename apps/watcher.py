#!/usr/bin/env python3
"""
Willow Drop Watcher
====================
Monitors the Drop folder for new files, classifies them, and routes to DBs.

Changes from v1:
- Watches Drop/ (not the non-existent Inbox/)
- Writes to willow_knowledge.db on ingestion (not just classify+log)
- Scans subfolders, detects NotebookLM notebook directories
- --process-backlog: treats all existing Drop files as new

GOVERNANCE: Started by human action only. AI cannot invoke directly.

Usage:
    python watcher.py                    # Interactive mode
    python watcher.py --no-consent       # Background service
    python watcher.py --process-backlog  # Process all existing Drop files then watch
"""

import sys
import time
import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List
import os

# --- Paths ---
DROP_PATH    = Path(r"C:\Users\Sean\My Drive\Willow\Auth Users\Sweet-Pea-Rudi19\Drop")
PICKUP_PATH  = Path(r"C:\Users\Sean\My Drive\Willow\Auth Users\Sweet-Pea-Rudi19\Pickup")
JOURNAL_PATH = Path(r"C:\Users\Sean\My Drive\Willow\Auth Users\Sweet-Pea-Rudi19\JOURNAL.md")
STATE_FILE   = Path(r"C:\Users\Sean\.willow\watcher_state.json")
EVENT_LOG    = Path(r"C:\Users\Sean\.willow\events.log")
KNOWLEDGE_DB = Path(r"C:\Users\Sean\Documents\GitHub\Willow\artifacts\Sweet-Pea-Rudi19\willow_knowledge.db")
CREDENTIALS  = Path(r"C:\Users\Sean\Documents\GitHub\Willow\credentials.json")
POLL_INTERVAL = 5  # seconds
LOCK_FILE    = Path(r"C:\Users\Sean\.willow\watcher.lock")

# Known API key names accepted in Drop key-update files
KNOWN_API_KEYS = {
    "GEMINI_API_KEY", "GEMINI_API_KEY_2", "GEMINI_API_KEY_3", "GEMINI_API_KEY_4",
    "GROQ_API_KEY", "GROQ_API_KEY_2",
    "CEREBRAS_API_KEY", "SAMBANOVA_API_KEY",
    "HUGGINGFACE_API_KEY", "DEEPSEEK_API_KEY", "MISTRAL_API_KEY",
    "TOGETHER_API_KEY", "OPENROUTER_API_KEY", "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY", "FIREWORKS_API_KEY", "COHERE_API_KEY",
    "BASETEN_API_KEY", "BASETEN_API_KEY_2",
    "NOVITA_API_KEY", "NOVITA_API_KEY_2", "NOVITA_API_KEY_3",
    "OCI_API_KEY", "OCI_API_KEY_2", "OCI_API_KEY_3",
}

# --- Extraction module (graceful fallback) ---
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.db import get_connection
try:
    from core import extraction
except ImportError:
    extraction = None

# --- File type sets ---
IMAGE_EXTS    = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff'}
DOC_EXTS      = {'.md', '.txt', '.rst', '.html', '.json', '.markdown'}
PDF_EXT       = '.pdf'
TRAINING_EXTS = {'.gguf', '.jsonl', '.ipynb'}
SKIP_EXTS     = {'.gdoc', '.gsheet', '.gslides', '.ds_store', '.ini', '.db',
                 '.pyc', '.pyd', '.dll', '.exe', '.node', '.map', '.lnk'}

# Specific filenames to never ingest (security-sensitive or system files)
SKIP_FILES    = {'credentials.json', 'credentials.json.bak', '.env', 'secrets.json',
                 'api_keys.json', 'watcher_state.json'}

# Subdirectory names to skip entirely during recursion
# (media archives, system dirs, already-processed data)
SKIP_DIRS = {
    '.git', '.backup',
    'New folder',      # personal media archive — 14k files, handle separately
    'Willow_Chunks',   # already-chunked output data
}


# ─── KEY UPDATE PROCESSOR ─────────────────────────────────────────────────────

def is_key_update_file(path: Path) -> bool:
    """
    A .txt or .env file dropped into Drop that contains KEY_NAME=value lines.
    Detected by presence of at least one known API key pattern.
    """
    if path.suffix.lower() not in {'.txt', '.env', '.keys'}:
        return False
    try:
        text = path.read_text(encoding='utf-8', errors='ignore')
        return any(k in text for k in KNOWN_API_KEYS)
    except Exception:
        return False


def process_key_update(path: Path) -> int:
    """
    Parse KEY=value lines, update credentials.json, delete the drop file.
    Returns count of keys updated.
    """
    updated = []
    try:
        text = path.read_text(encoding='utf-8', errors='ignore')
        creds = {}
        if CREDENTIALS.exists():
            with open(CREDENTIALS) as f:
                creds = json.load(f)

        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' not in line:
                continue
            key, _, val = line.partition('=')
            key = key.strip().upper()
            val = val.strip().strip('"').strip("'")
            if key in KNOWN_API_KEYS and val:
                creds[key] = val
                updated.append(key)

        if updated:
            with open(CREDENTIALS, 'w') as f:
                json.dump(creds, f, indent=2)
            # Write confirmation to Pickup
            confirm = PICKUP_PATH / f"keys_updated_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            confirm.write_text(
                f"Keys updated: {', '.join(updated)}\n"
                f"Source: {path.name}\n"
                f"Time: {datetime.now().isoformat()}\n"
            )
            # Delete the drop file (keys shouldn't sit in Drop)
            path.unlink()
            log_event("KEYS_UPDATED", f"{len(updated)} key(s): {', '.join(updated)}")

    except Exception as e:
        log_event("KEY_UPDATE_ERROR", f"{path.name} | {e}")

    return len(updated)


# ─── 23³ LATTICE CLASSIFIER ───────────────────────────────────────────────────
# Maps (source_type, category, name) → (domain, type_node, status)
# Axis 1: Domain  — matches die-namic-system/governance/INDEX_REGISTRY.md
# Axis 2: Type    — grounding, snapshot, ledger, template, schema, etc.
# Axis 3: Status  — live, archived, snapshot, draft, etc.

def classify_lattice(source_type: str, category: str, name: str = "") -> dict:
    """Return 23³ lattice coordinates for a knowledge record."""
    n = name.lower()
    st = source_type.lower()
    cat = category.lower()

    # ── Axis 1: Domain ────────────────────────────────────────────────────────
    if st == "ocr_image":
        domain = "archive"
    elif cat in ("narrative",) or any(k in n for k in ("aionic", "utety", "books of mann", "dispatch")):
        domain = "personas"
    elif cat == "training" or any(k in n for k in ("training", "finetune", ".gguf")):
        domain = "training"
    elif cat == "social" or any(k in n for k in ("reddit", "social", "digest")):
        domain = "telemetry"
    elif cat in ("reference", "personal") or st in ("notebooklm_export", "drop_pdf", "drop_doc"):
        domain = "docs"
    else:
        domain = "docs"

    # ── Axis 2: Type ──────────────────────────────────────────────────────────
    if st == "ocr_image":
        type_node = "snapshot"
    elif st == "notebooklm_export" and "audio" in n:
        type_node = "ledger"
    elif st == "notebooklm_export":
        type_node = "grounding"
    elif cat == "training":
        type_node = "template"
    elif any(k in n for k in ("schema", "spec", "config")):
        type_node = "schema"
    else:
        type_node = "grounding"

    # ── Axis 3: Status ────────────────────────────────────────────────────────
    if st == "ocr_image":
        status = "archived"
    else:
        status = "live"

    return {"lattice_domain": domain, "lattice_type": type_node, "lattice_status": status}


# ─── KNOWLEDGE CATEGORY DETECTION ────────────────────────────────────────────

def guess_category(name: str) -> str:
    """Infer knowledge category from filename."""
    n = name.lower()
    if any(k in n for k in ("dispatch", "gerald", "regarding jane", "what i carried",
                             "squeakdog", "itchy", "sweater", "ungentle", "the gate",
                             "books of mann", "book one", "book two", "book three",
                             "oakenscroll", "professor", "aionic")):
        return "narrative"
    if any(k in n for k in ("reddit", "digest", "social", "screenshot", "post_")):
        return "social"
    if any(k in n for k in ("legal", "agreement", "contract", "privacy", "workers comp",
                             "case summary", "creditor")):
        return "reference"
    if any(k in n for k in ("training", "classified", "sean_", ".gguf", "model",
                             "finetune", "colab", "kaggle")):
        return "training"
    if any(k in n for k in ("the seventeen", "utety", "llmphysics", "hotdog", "french toast")):
        return "narrative"
    if any(k in n for k in ("gemini", "google", "workspace", "badge", "profile")):
        return "reference"
    if any(k in n for k in ("grocery", "acquired", "voice note")):
        return "personal"
    return "reference"


# ─── STATE / LOG HELPERS ──────────────────────────────────────────────────────

def ensure_dirs():
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    PICKUP_PATH.mkdir(parents=True, exist_ok=True)



def _is_pid_running(pid: int) -> bool:
    """Check if a PID is still running (Windows)."""
    try:
        import ctypes
        handle = ctypes.windll.kernel32.OpenProcess(0x0400, False, pid)
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return False
    except Exception:
        return False


def acquire_instance_lock() -> bool:
    """Prevent multiple watcher instances. Returns False if another is running."""
    if LOCK_FILE.exists():
        try:
            pid = int(LOCK_FILE.read_text().strip())
            if _is_pid_running(pid):
                return False  # another watcher is alive
        except (ValueError, Exception):
            pass  # stale lock -- overwrite it
    LOCK_FILE.write_text(str(os.getpid()))
    return True


def release_instance_lock():
    LOCK_FILE.unlink(missing_ok=True)

def load_state() -> Dict:
    if STATE_FILE.exists():
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {"known_files": {}, "last_run": None}


def save_state(state: Dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, default=str)


def log_event(event_type: str, details: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"{event_type} | {timestamp} | {details}\n"
    with open(EVENT_LOG, "a", encoding="utf-8") as f:
        f.write(entry)
    # encode for Windows console (cp1252 can't handle all unicode)
    safe = details.encode(sys.stdout.encoding or 'utf-8', errors='replace').decode(sys.stdout.encoding or 'utf-8', errors='replace')
    print(f"[{event_type}] {safe}")


def get_item_hash(item: Path) -> str:
    """Hash for change detection. Dirs use mtime+size of Sources/ manifest."""
    try:
        if item.is_dir():
            sources = list((item / "Sources").glob("*.html")) if (item / "Sources").exists() else []
            sig = f"nlm:{len(sources)}:{item.stat().st_mtime}"
            return hashlib.md5(sig.encode()).hexdigest()
        # For large binaries (gguf), use mtime+size instead of content hash
        if item.suffix.lower() in {'.gguf'}:
            stat = item.stat()
            return f"mtime:{stat.st_mtime}:size:{stat.st_size}"
        with open(item, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()
    except Exception as e:
        return f"error:{e}"


# ─── DB INGESTION ─────────────────────────────────────────────────────────────

def ingest_to_knowledge(item: Path, text: str, source_type: str, category: str) -> bool:
    """
    Insert a file or notebook folder into willow_knowledge.db.
    Returns True if new row inserted, False if already present or error.
    """
    source_id = hashlib.md5(str(item).encode('utf-8')).hexdigest()
    snippet = (text[:400].replace('\n', ' ')).strip() if text else ""
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    title = item.name
    lattice = classify_lattice(source_type, category, title)

    try:
        conn = get_connection()
        existing = conn.execute(
            "SELECT id FROM knowledge WHERE source_id=?", (source_id,)
        ).fetchone()
        if existing:
            conn.close()
            return False  # already ingested

        conn.execute("""
            INSERT INTO knowledge(source_type, source_id, title, summary, content_snippet,
                                  category, ring, created_at,
                                  lattice_domain, lattice_type, lattice_status)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (source_type, source_id, title,
              f"Auto-ingested from Drop by watcher: {title}",
              snippet, category, 'bridge', now,
              lattice["lattice_domain"], lattice["lattice_type"], lattice["lattice_status"]))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        log_event("DB_ERROR", f"{item.name} | {e}")
        return False


# ─── DROP SCANNING ────────────────────────────────────────────────────────────

def is_notebooklm_notebook(path: Path) -> bool:
    """A directory with a Sources/ child is a NotebookLM notebook export."""
    return path.is_dir() and (path / "Sources").exists()


def scan_drop() -> List[Path]:
    """
    Recursively scan Drop/.
    - Returns regular files (non-skipped).
    - When a directory with Sources/ is encountered, returns the directory
      as a single item (notebook) rather than its individual files.
    """
    if not DROP_PATH.exists():
        log_event("DROP_MISSING", str(DROP_PATH))
        return []

    items: List[Path] = []

    def _recurse(directory: Path):
        try:
            children = sorted(directory.iterdir())
        except PermissionError:
            return
        for child in children:
            if child.name.startswith('.'):
                continue
            if child.is_dir():
                if child.name in SKIP_DIRS:
                    continue  # skip media archives and system dirs
                if is_notebooklm_notebook(child):
                    items.append(child)  # add notebook dir as single item
                else:
                    _recurse(child)  # recurse into non-notebook subdirs
            elif child.is_file():
                if child.name in SKIP_FILES:
                    continue  # never ingest credentials or system files
                if child.suffix.lower() not in SKIP_EXTS:
                    items.append(child)

    _recurse(DROP_PATH)
    return items


# ─── ITEM PROCESSORS ──────────────────────────────────────────────────────────

def process_doc(filepath: Path) -> Dict:
    """Read .md/.txt/.rst and ingest to knowledge DB."""
    try:
        text = filepath.read_text(encoding='utf-8', errors='replace')
    except Exception as e:
        log_event("READ_ERROR", f"{filepath.name} | {e}")
        return {"status": "error", "reason": str(e)}

    category = guess_category(filepath.name)
    ingested = ingest_to_knowledge(filepath, text, "drop_doc", category)
    status = "ingested" if ingested else "duplicate"
    log_event(status.upper(), f"{filepath.name} | cat={category} | chars={len(text)}")
    return {"status": status, "category": category, "chars": len(text)}


def process_pdf(filepath: Path) -> Dict:
    """Extract PDF text and ingest to knowledge DB."""
    text = ""
    if extraction:
        try:
            text = extraction.extract_text_from_pdf(filepath) or ""
        except Exception as e:
            log_event("PDF_ERROR", f"{filepath.name} | {e}")

    category = guess_category(filepath.name)
    ingested = ingest_to_knowledge(filepath, text, "drop_pdf", category)
    status = "ingested" if ingested else "duplicate"
    log_event(status.upper(), f"{filepath.name} | cat={category} | chars={len(text)}")
    return {"status": status, "category": category, "chars": len(text)}


def process_image(filepath: Path) -> Dict:
    """Queue image for OCR — write a marker to Pickup/ rather than block."""
    queue_entry = {
        "path": str(filepath),
        "queued_at": datetime.now().isoformat(),
        "type": "ocr_queue"
    }
    queue_file = PICKUP_PATH / f"ocr_queue_{filepath.stem[:60]}.json"
    try:
        queue_file.write_text(json.dumps(queue_entry, indent=2), encoding='utf-8')
        log_event("OCR_QUEUED", f"{filepath.name} -> {queue_file.name}")
        return {"status": "queued", "queue_file": str(queue_file)}
    except Exception as e:
        log_event("QUEUE_ERROR", f"{filepath.name} | {e}")
        return {"status": "error", "reason": str(e)}


def process_training_asset(filepath: Path) -> Dict:
    """Catalog a training asset by name/size (don't read binary content)."""
    size = filepath.stat().st_size
    text = f"Training asset: {filepath.name} | size={size:,} bytes | path={filepath}"
    ingested = ingest_to_knowledge(filepath, text, "training_asset", "training")
    status = "cataloged" if ingested else "duplicate"
    log_event(status.upper(), f"{filepath.name} | {size:,}B")
    return {"status": status, "size_bytes": size}


def process_notebooklm_notebook(folder: Path) -> Dict:
    """
    Flag a NotebookLM notebook for dedicated batch ingestion via ingest_notebooklm.py.
    Records it in knowledge DB as 'notebooklm_pending' so it's trackable.
    """
    sources_dir = folder / "Sources"
    source_count = len(list(sources_dir.glob("*.html"))) if sources_dir.exists() else 0
    text = (f"NotebookLM notebook: {folder.name}\n"
            f"Sources: {source_count} HTML files\n"
            f"Path: {folder}\n"
            f"Status: pending batch ingestion via ingest_notebooklm.py")

    ingested = ingest_to_knowledge(folder, text, "notebooklm_pending", "notebooklm")
    status = "flagged" if ingested else "duplicate"
    log_event(f"NLM_{status.upper()}", f"{folder.name} | sources={source_count}")
    return {"status": status, "sources": source_count}


def process_item(item: Path) -> Dict:
    """Dispatch to the right processor based on item type."""
    if item.is_dir():
        return process_notebooklm_notebook(item)

    # Key update files take priority — process and delete immediately
    if is_key_update_file(item):
        count = process_key_update(item)
        return {"status": "keys_updated", "count": count}

    suffix = item.suffix.lower()

    if suffix in IMAGE_EXTS:
        return process_image(item)
    elif suffix == PDF_EXT:
        return process_pdf(item)
    elif suffix in DOC_EXTS:
        return process_doc(item)
    elif suffix in TRAINING_EXTS:
        return process_training_asset(item)
    else:
        # Unknown type — catalog with no content
        ingested = ingest_to_knowledge(item, "", "drop_unknown", "reference")
        status = "cataloged" if ingested else "duplicate"
        log_event(status.upper(), f"{item.name} | type={suffix}")
        return {"status": status}


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Willow Drop Watcher")
    parser.add_argument("--no-consent", action="store_true",
                        help="Skip consent prompt (background service)")
    parser.add_argument("--process-backlog", action="store_true",
                        help="Process all existing Drop files as new, then watch")
    args = parser.parse_args()

    print("Willow Drop Watcher")
    print(f"  Drop:       {DROP_PATH}")
    print(f"  Pickup:     {PICKUP_PATH}")
    print(f"  KnowledgeDB:{KNOWLEDGE_DB}")
    print(f"  Poll:       {POLL_INTERVAL}s")

    if not args.no_consent:
        consent = input("\nStart watching? (yes/no): ").strip().lower()
        if consent != "yes":
            print("Aborted.")
            return
    else:
        print("Background mode: consent assumed from human startup.")

    if not acquire_instance_lock():
        log_event("WATCHER_LOCKED", f"Another watcher already running. Exiting.")
        return

    ensure_dirs()
    state = load_state()

    if args.process_backlog:
        print("\n--- BACKLOG MODE: resetting known_files, processing all Drop contents ---")
        state["known_files"] = {}
        save_state(state)

    log_event("WATCHER_ON", f"drop={DROP_PATH} | backlog={args.process_backlog}")
    print(f"\nWatcher online. Press Ctrl+C to stop.\n")

    consecutive_errors = 0

    try:
        while True:
            try:
                current_items = scan_drop()

                for item in current_items:
                    item_key = str(item)
                    try:
                        item_hash = get_item_hash(item)
                    except Exception as e:
                        log_event("HASH_ERROR", f"{item.name} | {e}")
                        continue

                    if item_key not in state["known_files"]:
                        # New item
                        try:
                            result = process_item(item)
                        except Exception as e:
                            log_event("PROCESS_ERROR", f"{item.name} | {e}")
                            result = {"status": "error"}
                        state["known_files"][item_key] = {
                            "hash": item_hash,
                            "first_seen": datetime.now().isoformat(),
                            "processed": True,
                            "result": result.get("status", "unknown"),
                        }
                    elif state["known_files"][item_key]["hash"] != item_hash:
                        # Changed item — re-process
                        log_event("CHANGED", item.name)
                        try:
                            result = process_item(item)
                        except Exception as e:
                            log_event("PROCESS_ERROR", f"{item.name} | {e}")
                            result = {"status": "error"}
                        state["known_files"][item_key]["hash"] = item_hash
                        state["known_files"][item_key]["last_changed"] = datetime.now().isoformat()
                        state["known_files"][item_key]["result"] = result.get("status", "unknown")

                # Detect removed items
                current_keys = {str(i) for i in current_items}
                for key in list(state["known_files"].keys()):
                    if key not in current_keys:
                        log_event("REMOVED", Path(key).name)
                        del state["known_files"][key]

                state["last_run"] = datetime.now().isoformat()
                save_state(state)
                consecutive_errors = 0  # reset on successful cycle

            except KeyboardInterrupt:
                raise
            except Exception as e:
                consecutive_errors += 1
                log_event("CYCLE_ERROR", f"#{consecutive_errors} | {e}")
                if consecutive_errors >= 10:
                    log_event("WATCHER_ABORT", f"Too many consecutive errors ({consecutive_errors}). Stopping.")
                    break
                # Back off on repeated errors
                time.sleep(POLL_INTERVAL * min(consecutive_errors, 5))
                continue

            time.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        pass
    finally:
        release_instance_lock()
        log_event("WATCHER_OFF", f"known_items={len(state['known_files'])}")
        save_state(state)
        print(f"\nWatcher off. Tracking {len(state['known_files'])} items.")


if __name__ == "__main__":
    main()

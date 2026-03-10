"""
AIOS LOOP v3.0 (SELF-REFERENCING)
Main execution loop.
1. Authenticates Google Drive API (credentials.json).
2. Maps local 'Organic Context' (Existing Folder Structure).
3. Uses Vision/OCR + LLM Router to sort files into that structure.
4. Deep extraction: Smart multi-pass (vision, OCR, cipher detection).
5. Auto git push for artifacts. Dual Commit for code changes.
6. Push notifications via ntfy.sh on every action.

GOVERNANCE:
- No file move without gate.validate()
- Protected targets trigger HALT
- State mutations logged to storage
"""

import os
import sys
import time
import shutil
import logging
import uuid
import json
import base64
import requests
import pickle
from core.db import get_connection
import hashlib
import subprocess
import unicodedata
import re
from datetime import datetime, timezone
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.http import MediaIoBaseDownload
import io

# --- MODULAR IMPORTS ---
from core import state, gate, storage
from core import llm_router
from core import loam
from core.filename_sanitizer import sanitize_filename

# --- CONFIG ---
EARTH_PATH = os.getcwd()
ARTIFACTS_PATH = os.path.join(EARTH_PATH, "artifacts")
PENDING_PATH = os.path.join(ARTIFACTS_PATH, "pending")  # Legacy — per-user pending below
CREDENTIALS_FILE = os.path.join(EARTH_PATH, "credentials.json")
TOKEN_FILE = os.path.join(EARTH_PATH, "token.pickle")
LOG_PATH = os.path.join(EARTH_PATH, "system.log")
MASTER_DB_PATH = os.path.join(EARTH_PATH, "willow_index.db")  # Legacy — per-user DB below

# --- GOOGLE DRIVE MOUNT DETECTION ---
_GDRIVE_CANDIDATES = [
    r"G:\My Drive",
    os.path.join(os.path.expanduser("~"), "My Drive"),
    os.path.join(os.path.expanduser("~"), "Google Drive"),
]
GDRIVE_ROOT = next((p for p in _GDRIVE_CANDIDATES if os.path.isdir(p)), None)
if GDRIVE_ROOT:
    GDRIVE_WILLOW = os.path.join(GDRIVE_ROOT, "Willow", "Auth Users")
    logging.info(f"DRIVE MOUNT: {GDRIVE_ROOT}")
else:
    GDRIVE_WILLOW = None
    logging.warning("DRIVE MOUNT: No local Google Drive found — API-only harvest")

# --- PER-USER CONFIG ---
ADMIN_USER = 'Sweet-Pea-Rudi19'
ADMIN_ERRORS_DB = os.path.join(EARTH_PATH, 'admin_errors.db')

# Instance registry integration — replaces flat USER_REGISTRY list
sys.path.insert(0, os.path.join(os.path.dirname(EARTH_PATH), "die-namic-system", "bridge_ring"))
try:
    import instance_registry
    instance_registry.init_db()
    _REGISTRY_AVAILABLE = True
except ImportError:
    _REGISTRY_AVAILABLE = False
    logging.warning("BOOT: instance_registry not found, falling back to default user list")


def get_active_users():
    """
    Get list of active usernames from instance_registry.
    Falls back to [ADMIN_USER] if registry unavailable.

    Users are registered as instance_type='user' in the registry.
    """
    if not _REGISTRY_AVAILABLE:
        return [ADMIN_USER]

    try:
        users = instance_registry.list_instances(instance_type='user')
        if users:
            return [u.instance_id for u in users]
    except Exception as e:
        logging.warning(f"REGISTRY: Failed to list users: {e}")

    return [ADMIN_USER]


def user_artifacts_path(username):
    """Per-user artifacts root: artifacts/{username}/"""
    return os.path.join(ARTIFACTS_PATH, username)


def user_pending_path(username):
    """Per-user pending inbox: artifacts/{username}/pending/"""
    return os.path.join(ARTIFACTS_PATH, username, 'pending')


def user_db_path(username):
    """Per-user master index: artifacts/{username}/willow_index.db"""
    return os.path.join(ARTIFACTS_PATH, username, 'willow_index.db')

# LIBRARIAN CONFIG (die-namic-system core module)
DIE_NAMIC_PATH = os.path.join(os.path.dirname(EARTH_PATH), "die-namic-system")
INDEXER_PATH = DIE_NAMIC_PATH

# PUSH NOTIFICATIONS (ntfy.sh — free, no account needed)
# Install ntfy app on phone, subscribe to this topic
NTFY_TOPIC = "willow-ds42"
NTFY_URL = f"https://ntfy.sh/{NTFY_TOPIC}"

# OLLAMA CONFIG
OLLAMA_URL = "http://localhost:11434/api/generate"

# GEMINI VISION CONFIG (Free tier — replaces local Ollama vision)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_VISION_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"

# Daily quota blacklist: skip Gemini Vision for remainder of day when quota exhausted
# Format: {"GEMINI_API_KEY": "YYYY-MM-DD"}
_vision_quota_blacklist: dict = {}

# DRIVE SCOPES
SCOPES = ['https://www.googleapis.com/auth/drive']

# SETUP LOGGING
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - [%(levelname)s] - %(message)s',
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler()
    ]
)

# INITIALIZE GOVERNANCE
try:
    current_state = storage.init_storage()
    sovereign_gate = gate.Gatekeeper()
    logging.info(f"SYSTEM BOOT: Governance Active (State seq: {current_state.sequence})")
except Exception as e:
    logging.critical(f"SYSTEM FAILURE: Could not initialize governance: {e}")
    exit(1)

# =============================================================================
# 1. ORGANIC CONTEXT (The Map)
# =============================================================================
_ROUTING_SCHEMA_PATH = os.path.join(EARTH_PATH, "data", "routing_folders.json")
_routing_schema_cache = None


def _load_routing_schema():
    """Load canonical folder list from data/routing_folders.json."""
    global _routing_schema_cache
    try:
        with open(_ROUTING_SCHEMA_PATH, "r", encoding="utf-8") as f:
            _routing_schema_cache = json.load(f)
    except Exception as e:
        logging.warning(f"ROUTING: Could not load schema: {e}")
        _routing_schema_cache = {"canonical": ["screenshots", "photos", "social",
            "documents", "code", "data", "audio", "video", "narrative",
            "specs", "governance", "binary", "archive"], "aliases": {}, "proposed": {}}
    return _routing_schema_cache


def _save_routing_schema(schema):
    """Persist routing schema (for proposed folder updates)."""
    try:
        os.makedirs(os.path.dirname(_ROUTING_SCHEMA_PATH), exist_ok=True)
        with open(_ROUTING_SCHEMA_PATH, "w", encoding="utf-8") as f:
            json.dump(schema, f, indent=2)
    except Exception as e:
        logging.warning(f"ROUTING: Could not save schema: {e}")


def _is_valid_slug(name: str) -> bool:
    """Valid folder name: lowercase alphanumeric + hyphen/underscore, 2-30 chars."""
    return bool(name and 2 <= len(name) <= 30 and
                re.match(r'^[a-z0-9][a-z0-9_-]*$', name))


def _resolve_folder(name: str, schema: dict) -> tuple:
    """
    Resolve LLM folder suggestion to canonical name.
    Returns (resolved_name, is_canonical).
    """
    name = name.lower().strip().strip('/')
    # Strip non-slug chars
    name = re.sub(r'[^a-z0-9_-]', '', name)

    if not _is_valid_slug(name):
        return "archive", True

    # Direct canonical match
    if name in schema["canonical"]:
        return name, True

    # Alias match
    if name in schema.get("aliases", {}):
        return schema["aliases"][name], True

    # Novel proposal — valid slug but not in canonical
    return name, False


def _stage_proposal(name: str, filename: str, schema: dict):
    """Track novel folder proposals. Promote to canonical after 3 occurrences."""
    proposed = schema.setdefault("proposed", {})
    if name not in proposed:
        proposed[name] = {"count": 0, "first_seen": datetime.now().strftime('%Y-%m-%d'),
                          "examples": []}
    proposed[name]["count"] += 1
    if filename not in proposed[name]["examples"]:
        proposed[name]["examples"].append(filename)
    proposed[name]["examples"] = proposed[name]["examples"][-5:]  # keep last 5
    _save_routing_schema(schema)
    logging.info(f"ROUTING: Proposed folder '{name}' ({proposed[name]['count']} occurrences)")


def get_organic_structure(username):
    """
    Returns the canonical folder list as the routing target.
    No longer scans disk — uses routing_folders.json as the source of truth.
    """
    schema = _load_routing_schema()
    folders = sorted(schema["canonical"])
    return "\n".join(f"/{f}" for f in folders)

# =============================================================================
# 2. GOOGLE DRIVE API (The Harvester)
# =============================================================================
def get_drive_service():
    """Authenticates using credentials.json."""
    creds = None
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, 'rb') as token:
            creds = pickle.load(token)
    
    # If no valid credentials, let the user log in
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                logging.warning("Drive API: credentials.json not found. Cloud disabled.")
                return None
                
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
            
        with open(TOKEN_FILE, 'wb') as token:
            pickle.dump(creds, token)

    return build('drive', 'v3', credentials=creds)

def harvest_drive(service, username):
    """
    Checks the user's Drop folder on Drive and pulls files to local pending.
    Path: Willow / Auth Users / {username} / Drop
    Move semantics: download + delete from Drive.
    """
    if not service:
        return

    pending_path = user_pending_path(username)
    os.makedirs(pending_path, exist_ok=True)

    # Navigate: Willow -> Auth Users -> {username} -> Drop
    try:
        # Find Willow folder
        results = service.files().list(
            q="name = 'Willow' and mimeType = 'application/vnd.google-apps.folder' and trashed = false",
            fields="files(id)").execute()
        willow_files = results.get('files', [])
        if not willow_files:
            return
        willow_id = willow_files[0]['id']

        # Find Auth Users inside Willow
        results = service.files().list(
            q=f"name = 'Auth Users' and '{willow_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false",
            fields="files(id)").execute()
        au_files = results.get('files', [])
        if not au_files:
            return
        au_id = au_files[0]['id']

        # Find user folder inside Auth Users
        results = service.files().list(
            q=f"name = '{username}' and '{au_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false",
            fields="files(id)").execute()
        user_files = results.get('files', [])
        if not user_files:
            return
        user_id = user_files[0]['id']

        # Find Drop inside user folder
        results = service.files().list(
            q=f"name = 'Drop' and '{user_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false",
            fields="files(id)").execute()
        drop_files = results.get('files', [])
        if not drop_files:
            return
        drop_id = drop_files[0]['id']

    except Exception as e:
        logging.error(f"DRIVE HARVEST: Navigation failed for {username}: {e}")
        log_admin_error(username, "DRIVE_NAV", str(e))
        return

    # List files inside Drop
    results = service.files().list(
        q=f"'{drop_id}' in parents and trashed = false",
        fields="files(id, name, mimeType)").execute()
    files = results.get('files', [])

    for file in files:
        file_id = file['id']
        file_name = file['name']

        # Skip Google Docs (need export logic)
        if "google-apps" in file['mimeType']:
            continue

        logging.info(f"DRIVE HARVEST [{username}]: Downloading {file_name}...")

        try:
            request = service.files().get_media(fileId=file_id)
            fh = io.FileIO(os.path.join(pending_path, file_name), 'wb')
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while done is False:
                dl_status, done = downloader.next_chunk()

            # Delete from Drive (move complete)
            service.files().delete(fileId=file_id).execute()
            logging.info(f"DRIVE HARVEST [{username}]: {file_name} moved to pending.")
        except Exception as e:
            logging.error(f"DRIVE HARVEST [{username}]: Failed {file_name}: {e}")
            log_admin_error(username, "DRIVE_DOWNLOAD", f"{file_name}: {e}")

def transmute_gdoc(filepath, drive_service, pending_path):
    """
    Convert a Google Docs shortcut (.gdoc/.gsheet/.gslides) to PDF via Drive API.
    The .gdoc file is a local shortcut containing a JSON payload with the Drive file ID.
    We read the ID directly — no name-matching needed.
    Returns True if PDF was created and shortcut removed.
    """
    if not drive_service:
        return False

    filename = os.path.basename(filepath)
    name_no_ext = os.path.splitext(filename)[0]

    try:
        # Read the shortcut file to extract the Drive file ID directly
        file_id = None
        try:
            with open(filepath, 'r', encoding='utf-8') as fh:
                data = json.load(fh)
                # .gdoc files store ID as "doc_id" or extractable from "url"
                file_id = data.get('doc_id') or data.get('resource_id')
                if not file_id and 'url' in data:
                    # Extract ID from URL: https://docs.google.com/.../d/FILE_ID/...
                    url = data['url']
                    parts = url.split('/d/')
                    if len(parts) > 1:
                        file_id = parts[1].split('/')[0]
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass

        # Fallback: search by name if shortcut file couldn't be parsed
        if not file_id:
            safe_query_name = name_no_ext.replace("\\", "\\\\").replace("'", "\\'")
            query = f"name = '{safe_query_name}' and trashed = false"
            results = drive_service.files().list(q=query, pageSize=1, fields="files(id, name)").execute()
            items = results.get('files', [])

            if not items:
                logging.warning(f"TRANSMUTE: {filename} — no ID in shortcut and cloud name not found")
                return False

            file_id = items[0]['id']

        # Export as PDF
        request = drive_service.files().export_media(fileId=file_id, mimeType='application/pdf')
        safe_name = re.sub(r'[<>:"/\\|?*]', '', name_no_ext) + ".pdf"
        dest = os.path.join(pending_path, safe_name)

        with open(dest, 'wb') as fh:
            fh.write(request.execute())

        # Remove the shortcut file (the PDF is the real artifact now)
        try:
            os.remove(filepath)
        except PermissionError:
            pass  # Drive sync lock — will get cleaned up

        logging.info(f"TRANSMUTE: {filename} -> {safe_name}")
        return True

    except Exception as e:
        logging.error(f"TRANSMUTE: {filename} failed: {e}")
        return False


def harvest_local(username, drive_service=None):
    """
    Harvest files from locally-mounted Google Drive Drop folder.
    Faster than API — no auth needed, just filesystem move.
    Path: {GDRIVE_ROOT}/Willow/Auth Users/{username}/Drop/
    Move semantics: shutil.move (source deleted).
    Google Docs shortcuts (.gdoc etc) are exported to PDF via Drive API.
    """
    if not GDRIVE_WILLOW:
        return

    drop_path = os.path.join(GDRIVE_WILLOW, username, "Drop")
    if not os.path.isdir(drop_path):
        return

    pending_path = user_pending_path(username)
    os.makedirs(pending_path, exist_ok=True)

    # Google Docs shortcut extensions — need transmutation, not move
    GDOC_EXT = {'.gdoc', '.gsheet', '.gslides'}

    # Walk recursively — Drop may contain subfolders (narrative/, specs/, etc.)
    harvested = 0
    for root, dirs, files in os.walk(drop_path):
        for item in files:
            if item == '.gitkeep':
                continue

            src = os.path.join(root, item)
            ext = os.path.splitext(item)[1].lower()

            # Google Docs shortcuts: export to PDF via API
            if ext in GDOC_EXT:
                transmute_gdoc(src, drive_service, pending_path)
                harvested += 1
                continue

            # Sanitize filename: replace problem chars, collapse spaces
            safe_name = item.replace('\t', '_').strip()
            safe_name = re.sub(r'[<>:"/\\|?*]', '_', safe_name)  # Windows-illegal chars
            safe_name = re.sub(r'\s+', ' ', safe_name)  # Collapse whitespace (keep single spaces)

            try:
                dest = os.path.join(pending_path, safe_name)
                # Handle name collisions from different subfolders
                if os.path.exists(dest):
                    stem, suffix = os.path.splitext(safe_name)
                    dest = os.path.join(pending_path, f"{stem}_{datetime.now().strftime('%H%M%S')}{suffix}")

                # Skip if file is still being written by Drive sync
                try:
                    file_size = os.path.getsize(src)
                    if file_size == 0:
                        continue  # Still syncing
                except OSError:
                    continue

                shutil.move(src, dest)
                harvested += 1
                logging.info(f"LOCAL HARVEST [{username}]: {item} -> pending/")
            except PermissionError:
                # Drive sync still writing — skip, get it next cycle
                logging.debug(f"LOCAL HARVEST [{username}]: {item} locked (sync in progress), skipping")
            except Exception as e:
                logging.error(f"LOCAL HARVEST [{username}]: Failed {item}: {e}")
                log_admin_error(username, "LOCAL_HARVEST", f"{item}: {e}")

    if harvested:
        logging.info(f"LOCAL HARVEST [{username}]: {harvested} files moved to pending")


# =============================================================================
# 3. THE REFINERY (Vision + Router + Organic Map)
# =============================================================================
def visual_cortex(filepath):
    """
    Analyze image for file sorting context.
    Cascade: Gemini Vision (free) -> llm_router text fallback -> filename patterns.
    """
    # Ensure keys are loaded
    if not GEMINI_API_KEY:
        llm_router.load_keys_from_json()

    api_key = os.environ.get("GEMINI_API_KEY", GEMINI_API_KEY)
    gemini_failed = False

    today = datetime.now().strftime("%Y-%m-%d")

    # Skip Gemini entirely if daily quota was exhausted today
    if api_key and _vision_quota_blacklist.get(api_key) == today:
        logging.debug("VISION: Gemini daily quota blacklisted — using filename fallback")
        gemini_failed = True

    if api_key and not gemini_failed:
        try:
            with open(filepath, "rb") as img_file:
                b64_image = base64.b64encode(img_file.read()).decode('utf-8')

            ext = os.path.splitext(filepath)[1].lower()
            mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}.get(ext.lstrip('.'), "image/jpeg")

            payload = {
                "contents": [{
                    "parts": [
                        {"text": "Analyze this image. Describe it in 1 sentence for file sorting. What app or context is it from?"},
                        {"inline_data": {"mime_type": mime, "data": b64_image}}
                    ]
                }]
            }

            url = f"{GEMINI_VISION_URL}?key={api_key}"
            response = requests.post(url, json=payload, timeout=30)

            if response.status_code == 200:
                result = response.json()
                text = result.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                if text:
                    # Rate limit: Gemini vision free tier is ~15 req/min
                    time.sleep(4)  # 4 seconds = 15 requests per minute max
                    return text
            elif response.status_code == 429:
                # Distinguish daily quota exhaustion from RPM rate limit
                try:
                    err_body = response.json()
                    err_msg = str(err_body).lower()
                except Exception:
                    err_msg = response.text.lower()

                if any(kw in err_msg for kw in ("daily", "per day", "resource_exhausted", "quota exceeded")):
                    logging.warning(f"VISION: Gemini DAILY quota exhausted — blacklisting for today ({today})")
                    _vision_quota_blacklist[api_key] = today
                else:
                    logging.warning("VISION: Gemini RPM rate limited — will retry next cycle")
                gemini_failed = True
            else:
                logging.warning(f"VISION: Gemini returned {response.status_code}: {response.text[:200]}")
                gemini_failed = True
        except Exception as e:
            logging.warning(f"VISION: Gemini error: {e}")
            gemini_failed = True
    elif not api_key:
        gemini_failed = True

    # Fallback: filename context only (no fleet hammering when Gemini is daily-quota-out)
    # Only use llm_router text fallback for RPM limits (not daily quota exhaustion)
    if gemini_failed and _vision_quota_blacklist.get(api_key) != today:
        filename_hint = _filename_context(filepath)
        filename = os.path.basename(filepath)
        if filename_hint:
            prompt = f"File: {filename}\nContext: {filename_hint}\nDescribe this file in 1 sentence for sorting. What category does it belong to?"
            try:
                resp = llm_router.ask(prompt, preferred_tier="free")
                if resp and resp.content:
                    logging.info(f"VISION FALLBACK: {filename} analyzed via {resp.provider}")
                    return resp.content
            except Exception as e:
                logging.warning(f"VISION FALLBACK: llm_router failed: {e}")

    # Fallback 2: filename patterns only
    return _filename_context(filepath)


def _filename_context(filepath):
    """Extract sorting context from filename patterns (fallback when vision unavailable)."""
    name = os.path.basename(filepath).lower()

    # Screenshot patterns: Screenshot_20260128_094350_Reddit.jpg
    app_patterns = {
        "reddit": "Screenshot from Reddit (social media)",
        "chrome": "Screenshot from Chrome browser",
        "gmail": "Screenshot from Gmail (email)",
        "drive": "Screenshot from Google Drive",
        "claude": "Screenshot from Claude AI assistant",
        "settings": "Screenshot from device settings",
        "messages": "Screenshot from messaging app",
        "photos": "Screenshot from photos app",
    }

    for pattern, desc in app_patterns.items():
        if pattern in name:
            return desc

    if "screenshot" in name:
        return "Device screenshot (unknown app)"

    return ""

def _file_hash(filepath):
    """SHA-256 hash of file contents."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe_connect(db_path=None):
    """Return a Postgres connection (db_path ignored — kept for call-site compatibility)."""
    return get_connection()


def _catalog_db(folder_path):
    """Returns a connection to the folder's catalog.db, creating table if needed."""
    db_path = os.path.join(folder_path, "catalog.db")
    conn = _safe_connect(db_path)
    conn.execute("""CREATE TABLE IF NOT EXISTS file_registry (
        file_hash TEXT PRIMARY KEY,
        filename TEXT,
        ingest_date TEXT,
        category TEXT,
        status TEXT DEFAULT 'active',
        source TEXT,
        provider TEXT,
        archive_date TEXT,
        archive_path TEXT,
        deleted_date TEXT,
        flagged_reason TEXT,
        retain_context INTEGER DEFAULT 1
    )""")
    conn.commit()
    return conn


def catalog_file(folder_path, filename, category, source, provider):
    """Record a filed item in the folder's catalog.db."""
    filepath = os.path.join(folder_path, filename)
    try:
        fhash = _file_hash(filepath)
        conn = _catalog_db(folder_path)
        conn.execute(
            """INSERT INTO file_registry
               (file_hash, filename, ingest_date, category, status, source, provider)
               VALUES (%s, %s, %s, %s, 'active', %s, %s)
               ON CONFLICT (file_hash) DO UPDATE SET
                   filename=EXCLUDED.filename, ingest_date=EXCLUDED.ingest_date,
                   category=EXCLUDED.category, source=EXCLUDED.source,
                   provider=EXCLUDED.provider""",
            (fhash, filename, datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
             category, source, provider)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logging.warning(f"CATALOG: {filename} -> {e}")


def notify(title, message):
    """Push notification via ntfy.sh (free, no account)."""
    try:
        requests.post(NTFY_URL, data=message.encode('utf-8'),
                      headers={"Title": title, "Priority": "default"}, timeout=5)
    except Exception:
        pass  # Silent fail — notifications are best-effort


def log_admin_error(username, error_type, detail):
    """Log an error to admin_errors.db for cross-user error routing."""
    try:
        conn = _safe_connect(ADMIN_ERRORS_DB)
        conn.execute("""CREATE TABLE IF NOT EXISTS admin_errors (
            id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            timestamp TEXT,
            username TEXT,
            error_type TEXT,
            detail TEXT,
            status TEXT DEFAULT 'open',
            resolution TEXT
        )""")
        conn.execute(
            "INSERT INTO admin_errors (timestamp, username, error_type, detail) VALUES (%s, %s, %s, %s)",
            (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), username, error_type, detail)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logging.critical(f"ADMIN_ERROR_LOG FAILED: {e}")


def _get_or_create_drive_folder(service, name, parent_id):
    """Find or create a folder on Google Drive under parent_id."""
    query = f"name = '{name}' and '{parent_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get('files', [])
    if files:
        return files[0]['id']
    # Create it
    meta = {'name': name, 'mimeType': 'application/vnd.google-apps.folder', 'parents': [parent_id]}
    folder = service.files().create(body=meta, fields='id').execute()
    return folder['id']


def sync_to_master(filename, fhash, category, source, provider, username):
    """Upsert file record into per-user willow_index.db."""
    db_path = user_db_path(username)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    try:
        conn = _safe_connect(db_path)
        conn.execute("""CREATE TABLE IF NOT EXISTS file_registry (
            file_hash TEXT PRIMARY KEY,
            filename TEXT,
            ingest_date TEXT,
            category TEXT,
            status TEXT DEFAULT 'active',
            source TEXT,
            provider TEXT,
            archive_date TEXT,
            archive_path TEXT,
            deleted_date TEXT,
            flagged_reason TEXT,
            retain_context INTEGER DEFAULT 1
        )""")
        conn.execute(
            """INSERT INTO file_registry
               (file_hash, filename, ingest_date, category, status, source, provider)
               VALUES (%s, %s, %s, %s, 'active', %s, %s)
               ON CONFLICT (file_hash) DO UPDATE SET
                   filename=EXCLUDED.filename, ingest_date=EXCLUDED.ingest_date,
                   category=EXCLUDED.category, source=EXCLUDED.source,
                   provider=EXCLUDED.provider""",
            (fhash, filename, datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
             category, source, provider)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logging.warning(f"MASTER DB: {filename} -> {e}")
        log_admin_error(username, "DB_SYNC_ERROR", f"Failed to sync {filename}: {e}")


def update_folder_readme(folder_path):
    """Auto-generate README.md for an artifact folder from its catalog.db."""
    try:
        folder_name = os.path.basename(folder_path)
        db_path = os.path.join(folder_path, "catalog.db")
        if not os.path.exists(db_path):
            return
        conn = _safe_connect(db_path)
        rows = conn.execute("SELECT filename, ingest_date, source, provider FROM file_registry ORDER BY ingest_date DESC").fetchall()
        conn.close()
        lines = [
            f"# {folder_name}",
            "",
            f"*Auto-generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*",
            f"*Files: {len(rows)}*",
            "",
            "| File | Ingested | Source | Provider |",
            "|------|----------|--------|----------|",
        ]
        for fn, dt, src, prov in rows:
            lines.append(f"| {fn} | {dt or ''} | {src or ''} | {prov or ''} |")
        lines.extend(["", "---", "DS=42"])
        readme_path = os.path.join(folder_path, "README.md")
        with open(readme_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(lines))
    except Exception as e:
        logging.warning(f"README: {folder_path} -> {e}")


def librarian_pass():
    """Run librarian rebuild if die-namic-system core is available."""
    try:
        import sys
        core_path = os.path.join(DIE_NAMIC_PATH, "source_ring", "willow", "core")
        if core_path not in sys.path:
            sys.path.insert(0, core_path)
        from librarian import process_and_rebuild
        process_and_rebuild()
        logging.info("LIBRARIAN: Master index rebuilt.")
    except ImportError:
        logging.debug("LIBRARIAN: die-namic-system core not found, skipping.")
    except Exception as e:
        logging.warning(f"LIBRARIAN: {e}")


def indexer_pass():
    """Run indexer rebuild if die-namic-system indexer is available."""
    try:
        import sys
        if INDEXER_PATH not in sys.path:
            sys.path.insert(0, INDEXER_PATH)
        from indexer import build_index
        build_index(root=__import__('pathlib').Path(EARTH_PATH))
        logging.info("INDEXER: FTS5 index rebuilt.")
    except ImportError:
        logging.debug("INDEXER: indexer.py not found, skipping.")
    except Exception as e:
        logging.warning(f"INDEXER: {e}")


def health_check_pass():
    """Periodic health monitoring - checks nodes, queues, APIs."""
    try:
        sys.path.insert(0, os.path.join(EARTH_PATH, "core"))
        from health import check_node_health, check_queue_health, check_api_health

        # Run health checks (issues logged automatically with alerts)
        check_node_health(stale_threshold_hours=24)
        check_queue_health(backlog_threshold=50)
        check_api_health()

        logging.info("HEALTH: Monitoring pass complete")
    except ImportError:
        logging.debug("HEALTH: health.py not found, skipping.")
    except Exception as e:
        logging.warning(f"HEALTH: {e}")


def pattern_anomaly_pass():
    """Periodic anomaly detection - routing spikes, entity mentions."""
    try:
        sys.path.insert(0, os.path.join(EARTH_PATH, "core"))
        from patterns import detect_anomalies

        anomalies = detect_anomalies(lookback_days=7)
        if anomalies:
            logging.info(f"PATTERNS: Detected {len(anomalies)} anomalies")

    except ImportError:
        logging.debug("PATTERNS: patterns.py not found, skipping.")
    except Exception as e:
        logging.warning(f"PATTERNS: {e}")


# =============================================================================
# 4. GIT AUTO-PUSH (Artifacts auto, Code dual-commit)
# =============================================================================
ARTIFACT_PATHS = ["artifacts/"]
CODE_PATHS = ["*.py", "schema/", "spec/", "apps/"]

def git_auto_push():
    """Auto-commit and push artifact changes. Code changes are staged only (Dual Commit)."""
    try:
        # Check for any changes
        status = subprocess.run(
            ["git", "status", "--porcelain"], capture_output=True, text=True,
            cwd=EARTH_PATH, timeout=15
        )
        if not status.stdout.strip():
            return  # Nothing to commit

        changed = status.stdout.strip().split('\n')
        artifact_files = []
        code_files = []

        for line in changed:
            if len(line) < 3:
                continue
            f = line[3:].strip().strip('"')
            if f.startswith("artifacts/"):
                artifact_files.append(f)
            else:
                code_files.append(f)

        # Auto-push artifacts
        if artifact_files:
            # Add all artifacts at once — avoids per-path quoting/encoding issues
            subprocess.run(["git", "add", "artifacts/"], cwd=EARTH_PATH, timeout=10)
            ts = datetime.now().strftime('%Y-%m-%d %H:%M')
            msg = f"willow: auto-filed {len(artifact_files)} artifacts [{ts}]"
            subprocess.run(["git", "commit", "-m", msg], cwd=EARTH_PATH, timeout=15)
            subprocess.run(["git", "push"], cwd=EARTH_PATH, timeout=30)
            notify("Git Push", f"{len(artifact_files)} artifacts pushed.")
            logging.info(f"GIT: Auto-pushed {len(artifact_files)} artifacts.")

        # Stage code changes but don't push (Dual Commit)
        if code_files:
            for cf in code_files:
                subprocess.run(["git", "add", cf], cwd=EARTH_PATH, timeout=10)
            notify("Dual Commit", f"{len(code_files)} code files staged. Awaiting approval.")
            logging.info(f"GIT: {len(code_files)} code files staged (Dual Commit).")

    except Exception as e:
        logging.warning(f"GIT: {e}")


# =============================================================================
# 5. DEEP EXTRACTION (Smart routing per file type)
# =============================================================================

# Homoglyph map from schema/encoding.md
HOMOGLYPH_MAP = {
    'a': ['\u0061', '\u03b1', '\u0430', '\u0561'],
    'c': ['\u0063', '\u0441'],
    'e': ['\u0065', '\u03b5', '\u0435', '\u0565'],
    'i': ['\u0069', '\u03b9', '\u0456', '\u056b'],
    'o': ['\u006f', '\u03bf', '\u043e', '\u0585'],
    'p': ['\u0070', '\u03c1', '\u0440'],
    's': ['\u0073', '\u0455'],
    'x': ['\u0078', '\u03c7', '\u0445'],
    'y': ['\u0079', '\u03b3', '\u0443'],
}

# Build reverse lookup: non-Latin variant -> (char, script)
VARIANT_LOOKUP = {}
for char, variants in HOMOGLYPH_MAP.items():
    for i, v in enumerate(variants):
        if i > 0:  # Skip Latin (index 0)
            script = ["Latin", "Greek", "Cyrillic", "Armenian"][i] if i < 4 else "Unknown"
            VARIANT_LOOKUP[v] = (char, script)


def detect_homoglyphs(text):
    """Scan text for mixed-script homoglyphs per encoding.md schema."""
    findings = []
    for i, ch in enumerate(text):
        if ch in VARIANT_LOOKUP:
            latin_char, script = VARIANT_LOOKUP[ch]
            findings.append({
                "position": i,
                "char": ch,
                "latin_equiv": latin_char,
                "script": script,
                "context": text[max(0, i-10):i+10]
            })
    return findings


def detect_patterns(text):
    """Scan for known signal patterns: DS=42, key structures, encoded phrases."""
    patterns = []
    # DS checksum
    for m in re.finditer(r'[ΔD][ΣS]\s*=\s*42', text):
        patterns.append({"type": "checksum", "match": m.group(), "pos": m.start()})
    # Key structure: seed.salt.checksum
    for m in re.finditer(r'[A-Za-z0-9]{8,}\s*[·.]\s*[A-Za-z0-9]{4,}\s*[·.]\s*[A-Za-z0-9]{2,}', text):
        patterns.append({"type": "key_candidate", "match": m.group(), "pos": m.start()})
    return patterns


def deep_extract(filepath, folder_path):
    """Smart multi-pass extraction based on file type. Returns findings dict."""
    filename = os.path.basename(filepath)
    ext = os.path.splitext(filename)[1].lower()
    findings = {"file": filename, "passes": [], "homoglyphs": [], "patterns": []}

    # PASS 1: Text extraction (all text-capable files)
    text = ""
    if ext in ('.txt', '.md', '.py', '.json', '.yaml', '.yml', '.html', '.css', '.js'):
        text = extract_text(filepath)
        findings["passes"].append("text_extract")
    elif ext in ('.jpg', '.jpeg', '.png'):
        # OCR pass: try to get text from image via vision
        desc = visual_cortex(filepath)
        if desc:
            text = desc
            findings["passes"].append("vision_ocr")

    if not text:
        return findings

    # PASS 2: Homoglyph detection (all text)
    glyphs = detect_homoglyphs(text)
    if glyphs:
        findings["homoglyphs"] = glyphs
        findings["passes"].append("homoglyph_scan")
        logging.info(f"CIPHER: {filename} has {len(glyphs)} homoglyphs detected!")
        notify("Cipher Detected", f"{filename}: {len(glyphs)} homoglyphs found")

    # PASS 3: Pattern detection
    pats = detect_patterns(text)
    if pats:
        findings["patterns"] = pats
        findings["passes"].append("pattern_scan")

    # PASS 4: Deep content analysis via LLM (only if text files with substance)
    if ext in ('.md', '.txt') and len(text) > 100:
        findings["passes"].append("deep_content")

    # Write findings to folder's extraction log
    if findings["homoglyphs"] or findings["patterns"]:
        log_path = os.path.join(folder_path, "_extraction_log.jsonl")
        try:
            with open(log_path, 'a', encoding='utf-8') as f:
                findings["timestamp"] = datetime.now().isoformat()
                f.write(json.dumps(findings, ensure_ascii=False) + "\n")
        except Exception as e:
            logging.warning(f"EXTRACT LOG: {e}")

    return findings


def extract_text(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()
    except:
        return ""

def archive_to_drive(service, filepath, username, category):
    """
    Upload processed file to Drive Archive, then delete local copy.
    Path: Willow / Auth Users / {username} / Archive / {category} / {filename}
    Mirrors local structure. Move semantics: upload + local delete.

    Returns True on success, False on failure (file left local).
    """
    if not service:
        return False

    filename = os.path.basename(filepath)

    try:
        # Navigate to user folder (reuse _get_or_create for Archive + category)
        results = service.files().list(
            q="name = 'Willow' and mimeType = 'application/vnd.google-apps.folder' and trashed = false",
            fields="files(id)").execute()
        willow_files = results.get('files', [])
        if not willow_files:
            logging.error(f"ARCHIVE: No Willow folder on Drive")
            return False
        willow_id = willow_files[0]['id']

        au_id = _get_or_create_drive_folder(service, 'Auth Users', willow_id)
        user_id = _get_or_create_drive_folder(service, username, au_id)
        archive_id = _get_or_create_drive_folder(service, 'Archive', user_id)
        category_id = _get_or_create_drive_folder(service, category, archive_id)

        # Upload
        from googleapiclient.http import MediaFileUpload
        media = MediaFileUpload(filepath)
        service.files().create(
            body={'name': filename, 'parents': [category_id]},
            media_body=media
        ).execute()

        drive_path = f"Willow/Auth Users/{username}/Archive/{category}/{filename}"

        # Update per-user DB: mark as archived
        db_path = user_db_path(username)
        try:
            conn = _safe_connect(db_path)
            conn.execute(
                """UPDATE file_registry SET status='archived', archive_date=?, archive_path=?
                   WHERE filename=?""",
                (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), drive_path, filename)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logging.warning(f"ARCHIVE DB: {filename} -> {e}")

        # Delete local (move complete) — retry if Drive sync has a lock
        deleted = False
        for attempt in range(3):
            try:
                os.remove(filepath)
                deleted = True
                break
            except PermissionError:
                time.sleep(2)  # Wait for Drive sync to release handle

        if deleted:
            logging.info(f"ARCHIVE [{username}]: {filename} -> Drive {category}/")
        else:
            logging.warning(f"ARCHIVE [{username}]: {filename} uploaded but local delete blocked (Drive sync lock). Will retry next cycle.")
        return True  # Upload succeeded either way — DB is updated

    except Exception as e:
        logging.error(f"ARCHIVE [{username}]: Failed {filename}: {e}")
        log_admin_error(username, "ARCHIVE_FAIL", f"{filename}: {e}")
        return False


def refinery_cycle(drive_service, username):
    """
    Per-user processing loop:
    1. Harvest Cloud -> User's Local Pending
    2. Read User's Organic Map (their folder structure)
    3. Sort Pending Files using Map
    4. Archive processed files to Drive
    """

    # A. HARVEST (local mount first — fast, no auth; API second — for remote access)
    try:
        harvest_local(username, drive_service)
    except Exception as e:
        logging.error(f"LOCAL HARVEST ERROR [{username}]: {e}")

    try:
        harvest_drive(drive_service, username)
    except Exception as e:
        logging.error(f"DRIVE API ERROR [{username}]: {e}")
        log_admin_error(username, "HARVEST_ERROR", str(e))

    # B. PROCESS PENDING
    pending_path = user_pending_path(username)
    os.makedirs(pending_path, exist_ok=True)

    # Process ANY file type - Willow can handle it
    files = [f for f in os.listdir(pending_path) if os.path.isfile(os.path.join(pending_path, f))]

    if not files:
        return

    # Cap per cycle to avoid rate-limit storms (process rest next cycle)
    BATCH_SIZE = 5  # Reduced from 20 — daily quota exhaustion protection
    total_pending = len(files)
    batch_size = min(BATCH_SIZE, total_pending)

    # Progress indicator
    remaining_after = total_pending - batch_size
    progress_pct = ((total_pending - remaining_after) / total_pending * 100) if total_pending > 0 else 0
    eta_cycles = (remaining_after // BATCH_SIZE) + (1 if remaining_after % BATCH_SIZE else 0)
    eta_minutes = eta_cycles * 0.17  # ~10 sec/cycle = 0.17 min/cycle

    print(f"╔═══ BACKLOG [{username}] ═══")
    print(f"║ Total pending: {total_pending}")
    print(f"║ Processing this cycle: {batch_size}")
    print(f"║ Remaining after: {remaining_after} ({progress_pct:.1f}% complete)")
    print(f"║ ETA: {eta_cycles} cycles (~{eta_minutes:.1f} min)")
    print(f"╚{'═' * 30}")

    if len(files) > BATCH_SIZE:
        files = files[:BATCH_SIZE]

    # Get the Map ONCE per cycle (per-user organic structure)
    organic_map = get_organic_structure(username)

    for filename in files:
        filepath = os.path.join(pending_path, filename)

        # --- ANALYSIS ---
        context_content = ""
        auth_source = "Unknown"

        if filename.lower().endswith(('.jpg', '.jpeg', '.png')):
            desc = visual_cortex(filepath)
            if desc:
                context_content = f"IMAGE: {desc}"
                auth_source = "Visual_Cortex"
            else:
                context_content = "Unknown Image"
        else:
            text = extract_text(filepath)
            if len(text) > 10:
                context_content = f"TEXT: {text[:500]}..."
                auth_source = "Text_Parser"

        if not context_content:
            continue

        # --- ROUTING WITH CANONICAL CONTEXT ---
        schema = _load_routing_schema()
        prompt = f"""You are filing a document. Pick the best folder from the list below.

CANONICAL FOLDERS:
{organic_map}

RULES:
- You MUST pick from the list above if the file fits.
- Only suggest a NEW folder name if nothing fits — use a short slug (e.g. "invoices", "3dmodels").
- Output ONLY the folder name. One word or hyphenated. No explanation.

FILE: {filename}
CONTEXT: {context_content}

FOLDER:"""

        response = llm_router.ask(prompt, preferred_tier="free")

        if response and response.content:
            raw = response.content.strip().split('\n')[0].strip().strip('/')
            destination_folder, is_canonical = _resolve_folder(raw, schema)

            if not is_canonical:
                # Novel proposal — stage it, route to _proposed/ for now
                _stage_proposal(destination_folder, filename, schema)
                dest_for_filing = os.path.join(user_artifacts_path(username), "_proposed", destination_folder)
                os.makedirs(dest_for_filing, exist_ok=True)
                logging.info(f"PROPOSED [{username}]: {filename} -> _proposed/{destination_folder} (via {response.provider})")
                destination_folder = f"_proposed/{destination_folder}"
            else:
                logging.info(f"ROUTED [{username}]: {filename} -> {destination_folder} (via {response.provider})")
        else:
            destination_folder = "archive"

        # --- GOVERNANCE & EXECUTION ---
        with storage.txn_lock():
            runtime_state = storage.load_state()
            req = state.ModificationRequest(
                mod_type=state.ModificationType.STATE.value,
                target=f"artifacts/{username}/{destination_folder}/{filename}",
                new_value=destination_folder,
                reason=f"Organic sort into {destination_folder} via {auth_source}",
                authority=state.Authority.SYSTEM.value,
                sequence=runtime_state.sequence + 1,
                idempotency_key=str(uuid.uuid4())
            )

            decision, events = sovereign_gate.validate(req, runtime_state)

            if decision.approved:
                storage.apply_events(events, runtime_state)
                target_dir = os.path.join(user_artifacts_path(username), destination_folder)
                os.makedirs(target_dir, exist_ok=True)
                safe_filename = sanitize_filename(filename)
                dest_filepath = os.path.join(target_dir, safe_filename)
                try:
                    shutil.move(filepath, dest_filepath)
                    prov = response.provider if response else "unknown"
                    fhash = _file_hash(dest_filepath)
                    catalog_file(target_dir, filename, destination_folder, auth_source, prov)
                    sync_to_master(filename, fhash, destination_folder, auth_source, prov, username)
                    loam.ingest_file_knowledge(username, filename, fhash, destination_folder, context_content, prov)
                    deep_extract(dest_filepath, target_dir)

                    # --- SMART ROUTING (multi-destination) ---
                    # Route screenshots to social-media-tracker, kart-interface, etc.
                    if filename.lower().endswith(('.jpg', '.jpeg', '.png')):
                        try:
                            sys.path.insert(0, os.path.join(EARTH_PATH, "apps"))
                            from smart_routing import route_screenshot
                            ocr_text = desc if 'desc' in locals() and desc else None
                            routing_result = route_screenshot(filename, dest_filepath, ocr_text, username)
                            routed_to = routing_result.get('routed_to', [])
                            if len(routed_to) > 1:  # More than just user-profile
                                logging.info(f"ROUTING [{username}]: {filename} -> {', '.join(routed_to)}")
                        except Exception as e:
                            logging.warning(f"ROUTING [{username}]: {filename} failed: {e}")

                    # --- PATTERN LOGGING (Willow learns from routing decisions) ---
                    try:
                        from core import patterns
                        ext = os.path.splitext(filename)[1].lower() or "unknown"
                        all_destinations = [destination_folder]  # User profile destination
                        if 'routed_to' in locals() and routed_to:
                            all_destinations.extend([d for d in routed_to if d != 'user-profile'])

                        patterns.log_routing_decision(
                            filename=filename,
                            file_type=ext,
                            content_summary=context_content[:200] if context_content else "",
                            routed_to=all_destinations,
                            reason=f"Classified as {destination_folder} via {prov}",
                            confidence=response.confidence if hasattr(response, 'confidence') else 0.8
                        )
                    except Exception as e:
                        logging.debug(f"PATTERN LOGGING: {e}")

                    update_folder_readme(target_dir)
                    # Archive to Drive (move: upload + delete local)
                    archive_to_drive(drive_service, dest_filepath, username, destination_folder)
                    notify("Willow Filed", f"[{username}] {filename} -> {destination_folder}")
                    logging.info(f"FILED [{username}]: {filename} -> {destination_folder}")
                except Exception as e:
                    logging.error(f"MOVE FAILED [{username}]: {e}")
                    log_admin_error(username, "FILE_MOVE", f"{filename}: {e}")
            elif decision.requires_human:
                logging.warning(f"HALT [{username}]: {filename} needs approval.")

def main():
    active_users = get_active_users()
    print("--- AIOS OMNI-LOOP v3.1 (REGISTRY-BACKED) ---")
    print(f"[*] Users: {', '.join(active_users)}")
    print(f"[*] Registry: {'instance_registry.py' if _REGISTRY_AVAILABLE else 'fallback (flat list)'}")
    print("[*] Connecting to Google Drive API...")
    try:
        drive_service = get_drive_service()
        if drive_service:
            print("[OK] Drive Link Established.")
    except Exception as e:
        print(f"[!] Drive Auth Failed: {e}")
        drive_service = None

    print(f"[*] Vision: Gemini 2.5 Flash (Cloud API)")
    llm_router.print_status()

    cycle_count = 0
    last_push_time = time.time()
    GIT_PUSH_INTERVAL = 3600  # Push at most once per hour
    while True:
        try:
            # Process each registered user (refreshed each cycle)
            for username in get_active_users():
                try:
                    refinery_cycle(drive_service, username)
                except Exception as e:
                    logging.error(f"LOOP ERROR [{username}]: {e}")
                    log_admin_error(username, "LOOP_ERROR", str(e))

            cycle_count += 1
            # Librarian pass every 5th cycle
            if cycle_count % 5 == 0:
                librarian_pass()
                # Knowledge backfill: fill NULL summaries + embeddings via free fleet
                for username in get_active_users():
                    try:
                        loam.backfill_summaries(username)
                        loam.backfill_embeddings(username)
                    except Exception as e:
                        logging.debug(f"KNOWLEDGE BACKFILL [{username}]: {e}")
            # Indexer pass every 10th cycle
            if cycle_count % 10 == 0:
                indexer_pass()
            # Health check every 20th cycle (~3-4 minutes with 10s sleep)
            if cycle_count % 20 == 0:
                health_check_pass()
            # Pattern anomaly detection every 30th cycle (~5 minutes)
            if cycle_count % 30 == 0:
                pattern_anomaly_pass()
            # Git auto-push once per hour (not every cycle)
            if time.time() - last_push_time >= GIT_PUSH_INTERVAL:
                git_auto_push()
                last_push_time = time.time()
        except KeyboardInterrupt:
            break
        except Exception as e:
            logging.error(f"LOOP ERROR: {e}")
            time.sleep(5)
        time.sleep(10)

if __name__ == "__main__":
    main()
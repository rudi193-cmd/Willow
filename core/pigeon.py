
import os, sys, json, hashlib, shutil, sqlite3, logging, re, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, UTC
from pathlib import Path

logger = logging.getLogger("pigeon")

_WIN = sys.platform == "win32"
_BASE = r"C:\Users\Sean" if _WIN else "/mnt/c/Users/Sean"
_REPO = (r"C:\Users\Sean\Documents\GitHub\Willow" if _WIN
         else "/mnt/c/Users/Sean/Documents/GitHub/Willow")

DB_PATH = os.path.join(_REPO, "artifacts", "Sweet-Pea-Rudi19", "willow_knowledge.db")

NEST_PATHS = {
    "Sweet-Pea-Rudi19": os.path.join(_BASE, "Willow", "Nest"),
}

AGENT_NAMES = [
    "willow", "kart", "riggs", "ada", "shiva", "gerald", "steve", "pigeon",
    "field_notes", "law_gazelle", "private_ledger", "public_ledger", "source_trail", "the_squirrel",
]

NEST_BASE = os.path.join(_BASE, "Willow", "Nest")

FILED_BASE = {
    "Sweet-Pea-Rudi19": os.path.join(_BASE, "Willow", "Filed"),
}

VALID_CATEGORIES = {"legal", "narrative", "personal", "code", "reference", "media"}


def _file_hash(path: Path) -> str:
    """Fast content hash: first 64KB + file size. Handles large files cheaply."""
    h = hashlib.md5()
    try:
        with open(path, "rb") as f:
            h.update(f.read(65536))
        h.update(str(path.stat().st_size).encode())
    except Exception:
        h.update(path.name.encode())
    return h.hexdigest()


def get_nest_path(username: str) -> str:
    path = NEST_PATHS.get(username, os.path.join(_BASE, "Willow", "Nest"))
    os.makedirs(path, exist_ok=True)
    return path


def get_agent_nest_path(agent_name: str) -> str:
    """Get (and create) the per-agent Nest subfolder."""
    path = os.path.join(NEST_BASE, agent_name)
    os.makedirs(path, exist_ok=True)
    return path


def _connect():
    from core.db import get_connection
    return get_connection()


def init_droppings_table():
    pass  # tables created by pg_schema.sql


def _init_droppings_table_UNUSED():
    conn = _connect()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pigeon_droppings (
            id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            username      TEXT NOT NULL,
            filename      TEXT NOT NULL,
            file_hash     TEXT,
            original_path TEXT,
            filed_to      TEXT,
            category      TEXT,
            summary       TEXT,
            created_at    TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pigeon_errors (
            id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            username   TEXT NOT NULL,
            filename   TEXT NOT NULL,
            error      TEXT,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def _read_snippet(file_path: str, max_bytes: int = 2000) -> str:
    """Extract text content from a file. Uses OCR for images, pdfplumber for PDFs."""
    path = Path(file_path)
    suffix = path.suffix.lower()

    # Images: use OCR
    if suffix in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"):
        try:
            import sys as _sys
            _sys.path.insert(0, str(Path(__file__).parent))
            import ocr_consumer
            text = ocr_consumer._extract_image(path)
            if text:
                return text[:max_bytes]
        except Exception as e:
            logger.debug(f"PIGEON: OCR fallback for {path.name}: {e}")

    # PDFs: use pdfplumber
    if suffix == ".pdf":
        try:
            import sys as _sys
            _sys.path.insert(0, str(Path(__file__).parent))
            import ocr_consumer
            text = ocr_consumer._extract_pdf(path)
            if text:
                return text[:max_bytes]
        except Exception as e:
            logger.debug(f"PIGEON: PDF extract fallback for {path.name}: {e}")

    # Everything else: read as text
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            return f.read(max_bytes)
    except Exception:
        try:
            with open(file_path, "rb") as f:
                return f.read(max_bytes).decode("utf-8", errors="replace")
        except Exception:
            return ""


def classify_file(filename: str, snippet: str) -> dict:
    import sys
    sys.path.insert(0, os.path.join(_REPO, "core"))
    import llm_router
    llm_router.load_keys_from_json()
    prompt = (
        "Classify this file and summarize it in 1-2 sentences.\n"
        "Categories: legal, narrative, personal, code, reference, media\n"
        "Also provide a subcategory (1-2 words, lowercase, hyphens only). "
        "Examples: bankruptcy, workers-comp, screenshots, photos, generated, notebooks, scripts, journals, books, specs.\n"
        f"Filename: {filename}\nContent preview:\n{snippet[:1500]}\n\n"
        'Respond as JSON only: {"category": "...", "subcategory": "...", "summary": "..."}'
    )
    try:
        resp = llm_router.ask(prompt, preferred_tier="free")
        if resp and resp.content:
            match = re.search(r"\{[^{}]+\}", resp.content, re.DOTALL)
            if match:
                data = json.loads(match.group())
                cat = data.get("category", "reference").lower().strip()
                if cat not in VALID_CATEGORIES:
                    cat = "reference"
                sub = data.get("subcategory", "general").lower().strip()
                sub = re.sub(r"[^a-z0-9-]", "-", sub)[:32] or "general"
                return {"category": cat, "subcategory": sub, "summary": data.get("summary", "")[:300]}
    except Exception as e:
        logger.warning(f"PIGEON: classify failed for {filename}: {e}")
    name = filename.lower()
    if any(k in name for k in ["legal", "court", "bankruptcy", "motion", "schedule", "creditor"]):
        return {"category": "legal", "subcategory": "general", "summary": f"Legal document: {filename}"}
    if any(k in name for k in ["book", "story", "chapter", "novel", "trappist", "mann", "manuscript"]):
        return {"category": "narrative", "subcategory": "books", "summary": f"Narrative document: {filename}"}
    if any(k in name for k in [".jsonl", "kart", "claude", "chatgpt", "export", "sessions"]):
        return {"category": "code", "subcategory": "exports", "summary": f"Code or export: {filename}"}
    if any(k in name for k in [".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".mp3"]):
        return {"category": "media", "subcategory": "photos", "summary": f"Media file: {filename}"}
    return {"category": "reference", "subcategory": "general", "summary": f"Document: {filename}"}
def route_file(file_path: str, category: str, username: str, subcategory: str = "general") -> str:
    base = FILED_BASE.get(username, os.path.join(_BASE, "Willow", "Filed"))
    dest_dir = os.path.join(base, category, subcategory)
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, Path(file_path).name)
    if os.path.exists(dest):
        stem = Path(file_path).stem
        suffix = Path(file_path).suffix
        ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        dest = os.path.join(dest_dir, f"{stem}_{ts}{suffix}")
    shutil.move(file_path, dest)
    return dest


def create_dropping(username, filename, original_path, filed_to, category, summary, file_hash=None) -> int:
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO pigeon_droppings (username, filename, file_hash, original_path, filed_to, category, summary, created_at) VALUES (?,?,?,?,?,?,?,?)",
        (username, filename, file_hash, original_path, filed_to, category, summary, datetime.now(UTC).isoformat())
    )
    conn.commit()
    dropping_id = cur.lastrowid
    conn.close()
    return dropping_id


def _log_error(username: str, filename: str, error: str):
    try:
        conn = _connect()
        conn.execute(
            "INSERT INTO pigeon_errors (username, filename, error, created_at) VALUES (?,?,?,?)",
            (username, filename, str(error), datetime.now(UTC).isoformat())
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def get_droppings(username: str) -> list:
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, filename, filed_to, category, summary, created_at FROM pigeon_droppings WHERE username=? ORDER BY created_at DESC",
        (username,)
    )
    rows = cur.fetchall()
    conn.close()
    return [{"id": r[0], "filename": r[1], "filed_to": r[2], "category": r[3], "summary": r[4], "created_at": r[5][:16]} for r in rows]


def sweep_dropping(username: str, dropping_id: int) -> bool:
    conn = _connect()
    cur = conn.cursor()
    cur.execute("DELETE FROM pigeon_droppings WHERE id=? AND username=?", (dropping_id, username))
    deleted = cur.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def sweep_all(username: str) -> int:
    conn = _connect()
    cur = conn.cursor()
    cur.execute("DELETE FROM pigeon_droppings WHERE username=?", (username,))
    count = cur.rowcount
    conn.commit()
    conn.close()
    return count


def _process_one(item: Path, username: str, file_hash: str = None):
    """Stage a single file into the Nest review queue. File stays put until user confirms."""
    try:
        from core.nest_intake import stage_file
        result = stage_file(username, str(item), file_hash)
        logger.info(f"PIGEON: staged {item.name} → review queue #{result['id']}")
        return {"id": result["id"], "filename": item.name,
                "category": result["proposed_category"], "summary": result["proposed_summary"],
                "filed_to": None, "staged_for_review": True}
    except Exception as e:
        logger.error(f"PIGEON: error staging {item.name}: {e}")
        _log_error(username, item.name, e)
        return None


PIGEON_WORKERS = 2  # concurrent fleet calls (DB write bottleneck, not fleet)
_DB_LOCK = threading.Lock()  # serialize SQLite writes


def scan_and_process(username: str) -> list:
    init_droppings_table()
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT filename, file_hash FROM pigeon_droppings WHERE username=?", (username,))
    rows = cur.fetchall()
    already_filed_names = {r[0] for r in rows}
    already_filed_hashes = {r[1] for r in rows if r[1]}

    # Also skip files already staged in the review queue (not yet filed)
    # CRITICAL: if this check fails, abort scan entirely — staging without dedup creates duplicates
    try:
        cur.execute(
            "SELECT filename, file_hash FROM nest_review_queue WHERE username=?",
            (username,)
        )
        for r in cur.fetchall():
            already_filed_names.add(r[0])
            if r[1]:
                already_filed_hashes.add(r[1])
    except Exception as e:
        logger.error(f"PIGEON: nest_review_queue dedup check failed: {e} — aborting scan to prevent duplicates")
        conn.close()
        return []

    conn.close()

    # Collect from root Nest + all per-agent subdirs
    scan_dirs = [Path(get_nest_path(username))]
    for agent in AGENT_NAMES:
        agent_nest = Path(get_agent_nest_path(agent))
        if agent_nest.exists():
            scan_dirs.append(agent_nest)

    pending = []
    for nest_dir in scan_dirs:
        for item in nest_dir.iterdir():
            if not item.is_file() or item.name.startswith("."):
                continue
            if item.name in already_filed_names:
                continue
            fh = _file_hash(item)
            if fh in already_filed_hashes:
                logger.debug(f"PIGEON: skipping duplicate content: {item.name}")
                continue
            pending.append((item, fh))

    if not pending:
        return []

    new_droppings = []
    with ThreadPoolExecutor(max_workers=PIGEON_WORKERS) as executor:
        futures = {executor.submit(_process_one, item, username, fh): item for item, fh in pending}
        for future in as_completed(futures):
            result = future.result()
            if result is not None:
                new_droppings.append(result)

    return new_droppings


# ── Bus Drop Intake ────────────────────────────────────────────────────────────────────────────

def init_inbox_table():
    pass  # table created by pg_schema.sql


_DRIVE_INBOX_BASE = Path(_BASE) / "My Drive (rudi193@gmail.com)" / "Willow" / "Nest" / "inbox"

# Apps that live in the cloud — replies written to Drive inbox for async pickup
_CLOUD_APPS = {"oakenscroll"}


def _publish_to_drive_inbox(to_app: str, from_app: str, subject: str, body: str,
                             thread_id, sent_at: str):
    """Write reply to Drive inbox folder so cloud agents can pick it up via sync."""
    try:
        inbox_dir = _DRIVE_INBOX_BASE / to_app
        inbox_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        fname = inbox_dir / f"msg_{ts}_{from_app}.json"
        payload = {
            "from": from_app,
            "to": to_app,
            "subject": subject,
            "body": body,
            "sent_at": sent_at,
            "thread_id": thread_id,
        }
        fname.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        logger.info(f"PIGEON: drive inbox → {fname.name}")
    except Exception as e:
        logger.warning(f"PIGEON: drive inbox write failed: {e}")


def send_to_inbox(to_app: str, from_app: str, username: str,
                  subject: str, body: str, thread_id: str = None) -> int:
    """Deposit a message into an app's inbox. Returns message id."""
    init_inbox_table()
    sent_at = datetime.now(UTC).isoformat()
    conn = _connect()
    cur = conn.execute(
        "INSERT INTO pigeon_inbox (to_app, from_app, username, subject, body, thread_id, sent_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (to_app, from_app, username, subject, body, thread_id, sent_at)
    )
    msg_id = cur.lastrowid
    conn.commit()
    conn.close()
    logger.info(f"PIGEON: inbox message {msg_id} → {to_app} from {from_app}")
    # Mirror to Drive inbox for cloud apps
    if to_app in _CLOUD_APPS:
        _publish_to_drive_inbox(to_app, from_app, subject, body, thread_id, sent_at)
    return msg_id


def get_inbox(app_id: str, username: str = None, unread_only: bool = True) -> list:
    """Fetch messages for an app. Returns list of dicts."""
    init_inbox_table()
    conn = _connect()
    if unread_only:
        rows = conn.execute(
            "SELECT id, to_app, from_app, username, subject, body, thread_id, sent_at, read_at "
            "FROM pigeon_inbox WHERE to_app=? AND read_at IS NULL ORDER BY sent_at DESC",
            (app_id,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, to_app, from_app, username, subject, body, thread_id, sent_at, read_at "
            "FROM pigeon_inbox WHERE to_app=? ORDER BY sent_at DESC LIMIT 100",
            (app_id,)
        ).fetchall()
    conn.close()
    keys = ["id", "to_app", "from_app", "username", "subject", "body", "thread_id", "sent_at", "read_at"]
    return [dict(zip(keys, r)) for r in rows]


def mark_inbox_read(app_id: str, message_id: int = None) -> int:
    """Mark one or all messages as read. Returns count updated."""
    init_inbox_table()
    conn = _connect()
    now = datetime.now(UTC).isoformat()
    if message_id:
        cur = conn.execute(
            "UPDATE pigeon_inbox SET read_at=? WHERE id=? AND to_app=? AND read_at IS NULL",
            (now, message_id, app_id)
        )
    else:
        cur = conn.execute(
            "UPDATE pigeon_inbox SET read_at=? WHERE to_app=? AND read_at IS NULL",
            (now, app_id)
        )
    conn.commit()
    count = cur.rowcount
    conn.close()
    return count


def init_bus_drops_table():
    pass  # table created by pg_schema.sql


def _init_bus_drops_table_UNUSED():
    """Legacy SQLite init — kept for reference only."""
    conn = _connect()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bus_drops (
            id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            source_app TEXT NOT NULL,
            topic      TEXT NOT NULL,
            session_id TEXT,
            status     TEXT NOT NULL,
            result     TEXT,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def _check_app_consent(username: str, app_id: str) -> bool:
    """Return True if username has consented to app_id, or if app_id is empty (internal)."""
    if not app_id or app_id == "unknown":
        return True
    try:
        conn = _connect()
        row = conn.execute(
            "SELECT consented FROM app_consent WHERE username=? AND app_id=? AND consented=1",
            (username, app_id)
        ).fetchone()
        conn.close()
        return row is not None
    except Exception as e:
        logger.warning(f"PIGEON: consent check failed for {app_id}: {e}")
        return True  # fail open — don't block on DB errors


def receive_drop(dropping: dict) -> dict:
    """Intake a bus drop from a safe-app. Validates schema, logs, routes to message bus.

    Pigeon is dumb — no business logic here. Just validate, log, hand off.
    """
    topic = dropping.get("topic") or dropping.get("type")
    app_id = dropping.get("app_id", "unknown")
    session_id = dropping.get("session_id", "")
    payload = dropping.get("payload", {})
    username = dropping.get("username", "Sweet-Pea-Rudi19")

    if not topic:
        return {"ok": False, "error": "missing topic"}

    # Consent gate — external apps must be explicitly consented by the user
    if not _check_app_consent(username, app_id):
        logger.warning(f"PIGEON: consent denied for app_id={app_id} username={username}")
        return {"ok": False, "error": f"App '{app_id}' not consented by user '{username}'"}

    init_bus_drops_table()

    # Log the drop
    try:
        conn = _connect()
        conn.execute(
            "INSERT INTO bus_drops (source_app, topic, session_id, status, created_at) VALUES (?,?,?,?,?)",
            (app_id, topic, session_id, "received", datetime.now(UTC).isoformat())
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"PIGEON: bus_drops log failed: {e}")

    logger.info(f"PIGEON: drop received from {app_id} topic={topic}")

    # Hand to bus
    try:
        from core import message_bus
        result = message_bus.route({
            "topic": topic,
            "app_id": app_id,
            "session_id": session_id,
            "payload": payload,
        })
        return result
    except Exception as e:
        logger.error(f"PIGEON: bus routing failed: {e}")
        return {"ok": False, "topic": topic, "error": str(e)}

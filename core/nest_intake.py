"""
nest_intake.py — Nest file staging and user review pipeline.

Flow:
  1. stage_file()     — OCR/extract + classify + match entities → nest_review_queue (status='pending')
  2. get_queue()      — return pending items for UI
  3. confirm_review() — user confirms/corrects/disposes → file + ingest OR delete
  4. scan_nest()      — scan Nest dir, stage all new files

File stays in Nest until user confirms. Nothing touches the graph until ratified.

Disposition options per item:
  keep_file + keep_data   → file moves to My Documents, data ingested
  delete_file + keep_data → file deleted, extracted data ingested
  delete_file + delete_data → file deleted, nothing ingested

ΔΣ=42
"""

import json
import logging
import os
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("nest_intake")

_REPO = Path(__file__).resolve().parent.parent

UTC = timezone.utc


# ── DB connection ──────────────────────────────────────────────────────────────

def _connect(username: str = None):
    from core.db import get_connection
    return get_connection()


# ── Schema ─────────────────────────────────────────────────────────────────────

def init_queue_table(username: str = None):
    pass  # managed by pg_schema.sql


# ── Destination path ───────────────────────────────────────────────────────────

def _documents_home() -> Path:
    """
    Return the user's My Documents equivalent.
    Windows/WSL: C:\\Users\\{name}\\Documents
    Mac/Linux: ~/Documents
    """
    import sys
    if sys.platform == "linux" and Path("/mnt/c/Users").exists():
        skip = {"All Users", "Default", "Default User", "Public", "desktop.ini"}
        candidates = [p for p in Path("/mnt/c/Users").iterdir()
                      if p.is_dir() and p.name not in skip]
        if len(candidates) == 1:
            docs = candidates[0] / "Documents"
            docs.mkdir(parents=True, exist_ok=True)
            return docs
        linux_user = os.getenv("USER", "")
        for p in candidates:
            if p.name.lower() == linux_user.lower():
                docs = p / "Documents"
                docs.mkdir(parents=True, exist_ok=True)
                return docs
    docs = Path.home() / "Documents"
    docs.mkdir(parents=True, exist_ok=True)
    return docs


def _proposed_path(filename: str, category: str, matched_entities: list) -> str:
    """
    Suggest a My Documents/Willow subfolder based on taxonomy.
    Returns a full path string.

    Taxonomy (GitHub-style, learnable):
      projects/     — active codebases (willow, safe, nasa-archive, die-namic, utety)
      creative/     — fiction, dispatches, papers, lectures (Gerald, Jane, Oakenscroll)
      reference/    — legal, medical, employment, correspondence
      media/        — screenshots, photos, audio, video
      sessions/     — handoffs, notes, session extracts
      operations/   — research operations (clipboard, etc.)
      community/    — clubs, people, rallies, community data
      misc/         — uncategorized (review queue)
    """
    docs = _documents_home()
    base = docs / "Willow"
    fn_lower = filename.lower()

    # Step 1: Check matched entities for known project routing
    entity_names = {e["name"].lower() for e in matched_entities
                    if e.get("confidence", 0) >= 0.7}

    # Project routing — map entity names to project folders
    _PROJECT_MAP = {
        "willow": "projects/willow",
        "safe": "projects/safe",
        "nasa": "projects/nasa-archive",
        "nasa-archive": "projects/nasa-archive",
        "scooter": "projects/nasa-archive",
        "die-namic": "projects/die-namic",
        "utety": "projects/utety",
        "gazelle": "projects/gazelle",
    }
    for key, path in _PROJECT_MAP.items():
        if key in entity_names:
            folder = base / path
            return str(folder / filename)

    # Creative routing
    _CREATIVE_KEYWORDS = {
        "gerald": "creative/dispatches",
        "dispatch": "creative/dispatches",
        "jane": "creative/regarding-jane",
        "oakenscroll": "creative/oakenscroll",
        "squeakdog": "creative/oakenscroll",
        "seventeen problem": "creative/oakenscroll",
        "stone soup": "creative/oakenscroll",
        "binder": "creative/binder",
    }
    for key, path in _CREATIVE_KEYWORDS.items():
        if key in entity_names or key in fn_lower:
            folder = base / path
            return str(folder / filename)

    # Operations routing
    if "clipboard" in entity_names or "paperclip" in fn_lower:
        return str(base / "operations" / "clipboard" / filename)

    # Step 2: Category-based routing (fallback)
    _CAT_MAP = {
        "media":             "media",
        "image":             "media",
        "audio":             "media",
        "video":             "media",
        "screenshot":        "media",
        "legal":             "reference/legal",
        "medical":           "reference/medical",
        "personal":          "reference/personal",
        "personal_document": "reference/personal",
        "employment":        "reference/employment",
        "correspondence":    "reference/correspondence",
        "narrative":         "sessions/journals",
        "handoff":           "sessions/handoffs",
        "session":           "sessions",
        "code":              "projects",
        "reference":         "reference",
        "archive":           "community",
    }
    subfolder = _CAT_MAP.get(category, "misc")
    folder = base / subfolder

    # Don't create folders during staging — only store the proposed path.
    # Folders are created in confirm_review() when the user actually approves.
    return str(folder / filename)


# ── Entity matching ────────────────────────────────────────────────────────────

def _match_entities(username: str, filename: str, ocr_text: str) -> list:
    """
    Search knowledge graph for entities that match this file's content.
    Returns list of {id, name, entity_type, confidence}.
    """
    conn = _connect(username)
    try:
        # Build search terms from filename (strip extension, split on separators)
        name_stem = Path(filename).stem.lower()
        # Extract app name from screenshot filenames like Screenshot_20251130_Reddit.jpg
        parts = name_stem.replace("_", " ").replace("-", " ").split()
        search_terms = set(parts)

        # Also scan OCR text for entity name hints (first 500 chars)
        if ocr_text:
            ocr_parts = ocr_text[:500].lower().replace("\n", " ").split()
            search_terms.update(ocr_parts)

        # Remove noise words — common English, tool names, and short code tokens
        # that false-match against entity names
        noise = {
            # English stopwords
            "screenshot", "img", "image", "jpg", "png", "jpeg", "the", "and",
            "for", "of", "to", "a", "an", "in", "on", "at", "2025", "2026",
            "20250101", "messages", "android", "with", "from", "this", "that",
            "not", "are", "was", "were", "been", "being", "have", "has", "had",
            "will", "would", "could", "should", "may", "can", "but", "all",
            "your", "you", "they", "them", "their", "its", "our", "what",
            "which", "who", "how", "when", "where", "why", "any", "each",
            "new", "use", "get", "set", "run", "out", "also", "just", "than",
            "more", "some", "other", "into", "over", "only", "very", "then",
            "about", "after", "before", "between", "under", "above",
            # Tool/CLI names that pollute entity matching
            "bash", "grep", "glob", "read", "write", "edit", "pip", "npm",
            "node", "curl", "wget", "git", "ssh", "cat", "head", "tail",
            "sed", "awk", "find", "echo", "mkdir", "kill", "top", "less",
            "diff", "sort", "test", "make", "man", "sudo", "apt", "brew",
            "code", "html", "json", "yaml", "toml", "csv", "sql", "http",
            "https", "www", "com", "org", "net", "api", "url", "uri",
            "true", "false", "null", "none", "self", "class", "def",
            "import", "return", "print", "async", "await", "function",
            "const", "var", "let", "type", "string", "number", "list",
            "dict", "file", "path", "data", "name", "text", "value",
            "error", "status", "config", "server", "client", "request",
            "response", "query", "result", "output", "input", "log",
        }
        search_terms -= noise

        matched = []
        seen_ids = set()

        for term in search_terms:
            if len(term) < 4:  # require 4+ chars to reduce noise
                continue
            # Exact match first, then prefix match — no more substring LIKE
            rows = conn.execute(
                "SELECT id, name, entity_type, mention_count FROM entities "
                "WHERE lower(name) = ? OR lower(name) LIKE ? LIMIT 5",
                (term.lower(), f"{term.lower()}%")
            ).fetchall()
            for row in rows:
                eid = row[0] if isinstance(row, (list, tuple)) else row["id"]
                if eid in seen_ids:
                    continue
                seen_ids.add(eid)
                ename = row[1] if isinstance(row, (list, tuple)) else row["name"]
                etype = row[2] if isinstance(row, (list, tuple)) else row["entity_type"]
                ecount = row[3] if isinstance(row, (list, tuple)) else row["mention_count"]
                # Simple confidence: how well does the term match the entity name
                confidence = 0.9 if term.lower() == ename.lower() else 0.6
                matched.append({
                    "id": eid,
                    "name": ename,
                    "entity_type": etype,
                    "mention_count": ecount,
                    "confidence": confidence,
                })

        # Sort by confidence then mention_count
        matched.sort(key=lambda x: (x["confidence"], x["mention_count"]), reverse=True)
        return matched[:10]
    finally:
        conn.close()


# ── Stage a file ───────────────────────────────────────────────────────────────

def stage_file(username: str, file_path: str, file_hash: str = None) -> dict:
    """
    Read + classify + match entities → insert into nest_review_queue.
    File is NOT moved. Returns the queue item dict.
    """
    init_queue_table(username)
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    # Already staged? Check all statuses — only re-allow if previously confirmed/skipped
    conn = _connect(username)
    existing = conn.execute(
        "SELECT id, status FROM nest_review_queue WHERE username=? AND filename=? ORDER BY id DESC LIMIT 1",
        (username, path.name)
    ).fetchone()
    conn.close()
    if existing:
        ex_status = existing[1] if isinstance(existing, (list, tuple)) else existing["status"]
        if ex_status == "pending":
            eid = existing[0] if isinstance(existing, (list, tuple)) else existing["id"]
            logger.debug(f"NEST: {path.name} already staged as #{eid}")
            return get_queue_item(username, eid)
        # confirmed or skipped: file may have reappeared — allow re-staging (fall through)

    # Extract text
    try:
        from core.pigeon import _read_snippet
        ocr_text = _read_snippet(str(path), max_bytes=3000)
    except Exception as e:
        logger.warning(f"NEST: extraction failed for {path.name}: {e}")
        ocr_text = ""

    # Classify via pigeon's classifier
    try:
        from core.pigeon import classify_file
        result = classify_file(path.name, ocr_text)
        proposed_category = result.get("category", "media")
        proposed_summary = result.get("summary", "")
    except Exception as e:
        logger.warning(f"NEST: classify failed for {path.name}: {e}")
        proposed_category = "media"
        proposed_summary = ""

    # Match entities
    matched = _match_entities(username, path.name, ocr_text)

    # Propose destination
    proposed_path = _proposed_path(path.name, proposed_category, matched)

    # Compute hash if not provided
    if not file_hash:
        try:
            import hashlib
            h = hashlib.md5()
            with open(path, "rb") as f:
                h.update(f.read(65536))
            h.update(str(path.stat().st_size).encode())
            file_hash = h.hexdigest()
        except Exception:
            file_hash = None

    # Postgres rejects NUL bytes (0x00) in string literals — strip from all text fields
    def _pg_safe(s: str) -> str:
        return s.replace("\x00", "") if s else s

    ocr_text       = _pg_safe(ocr_text)
    proposed_summary = _pg_safe(proposed_summary)
    proposed_category = _pg_safe(proposed_category)
    proposed_path  = _pg_safe(proposed_path)

    now = datetime.now(UTC).isoformat()
    conn = _connect(username)
    try:
        cur = conn.execute(
            """INSERT INTO nest_review_queue
               (username, filename, original_path, file_hash, ocr_text,
                proposed_summary, proposed_category, proposed_path,
                matched_entities, status, staged_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (username, path.name, str(path), file_hash, ocr_text,
             proposed_summary, proposed_category, proposed_path,
             json.dumps(matched), "pending", now)
        )
        conn.commit()
        item_id = cur.lastrowid
    finally:
        conn.close()

    logger.info(f"NEST: staged {path.name} → #{item_id} ({proposed_category})")
    return get_queue_item(username, item_id)


# ── Queue access ───────────────────────────────────────────────────────────────

def get_queue(username: str, status: str = "pending") -> list:
    """Return all review queue items for a user, optionally filtered by status."""
    init_queue_table(username)
    conn = _connect(username)
    try:
        rows = conn.execute(
            "SELECT * FROM nest_review_queue WHERE username=? AND status=? ORDER BY staged_at DESC",
            (username, status)
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def get_queue_item(username: str, item_id: int) -> dict:
    conn = _connect(username)
    try:
        row = conn.execute(
            "SELECT * FROM nest_review_queue WHERE id=? AND username=?",
            (item_id, username)
        ).fetchone()
        if not row:
            raise KeyError(f"Queue item #{item_id} not found for {username}")
        return _row_to_dict(row)
    finally:
        conn.close()


def _row_to_dict(row) -> dict:
    if hasattr(row, "keys"):
        d = dict(row)
    else:
        cols = ["id", "username", "filename", "original_path", "file_hash",
                "ocr_text", "proposed_summary", "proposed_category", "proposed_path",
                "matched_entities", "status", "user_summary", "user_category",
                "user_path", "dispose_file", "dispose_data", "staged_at", "reviewed_at"]
        d = dict(zip(cols, row))
    # Parse matched_entities JSON
    if isinstance(d.get("matched_entities"), str):
        try:
            d["matched_entities"] = json.loads(d["matched_entities"])
        except Exception:
            d["matched_entities"] = []
    return d


# ── Confirm review ─────────────────────────────────────────────────────────────

def confirm_review(
    username: str,
    item_id: int,
    user_summary: str = None,
    user_category: str = None,
    user_path: str = None,
    dispose_file: bool = False,
    dispose_data: bool = False,
    move_file: bool = False,
) -> dict:
    """
    Execute the user's decision on a staged file.

    dispose_file=False, move_file=False, dispose_data=False → keep in Nest + ingest data
    dispose_file=False, move_file=True,  dispose_data=False → move to My Documents + ingest data
    dispose_file=True,  dispose_data=False                  → delete file + ingest data
    dispose_file=True,  dispose_data=True                   → delete file + no ingest
    """
    item = get_queue_item(username, item_id)
    if item["status"] != "pending":
        raise ValueError(f"Item #{item_id} is not pending (status={item['status']})")

    src_path = Path(item["original_path"])
    final_summary = user_summary or item["proposed_summary"] or ""
    final_category = user_category or item["proposed_category"] or "media"
    final_path = user_path or item["proposed_path"]

    errors = []

    # ── File disposition ───────────────────────────────────────────────────────
    filed_to = None
    if src_path.exists():
        if dispose_file:
            try:
                src_path.unlink()
                logger.info(f"NEST: deleted file {src_path.name}")
            except Exception as e:
                errors.append(f"delete failed: {e}")
        elif move_file:
            # Move to proposed/user path
            dest = Path(final_path)
            dest.parent.mkdir(parents=True, exist_ok=True)
            # Avoid overwriting — suffix with counter
            if dest.exists():
                stem = dest.stem
                suffix = dest.suffix
                i = 1
                while dest.exists():
                    dest = dest.parent / f"{stem}_{i}{suffix}"
                    i += 1
            try:
                shutil.move(str(src_path), str(dest))
                filed_to = str(dest)
                logger.info(f"NEST: filed {src_path.name} → {dest}")
            except Exception as e:
                errors.append(f"move failed: {e}")
                filed_to = None
    else:
        logger.warning(f"NEST: source file missing: {src_path}")

    # ── Knowledge ingest ───────────────────────────────────────────────────────
    if not dispose_data:
        try:
            import sys
            sys.path.insert(0, str(_REPO))
            import core.knowledge as kmod
            file_hash = item.get("file_hash") or ""
            ocr_text = item.get("ocr_text") or ""
            # Pass chrome_ratio from OCR enrichment so entity extraction knows context
            _cr = 0.0
            try:
                _cr = float(item.get("chrome_ratio") or 0.0)
            except (TypeError, ValueError):
                pass
            kmod.ingest_file_knowledge(
                username=username,
                filename=item["filename"],
                file_hash=file_hash,
                category=final_category,
                content_text=final_summary + "\n\n" + ocr_text if final_summary else ocr_text,
                provider="nest_intake",
                context_tags={"chrome_ratio": _cr, "username": username},
            )
            logger.info(f"NEST: ingested {item['filename']} → {final_category}")
        except Exception as e:
            errors.append(f"ingest failed: {e}")
            logger.warning(f"NEST: ingest error for {item['filename']}: {e}")

    # ── Update queue record ────────────────────────────────────────────────────
    now = datetime.now(UTC).isoformat()
    conn = _connect(username)
    try:
        conn.execute(
            """UPDATE nest_review_queue SET
               status=?, user_summary=?, user_category=?, user_path=?,
               dispose_file=?, dispose_data=?, reviewed_at=?
               WHERE id=? AND username=?""",
            ("confirmed", final_summary, final_category,
             filed_to or final_path,
             1 if dispose_file else 0,
             1 if dispose_data else 0,
             now, item_id, username)
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "ok": True,
        "item_id": item_id,
        "filename": item["filename"],
        "filed_to": filed_to,
        "data_ingested": not dispose_data,
        "file_deleted": dispose_file,
        "errors": errors,
    }


# ── Auto-confirm (tiered review) ──────────────────────────────────────────────

# Categories that are safe for auto-confirm (low-risk, high-volume)
AUTO_CONFIRM_CATEGORIES = {
    "reference", "code", "narrative", "personal",
    "session_handoff", "agent_chat", "agent_task", "agent_chain",
}

# Categories that ALWAYS require human eyes
HUMAN_REQUIRED_CATEGORIES = {
    "legal", "legal_document", "property_record",
    "screenshot", "media", "unknown",
}

# Thresholds — items must meet ALL to auto-confirm
AUTO_CONFIRM_MIN_OCR_LEN = 50       # must have real content
AUTO_CONFIRM_MAX_CHROME_RATIO = 0.3  # not mostly browser noise
AUTO_CONFIRM_EXCLUDE_LOW_VALUE = True


def auto_confirm_queue(username: str, dry_run: bool = True) -> dict:
    """
    Auto-confirm high-confidence pending items. Crown-witnessed.

    Items qualify when:
      - category is in AUTO_CONFIRM_CATEGORIES
      - ocr_text length >= AUTO_CONFIRM_MIN_OCR_LEN (has real content)
      - chrome_ratio <= AUTO_CONFIRM_MAX_CHROME_RATIO (not noise)
      - not screenshot_low_value

    Governance: the human ratification was front-loaded into designing these rules.
    Each auto-confirm is Crown-witnessed for audit trail.
    Items that don't qualify stay pending for human review.

    Returns: {confirmed: int, skipped: int, confirmed_items: [...], skipped_reasons: {...}}
    """
    conn = _connect(username)
    try:
        rows = conn.execute(
            "SELECT * FROM nest_review_queue WHERE username=? AND status='pending' ORDER BY staged_at ASC",
            (username,)
        ).fetchall()
    finally:
        conn.close()

    items = [_row_to_dict(r) for r in rows]
    confirmed, skipped = [], []
    skip_reasons = {}

    for item in items:
        cat = item.get("proposed_category") or "unknown"
        ocr_len = len((item.get("ocr_text") or "").strip())
        chrome = float(item.get("chrome_ratio") or 0.0)

        # Check disqualifiers
        reason = None
        if cat in HUMAN_REQUIRED_CATEGORIES:
            reason = f"category:{cat}"
        elif cat == "screenshot_low_value":
            reason = "low_value_screenshot"
        elif cat not in AUTO_CONFIRM_CATEGORIES:
            reason = f"unknown_category:{cat}"
        elif ocr_len < AUTO_CONFIRM_MIN_OCR_LEN:
            reason = f"short_ocr:{ocr_len}"
        elif chrome > AUTO_CONFIRM_MAX_CHROME_RATIO:
            reason = f"high_chrome:{chrome:.2f}"

        if reason:
            skipped.append(item["filename"])
            skip_reasons[reason] = skip_reasons.get(reason, 0) + 1
            continue

        if not dry_run:
            try:
                confirm_review(
                    username=username,
                    item_id=item["id"],
                    user_summary=item.get("proposed_summary"),
                    user_category=cat,
                )
                # Crown witness the auto-confirm
                try:
                    from core.crown import witness_entity_event
                    witness_entity_event(
                        "auto_confirm", item["filename"],
                        agent="nest_intake",
                        username=username,
                        details={
                            "item_id": item["id"],
                            "category": cat,
                            "ocr_len": ocr_len,
                            "chrome_ratio": chrome,
                            "rule": "auto_confirm_v1",
                        },
                    )
                except Exception:
                    pass
            except Exception as e:
                logger.error(f"Auto-confirm failed for #{item['id']}: {e}")
                skipped.append(item["filename"])
                skip_reasons["error"] = skip_reasons.get("error", 0) + 1
                continue

        confirmed.append({"id": item["id"], "filename": item["filename"], "category": cat})

    return {
        "confirmed": len(confirmed),
        "skipped": len(skipped),
        "confirmed_items": confirmed[:20],  # first 20 for display
        "skipped_reasons": skip_reasons,
        "dry_run": dry_run,
        "total_pending": len(items),
    }


# ── Scan Nest ──────────────────────────────────────────────────────────────────

_SCAN_LOCK = threading.Lock()


def scan_nest(username: str) -> list:
    """
    Scan the user's Nest directory. Stage all new files into review queue.
    Returns list of newly staged items.
    """
    from core.willow_paths import nest_dir as _nest_dir
    nest = _nest_dir()
    if not nest.exists():
        return []

    init_queue_table(username)

    # Load already-staged filenames + hashes
    conn = _connect(username)
    try:
        rows = conn.execute(
            "SELECT filename, file_hash FROM nest_review_queue WHERE username=?",
            (username,)
        ).fetchall()
    finally:
        conn.close()

    already_names = {r[0] if isinstance(r, (list, tuple)) else r["filename"] for r in rows}
    already_hashes = {r[1] if isinstance(r, (list, tuple)) else r["file_hash"]
                      for r in rows if (r[1] if isinstance(r, (list, tuple)) else r["file_hash"])}

    import hashlib
    staged = []
    with _SCAN_LOCK:
        for item in nest.iterdir():
            if not item.is_file() or item.name.startswith("."):
                continue
            if item.name in already_names:
                continue
            # Check hash
            try:
                h = hashlib.md5()
                with open(item, "rb") as f:
                    h.update(f.read(65536))
                h.update(str(item.stat().st_size).encode())
                fhash = h.hexdigest()
            except Exception:
                fhash = None

            if fhash and fhash in already_hashes:
                logger.debug(f"NEST: skipping duplicate: {item.name}")
                continue

            try:
                result = stage_file(username, str(item), fhash)
                staged.append(result)
                already_names.add(item.name)
                if fhash:
                    already_hashes.add(fhash)
            except Exception as e:
                logger.error(f"NEST: staging failed for {item.name}: {e}")

    return staged

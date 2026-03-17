
import os, sys, json, hashlib, shutil, logging, re, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, UTC
from pathlib import Path

logger = logging.getLogger("pigeon")

QUARANTINE_THRESHOLD = 3  # max errors before a file is quarantined


def _pg_safe(text):
    """Strip NUL bytes from strings before Postgres insertion."""
    if isinstance(text, str):
        return text.replace('\x00', '')
    return text

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
    "ganesha",
    "field_notes", "law_gazelle", "private_ledger", "public_ledger", "source_trail", "the_squirrel",
]

NEST_BASE = os.path.join(_BASE, "Willow", "Nest")

FILED_BASE = {
    "Sweet-Pea-Rudi19": os.path.join(_BASE, "Willow", "Filed"),
}

# Classification delegated to classifier.py — Pigeon drives the bus, Willow reads the manifest
from core.classifier import get_valid_categories as _get_valid_categories, classify as _classify_file

VALID_CATEGORIES = _get_valid_categories()


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
                return text.replace("\x00", "")[:max_bytes]
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

    # Everything else: read as text (skip binary files to avoid NUL byte poisoning)
    if suffix in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".pdf"):
        return ""  # Binary file with no successful OCR — don't read raw bytes
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            return f.read(max_bytes).replace("\x00", "")
    except Exception:
        try:
            with open(file_path, "rb") as f:
                return f.read(max_bytes).decode("utf-8", errors="replace").replace("\x00", "")
        except Exception:
            return ""


def classify_file(filename: str, snippet: str) -> dict:
    """Delegate to classifier.py — Pigeon drives the bus, Willow reads the manifest."""
    return _classify_file(filename, snippet)


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
        (_pg_safe(username), _pg_safe(filename), _pg_safe(file_hash), _pg_safe(original_path),
         _pg_safe(filed_to), _pg_safe(category), _pg_safe(summary), datetime.now(UTC).isoformat())
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
            (_pg_safe(username), _pg_safe(filename), _pg_safe(str(error)), datetime.now(UTC).isoformat())
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


def _error_count(filename: str) -> int:
    """Count how many times a file has errored in pigeon_errors."""
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM pigeon_errors WHERE filename=?", (filename,))
        count = cur.fetchone()[0]
        conn.close()
        return count
    except Exception:
        return 0


def _chunk_task(message: str) -> list[dict]:
    """Decompose a task into sections for parallel fleet processing.

    Splits on markdown headers (##), numbered sections, or --- dividers.
    Each chunk gets a role: 'section' (parallel) or 'assembly' (Kart merges).
    Short tasks (<2000 chars) stay as a single chunk.
    """
    if len(message) < 2000:
        return [{"role": "single", "index": 0, "content": message}]

    # Split on section markers
    import re
    parts = re.split(r'\n(?=##\s|SECTION\s|---\n|\d+\.\s+[A-Z])', message)
    parts = [p.strip() for p in parts if p.strip()]

    if len(parts) <= 1:
        # No clear sections — split by paragraph groups (~1500 chars each)
        paragraphs = message.split('\n\n')
        chunks = []
        current = []
        current_len = 0
        for para in paragraphs:
            if current_len + len(para) > 1500 and current:
                chunks.append('\n\n'.join(current))
                current = [para]
                current_len = len(para)
            else:
                current.append(para)
                current_len += len(para)
        if current:
            chunks.append('\n\n'.join(current))
        parts = chunks

    return [{"role": "section", "index": i, "content": p} for i, p in enumerate(parts)]


def _call_agent(agent_name: str, message: str, username: str) -> str | None:
    """Call a local agent persona via chunked fleet pipeline.

    Pipeline: decompose → parallel fleet calls → Kart reassembles → Crown witnesses.
    Each chunk goes to the best available provider. Kart stitches with voice consistency.
    Full rings: mailbox (Crown-witnessed), reply file, knowledge graph eligible.
    """
    try:
        sys.path.insert(0, _REPO)
        sys.path.insert(0, os.path.join(_REPO, "core"))
        import local_api
        import llm_router

        # Resolve persona
        persona = agent_name.capitalize()
        if persona not in local_api.PERSONAS:
            if agent_name not in local_api.PERSONAS:
                logger.warning(f"PIGEON: no persona config for {agent_name}")
                return None
            persona = agent_name

        persona_prompt = local_api.PERSONAS.get(persona, "")

        llm_router.load_keys_from_json()

        # Decompose task into chunks
        chunks = _chunk_task(message)
        logger.info(f"PIGEON: {agent_name} task decomposed into {len(chunks)} chunks")

        if len(chunks) == 1 and chunks[0]["role"] == "single":
            # Short task — single fleet call
            full_prompt = f"{persona_prompt}\n\n{message}"
            resp = llm_router.ask(full_prompt, preferred_tier="free",
                                  task_type="general_completion", max_tokens=4096)
            if resp and resp.content:
                response = resp.content.strip()
                logger.info(f"PIGEON: {agent_name} (single) via {resp.provider} ({len(response)} chars)")
            else:
                return None
        else:
            # Multi-chunk — parallel fleet calls, then Kart assembly
            section_results = [None] * len(chunks)

            def _process_chunk(chunk):
                idx = chunk["index"]
                section_prompt = (
                    f"You are {persona}. {persona_prompt}\n\n"
                    f"Write section {idx + 1} of {len(chunks)} for this task. "
                    f"Maintain voice throughout. This is your section:\n\n"
                    f"{chunk['content']}"
                )
                resp = llm_router.ask(section_prompt, preferred_tier="free",
                                      task_type="general_completion", max_tokens=4096)
                if resp and resp.content:
                    section_results[idx] = resp.content.strip()
                    logger.info(f"PIGEON: {agent_name} chunk {idx+1}/{len(chunks)} "
                                f"via {resp.provider} ({len(resp.content)} chars)")
                else:
                    section_results[idx] = f"[Section {idx+1} generation failed]"

            # Parallel execution
            with ThreadPoolExecutor(max_workers=min(len(chunks), 4)) as executor:
                executor.map(_process_chunk, chunks)

            # Kart assembly: stitch sections with voice consistency
            sections_text = "\n\n---\n\n".join(
                f"## Section {i+1}\n{s}" for i, s in enumerate(section_results) if s
            )

            assembly_prompt = (
                f"You are Kart (infrastructure agent). Your task: assemble these {len(chunks)} "
                f"sections into ONE coherent document in the voice of {persona}.\n\n"
                f"Voice reference: {persona_prompt[:500]}\n\n"
                f"RULES:\n"
                f"- Maintain consistent {persona} voice throughout\n"
                f"- Smooth transitions between sections\n"
                f"- Remove duplicate content across sections\n"
                f"- Keep ALL substantive content — do not summarize or shorten\n"
                f"- Output the assembled document only, no meta-commentary\n\n"
                f"SECTIONS TO ASSEMBLE:\n\n{sections_text}"
            )

            logger.info(f"PIGEON: Kart assembling {len(chunks)} sections ({len(sections_text)} chars)")
            resp = llm_router.ask(assembly_prompt, preferred_tier="free",
                                  task_type="general_completion", max_tokens=8192)
            if resp and resp.content:
                response = resp.content.strip()
                logger.info(f"PIGEON: Kart assembled via {resp.provider} ({len(response)} chars)")
            else:
                # Fallback: concatenate sections without assembly
                response = "\n\n".join(s for s in section_results if s)
                logger.warning(f"PIGEON: Kart assembly failed, using raw concatenation")

        # Record in mailbox (Crown-witnessed)
        try:
            from core import agent_registry as _ar
            _ar.send_message(
                username, from_agent=agent_name, to_agent="user",
                subject=f"reply:{message[:60]}",
                body=f"Q: {message[:500]}...\n\nA: {response[:2000]}...",
            )
        except Exception:
            pass  # mailbox recording is best-effort

        return response
    except Exception as e:
        logger.error(f"PIGEON: _call_agent({agent_name}) failed: {e}")
        return None


def _call_chain(agents: list[str], message: str, username: str,
                 thread_id: str = None) -> dict:
    """Route a task through a chain of agents. Each agent sees accumulated context.

    Pipeline: agent_1 responds → agent_2 sees original + agent_1's response → ...
    Each exchange is Crown-witnessed via mailbox. Full audit trail.

    Returns: {
        "thread_id": str,
        "exchanges": [{agent, response, chars, provider_note}],
        "final_response": str,  # last agent's response
        "transcript": str,      # full formatted transcript
    }
    """
    sys.path.insert(0, _REPO)
    sys.path.insert(0, os.path.join(_REPO, "core"))
    import llm_router
    import local_api
    llm_router.load_keys_from_json()

    if not thread_id:
        thread_id = f"chain_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{agents[0]}"

    exchanges = []
    accumulated = f"## Original Task\n\n{message}\n"

    for i, agent_name in enumerate(agents):
        # Resolve persona
        persona = agent_name.capitalize()
        if persona not in local_api.PERSONAS:
            if agent_name not in local_api.PERSONAS:
                logger.warning(f"PIGEON: chain skipping {agent_name} — no persona config")
                exchanges.append({
                    "agent": agent_name, "response": "[no persona config — skipped]",
                    "chars": 0, "provider_note": "skipped",
                })
                continue
            persona = agent_name

        persona_prompt = local_api.PERSONAS.get(persona, "")

        # Build context: persona + accumulated conversation so far
        is_first = (i == 0)
        is_last = (i == len(agents) - 1)

        if is_first:
            chain_context = (
                f"You are {persona} in a faculty discussion with: {', '.join(agents)}.\n"
                f"You speak first. Respond to the task below in your voice.\n"
            )
        else:
            prev_names = [e["agent"] for e in exchanges if e["chars"] > 0]
            chain_context = (
                f"You are {persona} in a faculty discussion with: {', '.join(agents)}.\n"
                f"You've heard from: {', '.join(prev_names)}. "
                f"{'You have the final word. ' if is_last else ''}"
                f"Respond to what's been said. Add your perspective. "
                f"You may agree, disagree, extend, or redirect.\n"
            )

        full_prompt = f"{persona_prompt}\n\n{chain_context}\n\n{accumulated}"

        # Use chunked pipeline for this agent
        resp = _call_agent(agent_name, full_prompt, username)

        if resp:
            exchanges.append({
                "agent": agent_name,
                "response": resp,
                "chars": len(resp),
                "provider_note": "chunked" if len(full_prompt) > 2000 else "single",
            })
            accumulated += f"\n\n---\n\n## {persona}'s Response\n\n{resp}\n"
            logger.info(f"PIGEON: chain [{i+1}/{len(agents)}] {agent_name} → {len(resp)} chars")
        else:
            exchanges.append({
                "agent": agent_name,
                "response": "[no response]",
                "chars": 0,
                "provider_note": "failed",
            })
            logger.warning(f"PIGEON: chain [{i+1}/{len(agents)}] {agent_name} → failed")

        # Crown witness: record exchange in mailbox
        try:
            from core import agent_registry as _ar
            prev_agent = agents[i - 1] if i > 0 else "user"
            _ar.send_message(
                username, from_agent=agent_name, to_agent=agents[i + 1] if i < len(agents) - 1 else "user",
                subject=f"chain:{thread_id}:{agent_name}",
                body=f"{resp[:2000] if resp else '[no response]'}",
                thread_id=thread_id,
            )
        except Exception:
            pass

    # Build full transcript
    transcript_parts = [f"# Agent Chain: {' → '.join(agents)}\n"]
    transcript_parts.append(f"**Thread:** {thread_id}\n")
    transcript_parts.append(f"**Date:** {datetime.now(UTC).isoformat()}\n\n")
    transcript_parts.append(f"## Original Task\n\n{message}\n")
    for ex in exchanges:
        transcript_parts.append(f"\n---\n\n## {ex['agent'].capitalize()}'s Response\n")
        transcript_parts.append(f"*({ex['chars']} chars)*\n\n")
        transcript_parts.append(f"{ex['response']}\n")

    transcript = "\n".join(transcript_parts)

    return {
        "thread_id": thread_id,
        "exchanges": exchanges,
        "final_response": exchanges[-1]["response"] if exchanges else "",
        "transcript": transcript,
    }


def _process_one(item: Path, username: str, file_hash: str = None):
    """Stage a single file into the Nest review queue, then remove the source file."""
    # Bug 2: Quarantine files that have failed too many times
    if _error_count(item.name) >= QUARANTINE_THRESHOLD:
        logger.warning(f"PIGEON: Quarantined after {QUARANTINE_THRESHOLD} failures: {item.name}")
        return None

    try:
        from core.nest_intake import stage_file
        result = stage_file(username, str(item), file_hash)
        logger.info(f"PIGEON: staged {item.name} → review queue #{result['id']}")

        # Agent-addressed files: deliver to inbox AND trigger the agent conversation
        if result.get("proposed_category") == "agent_task":
            target_agent = result.get("proposed_subcategory", "")
            if target_agent:
                content = _read_snippet(str(item), max_bytes=50000)  # full content for agent
                try:
                    send_to_inbox(
                        to_app=target_agent, from_app="pigeon", username=username,
                        subject=f"Incoming task: {item.name}",
                        body=content,
                    )
                    logger.info(f"PIGEON: delivered {item.name} → {target_agent} inbox")
                except Exception as inbox_err:
                    logger.warning(f"PIGEON: inbox delivery failed for {target_agent}: {inbox_err}")

                # Knock on the door: call the agent and capture the reply
                try:
                    reply = _call_agent(target_agent, content, username)
                    if reply:
                        # Drop reply into Documents/Willow (user's file tree, outside Nest scan)
                        ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
                        reply_dir = Path(_BASE) / "Documents" / "Willow" / "agent_replies"
                        reply_dir.mkdir(parents=True, exist_ok=True)
                        reply_file = reply_dir / f"REPLY_FROM_{target_agent.upper()}_{ts}.md"
                        reply_file.write_text(
                            f"# Reply from {target_agent.capitalize()}\n"
                            f"**Task:** {item.name}\n"
                            f"**Date:** {datetime.now(UTC).isoformat()}\n\n"
                            f"---\n\n{reply}\n",
                            encoding="utf-8",
                        )
                        logger.info(f"PIGEON: {target_agent} replied → {reply_file.name}")
                except Exception as call_err:
                    logger.warning(f"PIGEON: agent call failed for {target_agent}: {call_err}")

        # Agent chain / conf call: route through multiple agents in sequence
        elif result.get("proposed_category") == "agent_chain":
            chain_str = result.get("proposed_subcategory", "")
            agents = [a.strip() for a in chain_str.split("→") if a.strip()]
            if len(agents) >= 2:
                content = _read_snippet(str(item), max_bytes=50000)
                try:
                    chain_result = _call_chain(agents, content, username)
                    if chain_result and chain_result["transcript"]:
                        # Save full transcript to Documents/Willow
                        ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
                        reply_dir = Path(_BASE) / "Documents" / "Willow" / "agent_replies"
                        reply_dir.mkdir(parents=True, exist_ok=True)
                        chain_name = "_".join(a[:4].upper() for a in agents)
                        reply_file = reply_dir / f"CHAIN_{chain_name}_{ts}.md"
                        reply_file.write_text(chain_result["transcript"], encoding="utf-8")
                        logger.info(
                            f"PIGEON: chain {' → '.join(agents)} complete → {reply_file.name} "
                            f"({len(chain_result['exchanges'])} exchanges, "
                            f"{sum(e['chars'] for e in chain_result['exchanges'])} total chars)"
                        )
                except Exception as chain_err:
                    logger.warning(f"PIGEON: chain call failed: {chain_err}")

        # Auto-remove source after successful staging
        try:
            item.unlink()
            logger.info(f"PIGEON: removed staged file {item.name}")
        except OSError as rm_err:
            logger.warning(f"PIGEON: could not remove {item.name}: {rm_err}")
        return {"id": result["id"], "filename": item.name,
                "category": result["proposed_category"], "summary": result["proposed_summary"],
                "filed_to": None, "staged_for_review": True}
    except FileNotFoundError:
        # Bug 3: File moved/deleted between scan and process — expected, not an error
        return None
    except OSError as e:
        if e.errno == 2:
            # Bug 3: errno 2 = ENOENT, same as FileNotFoundError
            return None
        logger.error(f"PIGEON: error staging {item.name}: {e}")
        _log_error(username, item.name, e)
        return None
    except Exception as e:
        logger.error(f"PIGEON: error staging {item.name}: {e}")
        _log_error(username, item.name, e)
        return None


PIGEON_WORKERS = 2  # concurrent fleet calls (DB write bottleneck, not fleet)


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

    # Collect from root Nest + all per-agent subdirs (don't create — just check existing)
    scan_dirs = [Path(get_nest_path(username))]
    for agent in AGENT_NAMES:
        agent_nest = Path(os.path.join(NEST_BASE, agent))
        if agent_nest.exists():
            scan_dirs.append(agent_nest)

    pending = []
    for nest_dir in scan_dirs:
        for item in nest_dir.rglob("*"):
            if not item.is_file() or item.name.startswith("."):
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
        (_pg_safe(to_app), _pg_safe(from_app), _pg_safe(username), _pg_safe(subject),
         _pg_safe(body), _pg_safe(thread_id), sent_at)
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
            (_pg_safe(app_id), _pg_safe(topic), _pg_safe(session_id), "received", datetime.now(UTC).isoformat())
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

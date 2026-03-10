#!/usr/bin/env python3
try:
    from dotenv import load_dotenv; load_dotenv()
except ImportError:
    pass
"""
Willow UI Server — FastAPI wrapper around local_api.py

GOVERNANCE: Localhost-only. No external network binding.
"""

import os
import sys
import shutil
import hashlib
import httpx
import psutil
import queue
import threading
import logging
from datetime import datetime
import asyncio
from pathlib import Path
from typing import Optional
from concurrent.futures import ThreadPoolExecutor

# Wire all module loggers to the console so pigeon/kart/knowledge output is visible
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
    force=True,
)
logger = logging.getLogger("willow.server")

from fastapi import FastAPI, Request, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles

# Wire imports
sys.path.insert(0, str(Path(__file__).parent))

import local_api
from core import loam
from core import ocr_consumer
from core import file_organizer

# context_store lives in ~/.claude — load dynamically
try:
    import importlib.util as _ilu
    _cs_path = Path.home() / ".claude" / "context_store.py"
    _cs_spec = _ilu.spec_from_file_location("context_store", str(_cs_path))
    cs = _ilu.module_from_spec(_cs_spec)
    _cs_spec.loader.exec_module(cs)
    _CS_AVAILABLE = True
except Exception:
    _CS_AVAILABLE = False
from core.coherence import get_coherence_report, check_intervention
from core import topology
from core import agent_registry
from core import tool_engine, rings, graft
from core.awareness import on_scan_complete, on_organize_complete, on_coherence_update, on_topology_update, say as willow_say
from apps.pa import drive_scan, drive_organize
from api import kart_routes, agent_routes, safe_routes, social_routes, social_workflow_routes, nasa_routes, roots_routes, utety_routes, vision_routes, dating_routes, die_namic_routes, journal_routes, auth_routes, apps_routes, nest_routes

app = FastAPI(title="Willow", docs_url=None, redoc_url=None)

# -- Launch Pigeon + OCR daemons (one set per Willow instance, not per worker) ---
import os as _os
import subprocess as _subprocess
import threading as _threading

_DAEMON_LOCK = Path(__file__).parent / ".daemon_owner.pid"


def _claim_daemon_lock() -> bool:
    """Return True if this process should spawn daemons (first worker wins)."""
    try:
        if _DAEMON_LOCK.exists():
            existing_pid = int(_DAEMON_LOCK.read_text().strip())
            try:
                _os.kill(existing_pid, 0)  # 0 = check existence only
                return False               # still alive — another worker owns it
            except OSError:
                pass                       # gone — claim it
        _DAEMON_LOCK.write_text(str(_os.getpid()))
        return True
    except Exception:
        return True  # if lock check fails, let it spawn


def _forward_daemon_output(pipe, logger_name: str) -> None:
    """Read lines from a daemon pipe and forward to server logger. Runs in daemon thread."""
    _log = logging.getLogger(logger_name)
    try:
        for raw in iter(pipe.readline, b""):
            line = raw.decode("utf-8", errors="replace").rstrip()
            if line:
                _log.info(line)
    except Exception:
        pass


if _claim_daemon_lock():
    _pigeon_daemon = _subprocess.Popen(
        [sys.executable, str(Path(__file__).parent / "core" / "pigeon_daemon.py")],
        stdout=_subprocess.PIPE,
        stderr=_subprocess.STDOUT,
        creationflags=_subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
    )
    _threading.Thread(
        target=_forward_daemon_output,
        args=(_pigeon_daemon.stdout, "pigeon_daemon"),
        daemon=True,
    ).start()

    _ocr_consumer_daemon = _subprocess.Popen(
        [sys.executable, str(Path(__file__).parent / "core" / "ocr_consumer_daemon.py")],
        stdout=_subprocess.PIPE,
        stderr=_subprocess.STDOUT,
        creationflags=_subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
    )
    _threading.Thread(
        target=_forward_daemon_output,
        args=(_ocr_consumer_daemon.stdout, "ocr_daemon"),
        daemon=True,
    ).start()
    logger.info("Daemons started (pigeon + ocr) — PID %d owns lock", _os.getpid())
else:
    logger.info("Daemon lock held by another worker — skipping spawn")

# Track server start time for uptime
SERVER_START_TIME = datetime.now()

# CORS for Vite dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # LAN + Neocities + tunnel all need access
    allow_methods=["*"],
    allow_headers=["*"],
)

USERNAME = local_api.DEFAULT_USER

# Mount API routes
app.include_router(kart_routes.router)  # Task orchestration
app.include_router(agent_routes.router)  # Conversational agents
app.include_router(safe_routes.router)   # SAFE OS — consent + knowledge query
app.include_router(social_routes.router)          # Social media queue + series + metrics
app.include_router(social_workflow_routes.router)  # Workflow: next → draft → publish
app.include_router(nasa_routes.router)             # NASA archive — scoped to nasa-archive/data/ only
app.include_router(roots_routes.router)            # Filesystem roots — configure + scan local dirs
app.include_router(utety_routes.router)    # UTETY chat + professors + sessions
app.include_router(vision_routes.router)   # Vision board image classification
app.include_router(dating_routes.router)   # Dating wellbeing red flag analysis
app.include_router(die_namic_routes.router) # Die-namic system state (read-only)
app.include_router(journal_routes.router)   # Journal sessions + events (Shiva's pipeline)
app.include_router(auth_routes.router)     # Local-first auth — login/verify/logout
app.include_router(apps_routes.router)    # SAFE app consent management
app.include_router(nest_routes.router)    # Nest review queue
# Governance endpoints already defined in server.py (lines 1023-1155)


# --- API Endpoints ---

@app.get("/api/health")
def health():
    """Fast health check — no Ollama ping, no DB queries."""
    return {"status": "ok"}


# ── Startup: configure thread pool ───────────────────────────────────────────
# NOTE: on_event("startup") removed — incompatible with Starlette 0.50.0.
# Thread pool is configured via uvicorn's lifespan instead (see __main__).


# ── Status cache ──────────────────────────────────────────────────────────────
import time as _time
_status_cache: dict = {"data": None, "ts": 0.0}
_STATUS_TTL = 5.0  # seconds
_status_lock: Optional[asyncio.Lock] = None


def _get_status_lock() -> asyncio.Lock:
    """Lazy-init lock (must be created inside the running event loop)."""
    global _status_lock
    if _status_lock is None:
        _status_lock = asyncio.Lock()
    return _status_lock


async def _check_ollama() -> dict:
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get("http://127.0.0.1:11434/api/tags")
            data = r.json()
            return {"running": True, "models": [m["name"] for m in data.get("models", [])]}
    except Exception:
        return {"running": False, "models": []}


async def _check_tunnel() -> dict:
    try:
        tunnel_file = Path(".tunnel_url")
        if not tunnel_file.is_file():
            return {"url": None, "reachable": False}
        tunnel_url = tunnel_file.read_text().strip()
        if not tunnel_url:
            return {"url": None, "reachable": False}
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.head(tunnel_url + "/api/health")
            return {"url": tunnel_url, "reachable": r.is_success}
    except Exception:
        return {"url": None, "reachable": False}


def _sync_status_checks() -> dict:
    """Blocking checks: filesystem, psutil, DB. Runs in thread executor."""
    governance = {"pending_commits": 0, "last_ratification": None}
    try:
        gov_dir = Path("governance/commits")
        if gov_dir.is_dir():
            pending = list(gov_dir.glob("*.pending"))
            governance["pending_commits"] = len(pending)
            all_files = [f for f in gov_dir.iterdir() if f.is_file() and not f.name.endswith(".pending")]
            if all_files:
                latest = max(all_files, key=lambda f: f.stat().st_mtime)
                governance["last_ratification"] = datetime.fromtimestamp(latest.stat().st_mtime).isoformat()
    except Exception:
        pass

    intake = {"dump": 0, "hold": 0, "process": 0, "route": 0, "clear": 0}
    try:
        intake_dir = Path("intake")
        for stage in intake:
            stage_path = intake_dir / stage
            if stage_path.is_dir():
                intake[stage] = len(list(stage_path.iterdir()))
    except Exception:
        pass

    engine = {"running": False}
    try:
        for proc in psutil.process_iter(['name']):
            if 'python' in proc.info['name'].lower():
                try:
                    if any('kart' in arg.lower() for arg in proc.cmdline()):
                        engine["running"] = True
                        break
                except (psutil.AccessDenied, psutil.NoSuchProcess):
                    pass
    except Exception:
        pass

    kart = {"available_tools": 0, "task_stats": {}, "trust_level": "UNKNOWN"}
    try:
        agent_info = agent_registry.get_agent("Sweet-Pea-Rudi19", "kart")
        if agent_info:
            kart["trust_level"] = agent_info.get("trust_level", "UNKNOWN")
        tools = tool_engine.list_tools("kart", "Sweet-Pea-Rudi19")
        kart["available_tools"] = len(tools)
        kart["task_stats"] = graft.get_stats("Sweet-Pea-Rudi19", "kart")
    except Exception:
        pass

    return {"governance": governance, "intake": intake, "engine": engine, "kart": kart}


@app.get("/api/system/status")
async def system_status():
    """Parallel system status with 5s result cache. Lock prevents thundering herd on cache miss."""
    now = _time.monotonic()
    if _status_cache["data"] and (now - _status_cache["ts"]) < _STATUS_TTL:
        return _status_cache["data"]

    async with _get_status_lock():
        # Re-check after acquiring — another waiter may have refreshed while we queued
        now = _time.monotonic()
        if _status_cache["data"] and (now - _status_cache["ts"]) < _STATUS_TTL:
            return _status_cache["data"]

        loop = asyncio.get_running_loop()
        ollama_result, tunnel_result, sync = await asyncio.gather(
            _check_ollama(),
            _check_tunnel(),
            loop.run_in_executor(None, _sync_status_checks),
            return_exceptions=True,
        )

        result = {
            "ollama":     ollama_result if isinstance(ollama_result, dict) else {"running": False, "models": []},
            "server":     {"uptime_seconds": int((_time.time() - SERVER_START_TIME.timestamp())), "port": 8420},
            "governance": sync["governance"] if isinstance(sync, dict) else {"pending_commits": 0, "last_ratification": None},
            "intake":     sync["intake"]     if isinstance(sync, dict) else {},
            "engine":     sync["engine"]     if isinstance(sync, dict) else {"running": False},
            "tunnel":     tunnel_result if isinstance(tunnel_result, dict) else {"url": None, "reachable": False},
            "kart":       sync["kart"]       if isinstance(sync, dict) else {"available_tools": 0, "task_stats": {}, "trust_level": "UNKNOWN"},
        }

        _status_cache["data"] = result
        _status_cache["ts"] = now
        return result


@app.get("/api/status")
def status():
    ollama_up = local_api.check_ollama()
    models = local_api.list_models() if ollama_up else []
    gemini = local_api.check_gemini_available()
    claude = local_api.check_claude_available()

    # Knowledge stats
    stats = {"atoms": 0, "conversations": 0, "entities": 0, "gaps": 0}
    try:
        from core.db import get_connection as _gc
        conn = _gc()
        cur = conn.cursor()
        for table, key in [("knowledge", "atoms"), ("conversation_memory", "conversations"),
                           ("entities", "entities"), ("knowledge_gaps", "gaps")]:
            try:
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                row = cur.fetchone()
                stats[key] = row[0] if row else 0
            except Exception:
                pass
        conn.close()
    except Exception:
        pass

    return {
        "ollama": ollama_up,
        "models": models,
        "gemini": gemini,
        "claude": claude,
        "knowledge": stats,
    }


@app.get("/api/personas")
def personas():
    result = {}
    for name, prompt in local_api.PERSONAS.items():
        result[name] = {
            "name": name,
            "folder": local_api.PERSONA_FOLDERS.get(name, name.lower()),
            "prompt_preview": prompt[:100] + "..." if len(prompt) > 100 else prompt,
        }
    return result


@app.post("/api/chat")
async def chat(request: Request):
    body = await request.json()
    prompt = body.get("prompt", "")
    persona = body.get("persona", "Willow")

    if not prompt:
        return {"error": "No prompt provided"}

    def generate():
        full_response = []
        for chunk in local_api.process_smart_stream(prompt, persona=persona, user=USERNAME):
            full_response.append(chunk)
            yield f"data: {chunk}\n\n"

        # Send coherence metrics as final SSE event
        try:
            coherence = local_api.log_conversation(
                persona=persona,
                user_input=prompt,
                assistant_response="".join(full_response),
                model="streamed",
                tier=0,
            )
            import json
            yield f"event: coherence\ndata: {json.dumps(coherence)}\n\n"
            on_coherence_update(coherence)
        except Exception:
            pass

        yield "event: done\ndata: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")



@app.post("/api/chat/multi")
async def chat_multi(request: Request):
    """
    Parallel multi-persona chat.

    Body: {"tasks": [{"persona": "Kart", "prompt": "..."}, ...]}

    Spawns threads for each persona, streams all responses tagged by persona.
    """
    body = await request.json()
    tasks = body.get("tasks", [])

    if not tasks:
        return {"error": "No tasks provided"}

    # Validate tasks
    for task in tasks:
        if "persona" not in task or "prompt" not in task:
            return {"error": "Each task must have 'persona' and 'prompt'"}

    def generate():
        # Queue for collecting chunks from all threads
        chunk_queue = queue.Queue()
        active_personas = set(task["persona"] for task in tasks)

        def worker(persona: str, prompt: str):
            """Worker thread that streams from one persona."""
            try:
                full_response = []
                for chunk in local_api.process_smart_stream(prompt, persona=persona, user=USERNAME):
                    full_response.append(chunk)
                    # Tag chunk with persona and put in queue
                    chunk_queue.put((persona, "chunk", chunk))

                # Log conversation for this persona
                try:
                    coherence = local_api.log_conversation(
                        persona=persona,
                        user_input=prompt,
                        assistant_response="".join(full_response),
                        model="streamed",
                        tier=0,
                    )
                    chunk_queue.put((persona, "coherence", coherence))
                except:
                    pass

                # Signal this persona is done
                chunk_queue.put((persona, "done", None))
            except Exception as e:
                chunk_queue.put((persona, "error", str(e)))

        # Start all threads
        with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
            futures = []
            for task in tasks:
                future = executor.submit(worker, task["persona"], task["prompt"])
                futures.append(future)

            # Stream events as they arrive
            while active_personas:
                try:
                    persona, event_type, data = chunk_queue.get(timeout=0.1)

                    if event_type == "chunk":
                        yield f"event: {persona}\ndata: {data}\n\n"

                    elif event_type == "coherence":
                        import json
                        yield f"event: coherence_{persona}\ndata: {json.dumps(data)}\n\n"

                    elif event_type == "done":
                        yield f"event: done_{persona}\ndata: [DONE]\n\n"
                        active_personas.discard(persona)

                    elif event_type == "error":
                        yield f"event: error_{persona}\ndata: {data}\n\n"
                        active_personas.discard(persona)

                except queue.Empty:
                    continue

            # All personas finished
            yield "event: complete\ndata: [COMPLETE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.get("/api/knowledge/search")
def knowledge_search(q: str = "", limit: int = 5):
    if not q:
        return {"results": [], "query": q}
    results = loam.search(USERNAME, q, max_results=limit)
    return {"results": results, "query": q}


@app.get("/api/knowledge/semantic-search")
def knowledge_semantic_search(q: str = "", limit: int = 5, username: str = USERNAME):
    if not q:
        return {"results": [], "query": q}
    results = loam.semantic_search(username, q, max_results=limit)
    return {"results": results, "query": q, "count": len(results)}


@app.get("/api/knowledge/gaps")
def knowledge_gaps(limit: int = 10):
    gaps = loam.get_top_gaps(USERNAME, limit=limit)
    return {"gaps": gaps}


@app.get("/api/knowledge/stats")
def knowledge_stats():
    from core.db import get_connection as _gc, is_postgres
    stats = {}
    try:
        if is_postgres():
            conn = _gc()
            for table in ["knowledge", "conversation_memory", "entities", "knowledge_gaps"]:
                try:
                    row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
                    stats[table] = row[0] if row else 0
                except Exception:
                    stats[table] = 0
            conn.close()
        else:
            import sqlite3
            db_path = loam._db_path(USERNAME)
            if Path(db_path).exists():
                conn = sqlite3.connect(db_path)
                cur = conn.cursor()
                for table in ["knowledge", "conversation_memory", "entities", "knowledge_gaps"]:
                    try:
                        cur.execute(f"SELECT COUNT(*) FROM {table}")
                        stats[table] = cur.fetchone()[0]
                    except Exception:
                        stats[table] = 0
                conn.close()
    except Exception:
        pass
    return stats


@app.get("/api/safe/whoami")
def safe_whoami():
    """Identity handshake — lets SAFE dashboard verify server connection and discover the default user."""
    return {
        "status": "ok",
        "username": USERNAME,
        "server": "willow",
        "version": "1.0"
    }


@app.get("/api/knowledge/entities")
def knowledge_entities_list(min_mentions: int = 1, username: str = USERNAME):
    """Return all known entities with source atom count — for user-facing 'What Willow Knows' dashboard."""
    from core.db import get_connection as _gc, is_postgres
    resolved = username or USERNAME
    try:
        if not is_postgres():
            db_path = loam._db_path(resolved)
            if not Path(db_path).exists():
                return {"entities": [], "username": resolved}
        conn = _gc() if is_postgres() else _gc(loam._db_path(resolved))
        cur = conn.cursor()
        cur.execute(
            "SELECT e.id, e.name, e.entity_type, e.mention_count, e.description, "
            "COUNT(ke.knowledge_id) AS source_count "
            "FROM entities e "
            "LEFT JOIN knowledge_entities ke ON e.id = ke.entity_id "
            "WHERE e.mention_count >= ? "
            "GROUP BY e.id "
            "ORDER BY e.entity_type, e.mention_count DESC",
            (min_mentions,)
        )
        rows = cur.fetchall()
        conn.close()
        return {"entities": [
            {"id": r[0], "name": r[1], "type": r[2], "mentions": r[3],
             "description": r[4] or "", "source_count": r[5]}
            for r in rows
        ], "username": resolved}
    except Exception as e:
        return {"entities": [], "error": str(e), "username": resolved}


@app.get("/api/knowledge/entities/{entity_id}/sources")
def knowledge_entity_sources(entity_id: int, username: str = USERNAME):
    """Return knowledge atoms that reference this entity — explains why Willow knows about them."""
    from core.db import get_connection as _gc, is_postgres
    resolved = username or USERNAME
    try:
        conn = _gc() if is_postgres() else _gc(loam._db_path(resolved))
        cur = conn.cursor()
        cur.execute(
            "SELECT k.id, k.title, k.source_type, k.source_id, k.summary, k.created_at "
            "FROM knowledge k "
            "JOIN knowledge_entities ke ON k.id = ke.knowledge_id "
            "WHERE ke.entity_id = ? "
            "ORDER BY k.created_at DESC LIMIT 10",
            (entity_id,)
        )
        rows = cur.fetchall()
        conn.close()
        return {"sources": [
            {"id": r[0], "title": r[1], "source_type": r[2],
             "source_id": r[3], "summary": r[4] or "", "created_at": r[5]}
            for r in rows
        ]}
    except Exception as e:
        return {"sources": [], "error": str(e)}


@app.delete("/api/knowledge/entities/{entity_id}")
def knowledge_entity_delete(entity_id: int, username: str = USERNAME):
    """Delete an entity and its edges. User-initiated correction — user is the authority on their own data."""
    from core.db import get_connection as _gc, is_postgres
    resolved = username or USERNAME
    try:
        conn = _gc() if is_postgres() else _gc(loam._db_path(resolved))
        cur = conn.cursor()
        cur.execute("DELETE FROM knowledge_edges WHERE source_id = ? OR target_id = ?", (entity_id, entity_id))
        edges_deleted = cur.rowcount
        cur.execute("DELETE FROM knowledge_entities WHERE entity_id = ?", (entity_id,))
        cur.execute("DELETE FROM entities WHERE id = ?", (entity_id,))
        entity_deleted = cur.rowcount
        conn.commit()
        conn.close()
        return {"success": bool(entity_deleted), "edges_deleted": edges_deleted}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.patch("/api/knowledge/entities/{entity_id}")
async def knowledge_entity_rename(entity_id: int, request: Request):
    """Rename or correct an entity. Creates an audit trail in the entity record."""
    body = await request.json()
    new_name = (body.get("name") or "").strip()
    new_description = body.get("description")
    username = body.get("username") or USERNAME
    if not new_name:
        raise HTTPException(status_code=400, detail="name required")

    def _do_rename():
        try:
            from core.db import get_connection as _gc, is_postgres
            conn = _gc() if is_postgres() else _gc(loam._db_path(username))
            cur = conn.cursor()
            if new_description is not None:
                cur.execute("UPDATE entities SET name = ?, description = ? WHERE id = ?",
                            (new_name, new_description, entity_id))
            else:
                cur.execute("UPDATE entities SET name = ? WHERE id = ?", (new_name, entity_id))
            updated = cur.rowcount
            conn.commit()
            conn.close()
            return {"success": bool(updated), "name": new_name}
        except Exception as e:
            return {"success": False, "error": str(e)}

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _do_rename)


@app.get("/api/knowledge/entities/verify-feed")
def knowledge_entities_verify_feed(limit: int = 100, skip_oral_history: bool = True):
    """Return unverified entities for Jeles to process (verified=FALSE or NULL).
    skip_oral_history=True (default) excludes oral_history_consented entities
    (private persons, file-path noise) that are correctly unverifiable."""
    from core.db import get_connection as _gc, is_postgres
    try:
        conn = _gc() if is_postgres() else _gc(loam._db_path(USERNAME))
        cur = conn.cursor()
        ph = "%s" if is_postgres() else "?"
        oral_filter = "AND (source_type IS NULL OR source_type != 'oral_history_consented') " if skip_oral_history else ""
        cur.execute(
            "SELECT id, name, entity_type, description, mention_count FROM entities "
            f"WHERE (verified = FALSE OR verified IS NULL) AND never_promote != 1 "
            f"{oral_filter}"
            f"ORDER BY mention_count DESC LIMIT {ph}",
            (limit,)
        )
        rows = cur.fetchall()
        conn.close()
        return {"entities": [
            {"id": r[0], "name": r[1], "type": r[2], "description": r[3] or "", "mentions": r[4]}
            for r in rows
        ], "count": len(rows)}
    except Exception as e:
        return {"entities": [], "error": str(e)}


@app.patch("/api/knowledge/entities/{entity_id}/verify")
async def knowledge_entity_verify(entity_id: int, request: Request):
    """Jeles writes verification results for an entity back to Willow."""
    import json as _json
    import datetime as _dt
    body = await request.json()
    verified = body.get("verified", False)
    confidence = body.get("confidence", "low")
    source_type = body.get("source_type", "oral_history_consented")
    sources = body.get("sources", [])
    corrections = body.get("corrections", [])
    if isinstance(sources, list):
        sources = _json.dumps(sources)
    if isinstance(corrections, list):
        corrections = _json.dumps(corrections)
    verified_at = _dt.datetime.utcnow().isoformat()

    def _do_verify():
        try:
            from core.db import get_connection as _gc, is_postgres
            conn = _gc() if is_postgres() else _gc(loam._db_path(USERNAME))
            cur = conn.cursor()
            cur.execute(
                "UPDATE entities SET verified=?, confidence=?, source_type=?, "
                "sources=?, corrections=?, verified_at=?, verified_by='jeles' WHERE id=?",
                (verified, confidence, source_type, sources, corrections, verified_at, entity_id)
            )
            updated = cur.rowcount
            conn.commit()
            conn.close()
            return {"success": bool(updated), "entity_id": entity_id,
                    "verified": verified, "confidence": confidence}
        except Exception as e:
            return {"success": False, "error": str(e)}

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _do_verify)


@app.get("/api/knowledge/graph")
def knowledge_graph(min_mentions: int = 1, max_nodes: int = 150, max_edges_per_node: int = 6, layout: str = "force"):
    from core.db import get_connection as _gc, is_postgres
    from collections import defaultdict
    TYPE_COLORS = {
        "person": "#4a90d9", "project": "#2d6a4f", "concept": "#9b59b6",
        "tool": "#d4860a", "location": "#c0392b", "event": "#8b4513",
    }
    logger.info("[knowledge-graph] Building: min_mentions=%d, max_nodes=%d", min_mentions, max_nodes)
    try:
        if not is_postgres():
            db_path = loam._db_path(USERNAME)
            if not Path(db_path).exists():
                return {"nodes": [], "edges": []}
        conn = _gc() if is_postgres() else _gc(loam._db_path(USERNAME))
        cur = conn.cursor()

        # Fix 3: exclude noise entities (file paths, extensions, directories)
        noise_filter = "name NOT LIKE '%.%' AND name NOT LIKE '%/'"

        # Standard filtered nodes
        cur.execute(
            f"SELECT id, name, entity_type, mention_count, description FROM entities "
            f"WHERE mention_count >= ? AND {noise_filter} "
            f"ORDER BY mention_count DESC LIMIT ?",
            (min_mentions, max_nodes)
        )
        entity_dict = {r[0]: r for r in cur.fetchall()}

        # Fix 2: always include the top person entity + all their direct neighbors
        cur.execute(
            f"SELECT id, name, entity_type, mention_count, description FROM entities "
            f"WHERE entity_type = 'person' AND {noise_filter} "
            f"ORDER BY mention_count DESC LIMIT 1"
        )
        user_row = cur.fetchone()
        user_id = None
        if user_row:
            user_id = user_row[0]
            entity_dict[user_id] = user_row
            # Add all neighbors of the user entity regardless of min_mentions
            cur.execute(
                f"SELECT DISTINCT e.id, e.name, e.entity_type, e.mention_count, e.description "
                f"FROM entities e "
                f"JOIN knowledge_edges ke ON "
                f"  (ke.source_id = ? AND ke.target_id = e.id) OR "
                f"  (ke.target_id = ? AND ke.source_id = e.id) "
                f"WHERE {noise_filter}",
                (user_id, user_id)
            )
            for r in cur.fetchall():
                entity_dict[r[0]] = r

        entity_ids = set(entity_dict.keys())

        if not entity_ids:
            conn.close()
            return {"nodes": [], "edges": [], "layout_available": False}

        id_placeholders = ",".join("?" * len(entity_ids))
        id_list = list(entity_ids)

        # Load cube coordinates from derived index (see CUBE_INDEX_SPEC.md)
        try:
            cur.execute(
                f"SELECT node_id, cx, cy, cz, domain_name, temporal_name "
                f"FROM cube_cells WHERE node_type='entity' AND node_id IN ({id_placeholders})",
                id_list
            )
            cube_lookup = {r[0]: {"cx": r[1], "cy": r[2], "cz": r[3],
                                  "cube_domain": r[4], "cube_temporal": r[5]}
                           for r in cur.fetchall()}
        except Exception:
            cube_lookup = {}

        _null_cube = {"cx": None, "cy": None, "cz": None,
                      "cube_domain": None, "cube_temporal": None}
        nodes = [{"id": r[0], "label": r[1], "type": r[2],
                  "size": max(8, min(40, r[3] * 4)), "mentions": r[3],
                  "description": r[4] or "",
                  "color": TYPE_COLORS.get(r[2], "#888888"),
                  **cube_lookup.get(r[0], _null_cube)} for r in entity_dict.values()]

        # knowledge_edges (semantic similarity)
        cur.execute(
            f"SELECT source_id, target_id, edge_type, weight, canonical FROM knowledge_edges "
            f"WHERE source_id IN ({id_placeholders}) AND target_id IN ({id_placeholders}) "
            f"ORDER BY weight DESC LIMIT 75000",
            id_list + id_list
        )
        raw_edges = list(cur.fetchall())

        # entity_connections (named relationships — pairs/triads/quints/septuplets)
        cur.execute(
            f"SELECT entity_a_id, entity_b_id, connection_type, weight, 0 FROM entity_connections "
            f"WHERE confirmed=1 "
            f"AND entity_a_id IN ({id_placeholders}) AND entity_b_id IN ({id_placeholders})",
            id_list + id_list
        )
        raw_edges.extend(cur.fetchall())

        # Deduplicate bidirectional edges
        all_edges, seen = [], set()
        for src, tgt, etype, weight, canonical in raw_edges:
            key = (min(src, tgt), max(src, tgt), etype)
            if key in seen:
                continue
            seen.add(key)
            all_edges.append((src, tgt, etype, float(weight), bool(canonical)))

        # Per-node edge cap — user entity is exempt
        node_edge_count = defaultdict(int)
        edges = []
        for src, tgt, etype, weight, canonical in all_edges:
            src_ok = (src == user_id) or (node_edge_count[src] < max_edges_per_node)
            tgt_ok = (tgt == user_id) or (node_edge_count[tgt] < max_edges_per_node)
            if src_ok and tgt_ok:
                if src != user_id:
                    node_edge_count[src] += 1
                if tgt != user_id:
                    node_edge_count[tgt] += 1
                edges.append({"from": src, "to": tgt, "type": etype,
                               "weight": weight, "canonical": canonical,
                               "width": max(1, min(5, int(weight * 3)))})

        layout_available = any(n.get("cx") is not None for n in nodes)
        logger.info("[knowledge-graph] Done: %d nodes, %d edges, cube=%s",
                    len(nodes), len(edges), layout_available)
        conn.close()
        return {"nodes": nodes, "edges": edges, "layout_available": layout_available}
    except Exception as e:
        logger.error("[knowledge-graph] Error: %s", e)
        return {"error": str(e), "nodes": [], "edges": []}


@app.get("/graph")
def serve_graph():
    return FileResponse("ui/graph.html")


@app.get("/api/coherence")
def coherence():
    report = get_coherence_report()
    needs_intervention, reason = check_intervention()
    return {**report, "needs_intervention": needs_intervention, "intervention_reason": reason}


# --- TTS Endpoints ---

@app.post("/api/tts/speak")
async def tts_speak(request: Request):
    """Convert text to speech. Returns audio/wav bytes."""
    try:
        from core import tts_router
        body = await request.json()
        text = body.get("text", "")
        voice = body.get("voice", "default")
        tier = body.get("tier", "local")
        if not text:
            return {"error": "text is required"}
        audio = tts_router.speak(text, voice, preferred_tier=tier)
        if audio:
            from fastapi.responses import Response as FastAPIResponse
            return FastAPIResponse(content=audio, media_type="audio/wav")
        return {"error": "No TTS providers available"}
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/tts/voices")
def tts_voices(provider: str = ""):
    """List available TTS voices."""
    try:
        from core import tts_router
        if provider:
            return {"provider": provider, "voices": tts_router.get_voices(provider)}
        avail = tts_router.get_available_providers()
        all_voices = {}
        for tier, providers in avail.items():
            for p in providers:
                all_voices[p.name] = tts_router.get_voices(p.name)
        return {"voices": all_voices}
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/tts/providers")
def tts_providers():
    """List available TTS providers by tier."""
    try:
        from core import tts_router
        avail = tts_router.get_available_providers()
        return {tier: [p.name for p in providers] for tier, providers in avail.items()}
    except Exception as e:
        return {"error": str(e)}


# --- Skills Endpoints ---

@app.get("/api/skills/status")
def skills_status():
    """System health check."""
    import subprocess, requests as req
    try:
        daemons = {}
        _is_win = sys.platform == "win32"
        for name in ["WILLOW-GovernanceMonitor", "WILLOW-CoherenceScanner",
                     "WILLOW-TopologyBuilder", "WILLOW-KnowledgeCompactor",
                     "WILLOW-SAFESync", "WILLOW-PersonaScheduler", "WILLOW-InboxWatcher"]:
            if _is_win:
                result = subprocess.run(["tasklist", "/FI", f"WINDOWTITLE eq {name}"],
                                        capture_output=True, text=True, timeout=3)
                daemons[name] = "python.exe" in result.stdout
            else:
                result = subprocess.run(["pgrep", "-f", name],
                                        capture_output=True, text=True, timeout=3)
                daemons[name] = result.returncode == 0
        return {
            "server": True,
            "daemons": daemons,
            "ollama": _check_service("http://localhost:11434/api/tags")
        }
    except Exception as e:
        return {"error": str(e)}


def _check_service(url: str) -> bool:
    try:
        import requests as req
        return req.get(url, timeout=2).status_code == 200
    except:
        return False


@app.get("/api/skills/query")
def skills_query(q: str, limit: int = 10):
    """Query knowledge base."""
    results = loam.search(USERNAME, q, limit)
    return {"query": q, "results": results, "count": len(results)}


@app.post("/api/skills/route")
async def skills_route(request: Request):
    """Route a file with content extraction."""
    try:
        from core import extraction
        body = await request.json()
        file_path = body.get("file")
        if not file_path or not Path(file_path).exists():
            return {"error": "file not found"}
        result = extraction.extract_content(file_path)
        analysis = {}
        if result["success"] and result["text"]:
            analysis = extraction.analyze_content_for_routing(
                result["text"], Path(file_path).name, Path(file_path).suffix)
        return {"file": file_path, "extraction": result, "routing": analysis}
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/skills/journal")
async def skills_journal(request: Request):
    """Add journal entry."""
    try:
        body = await request.json()
        content = body.get("content", "")
        category = body.get("category", "note")
        if not content:
            return {"error": "content is required"}
        journal_path = Path(__file__).parent / "data" / f"{USERNAME}_journal.md"
        journal_path.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(journal_path, "a", encoding="utf-8") as f:
            f.write(f"\n## {ts} — {category}\n\n{content}\n")
        return {"success": True, "timestamp": ts, "category": category}
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/skills/persona")
async def skills_persona(request: Request):
    """Invoke a persona."""
    try:
        from core import llm_router
        body = await request.json()
        persona = body.get("persona", "PA")
        prompt = body.get("prompt", "")
        personas = {
            "PA": "You are PA (Personal Assistant), helpful and proactive.",
            "Analyst": "You are Analyst, data-driven. Find patterns and insights.",
            "Archivist": "You are Archivist, organizing and preserving loam.",
            "Poet": "You are Poet, a creative writing agent.",
            "Debugger": "You are Debugger, finding and fixing bugs."
        }
        if persona not in personas:
            return {"error": f"Unknown persona. Available: {list(personas.keys())}"}
        full_prompt = f"{personas[persona]}\n\nUser: {prompt}"
        response = llm_router.ask(full_prompt, preferred_tier="free")
        if response:
            return {"persona": persona, "response": response.content, "provider": response.provider}
        return {"error": "No LLM response"}
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/ingest")
async def ingest(file: UploadFile = File(...)):
    """Ingest a dropped file into the knowledge DB (text, images, audio, video, code, etc.)."""
    # Document extensions
    text_ext = {".txt", ".md", ".pdf", ".docx", ".doc", ".rtf", ".odt", ".pages"}

    # Image extensions - route to screenshot processor
    image_ext = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp", ".svg", ".heic", ".gif"}

    # Code extensions - treat as text
    code_ext = {
        ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".cpp", ".c", ".h", ".cs", ".php",
        ".rb", ".go", ".rs", ".swift", ".kt", ".sh", ".bash", ".ps1",
        ".json", ".csv", ".xml", ".yaml", ".yml", ".html", ".htm"
    }

    # Audio/video - extract metadata
    audio_ext = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".wma"}
    video_ext = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".wmv"}

    # Archives - store reference
    archive_ext = {".zip", ".tar", ".gz", ".7z", ".rar"}

    # Google Workspace (will need Drive API in future)
    gdocs_ext = {".gdoc", ".gsheet", ".gslides", ".gdraw"}

    suffix = Path(file.filename).suffix.lower()

    # Route images to screenshot processing (with OCR + learning)
    if suffix in image_ext:
        return await upload_screenshot(file)

    # Read file content
    content_bytes = await file.read()
    file_hash = hashlib.md5(content_bytes).hexdigest()

    # Handle text/code files
    if suffix in (text_ext | code_ext) or not suffix:  # No extension = try as text
        try:
            text = content_bytes.decode("utf-8", errors="ignore")
        except:
            return {"error": f"Could not decode {file.filename} as text"}

        if len(text) < 10:
            return {"error": "File too small or empty"}

        # Truncate for ingestion (same as unified_watcher)
        text_for_ingest = text[:4000]

        # Determine category
        category = "code" if suffix in code_ext else "ui_drop"

        loam.ingest_file_knowledge(
            username=USERNAME,
            filename=file.filename,
            file_hash=file_hash,
            category=category,
            content_text=text_for_ingest,
            provider="willow_ui",
        )

        asyncio.create_task(_ecosystem_refresh())
        return {
            "status": "ingested",
            "filename": file.filename,
            "hash": file_hash,
            "chars": len(text_for_ingest),
            "type": "text/code"
        }

    # Handle audio/video files - extract basic metadata
    if suffix in (audio_ext | video_ext):
        metadata = {
            "filename": file.filename,
            "size_bytes": len(content_bytes),
            "hash": file_hash,
            "type": "audio" if suffix in audio_ext else "video"
        }

        # Store reference in knowledge DB
        loam.ingest_file_knowledge(
            username=USERNAME,
            filename=file.filename,
            file_hash=file_hash,
            category="media",
            content_text=f"{metadata['type'].title()} file: {file.filename} ({metadata['size_bytes']} bytes)",
            provider="willow_ui",
        )

        return {
            "status": "indexed",
            "filename": file.filename,
            "hash": file_hash,
            "type": metadata["type"],
            "message": f"{metadata['type'].title()} file indexed. Full transcription/analysis coming soon."
        }

    # Handle archives - store reference
    if suffix in archive_ext:
        loam.ingest_file_knowledge(
            username=USERNAME,
            filename=file.filename,
            file_hash=file_hash,
            category="archive",
            content_text=f"Archive file: {file.filename} ({len(content_bytes)} bytes)",
            provider="willow_ui",
        )

        return {
            "status": "indexed",
            "filename": file.filename,
            "hash": file_hash,
            "type": "archive",
            "message": "Archive indexed. Content extraction coming soon."
        }

    # Handle Google Docs (placeholder)
    if suffix in gdocs_ext:
        return {
            "error": "Google Docs files require Drive API integration",
            "message": "Please share the file directly or export as PDF/text"
        }

    # Unknown file type - still try to index it
    loam.ingest_file_knowledge(
        username=USERNAME,
        filename=file.filename,
        file_hash=file_hash,
        category="unknown",
        content_text=f"File: {file.filename} ({len(content_bytes)} bytes, type: {suffix or 'no extension'})",
        provider="willow_ui",
    )

    return {
        "status": "indexed",
        "filename": file.filename,
        "hash": file_hash,
        "type": "unknown",
        "message": f"File indexed as binary/unknown type. Extension: {suffix or 'none'}"
    }


@app.post("/api/knowledge/ingest")
async def knowledge_ingest_json(request: Request):
    """Ingest knowledge directly from JSON (no file upload needed).
    Returns 202 immediately — ingestion runs in background (fleet calls take 30-60s).
    Body: {username, filename, content_text, category, provider, file_hash (optional)}
    Used by: session-extract hook, agents, external tools."""
    try:
        body = await request.json()
        username   = body.get("username", USERNAME)
        filename   = body.get("filename", "unknown")
        content    = body.get("content_text", "")
        category   = body.get("category", "reference")
        provider   = body.get("provider", "api")
        file_hash  = body.get("file_hash", "") or hashlib.md5(content.encode()).hexdigest()
        if not content:
            raise HTTPException(status_code=400, detail="content_text required")

        async def _do_ingest():
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, lambda: loam.ingest_file_knowledge(
                    username=username,
                    filename=filename,
                    file_hash=file_hash,
                    category=category,
                    content_text=content[:4000],
                    provider=provider,
                ))
                await _ecosystem_refresh()
            except Exception:
                pass

        asyncio.create_task(_do_ingest())
        return {"status": "accepted", "filename": filename, "category": category}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/upload/screenshot")
async def upload_screenshot(file: UploadFile = File(...)):
    """
    Upload a screenshot - runs OCR, extracts to knowledge DB, routes via smart routing, learns patterns.

    This is the complete pipeline: Upload → OCR → Extract → Route → Learn
    """
    try:
        # Validate file type
        suffix = Path(file.filename).suffix.lower()
        if suffix not in {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"}:
            return {"error": f"Unsupported image type: {suffix}. Use .jpg, .png, etc."}

        # Save to temp location
        temp_dir = Path("temp")
        temp_dir.mkdir(exist_ok=True)
        temp_path = temp_dir / file.filename

        content_bytes = await file.read()
        temp_path.write_bytes(content_bytes)

        # Run OCR to extract text
        ocr_text = None
        try:
            from apps.pa import drive_organize
            ocr_text = drive_organize._ocr_image(temp_path)
            # log.info(f"OCR extracted {len(ocr_text)} chars from {file.filename}")
        except Exception as e:
            # log.warning(f"OCR failed for {file.filename}: {e}")
            ocr_text = ""

        # Route via smart_routing (does OCR extraction + pattern learning)
        routing_result = None
        try:
            from apps import smart_routing
            routing_result = smart_routing.route_screenshot(
                filename=file.filename,
                filepath=str(temp_path),
                ocr_text=ocr_text,
                source_user=USERNAME
            )
            # log.info(f"Routed {file.filename} to: {routing_result.get('routed_to', [])}")
        except Exception as e:
            # log.warning(f"Smart routing failed for {file.filename}: {e}")
            # Fallback: just ingest to knowledge DB
            try:
                from apps.pa import drive_organize
                entry = {"source": str(temp_path), "category": "screenshot", "ingestable": True}
                drive_organize._ingest_text(temp_path, entry, USERNAME)
            except Exception as ingest_error:
                # log.error(f"Fallback ingest failed: {ingest_error}")
                pass

        # Clean up temp file
        try:
            temp_path.unlink()
        except:
            pass

        return {
            "status": "processed",
            "filename": file.filename,
            "ocr_chars": len(ocr_text) if ocr_text else 0,
            "routed_to": routing_result.get("routed_to", []) if routing_result else ["fallback"],
            "classification": routing_result.get("classification", {}) if routing_result else {},
            "message": "Screenshot uploaded, OCR extracted, routed, and learned ✓"
        }

    # Generated by: Cerebras (llm_router)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


# --- Routing Schema Endpoints ---

@app.get("/api/routing/schema")
def routing_schema():
    """Return canonical folders, aliases, and proposed folders."""
    import json
    schema_path = os.path.join(os.path.dirname(__file__), "data", "routing_folders.json")
    try:
        with open(schema_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/routing/promote")
def routing_promote(folder: str):
    """Promote a proposed folder to canonical."""
    import json
    schema_path = os.path.join(os.path.dirname(__file__), "data", "routing_folders.json")
    try:
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = json.load(f)
        if folder in schema.get("proposed", {}):
            schema["canonical"].append(folder)
            schema["canonical"] = sorted(set(schema["canonical"]))
            del schema["proposed"][folder]
            with open(schema_path, "w", encoding="utf-8") as f:
                json.dump(schema, f, indent=2)
            return {"promoted": folder, "canonical": schema["canonical"]}
        return {"error": f"'{folder}' not in proposed"}
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/routing/reject")
def routing_reject(folder: str):
    """Reject a proposed folder — route its contents to archive."""
    import json
    schema_path = os.path.join(os.path.dirname(__file__), "data", "routing_folders.json")
    try:
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = json.load(f)
        if folder in schema.get("proposed", {}):
            del schema["proposed"][folder]
            with open(schema_path, "w", encoding="utf-8") as f:
                json.dump(schema, f, indent=2)
            # Move files from _proposed/{folder} to archive
            proposed_path = os.path.join("artifacts", USERNAME, "_proposed", folder)
            archive_path = os.path.join("artifacts", USERNAME, "archive")
            if os.path.isdir(proposed_path):
                import shutil
                os.makedirs(archive_path, exist_ok=True)
                for f in os.listdir(proposed_path):
                    shutil.move(os.path.join(proposed_path, f), os.path.join(archive_path, f))
                os.rmdir(proposed_path)
            return {"rejected": folder}
        return {"error": f"'{folder}' not in proposed"}
    except Exception as e:
        return {"error": str(e)}


# --- File Browser Endpoints ---

@app.get("/api/files/folders")
def files_folders():
    """List canonical folders with file counts."""
    base = os.path.join("artifacts", USERNAME)
    schema_path = os.path.join(os.path.dirname(__file__), "data", "routing_folders.json")
    try:
        import json
        with open(schema_path) as f:
            schema = json.load(f)
        folders = []
        for name in sorted(schema["canonical"]) + ["_proposed", "pending"]:
            path = os.path.join(base, name)
            count = 0
            if os.path.isdir(path):
                count = sum(1 for f in os.listdir(path) if os.path.isfile(os.path.join(path, f)))
            folders.append({"name": name, "count": count, "path": path})
        # Also include _proposed subfolders
        proposed_path = os.path.join(base, "_proposed")
        if os.path.isdir(proposed_path):
            for sub in sorted(os.listdir(proposed_path)):
                sub_path = os.path.join(proposed_path, sub)
                if os.path.isdir(sub_path):
                    count = sum(1 for f in os.listdir(sub_path) if os.path.isfile(os.path.join(sub_path, f)))
                    folders.append({"name": f"_proposed/{sub}", "count": count, "path": sub_path})
        return {"folders": folders, "proposed": schema.get("proposed", {})}
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/files/list")
def files_list(folder: str = "pending", page: int = 1, per_page: int = 50):
    """List files in a folder with metadata."""
    base = os.path.join("artifacts", USERNAME)
    path = os.path.join(base, folder)
    if not os.path.isdir(path):
        return {"files": [], "total": 0, "folder": folder}
    try:
        all_files = sorted([f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))])
        total = len(all_files)
        start = (page - 1) * per_page
        page_files = all_files[start:start + per_page]
        files = []
        for name in page_files:
            fp = os.path.join(path, name)
            stat = os.stat(fp)
            files.append({
                "name": name,
                "folder": folder,
                "size": stat.st_size,
                "size_human": _human_size(stat.st_size),
                "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                "ext": os.path.splitext(name)[1].lower(),
            })
        return {"files": files, "total": total, "page": page, "per_page": per_page, "folder": folder}
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/files/preview")
def files_preview(file: str, folder: str):
    """Return file preview: image as base64, text as snippet, binary as metadata."""
    base = os.path.join("artifacts", USERNAME)
    path = os.path.join(base, folder, file)
    if not os.path.isfile(path):
        return {"error": "Not found"}
    try:
        ext = os.path.splitext(file)[1].lower()
        size = os.path.getsize(path)
        IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
        TEXT_EXTS = {".txt", ".md", ".py", ".js", ".ts", ".jsx", ".tsx",
                     ".json", ".csv", ".html", ".css", ".sh", ".bat", ".yaml", ".toml"}
        if ext in IMAGE_EXTS:
            import base64
            with open(path, "rb") as f:
                data = base64.b64encode(f.read()).decode()
            mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                    "gif": "image/gif", "webp": "image/webp"}.get(ext.lstrip("."), "image/jpeg")
            return {"type": "image", "data": data, "mime": mime, "size": size, "name": file}
        elif ext in TEXT_EXTS:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read(3000)
            return {"type": "text", "content": content, "size": size, "name": file,
                    "truncated": os.path.getsize(path) > 3000}
        elif ext == ".pdf":
            try:
                import pdfplumber
                with pdfplumber.open(path) as pdf:
                    pages = len(pdf.pages)
                    text = pdf.pages[0].extract_text() or "" if pages > 0 else ""
                return {"type": "text", "content": f"[PDF: {pages} pages]\n\n{text[:2000]}", "size": size, "name": file}
            except Exception:
                return {"type": "binary", "size": size, "name": file, "ext": ext}
        else:
            return {"type": "binary", "size": size, "name": file, "ext": ext}
    except Exception as e:
        return {"error": str(e)}


def _human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


@app.post("/api/files/move")
def files_move(filename: str, from_folder: str, to_folder: str):
    """Move a file between folders."""
    base = os.path.join("artifacts", USERNAME)
    src = os.path.join(base, from_folder, filename)
    dest_dir = os.path.join(base, to_folder)
    dest = os.path.join(dest_dir, filename)
    if not os.path.isfile(src):
        return {"error": f"File not found: {src}"}
    try:
        os.makedirs(dest_dir, exist_ok=True)
        if os.path.exists(dest):
            name, ext = os.path.splitext(filename)
            dest = os.path.join(dest_dir, f"{name}_moved{ext}")
        shutil.move(src, dest)
        # Log as knowledge feedback
        # log.info(f"FILE MOVE: {filename} {from_folder} -> {to_folder} (manual)")
        return {"moved": filename, "from": from_folder, "to": to_folder}
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/files/tag")
def files_tag(filename: str, folder: str, ring: str = None, category: str = None,
              tags: str = None, feedback_correct: bool = None, corrected_folder: str = None):
    """Tag a file and optionally provide routing feedback for learning."""
    try:
        # Store annotation
        from core import file_annotations
        note = f"Manual tag: ring={ring}, category={category}, tags={tags}"
        if feedback_correct is False and corrected_folder:
            note += f" | CORRECTION: should be {corrected_folder}"
        file_annotations.add_annotation(
            routing_id=f"{folder}/{filename}",
            filename=filename,
            routed_to=[folder],
            is_correct=feedback_correct,
            corrected_destination=corrected_folder,
            notes=note
        )
        # If ring override specified, update knowledge DB
        if ring and ring in ("source", "bridge", "continuity"):
            import hashlib
            fhash = hashlib.md5(f"{folder}/{filename}".encode()).hexdigest()
            conn = loam._connect(USERNAME)
            conn.execute("UPDATE knowledge SET ring=?, ring_override=? WHERE source_id=?",
                        (ring, ring, fhash))
            conn.commit()
            conn.close()
        # log.info(f"FILE TAG: {folder}/{filename} ring={ring} cat={category} correct={feedback_correct}")
        return {"tagged": filename, "folder": folder}
    except Exception as e:
        return {"error": str(e)}

# Generated by: Free Fleet Pattern (manual due to truncation issues)

# Schema helper functions (Generated using free fleet pattern)
def _load_routing_schema():
    """Load routing schema from routing_folders.json"""
    import json
    import os
    schema_path = os.path.join(os.path.dirname(__file__), "data", "routing_folders.json")
    try:
        with open(schema_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {"canonical": [], "aliases": {}, "proposed": {}}

def _save_routing_schema(schema):
    """Save routing schema to routing_folders.json"""
    import json
    import os
    schema_path = os.path.join(os.path.dirname(__file__), "data", "routing_folders.json")
    with open(schema_path, 'w', encoding='utf-8') as f:
        json.dump(schema, f, indent=2)

# Helper functions
def _find_similar_canonical(proposed_name, canonical_list):
    """Find canonical folders with similar names using fuzzy matching."""
    import difflib
    matches = difflib.get_close_matches(proposed_name, canonical_list, n=2, cutoff=0.6)
    return matches


def _migrate_proposed_folder(username, folder_name):
    """Move files from artifacts/{user}/_proposed/{folder} to artifacts/{user}/{folder}."""
    import os
    import shutil
    base = os.path.join("artifacts", username)
    src_dir = os.path.join(base, "_proposed", folder_name)
    dest_dir = os.path.join(base, folder_name)

    if not os.path.isdir(src_dir):
        return 0

    os.makedirs(dest_dir, exist_ok=True)

    moved_count = 0
    for file_name in os.listdir(src_dir):
        src = os.path.join(src_dir, file_name)
        dest = os.path.join(dest_dir, file_name)
        if os.path.isfile(src):
            if os.path.exists(dest):
                name, ext = os.path.splitext(file_name)
                counter = 1
                while os.path.exists(dest):
                    dest = os.path.join(dest_dir, f"{name}_moved{counter}{ext}")
                    counter += 1
            shutil.move(src, dest)
            moved_count += 1

    try:
        os.rmdir(src_dir)
    except:
        pass

    return moved_count


# API Endpoints
@app.get("/api/routing/proposed")
def routing_proposed_list():
    """List all proposed folders with metadata and smart suggestions."""
    schema = _load_routing_schema()
    proposed = schema.get("proposed", {})

    results = []
    for name, info in sorted(proposed.items(), key=lambda x: x[1].get("count", 0), reverse=True):
        similar = _find_similar_canonical(name, schema["canonical"])
        suggestion = "promote" if not similar else f"merge_into_{similar[0]}"

        results.append({
            "name": name,
            "count": info.get("count", 0),
            "first_seen": info.get("first_seen", "unknown"),
            "examples": info.get("examples", [])[:3],
            "similar_canonical": similar[:2],
            "suggestion": suggestion
        })

    return {"proposed": results, "total": len(results)}


@app.post("/api/routing/batch_promote")
async def routing_batch_promote(request: Request):
    """Promote multiple folders to canonical."""
    body = await request.json()
    folders = body.get("folders", [])

    schema = _load_routing_schema()
    promoted = []
    failed = []

    for folder in folders:
        if folder in schema.get("proposed", {}):
            if folder not in schema["canonical"]:
                schema["canonical"].append(folder)
            del schema["proposed"][folder]
            promoted.append(folder)
        else:
            failed.append({"folder": folder, "reason": "Not in proposed"})

    schema["canonical"] = sorted(set(schema["canonical"]))
    _save_routing_schema(schema)

    for folder in promoted:
        _migrate_proposed_folder(USERNAME, folder)

    return {"success": True, "promoted": promoted, "failed": failed}


@app.post("/api/routing/merge")
async def routing_merge(request: Request):
    """Merge proposed folder into canonical."""
    body = await request.json()
    proposed_folder = body.get("proposed")
    into_folder = body.get("into")

    if not proposed_folder or not into_folder:
        return {"error": "Missing proposed or into parameter"}

    schema = _load_routing_schema()

    if proposed_folder not in schema.get("proposed", {}):
        return {"error": f"Proposed folder not found"}

    if into_folder not in schema.get("canonical", []):
        return {"error": f"Canonical folder not found"}

    base = os.path.join("artifacts", USERNAME)
    src_dir = os.path.join(base, "_proposed", proposed_folder)
    dest_dir = os.path.join(base, into_folder)

    moved_count = 0
    if os.path.isdir(src_dir):
        os.makedirs(dest_dir, exist_ok=True)
        for file_name in os.listdir(src_dir):
            src = os.path.join(src_dir, file_name)
            dest = os.path.join(dest_dir, file_name)
            if os.path.isfile(src):
                if os.path.exists(dest):
                    name, ext = os.path.splitext(file_name)
                    dest = os.path.join(dest_dir, f"{name}_merged{ext}")
                shutil.move(src, dest)
                moved_count += 1
        try:
            os.rmdir(src_dir)
        except:
            pass

    del schema["proposed"][proposed_folder]
    _save_routing_schema(schema)

    return {"success": True, "moved_files": moved_count, "from": f"_proposed/{proposed_folder}", "to": into_folder}

# --- Topology Endpoints ---

@app.get("/api/topology/rings")
def topology_rings():
    """Atom counts by ring."""
    return topology.get_ring_distribution(USERNAME)


@app.get("/api/topology/zoom/{node_id}")
def topology_zoom(node_id: int, depth: int = 1):
    """Traverse from an atom. ?depth=2 for recursive."""
    depth = min(depth, 3)  # Cap recursion
    return topology.zoom(USERNAME, node_id, depth)


@app.get("/api/topology/continuity")
def topology_continuity():
    """Strip continuity check — find gaps in the Möbius strip."""
    return topology.check_strip_continuity(USERNAME)


@app.get("/api/topology/flow")
def topology_flow():
    """Sankey-style ring flow graph."""
    return topology.get_ring_flow_graph(USERNAME)


@app.post("/api/topology/build_edges")
def topology_build_edges(batch_size: int = 50):
    """Compute edges between atoms. Incremental."""
    created = topology.build_edges(USERNAME, batch_size=batch_size)
    if created:
        on_topology_update(edges_created=created)
    return {"edges_created": created}


@app.post("/api/topology/cluster")
def topology_cluster(n_clusters: int = 10):
    """Cluster atoms via KMeans over embeddings."""
    cluster_ids = topology.cluster_atoms(USERNAME, n_clusters=n_clusters)
    if cluster_ids:
        on_topology_update(clusters_created=len(cluster_ids))
    return {"clusters_created": len(cluster_ids), "cluster_ids": cluster_ids}


# --- Agent Registry Endpoints ---

@app.post("/api/agents/init")
def agents_init():
    """Initialize agent tables and register all default personas."""
    results = agent_registry.register_default_agents(USERNAME)
    return {"registered": results}


@app.get("/api/agents")
def agents_list():
    """List all registered agents."""
    return {"agents": agent_registry.list_agents(USERNAME)}


@app.post("/api/agents/register")
def agents_register(name: str, display_name: str = "", trust_level: str = "WORKER",
                    agent_type: str = "llm", purpose: str = ""):
    """Register a new agent/user."""
    is_new = agent_registry.register_agent(USERNAME, name, display_name or name,
                                           trust_level, agent_type, purpose)
    agent = agent_registry.get_agent(USERNAME, name)
    return {"registered": is_new, "agent": agent}


@app.get("/api/agents/{name}")
def agents_get(name: str):
    """Get agent profile."""
    agent = agent_registry.get_agent(USERNAME, name)
    if not agent:
        return {"error": f"Agent '{name}' not found"}
    agent_registry.update_last_seen(USERNAME, name)
    return agent


@app.post("/api/agents/{name}/message")
def agents_send_message(name: str, from_agent: str, subject: str = "", body: str = "", thread_id: str = ""):
    """Send a message to an agent."""
    msg_id = agent_registry.send_message(USERNAME, from_agent, name, subject, body, thread_id or None)
    return {"message_id": msg_id}


@app.get("/api/agents/{name}/mailbox")
def agents_mailbox(name: str, unread_only: bool = False):
    """Get messages for an agent."""
    messages = agent_registry.get_mailbox(USERNAME, name, unread_only)
    return {"agent": name, "messages": messages, "count": len(messages)}


@app.post("/api/agents/{name}/mailbox")
async def agents_mailbox_send(name: str, request: Request):
    """Send a message to an agent's mailbox."""
    body = await request.json()
    from_agent = body.get("from_agent", "")
    subject = body.get("subject", "")
    message_body = body.get("body", "")
    thread_id = body.get("thread_id")
    if not from_agent or not subject or not message_body:
        raise HTTPException(status_code=400, detail="missing from_agent, subject, or body")
    agent_registry.send_message(USERNAME, from_agent, name, subject, message_body, thread_id)
    return {"ok": True, "to": name, "from": from_agent}


@app.post("/api/agents/messages/{message_id}/read")
def agents_mark_read(message_id: int):
    """Mark a message as read."""
    agent_registry.mark_read(USERNAME, message_id)
    return {"marked_read": message_id}


# --- PA (Personal Assistant) Endpoints ---

DRIVE_ROOT = str(Path.home() / "My Drive")
_pa_catalog = []  # Module-level state for scan results
_pa_plan = {}     # Module-level state for current plan
_pa_near_dupes = []  # Near-duplicate pairs


@app.post("/api/pa/scan")
async def pa_scan():
    """Scan the entire Drive, classify everything, detect duplicates."""
    global _pa_catalog, _pa_plan, _pa_near_dupes
    if not Path(DRIVE_ROOT).exists():
        return {"error": f"Drive not mounted at {DRIVE_ROOT}"}

    _pa_catalog = drive_scan.scan(DRIVE_ROOT)
    drive_scan.find_duplicates(_pa_catalog, DRIVE_ROOT)
    _pa_near_dupes = drive_scan.find_near_duplicates(_pa_catalog, DRIVE_ROOT)
    _pa_plan = drive_organize.generate_plan(_pa_catalog)
    summary = drive_scan.catalog_summary(_pa_catalog)
    summary["near_duplicate_pairs"] = len(_pa_near_dupes)
    on_scan_complete(summary)
    return {"status": "scanned", "summary": summary}


@app.get("/api/pa/plan")
def pa_plan():
    """Get the current move plan."""
    if not _pa_plan:
        return {"error": "No scan performed yet. POST /api/pa/scan first."}
    return {
        "summary": _pa_plan.get("summary", {}),
        "folders_to_create": _pa_plan.get("folders_to_create", []),
        "review": drive_organize.review(_pa_plan),
        "move_count": len(_pa_plan.get("moves", [])),
        "delete_count": len(_pa_plan.get("deletes", [])),
    }


@app.post("/api/pa/execute")
async def pa_execute(request: Request):
    """Execute approved moves. Body: {scope: "organize"|"dedupe"|"cleanup"}"""
    if not _pa_plan:
        return {"error": "No plan generated. POST /api/pa/scan first."}

    body = await request.json()
    scope = body.get("scope", "organize")

    if scope == "organize":
        result = drive_organize.execute_moves(_pa_plan, DRIVE_ROOT, USERNAME)
    elif scope == "dedupe":
        result = drive_organize.execute_deletes(_pa_plan, DRIVE_ROOT, scope="dedupe")
    elif scope == "cleanup":
        result = drive_organize.execute_deletes(_pa_plan, DRIVE_ROOT, scope="cleanup")
        # Also remove empty dirs
        removed = drive_organize.cleanup_empty_dirs(DRIVE_ROOT)
        result["empty_dirs_removed"] = removed
    else:
        return {"error": f"Unknown scope: {scope}. Use organize|dedupe|cleanup"}

    on_organize_complete(result)
    return {"status": "executed", "scope": scope, "result": result}


@app.get("/api/pa/status")
def pa_status():
    """Get current PA progress."""
    return drive_organize.get_progress()


@app.post("/api/pa/correct")
async def pa_correct(request: Request):
    """
    Correct a misrouted file or mis-transcribed content.
    Body: {
        path: "current/relative/path.md",        (required)
        destination: "Creative/",                 (optional — move here)
        text: "corrected transcription content",  (optional — re-ingest)
        category: "creative"                      (optional — new category)
    }
    """
    body = await request.json()
    path = body.get("path")
    if not path:
        return {"error": "path is required"}
    result = drive_organize.correct_file(
        drive_root=DRIVE_ROOT,
        current_path=path,
        new_destination=body.get("destination"),
        corrected_text=body.get("text"),
        new_category=body.get("category"),
        username=USERNAME,
    )
    return {"status": "corrected", "result": result}


# --- Neocities Deploy ---

@app.post("/api/neocities/deploy")
def neocities_deploy():
    """Push pocket Willow to seancampbell.neocities.org."""
    try:
        from apps.neocities import deploy_pocket_willow
        result = deploy_pocket_willow()
        return {"status": "deployed", "result": result}
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/neocities/info")
def neocities_info():
    """Get Neocities site info."""
    try:
        from apps.neocities import info
        return info()
    except Exception as e:
        return {"error": str(e)}


# --- Governance (Dual Commit) ---

GOV_COMMITS_DIR = Path("governance/commits")
GOV_COMMITS_DIR.mkdir(parents=True, exist_ok=True)


@app.get("/api/governance/pending")
def governance_pending():
    """List all pending governance commits awaiting ratification."""
    try:
        pending = []
        for f in GOV_COMMITS_DIR.glob("*.pending"):
            stat = f.stat()
            pending.append({
                "id": f.stem,
                "filename": f.name,
                "timestamp": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "size": stat.st_size,
            })
        # Sort by timestamp descending (newest first)
        pending.sort(key=lambda x: x["timestamp"], reverse=True)
        return {"pending": pending}
    except Exception as e:
        return {"error": str(e), "pending": []}


@app.get("/api/governance/pending/{commit_id}")
def governance_pending_status(commit_id: str):
    """Poll a single governance proposal's status by commit_id."""
    try:
        if (GOV_COMMITS_DIR / f"{commit_id}.pending").exists():
            return {"commit_id": commit_id, "status": "pending"}
        if (GOV_COMMITS_DIR / f"{commit_id}.commit").exists():
            return {"commit_id": commit_id, "status": "approved"}
        if (GOV_COMMITS_DIR / f"{commit_id}.rejected").exists():
            return {"commit_id": commit_id, "status": "rejected"}
        raise HTTPException(status_code=404, detail=f"Proposal {commit_id} not found")
    except HTTPException:
        raise
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/governance/propose")
async def governance_propose(request: Request):
    """
    Create a new governance proposal. Returns commit_id and status.
    Checks precedent — auto-approves if a matching ratified decision exists.
    Body: {title, proposer, summary, file_path, diff, proposal_type?, trust_level?, risk_level?}
    """
    try:
        body = await request.json()
        from governance import proposal as gov_proposal
        commit_id = gov_proposal.create_proposal(
            title=body.get("title", "Untitled Proposal"),
            proposer=body.get("proposer", "ganesha"),
            summary=body.get("summary", ""),
            file_path=body.get("file_path", ""),
            diff=body.get("diff", ""),
            proposal_type=body.get("proposal_type", "Code Enhancement"),
            trust_level=body.get("trust_level", "ENGINEER"),
            risk_level=body.get("risk_level", "LOW"),
        )
        if commit_id.startswith("AUTO:"):
            return {"commit_id": commit_id, "status": "auto_approved", "message": "Precedent match — no approval needed."}
        if commit_id.startswith("DIST:"):
            return {"commit_id": commit_id, "status": "distributed", "message": "Distributed ratification — no approval needed."}
        return {"commit_id": commit_id, "status": "pending", "message": "Proposal created. Awaiting human ratification."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/governance/history")
def governance_history(limit: int = 50):
    """List ratified and rejected commits (history)."""
    try:
        history = []
        for f in list(GOV_COMMITS_DIR.glob("*.commit")) + list(GOV_COMMITS_DIR.glob("*.reject")):
            stat = f.stat()
            action = "approved" if f.suffix == ".commit" else "rejected"
            history.append({
                "id": f.stem,
                "filename": f.name,
                "action": action,
                "timestamp": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            })
        # Sort by timestamp descending
        history.sort(key=lambda x: x["timestamp"], reverse=True)
        return {"history": history[:limit]}
    except Exception as e:
        return {"error": str(e), "history": []}


@app.get("/api/governance/decisions")
def governance_decisions(limit: int = 10, project: str = None):
    """Human-readable feed of recent governance decisions for user-facing views."""
    import re
    decisions = []
    for pat in ("*.commit", "*.applied", "*.reject"):
        for f in GOV_COMMITS_DIR.glob(pat):
            try:
                content = f.read_text(encoding="utf-8", errors="replace")
                stat = f.stat()

                # Title: from "# Governance Proposal: ..." or fall back to filename
                title = f.stem.replace("-", " ").title()
                m = re.search(r"^#\s*Governance Proposal:\s*(.+)$", content, re.MULTILINE)
                if m:
                    title = m.group(1).strip()

                # Summary block
                summary = ""
                m = re.search(r"##\s*Summary\s*\n([\s\S]+?)(?=\n##|\Z)", content)
                if m:
                    summary = " ".join(m.group(1).split())[:400]

                # Proposer
                proposer = "Unknown"
                m = re.search(r"\*\*Proposer:\*\*\s*(.+)$", content, re.MULTILINE)
                if m:
                    proposer = m.group(1).strip().split("(")[0].strip()

                # Change type
                change_type = "Change"
                m = re.search(r"\*\*Type:\*\*\s*(.+)$", content, re.MULTILINE)
                if m:
                    change_type = m.group(1).strip()

                action = {"commit": "approved", "applied": "applied", "reject": "rejected"}.get(
                    f.suffix.lstrip("."), "unknown"
                )

                # Optional project filter
                if project and project.lower() not in f.stem.lower() and project.lower() not in content.lower():
                    continue

                decisions.append({
                    "id": f.stem,
                    "title": title,
                    "summary": summary,
                    "proposer": proposer,
                    "type": change_type,
                    "action": action,
                    "timestamp": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                })
            except Exception:
                continue

    decisions.sort(key=lambda x: x["timestamp"], reverse=True)
    return {"decisions": decisions[:limit]}


@app.get("/api/governance/diff/{commit_id}")
def governance_diff(commit_id: str):
    """Get the contents of a pending commit for review."""
    try:
        filepath = GOV_COMMITS_DIR / f"{commit_id}.pending"
        if not filepath.exists():
            return {"error": "Commit not found"}
        content = filepath.read_text(encoding="utf-8")
        return {"id": commit_id, "content": content}
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/governance/approve")
async def governance_approve(request: Request):
    """Approve (ratify) a pending commit. Moves .pending → .commit and routes through Willow."""
    try:
        body = await request.json()
        commit_id = body.get("commit_id")
        if not commit_id:
            return {"error": "Missing commit_id"}

        pending_file = GOV_COMMITS_DIR / f"{commit_id}.pending"
        if not pending_file.exists():
            return {"error": "Commit not found"}

        # Read commit content before moving
        commit_content = pending_file.read_text(encoding='utf-8')

        # Extract proposer from commit (look for "**Proposer:**" line)
        proposer = "unknown"
        for line in commit_content.split('\n'):
            if line.startswith('**Proposer:**'):
                proposer = line.split('**Proposer:**')[1].strip().split('(')[0].strip().lower()
                break

        # Move to .commit
        approved_file = GOV_COMMITS_DIR / f"{commit_id}.commit"
        pending_file.rename(approved_file)

        # Route through Willow to Kart (for application) and proposer (for notification)
        try:
            # Send full commit to Kart for application
            local_api.send_to_pickup(
                filename=f"GOVERNANCE_APPROVED_{commit_id}.md",
                content=f"# Governance Commit Approved\n\n**Commit ID:** {commit_id}\n**Action:** Apply this commit\n\n---\n\n{commit_content}",
                username="kart"
            )

            # Send notification to proposer
            if proposer != "unknown":
                local_api.send_to_pickup(
                    filename=f"GOVERNANCE_APPROVED_{commit_id}.md",
                    content=f"# Your Governance Proposal Was Approved!\n\n**Commit ID:** {commit_id}\n**Approved by:** Sean Campbell\n**Date:** {datetime.now().isoformat()}\n\nYour proposal has been approved and routed to Kart for implementation.\n\nΔΣ=42",
                    username=proposer
                )

            # Write to context_store so Ganesha sees it at next session start
            if _CS_AVAILABLE:
                try:
                    cs.put(
                        key=f"governance:pending_apply:{commit_id}",
                        query="pending governance commits to apply",
                        result=f"APPROVED: {commit_id} — ratified by Sean Campbell. Run: python governance/apply_commits.py {commit_id}",
                        category="governance",
                        ttl_hours=168
                    )
                except Exception:
                    pass  # routing failure never blocks approval

            return {"success": True, "action": "approved", "commit_id": commit_id, "routed_to": ["kart", proposer]}
        except Exception as routing_error:
            # Approval still succeeded even if routing failed
            return {"success": True, "action": "approved", "commit_id": commit_id, "routing_error": str(routing_error)}

    except Exception as e:
        return {"error": str(e), "success": False}


@app.post("/api/governance/reject")
async def governance_reject(request: Request):
    """Reject a pending commit. Moves .pending → .reject and appends reason."""
    try:
        body = await request.json()
        commit_id = body.get("commit_id")
        reason = body.get("reason", "No reason provided")

        if not commit_id:
            return {"error": "Missing commit_id"}

        pending_file = GOV_COMMITS_DIR / f"{commit_id}.pending"
        if not pending_file.exists():
            return {"error": "Commit not found"}

        # Move to .reject
        rejected_file = GOV_COMMITS_DIR / f"{commit_id}.reject"
        content = pending_file.read_text(encoding="utf-8")

        # Append rejection reason
        new_content = f"{content}\n\n---\nREJECTED: {datetime.now().isoformat()}\nReason: {reason}\n"
        rejected_file.write_text(new_content, encoding="utf-8")
        pending_file.unlink()

        return {"success": True, "action": "rejected", "commit_id": commit_id}
    except Exception as e:
        return {"error": str(e), "success": False}


@app.post("/api/governance/approve_and_apply")
async def governance_approve_and_apply(request: Request):
    """Approve and immediately apply a pending commit in one step.

    Apply strategy:
    1. Try apply_commits.py (handles standard unified diffs)
    2. If that fails, extract and run the ```python block from ## Implementation
       (used by Python string-replacement proposals)
    3. On success either way, rename to .applied
    """
    import subprocess, re, textwrap, tempfile, os
    try:
        body = await request.json()
        commit_id = body.get("commit_id", "").strip()
        if not commit_id:
            return {"success": False, "error": "commit_id required"}

        # Step 1: Approve (move .pending -> .commit)
        pending = GOV_COMMITS_DIR / f"{commit_id}.pending"
        commit_file = GOV_COMMITS_DIR / f"{commit_id}.commit"
        applied_file = GOV_COMMITS_DIR / f"{commit_id}.applied"

        if not pending.exists():
            if commit_file.exists():
                pass  # Already approved, proceed to apply
            elif applied_file.exists():
                return {"success": True, "commit_id": commit_id, "output": "Already applied.", "method": "noop"}
            else:
                return {"success": False, "error": f"Commit not found: {commit_id}"}
        else:
            pending.rename(commit_file)

        # Read proposal before apply_commits.py might move it
        proposal_text = commit_file.read_text(encoding="utf-8", errors="replace") if commit_file.exists() else \
                        applied_file.read_text(encoding="utf-8", errors="replace") if applied_file.exists() else ""

        # Step 2a: Try apply_commits.py
        apply_script = Path(__file__).parent / "governance" / "apply_commits.py"
        result = subprocess.run(
            [sys.executable, str(apply_script), commit_id],
            cwd=Path(__file__).parent,
            capture_output=True, text=True, timeout=30
        )
        diff_output = result.stdout + result.stderr
        # "[WARN] No diff block" means apply_commits treated it as a no-op — we still need to run the Python block
        no_diff_block = "[WARN] No diff block" in diff_output
        diff_ok = result.returncode == 0 and "[FAIL]" not in diff_output and not no_diff_block

        if diff_ok:
            # apply_commits.py succeeded with a real diff — file may already be .applied
            if commit_file.exists():
                commit_file.rename(applied_file)
            return {"success": True, "commit_id": commit_id, "output": diff_output, "method": "apply_commits"}

        # Step 2b: Extract ```python block from ## Implementation section and run it
        py_match = re.search(r"##\s*Implementation[\s\S]*?```python\s*\n([\s\S]+?)\n```", proposal_text)
        if py_match:
            py_code = textwrap.dedent(py_match.group(1))
            with tempfile.NamedTemporaryFile(
                suffix=".py", delete=False, mode="w", encoding="utf-8"
            ) as tmp:
                tmp.write(py_code)
                tmp_path = tmp.name
            try:
                py_result = subprocess.run(
                    [sys.executable, tmp_path],
                    cwd=Path(__file__).parent,
                    capture_output=True, text=True, timeout=60
                )
                py_output = py_result.stdout + py_result.stderr
                py_ok = py_result.returncode == 0
            finally:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

            if py_ok:
                # Ensure file is marked .applied (apply_commits may have already done this)
                if commit_file.exists():
                    commit_file.rename(applied_file)
                return {
                    "success": True,
                    "commit_id": commit_id,
                    "output": py_output or "Applied via Python block.",
                    "method": "python_block"
                }
            else:
                return {
                    "success": False,
                    "commit_id": commit_id,
                    "output": f"apply_commits.py:\n{diff_output}\n\nPython block:\n{py_output}",
                    "error": "Both apply strategies failed — check output"
                }

        # Step 2c: No Python block — return apply_commits output with guidance
        return {
            "success": False,
            "commit_id": commit_id,
            "output": diff_output,
            "error": "apply_commits.py failed and no Python block found in proposal"
        }

    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Apply timed out after 60s"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# --- Governance Audit Chain ---

@app.get("/api/governance/audit/head")
def governance_audit_head():
    """Current audit chain head: hash + sequence + entry count."""
    try:
        from core.storage import get_audit_head
        return get_audit_head()
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/governance/audit/verify")
def governance_audit_verify():
    """Verify audit chain integrity (tamper check)."""
    try:
        from core.storage import verify_audit_chain
        return verify_audit_chain()
    except Exception as e:
        return {"error": str(e)}


# --- SAFE Sync Status ---

SAFE_LOG = Path(__file__).parent / "core" / "safe_sync.log"
SAFE_REPO_PATH = Path(__file__).parent.parent / "SAFE"


@app.get("/api/safe/status")
def safe_status():
    """SAFE repo sync status: last sync, last error, repo reachability."""
    try:
        reachable = SAFE_REPO_PATH.exists() and (SAFE_REPO_PATH / ".git").exists()
        last_lines = []
        last_sync = None
        last_error = None
        if SAFE_LOG.exists():
            lines = SAFE_LOG.read_text(encoding="utf-8", errors="replace").splitlines()
            last_lines = lines[-10:]
            for line in reversed(lines):
                if "sync" in line.lower() and last_sync is None:
                    last_sync = line.strip()
                if "error" in line.lower() and last_error is None:
                    last_error = line.strip()
        return {
            "reachable": reachable,
            "repo_path": str(SAFE_REPO_PATH),
            "last_sync": last_sync,
            "last_error": last_error,
            "recent_log": last_lines,
        }
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/safe/sync")
def safe_sync_now():
    """Trigger a one-shot SAFE sync."""
    try:
        import subprocess
        result = subprocess.run(
            ["python", str(Path(__file__).parent / "core" / "safe_sync.py")],
            capture_output=True, text=True, timeout=30,
            cwd=str(Path(__file__).parent)
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout[-1000:] if result.stdout else "",
            "stderr": result.stderr[-500:] if result.stderr else "",
        }
    except Exception as e:
        return {"error": str(e), "success": False}


# --- Pattern Recognition & Health Monitoring ---

@app.get("/api/patterns/stats")
def patterns_stats():
    """Get routing pattern statistics."""
    try:
        from core import patterns
        stats = patterns.get_routing_stats(days=30)
        return stats
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/patterns/preferences")
def patterns_preferences():
    """Get learned routing preferences."""
    try:
        from core import patterns
        prefs = patterns.get_learned_preferences(min_confidence=0.3)
        return {"preferences": prefs}
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/patterns/suggestions")
def patterns_suggestions():
    """Get suggested automatic routing rules."""
    try:
        from core import patterns
        suggestions = patterns.suggest_rules()
        return {"suggestions": suggestions}
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/patterns/confirm_rule")
async def patterns_confirm_rule(request: Request):
    """User confirms a suggested routing rule."""
    try:
        from core import patterns
        body = await request.json()
        pattern_type = body.get("pattern_type")
        pattern_value = body.get("pattern_value")
        destination = body.get("destination")

        if not all([pattern_type, pattern_value, destination]):
            return {"error": "Missing required fields"}

        patterns.confirm_rule(pattern_type, pattern_value, destination)
        return {"success": True}
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/patterns/reject_rule")
async def patterns_reject_rule(request: Request):
    """User rejects a suggested routing rule."""
    try:
        from core import patterns
        body = await request.json()
        pattern_type = body.get("pattern_type")
        pattern_value = body.get("pattern_value")
        destination = body.get("destination")

        if not all([pattern_type, pattern_value, destination]):
            return {"error": "Missing required fields"}

        def _do_reject():
            conn = patterns._connect()
            conn.execute("""
                DELETE FROM learned_preferences
                WHERE pattern_type = ? AND pattern_value = ? AND destination = ?
            """, (pattern_type, pattern_value, destination))
            conn.commit()
            conn.close()

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _do_reject)
        return {"success": True, "message": "Rule rejected and removed from suggestions"}
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/patterns/anomalies")
def patterns_anomalies():
    """Detect routing and entity anomalies."""
    try:
        from core import patterns
        anomalies = patterns.detect_anomalies(lookback_days=7)
        return {"anomalies": anomalies}
    except Exception as e:
        return {"error": str(e)}


# --- Fleet Feedback Endpoints ---

@app.get("/api/feedback/stats")
def feedback_stats():
    """Get feedback statistics by provider and task type."""
    try:
        from core import fleet_feedback
        stats = fleet_feedback.get_feedback_stats()
        return stats
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/feedback/tasks/{task_type}")
def feedback_for_task(task_type: str, min_quality: Optional[int] = None, limit: int = 10):
    """Get feedback for a specific task type."""
    try:
        from core import fleet_feedback
        feedback = fleet_feedback.get_feedback_for_task(task_type, min_quality, limit)
        return {"task_type": task_type, "feedback": feedback, "count": len(feedback)}
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/feedback/provide")
async def provide_feedback(request: Request):
    """
    Submit feedback about a fleet output.

    Body: {
        "provider": "Groq",
        "task_type": "html_generation",
        "prompt": "original prompt",
        "output": "what the fleet generated",
        "quality": 2,  // 1-5 stars
        "issues": ["wrong_tech_stack", "syntax_errors"],
        "notes": "Generated React code instead of vanilla JS",
        "corrected": "optional corrected version"
    }
    """
    try:
        from core import fleet_feedback
        body = await request.json()

        # Validate required fields
        required = ["provider", "task_type", "prompt", "output", "quality", "issues", "notes"]
        missing = [f for f in required if f not in body]
        if missing:
            return {"error": f"Missing required fields: {missing}"}

        # Validate quality rating
        quality = body["quality"]
        if not isinstance(quality, int) or quality < 1 or quality > 5:
            return {"error": "quality must be an integer between 1 and 5"}

        # Store feedback
        fleet_feedback.provide_feedback(
            provider=body["provider"],
            task_type=body["task_type"],
            prompt=body["prompt"],
            output=body["output"],
            quality=quality,
            issues_list=body["issues"],
            notes=body["notes"],
            corrected=body.get("corrected")
        )

        return {
            "success": True,
            "message": f"Feedback recorded for {body['provider']} - {body['task_type']}"
        }
    except Exception as e:
        return {"error": str(e)}


# --- File Annotation Endpoints ---

@app.get("/api/annotations/unannotated")
def get_unannotated_routings(limit: int = 20):
    """Get routing decisions that haven't been annotated yet."""
    try:
        from core import file_annotations
        routings = file_annotations.get_unannotated_routings(limit=limit)
        return {"routings": routings, "count": len(routings)}
    except Exception as e:
        return {"error": str(e), "routings": []}


@app.post("/api/annotations/provide")
async def provide_annotation(request: Request):
    """
    Submit an annotation for a routing decision.

    Body: {
        "routing_id": 123,
        "filename": "test.py",
        "routed_to": ["node1", "node2"],
        "is_correct": false,
        "notes": "Should have gone to code_review because...",
        "corrected_destination": ["code_review"]
    }
    """
    try:
        from core import file_annotations
        body = await request.json()

        # Validate required fields
        required = ["routing_id", "filename", "routed_to", "is_correct", "notes"]
        missing = [f for f in required if f not in body]
        if missing:
            return {"error": f"Missing required fields: {missing}"}

        # Store annotation
        file_annotations.provide_annotation(
            routing_id=body["routing_id"],
            filename=body["filename"],
            routed_to=body["routed_to"],
            is_correct=body["is_correct"],
            notes=body["notes"],
            corrected_destination=body.get("corrected_destination"),
            annotated_by=body.get("annotated_by", "user")
        )

        return {
            "success": True,
            "message": f"Annotation recorded for routing {body['routing_id']}"
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/annotations/stats")
def get_annotation_stats():
    """Get file annotation statistics."""
    try:
        from core import file_annotations
        stats = file_annotations.get_annotation_stats()
        by_type = file_annotations.get_annotations_by_file_type()
        recent = file_annotations.get_recent_annotations(limit=10)
        return {
            "overall": stats,
            "by_file_type": by_type,
            "recent_annotations": recent
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/health/report")
def health_report():
    """Comprehensive system health report."""
    try:
        from core import health
        report = health.get_health_report()
        return report
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/health/nodes")
def health_nodes():
    """Check health of all nodes' knowledge databases."""
    try:
        from core import health
        nodes = health.check_node_health(stale_threshold_hours=24)
        return {"nodes": nodes}
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/nodes/create_db")
async def create_node_db(request: Request):
    """
    Create knowledge database for a node.

    Body: {"node_name": "some_node"}
    """
    try:
        from core import loam
        body = await request.json()
        node_name = body.get("node_name")

        if not node_name:
            return {"error": "Missing node_name"}

        # Validate node name (alphanumeric, underscore, hyphen only)
        import re
        if not re.match(r'^[a-zA-Z0-9_-]+$', node_name):
            return {"error": "Invalid node_name. Use only letters, numbers, underscores, and hyphens."}

        # Create database
        loam.init_db(node_name)

        return {
            "success": True,
            "message": f"Knowledge database created for node: {node_name}",
            "node_name": node_name
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/health/queues")
def health_queues():
    """Check pending queue backlogs."""
    try:
        from core import health
        queues = health.check_queue_health(backlog_threshold=50)
        return {"queues": queues}
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/health/apis")
def health_apis():
    """Check API health (Ollama, Gemini, Groq, etc.)."""
    try:
        from core import health
        apis = health.check_api_health()
        return {"apis": apis}
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/health/issues")
def health_issues():
    """Get unresolved health issues."""
    try:
        from core import health
        issues = health.get_unresolved_issues()
        return {"issues": issues}
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/health/heal")
async def health_heal(request: Request):
    """Attempt to self-heal a specific issue."""
    try:
        from core import health
        body = await request.json()
        issue_id = body.get("issue_id")

        if not issue_id:
            return {"error": "Missing issue_id"}

        success = health.attempt_self_heal(issue_id)
        return {"success": success, "issue_id": issue_id}
    except Exception as e:
        return {"error": str(e)}


# --- Provider Health Endpoints ---

@app.get("/api/health/providers")
def get_provider_health():
    """Get health status for all LLM providers."""
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent / "core"))
        import provider_health

        health_data = provider_health.get_all_health_status()

        # Convert ProviderHealth objects to dicts
        providers = {}
        for name, h in health_data.items():
            providers[name] = {
                "provider": h.provider,
                "status": h.status,
                "consecutive_failures": h.consecutive_failures,
                "last_success": h.last_success,
                "last_failure": h.last_failure,
                "blacklisted_until": h.blacklisted_until,
                "total_requests": h.total_requests,
                "total_successes": h.total_successes,
                "total_failures": h.total_failures,
                "success_rate": (h.total_successes / h.total_requests * 100) if h.total_requests > 0 else 0
            }

        return {"providers": providers}
    except Exception as e:
        return {"error": str(e), "providers": {}}


@app.post("/api/health/providers/unblacklist")
async def unblacklist_provider(request: Request):
    """Manually unblacklist a provider."""
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent / "core"))
        import provider_health
        import sqlite3

        body = await request.json()
        provider_name = body.get("provider")

        if not provider_name:
            return {"error": "Missing provider name"}

        # Manually unblacklist by updating database
        def _do_unblacklist():
            conn = provider_health._connect()
            conn.execute("""
                UPDATE provider_health
                SET status = 'healthy', blacklisted_until = NULL, consecutive_failures = 0
                WHERE provider = ?
            """, (provider_name,))
            conn.commit()
            conn.close()

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _do_unblacklist)
        return {"success": True, "provider": provider_name, "message": f"{provider_name} unblacklisted"}
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/health/providers/reset")
async def reset_provider_health(request: Request):
    """Reset health counters for a provider."""
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent / "core"))
        import provider_health

        body = await request.json()
        provider_name = body.get("provider")

        if not provider_name:
            return {"error": "Missing provider name"}

        # Reset health counters
        conn = provider_health._connect()
        conn.execute("""
            UPDATE provider_health
            SET status = 'healthy',
                consecutive_failures = 0,
                blacklisted_until = NULL
            WHERE provider = ?
        """, (provider_name,))
        conn.commit()
        conn.close()

        return {"success": True, "provider": provider_name, "message": f"{provider_name} health reset"}
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/queues/files")
async def get_queue_files(queue: str = None):
    """List files in a specific user's pending queue."""
    try:
        if not queue:
            return {"error": "Missing queue parameter"}

        artifacts_path = Path(__file__).parent / "artifacts"
        pending_dir = artifacts_path / queue / "pending"

        if not pending_dir.exists():
            return {"files": [], "message": "Queue does not exist"}

        files = []
        for file_path in pending_dir.iterdir():
            if file_path.is_file():
                stat = file_path.stat()
                files.append({
                    "name": file_path.name,
                    "size": stat.st_size,
                    "modified": stat.st_mtime
                })

        # Sort by modified time (newest first)
        files.sort(key=lambda x: x["modified"], reverse=True)

        return {"files": files, "queue": queue, "count": len(files)}
    except Exception as e:
        return {"error": str(e), "files": []}


@app.post("/api/queues/clear")
async def clear_queue(request: Request):
    """Clear all files from a user's pending queue."""
    try:
        import shutil

        body = await request.json()
        queue = body.get("queue")

        if not queue:
            return {"error": "Missing queue parameter"}

        # Security: validate queue name (no path traversal)
        import re
        if not re.match(r'^[a-zA-Z0-9_-]+$', queue):
            return {"error": "Invalid queue name"}

        artifacts_path = Path(__file__).parent / "artifacts"
        pending_dir = artifacts_path / queue / "pending"

        if not pending_dir.exists():
            return {"error": "Queue does not exist"}

        # Count files before deletion
        file_count = len([f for f in pending_dir.iterdir() if f.is_file()])

        # Delete all files in the pending directory
        for file_path in pending_dir.iterdir():
            if file_path.is_file():
                file_path.unlink()

        return {
            "success": True,
            "queue": queue,
            "files_deleted": file_count,
            "message": f"Cleared {file_count} files from {queue} queue"
        }
    except Exception as e:
        return {"error": str(e)}


# --- Intake Queue Management ---

@app.post("/api/intake/retry/{stage}")
async def retry_intake_stage(stage: str):
    """Retry all files in an intake stage by moving them back to dump."""
    try:
        intake_base = Path("intake")
        stage_path = intake_base / stage
        dump_path = intake_base / "dump"

        if not stage_path.exists():
            return {"error": f"Stage '{stage}' not found"}

        if not dump_path.exists():
            dump_path.mkdir(parents=True, exist_ok=True)

        # Move all files from stage back to dump
        moved_count = 0
        for file_path in stage_path.iterdir():
            if file_path.is_file():
                dest = dump_path / file_path.name
                file_path.rename(dest)
                moved_count += 1

        return {
            "success": True,
            "stage": stage,
            "files_retried": moved_count,
            "message": f"Moved {moved_count} files from {stage} back to dump for retry"
        }
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/intake/clear/{stage}")
async def clear_intake_stage(stage: str):
    """Clear all files from an intake stage (moves to clear)."""
    try:
        intake_base = Path("intake")
        stage_path = intake_base / stage
        clear_path = intake_base / "clear"

        if not stage_path.exists():
            return {"error": f"Stage '{stage}' not found"}

        if not clear_path.exists():
            clear_path.mkdir(parents=True, exist_ok=True)

        # Move all files from stage to clear
        cleared_count = 0
        for file_path in stage_path.iterdir():
            if file_path.is_file():
                dest = clear_path / file_path.name
                file_path.rename(dest)
                cleared_count += 1

        return {
            "success": True,
            "stage": stage,
            "files_cleared": cleared_count,
            "message": f"Cleared {cleared_count} files from {stage}"
        }
    except Exception as e:
        return {"error": str(e)}


# --- Issue Management ---

@app.post("/api/health/issues/dismiss")
async def dismiss_issue(request: Request):
    """Dismiss a health issue by ID."""
    try:
        from core import health
        body = await request.json()
        issue_id = body.get("issue_id")

        if not issue_id:
            return {"error": "Missing issue_id"}

        # Mark issue as dismissed
        success = health.dismiss_issue(issue_id)

        return {
            "success": success,
            "issue_id": issue_id,
            "message": f"Issue {issue_id} dismissed" if success else "Failed to dismiss issue"
        }
    except Exception as e:
        return {"error": str(e)}


# --- Pocket Willow (mobile-friendly, served same-origin) ---

POCKET_HTML = Path(__file__).parent / "neocities" / "index.html"

@app.get("/pocket")
def serve_pocket():
    """Serve pocket Willow from same origin — no CORS / mixed-content issues."""
    if not POCKET_HTML.exists():
        return {"error": "neocities/index.html not found"}
    return FileResponse(POCKET_HTML, media_type="text/html")


# --- The Binder ---

# --- Binder / Relationship Tracker API ---

@app.get("/api/binder/entities")
def binder_entities(username: str = "Sweet-Pea-Rudi19", layer: int = None, entity_type: str = None):
    """List tracked entities (L1=anonymous, L2=recognized, L3=named)."""
    try:
        from core.vine import RelationshipTracker
        rt = RelationshipTracker(username)
        return {"entities": rt.list_entities(username=username, layer=layer, entity_type=entity_type)}
    except Exception as e:
        return {"entities": [], "error": str(e)}

@app.get("/api/binder/connections/{entity_id}")
def binder_connections(entity_id: int, username: str = "Sweet-Pea-Rudi19", min_weight: float = 0.3):
    """Get connections for an entity."""
    try:
        from core.vine import RelationshipTracker
        rt = RelationshipTracker(username)
        return {"connections": rt.get_connections(entity_id, min_weight=min_weight)}
    except Exception as e:
        return {"connections": [], "error": str(e)}

@app.post("/api/binder/connections/suggest")
def binder_suggest_connections(body: dict):
    """Suggest connections from knowledge atom IDs."""
    try:
        from core.vine import RelationshipTracker
        username = body.get("username", "Sweet-Pea-Rudi19")
        knowledge_ids = body.get("knowledge_ids", [])
        rt = RelationshipTracker(username)
        return {"suggestions": rt.suggest_connections(knowledge_ids)}
    except Exception as e:
        return {"suggestions": [], "error": str(e)}

@app.get("/api/binder/eligible")
def binder_eligible(username: str = "Sweet-Pea-Rudi19", min_mentions: int = 5):
    """Get L2 entities eligible for promotion to L3."""
    try:
        from core.vine import RelationshipTracker
        rt = RelationshipTracker(username)
        return {"eligible": rt.get_eligible_for_promotion(username=username, min_mentions=min_mentions)}
    except Exception as e:
        return {"eligible": [], "error": str(e)}

@app.post("/api/binder/promote")
def binder_promote(body: dict):
    """Promote an L2 entity to L3 (named/confirmed)."""
    try:
        from core.vine import RelationshipTracker
        username = body.get("username", "Sweet-Pea-Rudi19")
        rt = RelationshipTracker(username)
        result = rt.promote_to_named(
            reference_id=body["reference_id"],
            confirmed_name=body["confirmed_name"],
            entity_type=body.get("entity_type", "person"),
            relationship_type=body.get("relationship_type")
        )
        return {"entity": result, "success": bool(result)}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/api/binder/dismiss")
def binder_dismiss(body: dict):
    """Dismiss a promotion prompt (optionally permanently)."""
    try:
        from core.vine import RelationshipTracker
        username = body.get("username", "Sweet-Pea-Rudi19")
        rt = RelationshipTracker(username)
        ok = rt.dismiss_promotion(body["reference_id"], never=body.get("never", False))
        return {"success": ok}
    except Exception as e:
        return {"success": False, "error": str(e)}

# --- Willow Connections (pending approval) ---

@app.get("/api/willow/connections/pending")
def willow_connections_pending(username: str = "Sweet-Pea-Rudi19", limit: int = 20):
    """Unconfirmed connections Willow proposed — awaiting user approve/deny/edit."""
    try:
        from core.vine import RelationshipTracker
        rt = RelationshipTracker(username)
        if not rt.conn:
            return {"connections": [], "error": "DB unavailable"}
        rows = rt.conn.execute("""
            SELECT ec.id, ec.connection_type, ec.weight, ec.source, ec.created_at,
                   ea.name AS name_a, ea.entity_type AS type_a,
                   eb.name AS name_b, eb.entity_type AS type_b
            FROM entity_connections ec
            JOIN entities ea ON ec.entity_a_id = ea.id
            JOIN entities eb ON ec.entity_b_id = eb.id
            WHERE ec.confirmed = 0
            ORDER BY ec.created_at DESC
            LIMIT ?
        """, (limit,)).fetchall()
        return {"connections": [dict(r) for r in rows]}
    except Exception as e:
        return {"connections": [], "error": str(e)}


@app.post("/api/willow/connections/{connection_id}/approve")
async def willow_connection_approve(connection_id: int, username: str = "Sweet-Pea-Rudi19"):
    """Approve a pending connection — sets confirmed=1."""
    try:
        from core.db import get_connection as _gc, is_postgres
        conn = _gc() if is_postgres() else _gc(str(Path("artifacts") / username / "willow_knowledge.db"))
        conn.execute("UPDATE entity_connections SET confirmed=1 WHERE id=?", (connection_id,))
        conn.commit()
        conn.close()
        asyncio.create_task(_ecosystem_refresh())
        return {"success": True, "id": connection_id, "action": "approved"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/willow/connections/{connection_id}/deny")
async def willow_connection_deny(connection_id: int, username: str = "Sweet-Pea-Rudi19"):
    """Deny a pending connection — confirmed=-1 tombstone.
    The UNIQUE(entity_a_id, entity_b_id, connection_type) constraint means
    INSERT OR IGNORE in scan-connections will skip this pair forever.
    No means no unless the user explicitly clears it."""
    try:
        from core.db import get_connection as _gc, is_postgres
        conn = _gc() if is_postgres() else _gc(str(Path("artifacts") / username / "willow_knowledge.db"))
        conn.execute("UPDATE entity_connections SET confirmed=-1 WHERE id=?", (connection_id,))
        conn.commit()
        conn.close()
        asyncio.create_task(_ecosystem_refresh())
        return {"success": True, "id": connection_id, "action": "denied"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/willow/connections/{connection_id}/edit")
async def willow_connection_edit(connection_id: int, request: Request, username: str = "Sweet-Pea-Rudi19"):
    """Edit a pending connection's type or weight, then auto-approve it."""
    try:
        body = await request.json()
        from core.vine import RelationshipTracker
        rt = RelationshipTracker(username)
        if not rt.conn:
            return {"success": False, "error": "DB unavailable"}
        if "connection_type" in body:
            rt.conn.execute(
                "UPDATE entity_connections SET connection_type=? WHERE id=?",
                (body["connection_type"], connection_id)
            )
        if "weight" in body:
            rt.conn.execute(
                "UPDATE entity_connections SET weight=? WHERE id=?",
                (float(body["weight"]), connection_id)
            )
        rt.conn.execute("UPDATE entity_connections SET confirmed=1 WHERE id=?", (connection_id,))
        rt.conn.commit()
        return {"success": True, "id": connection_id, "action": "edited"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def _willow_scan_connections_internal(username: str = "Sweet-Pea-Rudi19") -> dict:
    """Core scan logic — reusable by route and auto-triggers."""
    try:
        from core.vine import RelationshipTracker
        rt = RelationshipTracker(username)
        if not rt.conn:
            return {"status": "error", "error": "DB unavailable"}
        # Get all knowledge atom IDs
        rows = rt.conn.execute("SELECT id FROM knowledge ORDER BY id").fetchall()
        knowledge_ids = [r["id"] for r in rows]
        if not knowledge_ids:
            return {"status": "ok", "new_proposals": 0, "total_suggestions": 0}
        logger.info("[scan-connections] Scanning %d atoms for %s", len(knowledge_ids), username)
        suggestions = rt.suggest_connections(knowledge_ids)
        logger.info("[scan-connections] %d suggestions found", len(suggestions))
        new_count = 0
        for s in suggestions:
            result = rt.record_connection(
                entity_a_id=s["entity_a"]["id"],
                entity_b_id=s["entity_b"]["id"],
                connection_type=s.get("suggested_type", "co-mention"),
                weight=s.get("confidence", 0.5),
                source="willow-auto-scan",
            )
            if result:
                new_count += 1
        logger.info("[scan-connections] Done: %d new proposals recorded", new_count)
        return {"status": "scanned", "new_proposals": new_count, "total_suggestions": len(suggestions)}
    except Exception as e:
        logger.error("[scan-connections] Error: %s", e)
        return {"status": "error", "error": str(e)}


@app.post("/api/willow/scan-connections")
async def willow_scan_connections(username: str = "Sweet-Pea-Rudi19"):
    """Scan all knowledge atoms for co-occurring entity pairs and propose connections.
    Results appear in /api/willow/connections/pending for user approve/deny."""
    return _willow_scan_connections_internal(username)



BINDER_HTML = Path(__file__).parent / "binder.html"

@app.get("/binder")
def serve_binder():
    """Serve The Binder — UTETY Local Stacks knowledge browser."""
    if not BINDER_HTML.exists():
        return {"error": "binder.html not found"}
    return FileResponse(BINDER_HTML, media_type="text/html; charset=utf-8")


# --- Shiva GM Game Routes ---

GAME_HTML = Path(__file__).parent / "game.html"

@app.get("/game")
def serve_game():
    if not GAME_HTML.exists():
        return {"error": "game.html not found"}
    return FileResponse(GAME_HTML, media_type="text/html; charset=utf-8")

@app.post("/api/game/session/start")
async def game_session_start(request: Request):
    try:
        import game_engine as ge
        body = await request.json()
        result = ge.create_session(
            player_name=body.get("player_name", "Adventurer"),
            game_type=body.get("game_type", "pbta"),
            mode=body.get("mode", "full_gm"),
            world=body.get("world"),
            persist=body.get("persist", False),
        )
        ge.add_history(result["session_id"], "system", "Session started.")
        return {"success": True, **result}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/api/game/session/{session_id}")
def game_session_get(session_id: str):
    try:
        import game_engine as ge
        session = ge.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        character = ge.get_character(session_id)
        return {"success": True, "session": session, "character": character}
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.delete("/api/game/session/{session_id}")
def game_session_delete(session_id: str):
    try:
        import game_engine as ge
        ge.delete_session(session_id)
        return {"success": True, "deleted": session_id}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/api/game/playbooks")
def game_playbooks():
    import game_engine as ge
    return {"playbooks": ge.get_playbooks()}

@app.post("/api/game/character/create")
async def game_character_create(request: Request):
    try:
        import game_engine as ge
        body = await request.json()
        result = ge.create_character(
            session_id=body["session_id"],
            name=body["name"],
            playbook=body["playbook"],
            custom_stats=body.get("custom_stats"),
        )
        ge.add_history(body["session_id"], "system", f"{result['name']} the {result['playbook']} enters the story.")
        return {"success": True, **result}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/api/game/roll")
async def game_roll(request: Request):
    try:
        import game_engine as ge
        body = await request.json()
        result = ge.roll_dice(
            session_id=body["session_id"],
            dice=body.get("dice", "2d6"),
            modifier=body.get("modifier", 0),
            modifier_label=body.get("modifier_label", ""),
            context=body.get("context", ""),
        )
        if result.get("success"):
            label = body.get("modifier_label", "")
            roll_text = f"Rolled {body.get('dice','2d6')}: {result['rolls']} + {result['modifier']} ({label}) = **{result['total']}**"
            if result.get("outcome"):
                roll_text += f" → {result['outcome'].replace('_',' ').title()}"
            ge.add_history(body["session_id"], "roll", roll_text, {"hash": result["hash"]})
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/api/game/rolls/{session_id}")
def game_roll_history(session_id: str, limit: int = 20):
    try:
        import game_engine as ge
        return {"rolls": ge.get_roll_history(session_id, limit)}
    except Exception as e:
        return {"rolls": [], "error": str(e)}

@app.post("/api/game/narrate")
async def game_narrate(request: Request):
    """Shiva narrates — builds GM prompt and calls the fleet."""
    try:
        import game_engine as ge
        body = await request.json()
        session_id = body["session_id"]
        player_action = body.get("action", "")

        if player_action:
            ge.add_history(session_id, "player", player_action)

        prompt = ge.build_gm_prompt(session_id, player_action)

        response = llm_router.ask(prompt, preferred_tier="free")
        if not response:
            return {"success": False, "error": "Fleet unavailable — all providers failed"}

        narration = response.content.strip()
        ge.add_history(session_id, "shiva", narration)

        return {
            "success": True,
            "narration": narration,
            "provider": response.provider,
            "history": ge.get_history(session_id, limit=30),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/api/game/pbta/convert")
async def game_pbta_convert(request: Request):
    """Convert any IP/franchise into a PBtA game on demand."""
    try:
        body = await request.json()
        ip = body.get("ip", "")
        if not ip:
            return {"success": False, "error": "ip required"}

        prompt = f"""You are a PBtA game designer. Convert the world of "{ip}" into a complete PBtA game.

Return valid JSON only, no other text:
{{
  "title": "Name of game",
  "tagline": "One-line description",
  "world_intro": "2-3 sentences setting the scene, age-appropriate",
  "stats": {{"Stat1": "description", "Stat2": "description", "Stat3": "description", "Stat4": "description", "Stat5": "description"}},
  "basic_moves": [
    {{"name": "Move Name", "trigger": "When you...", "mechanic": "Roll+Stat. On 10+... On 7-9... On 6-..."}}
  ],
  "playbooks": [
    {{"name": "Playbook Name", "description": "One line", "stats": {{}}, "moves": [], "gear": [], "hp": 6}}
  ],
  "gm_principles": ["Principle 1", "Principle 2", "Principle 3"]
}}

Keep it fun, age-appropriate (9-14), and true to the source material."""

        response = llm_router.ask(prompt, preferred_tier="free")
        if not response:
            return {"success": False, "error": "Fleet unavailable"}

        import re, json as _json
        content = response.content.strip()
        m = re.search(r'\{[\s\S]+\}', content)
        if m:
            game_data = _json.loads(m.group(0))
            return {"success": True, "ip": ip, "game": game_data}
        return {"success": False, "error": "Could not parse game JSON", "raw": content[:500]}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/api/game/history/{session_id}")
def game_history(session_id: str, limit: int = 30):
    try:
        import game_engine as ge
        return {"history": ge.get_history(session_id, limit)}
    except Exception as e:
        return {"history": [], "error": str(e)}


# --- Governance Dashboard ---

GOVERNANCE_DASHBOARD = Path(__file__).parent / "governance" / "dashboard.html"

@app.get("/governance")
def serve_governance_dashboard():
    """Serve governance dashboard for dual commit review (admin only)."""
    if not GOVERNANCE_DASHBOARD.exists():
        return {"error": "governance/dashboard.html not found"}
    return FileResponse(GOVERNANCE_DASHBOARD, media_type="text/html")


# --- System Dashboard ---

SYSTEM_DASHBOARD = Path(__file__).parent / "system" / "dashboard.html"

@app.get("/system")
def serve_system_dashboard():
    """Serve system dashboard for pattern recognition and health monitoring."""
    if not SYSTEM_DASHBOARD.exists():
        return {"error": "system/dashboard.html not found"}
    return FileResponse(SYSTEM_DASHBOARD, media_type="text/html")


UI_DIST = Path(__file__).parent / "ui" / "dist"


# --- Request Manager Endpoints ---

@app.get("/api/request_manager/stats")
def request_manager_stats():
    """Rate limit status and cache stats for all providers."""
    try:
        from core import request_manager
        return request_manager.get_stats()
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/request_manager/clear_cache")
def request_manager_clear_cache():
    """Clear the LLM response cache."""
    try:
        from core import request_manager
        request_manager.clear_cache()
        return {"status": "cache cleared"}
    except Exception as e:
        return {"error": str(e)}


# --- Hot Reload Endpoint ---

@app.post("/api/reload")
def reload_module(module: str):
    """Hot-reload a core module without restarting the server.

    Works for: llm_router, extraction, tts_router, knowledge, coherence,
               topology, provider_health, patterns_provider, fleet_feedback,
               tool_engine
    Does NOT affect route definitions (those need server restart).
    """
    import importlib
    allowed = {
        "llm_router", "extraction", "tts_router", "knowledge",
        "coherence", "topology", "provider_health", "patterns_provider",
        "fleet_feedback", "embeddings", "tool_engine"
    }
    if module not in allowed:
        return {"error": f"Module '{module}' not reloadable. Allowed: {sorted(allowed)}"}
    try:
        import core
        mod = getattr(core, module, None)
        if mod is None:
            import importlib
            mod = importlib.import_module(f"core.{module}")
        importlib.reload(mod)
        return {"reloaded": f"core.{module}", "status": "ok"}
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/ecosystem")
def ecosystem_read():
    """Return current ECOSYSTEM.md content (Willow self-model)."""
    try:
        from core import ecosystem_writer as ew
        return {"content": ew._read(), "path": str(ew.ECOSYSTEM_PATH)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/ecosystem/update-stats")
async def ecosystem_update_stats():
    """Refresh the Architecture section of ECOSYSTEM.md with live DB stats.
    Call after knowledge ingest, connection approval, or any significant state change."""
    try:
        import re as _re
        from core import ecosystem_writer as ew
        from core.db import get_connection as _gc, is_postgres
        conn = _gc() if is_postgres() else _gc(loam._db_path(USERNAME))
        k  = conn.execute("SELECT COUNT(*) FROM knowledge").fetchone()[0]
        e  = conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
        ec = conn.execute("SELECT COUNT(*) FROM entity_connections WHERE confirmed=1").fetchone()[0]
        ke = conn.execute("SELECT COUNT(*) FROM knowledge_edges").fetchone()[0]
        conn.close()
        arch = ew.get_section("Architecture")
        arch = _re.sub(
            r"\*\*Knowledge graph:\*\*[^\n]+",
            f"**Knowledge graph:** {ke:,} canonical edges / {e:,} entities / {k:,} knowledge atoms",
            arch
        )
        arch = _re.sub(
            r"\*\*Entity connections:\*\*[^\n]+",
            f"**Entity connections:** {ec:,} confirmed",
            arch
        )
        ew.update_section("Architecture", arch)
        return {"updated": True, "knowledge": k, "entities": e, "edges": ke, "connections": ec}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/ecosystem/decision")
async def ecosystem_append_decision(request: Request):
    """Append a timestamped entry to the Design Decisions section of ECOSYSTEM.md."""
    try:
        from core import ecosystem_writer as ew
        body = await request.json()
        decision = body.get("decision", "").strip()
        if not decision:
            raise HTTPException(status_code=400, detail="decision field required")
        result = ew.append_decision(decision)
        return {"appended": result, "decision": decision}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



async def _ecosystem_refresh():
    """Background task: refresh ECOSYSTEM.md Architecture stats from live DB."""
    try:
        import re as _re
        from core import ecosystem_writer as _ew
        from core.db import get_connection as _gc, is_postgres
        conn = _gc() if is_postgres() else _gc(loam._db_path(USERNAME))
        k  = conn.execute("SELECT COUNT(*) FROM knowledge").fetchone()[0]
        e  = conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
        ec = conn.execute("SELECT COUNT(*) FROM entity_connections WHERE confirmed=1").fetchone()[0]
        ke = conn.execute("SELECT COUNT(*) FROM knowledge_edges").fetchone()[0]
        conn.close()
        arch = _ew.get_section("Architecture")
        arch = _re.sub(r"\*\*Knowledge graph:\*\*[^\n]+",
            f"**Knowledge graph:** {ke:,} canonical edges / {e:,} entities / {k:,} knowledge atoms", arch)
        arch = _re.sub(r"\*\*Entity connections:\*\*[^\n]+",
            f"**Entity connections:** {ec:,} confirmed", arch)
        _ew.update_section("Architecture", arch)
    except Exception:
        pass


@app.post("/api/reload/all")
def reload_all():
    """Hot-reload all core modules at once."""
    import importlib
    modules = [
        "llm_router", "extraction", "tts_router", "knowledge",
        "coherence", "topology", "provider_health", "patterns_provider",
        "fleet_feedback", "tool_engine"
    ]
    results = {}
    for name in modules:
        try:
            mod = importlib.import_module(f"core.{name}")
            importlib.reload(mod)
            results[name] = "ok"
        except Exception as e:
            results[name] = f"error: {e}"
    return {"reloaded": results}


# --- Bulk Learn ---

_learn_status = {"running": False, "progress": "", "ingested": 0, "skipped": 0, "errors": 0}

LEARN_SOURCES = [
    # Repos
    (Path("../die-namic-system/governance"),      "source",     "governance"),
    (Path("../die-namic-system/source_ring"),      "source",     "code"),
    (Path("../die-namic-system/docs"),             "source",     "narrative"),
    (Path("../die-namic-system/continuity_ring"),  "continuity", "narrative"),
    (Path("../die-namic-system/scripts"),          "source",     "code"),
    (Path("../die-namic-system/tools"),            "source",     "code"),
    (Path("../SAFE/governance"),                   "source",     "governance"),
    (Path("../SAFE/schemas"),                      "source",     "specs"),
    (Path("../SAFE/docs"),                         "source",     "narrative"),
    (Path("core"),                                 "bridge",     "code"),
    (Path("apps"),                                 "bridge",     "code"),
    (Path("scripts"),                              "bridge",     "code"),
    (Path("schema"),                               "bridge",     "specs"),
    (Path("governance"),                           "bridge",     "governance"),
    (Path("../vision-board/backend"),              "bridge",     "code"),
    (Path("../vision-board/frontend/src"),         "bridge",     "code"),
    # Google Drive
    (Path("C:/Users/Sean/My Drive/die-namic-system/training_data"),    "source",     "data"),
    (Path("C:/Users/Sean/My Drive/die-namic-system/origin_materials"),  "source",     "narrative"),
    (Path("C:/Users/Sean/My Drive/die-namic-system/docs"),             "source",     "narrative"),
    (Path("C:/Users/Sean/My Drive/die-namic-system/governance"),       "source",     "governance"),
    (Path("C:/Users/Sean/My Drive/die-namic-system/continuity_ring"),  "continuity", "narrative"),
    (Path("C:/Users/Sean/My Drive/Archive"),       "continuity", "documents"),
    (Path("C:/Users/Sean/My Drive/Career"),        "continuity", "documents"),
    (Path("C:/Users/Sean/My Drive/Creative"),      "source",     "narrative"),
    (Path("C:/Users/Sean/My Drive/Data"),          "bridge",     "data"),
    (Path("C:/Users/Sean/My Drive/Journal"),       "continuity", "narrative"),
    (Path("C:/Users/Sean/My Drive/Personal"),      "continuity", "narrative"),
    (Path("C:/Users/Sean/My Drive/Projects"),      "source",     "narrative"),
    (Path("C:/Users/Sean/My Drive/System"),        "source",     "specs"),
    (Path("C:/Users/Sean/My Drive/Transcripts"),   "continuity", "narrative"),
    # Existing artifacts (already sorted)
    (Path("artifacts/Sweet-Pea-Rudi19"),           "bridge",     "documents"),
]

LEARN_TEXT_EXTS = {".py",".js",".ts",".jsx",".tsx",".html",".css",".md",".txt",
                   ".json",".yaml",".yml",".toml",".csv",".sh",".bat",".sql",".xml",".rst"}
LEARN_SKIP_DIRS = {"node_modules","__pycache__",".git",".venv","venv","dist","build",
                   ".next",".tmp.drivedownload",".tmp.driveupload","$RECYCLE.BIN",".pytest_cache"}
LEARN_MAX_SIZE = 200_000


def _learn_infer_cat(path: Path, default: str) -> str:
    parts = {p.lower() for p in path.parts}
    if "governance" in parts: return "governance"
    if any(x in parts for x in ("continuity_ring","journal","transcripts")): return "narrative"
    if any(x in parts for x in ("schemas","schema","specs","awa")): return "specs"
    if any(x in parts for x in ("training_data",)): return "data"
    if path.suffix in (".py",".js",".ts",".sh",".bat"): return "code"
    if path.suffix in (".json",".csv",".yaml",".yml"): return "data"
    if path.suffix == ".md": return "narrative"
    return default


def _learn_worker(username: str):
    """Run bulk ingest inside the server process."""
    import hashlib
    from core.loam import init_db, _connect, _extract_entities_regex
    _learn_status["running"] = True
    _learn_status["ingested"] = 0
    _learn_status["skipped"] = 0
    _learn_status["errors"] = 0

    init_db(username)
    conn = _connect(username)
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    for base, ring, default_cat in LEARN_SOURCES:
        if not base.exists():
            continue
        _learn_status["progress"] = f"scanning {base.name}"
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            if any(s in path.parts for s in LEARN_SKIP_DIRS):
                continue
            if path.name in {"desktop.ini",".DS_Store","package-lock.json","yarn.lock"}:
                continue
            if path.suffix.lower() not in LEARN_TEXT_EXTS:
                continue
            try:
                if path.stat().st_size > LEARN_MAX_SIZE:
                    continue
            except Exception:
                continue

            try:
                content = path.read_text(encoding="utf-8", errors="replace")
                if len(content.strip()) < 20:
                    _learn_status["skipped"] += 1
                    continue

                fhash = hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()[:32]
                cat = _learn_infer_cat(path, default_cat)

                existing = conn.execute(
                    "SELECT id FROM knowledge WHERE source_type='file' AND source_id=?",
                    (fhash,)
                ).fetchone()
                if existing:
                    _learn_status["skipped"] += 1
                    continue

                entities = _extract_entities_regex(f"{path.name} {content[:500]}")
                conn.execute(
                    """INSERT OR IGNORE INTO knowledge
                       (source_type, source_id, title, summary, content_snippet,
                        category, ring, created_at)
                       VALUES ('file', ?, ?, NULL, ?, ?, ?, ?)""",
                    (fhash, str(path), content[:1000], cat, ring, now)
                )
                kid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                if kid and entities:
                    for ent in entities:
                        conn.execute(
                            "INSERT OR IGNORE INTO entities (name, entity_type) VALUES (?, ?)",
                            (ent["name"], ent.get("type", "unknown"))
                        )
                        eid = conn.execute("SELECT id FROM entities WHERE name=?", (ent["name"],)).fetchone()
                        if eid:
                            conn.execute(
                                "INSERT OR IGNORE INTO knowledge_entities (knowledge_id, entity_id) VALUES (?, ?)",
                                (kid, eid[0])
                            )
                conn.commit()
                _learn_status["ingested"] += 1
            except Exception as e:
                _learn_status["errors"] += 1

    conn.close()
    _learn_status["running"] = False
    _learn_status["progress"] = f"done: {_learn_status['ingested']} ingested"


@app.post("/api/learn")
def learn_start():
    """Start bulk ingest of all repos + Google Drive into knowledge DB."""
    if _learn_status["running"]:
        return {"error": "Already running", "status": _learn_status}
    import threading
    username = USERNAME
    t = threading.Thread(target=_learn_worker, args=(username,), daemon=True)
    t.start()
    return {"started": True, "message": "Bulk learn started in background"}


@app.get("/api/learn/status")
def learn_status():
    """Check bulk learn progress."""
    return _learn_status


@app.post("/api/admin/restart")
async def admin_restart():
    """Hot-restart the Willow server. Called by Kart REPL :server_restart command."""
    import threading
    def _do_restart():
        import time, os, sys, subprocess
        time.sleep(0.5)
        subprocess.Popen(
            [sys.executable, __file__],
            cwd=str(Path(__file__).parent),
        )
        os._exit(0)
    threading.Thread(target=_do_restart, daemon=True).start()
    return {"status": "restarting", "message": "Server restarting in 0.5s — reconnect in ~5s"}


# ── Pigeon Mail ────────────────────────────────────────────

@app.get('/api/pigeon/droppings')
async def pigeon_get_droppings(username: str = 'Sweet-Pea-Rudi19'):
    try:
        from core import pigeon
        pigeon.init_droppings_table()
        return {'droppings': pigeon.get_droppings(username)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete('/api/pigeon/droppings/{dropping_id}')
async def pigeon_sweep_one(dropping_id: int, username: str = 'Sweet-Pea-Rudi19'):
    try:
        from core import pigeon
        ok = pigeon.sweep_dropping(username, dropping_id)
        return {'success': ok}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete('/api/pigeon/droppings')
async def pigeon_sweep_all_route(username: str = 'Sweet-Pea-Rudi19'):
    try:
        from core import pigeon
        count = pigeon.sweep_all(username)
        return {'success': True, 'swept': count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post('/api/pigeon/drop')
async def pigeon_drop(request: Request):
    """Universal safe-app drop point. Routes by topic to the correct Willow agent."""
    try:
        dropping = await request.json()
        from core import pigeon
        return pigeon.receive_drop(dropping)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get('/api/pigeon/inbox')
async def pigeon_inbox_get(app_id: str, username: str = 'Sweet-Pea-Rudi19', unread_only: bool = True):
    """Fetch inbox messages for an app_id.
    GET /api/pigeon/inbox?app_id=ganesha-cli&unread_only=true
    """
    try:
        from core import pigeon
        messages = pigeon.get_inbox(app_id, username, unread_only)
        return {'ok': True, 'app_id': app_id, 'messages': messages, 'count': len(messages)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post('/api/pigeon/inbox/{message_id}/read')
async def pigeon_inbox_mark_read(message_id: int, app_id: str):
    """Mark a single inbox message as read.
    POST /api/pigeon/inbox/42/read?app_id=ganesha-cli
    """
    try:
        from core import pigeon
        count = pigeon.mark_inbox_read(app_id, message_id)
        return {'ok': True, 'marked': count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post('/api/pigeon/inbox/read-all')
async def pigeon_inbox_mark_all_read(app_id: str):
    """Mark all inbox messages as read for an app."""
    try:
        from core import pigeon
        count = pigeon.mark_inbox_read(app_id)
        return {'ok': True, 'marked': count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post('/api/pigeon/scan')
async def pigeon_scan(username: str = 'Sweet-Pea-Rudi19'):
    try:
        trigger = Path(f'artifacts/{username}/.pigeon_trigger')
        trigger.parent.mkdir(parents=True, exist_ok=True)
        trigger.touch()
        return {'success': True, 'new_droppings': 0, 'droppings': [], 'status': 'triggered'}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# User schema initialization
# ─────────────────────────────────────────────────────────────────────────────
@app.post("/api/user/init")
async def user_schema_init(username: str = "Sweet-Pea-Rudi19"):
    """Initialize PostgreSQL schema for this user.
    Creates private schema, moves user tables from public, registers in schema_registry.
    Safe to call multiple times -- idempotent.
    On SQLite: no-op, returns safe schema name only."""
    try:
        from core.db import init_user_schema, _safe_schema_name, is_postgres
        safe = init_user_schema(username)
        detail = {}
        if is_postgres():
            # Register in schema_registry
            import datetime
            from core.db import get_connection as _gc
            conn = _gc()
            now = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            conn.execute(
                "INSERT OR IGNORE INTO schema_registry (username, schema_name, created_at) "
                "VALUES (?, ?, ?)",
                (username, safe, now),
            )
            conn.commit()
            conn.close()
            detail["registered"] = True
        return {
            "success": True,
            "username": username,
            "schema": safe,
            "postgres": is_postgres(),
            **detail,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    from core.boot import boot_check

    status, cfg, msg = boot_check()
    if status == "already_running":
        print(f"[BOOT] {msg}")
        sys.exit(0)
    elif status == "conflict":
        print(f"[BOOT] ERROR: {msg}")
        print("[BOOT] Free port 8420 or change Willow port in ~/.willow/config.json")
        sys.exit(1)
    else:
        print(f"[BOOT] {msg}")  # start or stale_reclaimed

    print(f"Willow UI: http://{cfg.host}:{cfg.port}")
    from concurrent.futures import ThreadPoolExecutor
    import asyncio as _asyncio

    async def _setup_and_serve():
        loop = _asyncio.get_running_loop()
        loop.set_default_executor(ThreadPoolExecutor(max_workers=50, thread_name_prefix="willow"))
        config = uvicorn.Config(
            app,
            host=cfg.host,
            port=cfg.port,
            log_level="info",
            timeout_keep_alive=2,
            limit_concurrency=500,
            access_log=False,
        )
        server = uvicorn.Server(config)
        await server.serve()

    _asyncio.run(_setup_and_serve())

# BASE 17 Compact Communication Endpoint
@app.route('/api/compact', methods=['POST'])
def compact_request():
    """Handle BASE 17 compact format: task_id|action|params"""
    try:
        data = request.get_json()
        compact = data.get('compact', '')
        
        # Parse: task_id|action|params
        parts = compact.split('|')
        if len(parts) < 2:
            return jsonify({'error': 'Invalid format'}), 400
            
        task_id = parts[0]
        action = parts[1]
        params = parts[2] if len(parts) > 2 else ''
        
        # Route to agent based on action
        # TODO: Implement routing logic
        
        return jsonify({'task_id': task_id, 'result': 'acknowledged'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Agent Delivery Routing (EVERYTHING goes through Willow)
@app.route('/api/agents/deliver', methods=['POST'])
def agent_deliver():
    """Route agent deliveries through Willow to user Pickup folders."""
    try:
        data = request.get_json()
        
        # Validate
        required = ['from', 'to', 'destination', 'items']
        if not all(k in data for k in required):
            return jsonify({'error': 'Missing required fields'}), 400
        
        from_agent = data['from']
        to_user = data['to']
        destination = data['destination']
        items = data['items']
        
        # Log routing through Willow
        logging.info(f"WILLOW_ROUTING | {from_agent} → {to_user}/{destination} | {len(items)} items")
        
        # Route each item
        results = []
        for item in items:
            filename = item.get('filename')
            content = item.get('content')
            
            if not filename or not content:
                results.append({'filename': filename, 'status': 'ERROR', 'reason': 'missing data'})
                continue
            
            # Route through Willow to destination
            if destination == 'Pickup':
                from local_api import send_to_pickup
                success = send_to_pickup(filename, content, to_user)
                results.append({
                    'filename': filename,
                    'status': 'DELIVERED' if success else 'FAILED'
                })
            else:
                results.append({'filename': filename, 'status': 'ERROR', 'reason': 'unknown destination'})
        
        # Return receipt
        return jsonify({
            'from': from_agent,
            'to': to_user,
            'destination': destination,
            'routed_by': 'willow',
            'items': results,
            'status': 'COMPLETE'
        }), 200
        
    except Exception as e:
        logging.error(f"WILLOW_ROUTING_ERROR | {e}")
        return jsonify({'error': str(e)}), 500


@app.get("/api/pickup")
async def api_pickup_list(username: str = "Sweet-Pea-Rudi19"):
    """List files in the user's Pickup box."""
    try:
        gdrive = Path(r"G:\My Drive\Willow\Auth Users") / username / "Pickup"
        local = Path(__file__).parent / "artifacts" / "willow" / "Auth Users" / username / "Pickup"
        pickup_dir = gdrive if gdrive.exists() else local

        if not pickup_dir.exists():
            return {"items": [], "path": str(pickup_dir), "exists": False}

        items = []
        for f in sorted(pickup_dir.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
            if f.is_file() and not f.name.startswith('.') and f.suffix not in ('.pyc', '.db'):
                try:
                    file_content = f.read_text(encoding="utf-8", errors="replace")
                    preview = file_content[:200].strip()
                except Exception:
                    preview = "[binary]"
                items.append({
                    "filename": f.name,
                    "size": f.stat().st_size,
                    "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
                    "preview": preview,
                })
        return {"items": items, "path": str(pickup_dir), "exists": True}
    except Exception as e:
        return {"error": str(e), "items": []}


@app.delete("/api/pickup/{filename}")
async def api_pickup_dismiss(filename: str, username: str = "Sweet-Pea-Rudi19"):
    """Delete (dismiss) a file from the user's Pickup box."""
    try:
        gdrive = Path(r"G:\My Drive\Willow\Auth Users") / username / "Pickup"
        local = Path(__file__).parent / "artifacts" / "willow" / "Auth Users" / username / "Pickup"
        pickup_dir = gdrive if gdrive.exists() else local

        target = pickup_dir / filename
        if pickup_dir in target.parents and target.exists():
            target.unlink()
            return {"status": "ok", "deleted": filename}
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="File not found")
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# FLEET API — External repo integration endpoint
# Other repos (nasa-archive, safe-app-utety-chat, aios-minimal) call this
# instead of sys.path-hacking into core/llm_router.py directly.
# ---------------------------------------------------------------------------

@app.post("/api/fleet/ask")
async def fleet_ask(request: Request):
    """
    External fleet passthrough. Accepts prompt, returns LLM response.
    Replaces sys.path hacking in nasa-archive, safe-app-utety-chat, etc.

    Request body:
        prompt      (str, required)  — the prompt text
        tier        (str, optional)  — "free" (default), "cheap", "paid"
        source      (str, optional)  — caller identifier for logging
        username    (str, optional)  — user context (default: Sweet-Pea-Rudi19)

    Response:
        {"response": str, "provider": str, "tier": str, "source": str}
    """
    body = await request.json()
    prompt = body.get("prompt", "").strip()
    tier = body.get("tier", "free")
    source = body.get("source", "external")

    if not prompt:
        return {"error": "No prompt provided"}, 400

    try:
        from core import llm_router
        result = llm_router.ask(prompt, preferred_tier=tier)
        if not result:
            return {"error": "All providers failed", "source": source}
        return {
            "response": result.content,
            "provider": result.provider,
            "tier": result.tier,
            "source": source,
        }
    except Exception as e:
        return {"error": str(e), "source": source}


@app.get("/api/fleet/providers")
async def fleet_providers():
    """List all active fleet providers and their key status."""
    import os
    from core import llm_router
    providers = []
    for p in llm_router.PROVIDERS:
        has_key = (p.env_key == "PATH") or bool(os.environ.get(p.env_key))
        providers.append({
            "name": p.name,
            "model": p.model,
            "tier": p.tier,
            "active": has_key,
        })
    active = sum(1 for p in providers if p["active"])
    return {"providers": providers, "active": active, "total": len(providers)}


# ---------------------------------------------------------------------------
# LAW GAZELLE — Legal assistant routes
# Conversational legal Q&A, statute lookup, document generation
# Engine: safe-app-law-gazelle/src/gazelle_engine.py
# ---------------------------------------------------------------------------

_GAZELLE_ENGINE_PATH = Path(__file__).parent.parent / "safe-app-law-gazelle" / "src"

def _get_gazelle():
    import sys as _sys
    if str(_GAZELLE_ENGINE_PATH) not in _sys.path:
        _sys.path.insert(0, str(_GAZELLE_ENGINE_PATH))
    import gazelle_engine
    return gazelle_engine


@app.get("/gazelle")
async def serve_gazelle():
    from fastapi.responses import FileResponse
    p = Path(__file__).parent / "gazelle.html"
    if p.exists():
        return FileResponse(p)
    raise HTTPException(status_code=404, detail="gazelle.html not found")


def _ingest_pickup_for_gazelle(username: str) -> dict:
    """Scan Pickup box, ingest any unprocessed text files into the knowledge graph."""
    gdrive = Path(r"G:\My Drive\Willow\Auth Users") / username / "Pickup"
    local = Path(__file__).parent / "artifacts" / "willow" / "Auth Users" / username / "Pickup"
    pickup_dir = gdrive if gdrive.exists() else local

    ingested, skipped = [], []
    if not pickup_dir.exists():
        return {"ingested": ingested, "skipped": skipped}

    text_ext = {".txt", ".md", ".pdf", ".doc", ".docx", ".rtf", ".csv", ".json"}
    for f in pickup_dir.iterdir():
        if not f.is_file() or f.name.startswith(".") or f.suffix.lower() not in text_ext:
            skipped.append(f.name)
            continue
        try:
            content = f.read_text(encoding="utf-8", errors="replace")
            file_hash = __import__("hashlib").md5(content.encode()).hexdigest()
            loam.ingest_file_knowledge(
                username=username,
                filename=f.name,
                file_hash=file_hash,
                category="personal_document",
                content_text=content[:4000],
                provider="gazelle_pickup",
            )
            ingested.append(f.name)
        except Exception as ex:
            logging.warning(f"GAZELLE_PICKUP: failed to ingest {f.name}: {ex}")
            skipped.append(f.name)

    return {"ingested": ingested, "skipped": skipped}


def _get_willow_context(username: str) -> dict:
    """Pull relevant context from the knowledge graph for Gazelle pre-population."""
    legal_terms = "legal court bankruptcy debt financial dispute rights claim"
    results = loam.search(username, legal_terms, max_results=8)

    facts = []
    source_files = []
    for r in results:
        if r.get("summary"):
            facts.append(r["summary"])
        elif r.get("content_snippet"):
            facts.append(r["content_snippet"][:200])
        if r.get("title") and r["title"] not in source_files:
            source_files.append(r["title"])

    return {"facts": facts, "source_files": source_files}


@app.post("/api/binder/ingest-pickup")
async def binder_ingest_pickup(username: str = USERNAME):
    """Manually trigger ingestion of all Pickup box files into the knowledge graph."""
    try:
        result = _ingest_pickup_for_gazelle(username)
        return {"status": "ok", **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/binder/process-queue")
async def binder_process_queue(batch: int = 20, username: str = USERNAME):
    """Drain the OCR queue — process up to batch items from Pickup."""
    try:
        result = ocr_consumer.process_queue(username=username, max_batch=batch)
        return {"status": "ok", **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))




# --- File Organizer API ---

@app.get("/api/organizer/scan")
async def organizer_scan(username: str = USERNAME):
    try:
        files = file_organizer.scan_pickup(username)
        return {"status": "ok", "files": files, "count": len(files)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/organizer/rename")
async def organizer_rename(request: Request):
    try:
        body = await request.json()
        import pathlib as _pl
        file_path = _pl.Path(body["file_path"])
        new_stem = body["new_stem"]
        dry_run = body.get("dry_run", False)
        result = file_organizer.apply_rename(file_path, new_stem, dry_run=dry_run)
        return {"status": "ok", "new_path": str(result), "applied": not dry_run}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/organizer/move")
async def organizer_move(request: Request):
    try:
        body = await request.json()
        import pathlib as _pl
        file_path = _pl.Path(body["file_path"])
        category = body.get("category", "document")
        username = body.get("username", USERNAME)
        dry_run = body.get("dry_run", False)
        result = file_organizer.move_to_filed(file_path, category, username, dry_run=dry_run)
        return {"status": "ok", "destination": str(result), "applied": not dry_run}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/organizer/batch")
async def organizer_batch(request: Request):
    try:
        body = await request.json()
        username = body.get("username", USERNAME)
        auto_apply = body.get("auto_apply", False)
        results = file_organizer.batch_organize(username, auto_apply=auto_apply)
        applied = sum(1 for r in results if r.get("applied"))
        return {"status": "ok", "results": results, "total": len(results), "applied": applied}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/organizer/duplicates")
async def organizer_duplicates(username: str = USERNAME):
    try:
        groups = file_organizer.find_duplicates(username)
        return {"status": "ok", "groups": groups, "duplicate_sets": len(groups)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def _ocr_queue_background_loop():
    """Background thread: drain OCR queue every 5 minutes."""
    import time
    while True:
        try:
            result = ocr_consumer.process_queue(max_batch=10)
            if result.get("processed", 0) > 0:
                logging.info(f"OCR_BACKGROUND: processed={result['processed']} remaining={result['queue_remaining']}")
        except Exception as e:
            logging.warning(f"OCR_BACKGROUND error: {e}")
        time.sleep(300)  # 5 minutes


@app.post("/api/gazelle/session/start")
async def gazelle_session_start(request: Request):
    try:
        body = await request.json()
        user_name = body.get("user_name", "user")

        # Step 1: ingest any Pickup files not yet in knowledge graph
        ingest_result = _ingest_pickup_for_gazelle(USERNAME)

        # Step 2: pull relevant context from knowledge graph
        ctx = _get_willow_context(USERNAME)

        # Step 3: create session with context
        ge = _get_gazelle()
        result = ge.create_session(user_name, context=ctx if ctx["facts"] else None)
        result["pickup_ingested"] = ingest_result["ingested"]
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/gazelle/session/{session_id}")
async def gazelle_session_get(session_id: str):
    try:
        ge = _get_gazelle()
        session = ge.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        return session
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/gazelle/session/{session_id}")
async def gazelle_session_delete(session_id: str):
    try:
        ge = _get_gazelle()
        ge.delete_session(session_id)
        return {"status": "deleted", "message": "All session data deleted."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/gazelle/chat")
async def gazelle_chat(request: Request):
    try:
        body = await request.json()
        session_id = body.get("session_id", "")
        message = body.get("message", "")
        if not session_id or not message:
            raise HTTPException(status_code=400, detail="session_id and message required")
        ge = _get_gazelle()
        result = ge.process_message(session_id, message)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/gazelle/documents/{session_id}")
async def gazelle_documents(session_id: str):
    try:
        ge = _get_gazelle()
        docs = ge.get_documents(session_id)
        return {"documents": docs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- NASA archive static files ---
NASA_DIST = Path(__file__).parent.parent / "safe-app-nasa-archive" / "site" / "dist"
if NASA_DIST.exists():
    app.mount("/nasa", StaticFiles(directory=str(NASA_DIST)), name="nasa-dist")

# --- SAFE web static files ---
SAFE_WEB = Path(__file__).parent.parent / "SAFE" / "web"
if SAFE_WEB.exists():
    app.mount("/SAFE/web", StaticFiles(directory=str(SAFE_WEB)), name="safe-web")

# ── Calendar & Personal Todos ──────────────────────────────────────────────────

@app.get("/api/calendar/events")
def calendar_events_list(
    username: str = USERNAME,
    from_dt: str = None,
    to_dt: str = None,
    category: str = None,
):
    """Events in a date range. Defaults to next 30 days."""
    from datetime import datetime, timezone, timedelta
    from core.db import get_connection as _gc, is_postgres
    now = datetime.now(timezone.utc)
    start = from_dt or now.date().isoformat()
    end = to_dt or (now + timedelta(days=30)).date().isoformat()
    conn = _gc() if is_postgres() else _gc(loam._db_path(username))
    try:
        query = """
            SELECT * FROM calendar_events
            WHERE username = ? AND status = 'active'
              AND date(start_dt) >= date(?) AND date(start_dt) <= date(?)
        """
        params = [username, start, end]
        if category:
            query += " AND category = ?"
            params.append(category)
        query += " ORDER BY start_dt"
        rows = conn.execute(query, params).fetchall()
        return {"events": [dict(r) for r in rows]}
    finally:
        conn.close()


@app.get("/api/calendar/upcoming")
def calendar_upcoming(username: str = USERNAME, days: int = 14):
    """Next N days of events + open todos with due dates. For agent/Shiva use."""
    from datetime import datetime, timezone, timedelta
    from core.db import get_connection as _gc, is_postgres
    now = datetime.now(timezone.utc)
    end = (now + timedelta(days=days)).date().isoformat()
    today = now.date().isoformat()
    conn = _gc() if is_postgres() else _gc(loam._db_path(username))
    try:
        events = conn.execute("""
            SELECT id, title, start_dt, end_dt, all_day, category
            FROM calendar_events
            WHERE username = ? AND status = 'active'
              AND date(start_dt) >= date(?) AND date(start_dt) <= date(?)
            ORDER BY start_dt
        """, [username, today, end]).fetchall()
        todos = conn.execute("""
            SELECT id, title, due_date, priority, category
            FROM personal_todos
            WHERE username = ? AND status = 'open'
              AND due_date IS NOT NULL AND date(due_date) <= date(?)
            ORDER BY due_date, priority DESC
        """, [username, end]).fetchall()
        return {
            "events": [dict(r) for r in events],
            "todos": [dict(r) for r in todos],
        }
    finally:
        conn.close()


@app.post("/api/calendar/events")
async def calendar_event_create(request: Request):
    from datetime import datetime, timezone
    from core.db import get_connection as _gc, is_postgres
    body = await request.json()
    username = body.get("username") or USERNAME
    now = datetime.now(timezone.utc).isoformat()
    required = ("title", "start_dt")
    if not all(body.get(f) for f in required):
        return JSONResponse({"ok": False, "error": "title and start_dt required"}, status_code=400)
    conn = _gc() if is_postgres() else _gc(loam._db_path(username))
    try:
        cur = conn.execute("""
            INSERT INTO calendar_events
                (username, title, description, start_dt, end_dt, all_day,
                 category, recurrence, status, source, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)
        """, [
            username, body["title"], body.get("description"),
            body["start_dt"], body.get("end_dt"), int(body.get("all_day", 0)),
            body.get("category", "personal"), body.get("recurrence"),
            body.get("source", "manual"), now, now,
        ])
        conn.commit()
        return {"ok": True, "id": cur.lastrowid}
    finally:
        conn.close()


@app.patch("/api/calendar/events/{event_id}")
async def calendar_event_update(event_id: int, request: Request):
    from datetime import datetime, timezone
    from core.db import get_connection as _gc, is_postgres
    body = await request.json()
    username = body.get("username") or USERNAME
    now = datetime.now(timezone.utc).isoformat()
    allowed = {"title", "description", "start_dt", "end_dt", "all_day",
               "category", "recurrence", "status"}
    updates = {k: v for k, v in body.items() if k in allowed}
    if not updates:
        return JSONResponse({"ok": False, "error": "no valid fields"}, status_code=400)
    updates["updated_at"] = now
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [event_id, username]
    conn = _gc() if is_postgres() else _gc(loam._db_path(username))
    try:
        conn.execute(
            f"UPDATE calendar_events SET {set_clause} WHERE id = ? AND username = ?",
            values
        )
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@app.get("/api/calendar/todos")
def calendar_todos_list(username: str = USERNAME, status: str = "open", category: str = None):
    from core.db import get_connection as _gc, is_postgres
    conn = _gc() if is_postgres() else _gc(loam._db_path(username))
    try:
        query = "SELECT * FROM personal_todos WHERE username = ? AND status = ?"
        params = [username, status]
        if category:
            query += " AND category = ?"
            params.append(category)
        query += " ORDER BY CASE priority WHEN 'urgent' THEN 1 WHEN 'high' THEN 2 WHEN 'normal' THEN 3 ELSE 4 END, due_date"
        rows = conn.execute(query, params).fetchall()
        return {"todos": [dict(r) for r in rows]}
    finally:
        conn.close()


@app.post("/api/calendar/todos")
async def calendar_todo_create(request: Request):
    from datetime import datetime, timezone
    from core.db import get_connection as _gc, is_postgres
    body = await request.json()
    username = body.get("username") or USERNAME
    if not body.get("title"):
        return JSONResponse({"ok": False, "error": "title required"}, status_code=400)
    now = datetime.now(timezone.utc).isoformat()
    conn = _gc() if is_postgres() else _gc(loam._db_path(username))
    try:
        cur = conn.execute("""
            INSERT INTO personal_todos
                (username, title, description, due_date, priority,
                 status, category, source, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 'open', ?, ?, ?, ?)
        """, [
            username, body["title"], body.get("description"),
            body.get("due_date"), body.get("priority", "normal"),
            body.get("category", "personal"), body.get("source", "manual"),
            now, now,
        ])
        conn.commit()
        return {"ok": True, "id": cur.lastrowid}
    finally:
        conn.close()


@app.patch("/api/calendar/todos/{todo_id}")
async def calendar_todo_update(todo_id: int, request: Request):
    from datetime import datetime, timezone
    from core.db import get_connection as _gc, is_postgres
    body = await request.json()
    username = body.get("username") or USERNAME
    now = datetime.now(timezone.utc).isoformat()
    allowed = {"title", "description", "due_date", "priority", "status", "category"}
    updates = {k: v for k, v in body.items() if k in allowed}
    if not updates:
        return JSONResponse({"ok": False, "error": "no valid fields"}, status_code=400)
    updates["updated_at"] = now
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [todo_id, username]
    conn = _gc() if is_postgres() else _gc(loam._db_path(username))
    try:
        conn.execute(
            f"UPDATE personal_todos SET {set_clause} WHERE id = ? AND username = ?",
            values
        )
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


# --- Static file serving (production) — must be last to avoid shadowing API routes ---
if UI_DIST.exists():
    @app.get("/")
    def serve_index():
        return FileResponse(UI_DIST / "index.html")

    app.mount("/", StaticFiles(directory=str(UI_DIST)), name="static")

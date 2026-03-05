"""
Job Queue — Willow
==================
Async worker pool for LLM and Kart orchestration calls.
Keeps blocking calls off the event loop.

Two pools:
  - default (N_WORKERS=4)  — generic LLM calls via agent_engine / llm_router
  - kart    (KART_WORKERS=8) — Kart orchestration via rings.execute_task

Usage:
    # Generic LLM job
    job_id = await submit(fn, *args, **kwargs)

    # Kart orchestration job
    job_id = await submit_kart(task, username, notify_agent=None)

    # Poll either
    result = poll(job_id)   # {status, result, error, elapsed_ms}
"""
import asyncio
import uuid
import time
import logging
from typing import Callable, Optional

logger = logging.getLogger("job_queue")

# ── Job store ────────────────────────────────────────────────────────────────
_jobs: dict = {}          # job_id -> {status, result, error, created_at, pool}
JOB_TTL = 300             # seconds — prune completed jobs older than this

# ── Pool config ──────────────────────────────────────────────────────────────
N_WORKERS    = 4          # generic LLM pool
KART_WORKERS = 8          # Kart orchestration pool — ENGINEER trust, more capacity

_default_queue: Optional[asyncio.Queue] = None
_kart_queue:    Optional[asyncio.Queue] = None
_default_started = False
_kart_started    = False

USERNAME = "Sweet-Pea-Rudi19"


def _get_queue(pool: str) -> asyncio.Queue:
    global _default_queue, _kart_queue
    if pool == "kart":
        if _kart_queue is None:
            _kart_queue = asyncio.Queue()
        return _kart_queue
    if _default_queue is None:
        _default_queue = asyncio.Queue()
    return _default_queue


# ── Submit ───────────────────────────────────────────────────────────────────

async def submit(fn: Callable, *args, **kwargs) -> str:
    """Submit a blocking callable to the default LLM pool. Returns job_id immediately."""
    job_id = uuid.uuid4().hex[:8]
    _jobs[job_id] = {
        "status": "pending", "result": None, "error": None,
        "created_at": time.monotonic(), "pool": "default",
    }
    await _get_queue("default").put((job_id, fn, args, kwargs, None))
    await _ensure_default_workers()
    return job_id


async def submit_kart(task: str, username: str = USERNAME,
                      notify_agent: Optional[str] = None) -> str:
    """
    Submit an orchestration task to Kart's dedicated worker pool.

    Args:
        task:         Natural language task description
        username:     User context
        notify_agent: Agent name to notify via mailbox on completion (optional)

    Returns:
        job_id — poll with poll(job_id)
    """
    job_id = uuid.uuid4().hex[:8]
    _jobs[job_id] = {
        "status": "pending", "result": None, "error": None,
        "created_at": time.monotonic(), "pool": "kart",
        "notify_agent": notify_agent,
    }
    await _get_queue("kart").put((job_id, task, username, notify_agent))
    await _ensure_kart_workers()
    logger.info(f"QUEUE: kart job {job_id} submitted — task={task[:60]!r}")
    return job_id


# ── Poll ─────────────────────────────────────────────────────────────────────

def poll(job_id: str) -> dict:
    """Poll job status. Returns dict with status/result/error/elapsed_ms."""
    job = _jobs.get(job_id)
    if not job:
        return {"status": "not_found"}
    elapsed = time.monotonic() - job["created_at"]
    return {
        "status":     job["status"],
        "result":     job["result"],
        "error":      job["error"],
        "elapsed_ms": int(elapsed * 1000),
        "pool":       job.get("pool", "default"),
    }


# ── Prune ────────────────────────────────────────────────────────────────────

def _prune():
    now = time.monotonic()
    stale = [jid for jid, j in list(_jobs.items())
             if j["status"] in ("done", "error")
             and (now - j["created_at"]) > JOB_TTL]
    for jid in stale:
        del _jobs[jid]


# ── Workers ──────────────────────────────────────────────────────────────────

async def _default_worker():
    """Generic LLM worker. Runs blocking callables in thread executor."""
    loop = asyncio.get_event_loop()
    while True:
        job_id, fn, args, kwargs, _ = await _get_queue("default").get()
        _jobs[job_id]["status"] = "running"
        try:
            result = await loop.run_in_executor(None, lambda: fn(*args, **kwargs))
            _jobs[job_id]["status"] = "done"
            _jobs[job_id]["result"] = result
        except Exception as e:
            _jobs[job_id]["status"] = "error"
            _jobs[job_id]["error"] = str(e)
            logger.error(f"QUEUE: default job {job_id} failed: {e}")
        finally:
            _get_queue("default").task_done()
            _prune()


async def _kart_worker():
    """
    Kart orchestration worker.
    Calls rings.execute_task() in a thread executor (it's sync/blocking).
    On completion, notifies requesting agent via mailbox if notify_agent is set.
    """
    loop = asyncio.get_event_loop()
    while True:
        job_id, task, username, notify_agent = await _get_queue("kart").get()
        _jobs[job_id]["status"] = "running"
        logger.info(f"QUEUE: kart worker picked up job {job_id}")
        try:
            from core import rings
            result = await loop.run_in_executor(
                None,
                lambda: rings.execute_task(
                    username=username,
                    user_request=task,
                    agent_name="kart",
                )
            )
            _jobs[job_id]["status"] = "done"
            _jobs[job_id]["result"] = result
            logger.info(f"QUEUE: kart job {job_id} done")

            # Notify requesting agent via mailbox if requested
            if notify_agent:
                await _notify_agent(notify_agent, job_id, result, username)

        except Exception as e:
            _jobs[job_id]["status"] = "error"
            _jobs[job_id]["error"] = str(e)
            logger.error(f"QUEUE: kart job {job_id} failed: {e}")
        finally:
            _get_queue("kart").task_done()
            _prune()


async def _notify_agent(agent_name: str, job_id: str, result: dict, username: str):
    """Post job completion to agent's mailbox via Pigeon bus."""
    try:
        import httpx
        result_summary = result.get("result", str(result))[:500] if isinstance(result, dict) else str(result)[:500]
        drop = {
            "topic": "message",
            "app_id": "kart",
            "payload": {
                "from_agent": "kart",
                "to_agent": agent_name,
                "subject": f"Job {job_id} complete",
                "body": f"Kart job {job_id} finished.\n\nResult:\n{result_summary}",
                "username": username,
            },
        }
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post("http://localhost:8420/api/pigeon/drop", json=drop)
        logger.info(f"QUEUE: notified {agent_name} of job {job_id} completion")
    except Exception as e:
        logger.warning(f"QUEUE: mailbox notify failed for {agent_name}: {e}")


# ── Worker lifecycle ──────────────────────────────────────────────────────────

async def _ensure_default_workers():
    global _default_started
    if not _default_started:
        _default_started = True
        for _ in range(N_WORKERS):
            asyncio.create_task(_default_worker())
        logger.info(f"QUEUE: started {N_WORKERS} default workers")


async def _ensure_kart_workers():
    global _kart_started
    if not _kart_started:
        _kart_started = True
        for _ in range(KART_WORKERS):
            asyncio.create_task(_kart_worker())
        logger.info(f"QUEUE: started {KART_WORKERS} kart workers")


def queue_depth() -> dict:
    """Return current queue depths and job counts by status."""
    statuses = {}
    for j in _jobs.values():
        statuses[j["status"]] = statuses.get(j["status"], 0) + 1
    return {
        "default_depth": _default_queue.qsize() if _default_queue else 0,
        "kart_depth":    _kart_queue.qsize() if _kart_queue else 0,
        "jobs":          statuses,
    }

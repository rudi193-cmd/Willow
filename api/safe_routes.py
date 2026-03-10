"""
SAFE API Routes
================
Consent management + knowledge query endpoints for SAFE OS web clients.

Endpoints:
  POST /api/safe/consent/grant    — grant session consent (4h TTL)
  POST /api/safe/consent/revoke   — revoke consent
  GET  /api/safe/consent/status   — check consent status
  GET  /api/safe/query            — query willow_knowledge.db
  GET  /api/safe/health           — system health

Consent is in-memory (sessions lost on server restart — intentional).
Knowledge queries hit willow_knowledge.db with optional full-text search.

CHECKSUM: ΔΣ=42
"""

from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from core.db import get_connection

# Health monitor (ported from Willow1.1)
try:
    from core.health import check_node_health
except ImportError:
    check_node_health = None

router = APIRouter(prefix="/api/safe", tags=["safe"])

# ── In-memory consent sessions ─────────────────────────────────────────────
# {session_id: {"scope": str, "granted_at": datetime, "expires": datetime}}
_sessions: dict = {}

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
}


def _db():
    """Open a connection to the knowledge DB."""
    return get_connection()


def _prune_expired():
    """Remove expired sessions from memory."""
    now = datetime.now()
    expired = [sid for sid, s in _sessions.items() if s["expires"] < now]
    for sid in expired:
        del _sessions[sid]


# ── Models ─────────────────────────────────────────────────────────────────

class ConsentGrantRequest(BaseModel):
    session_id: str
    scope: str = "web"
    duration_hours: Optional[int] = None  # 1-24. None defaults to 4hrs.

class ConsentRevokeRequest(BaseModel):
    session_id: str


# ── Consent endpoints ──────────────────────────────────────────────────────

@router.post("/consent/grant")
def grant_consent(body: ConsentGrantRequest):
    _prune_expired()
    hours = min(int(body.duration_hours), 24) if body.duration_hours else 4
    expires = datetime.now() + timedelta(hours=hours)
    _sessions[body.session_id] = {
        "scope": body.scope,
        "granted_at": datetime.now().isoformat(),
        "expires": expires,
        "duration_hours": hours,
    }
    return JSONResponse(
        {"ok": True, "token": body.session_id, "expires": expires.isoformat(), "duration_hours": hours},
        headers=CORS_HEADERS,
    )


@router.post("/consent/revoke")
def revoke_consent(body: ConsentRevokeRequest):
    _sessions.pop(body.session_id, None)
    return JSONResponse({"ok": True}, headers=CORS_HEADERS)


@router.get("/consent/status")
def consent_status(session_id: str = Query(...)):
    _prune_expired()
    s = _sessions.get(session_id)
    if s and s["expires"] > datetime.now():
        return JSONResponse(
            {"active": True, "expires": s["expires"].isoformat()},
            headers=CORS_HEADERS,
        )
    return JSONResponse({"active": False, "expires": None}, headers=CORS_HEADERS)


# ── Knowledge query ────────────────────────────────────────────────────────

@router.get("/query")
def query_knowledge(
    q: Optional[str] = Query(None, description="Full-text search query"),
    category: Optional[str] = Query(None),
    ring: str = Query("bridge"),
    lattice_domain: Optional[str] = Query(None, description="23³ domain axis (e.g. archive, docs, personas)"),
    lattice_type: Optional[str] = Query(None, description="23³ type axis (e.g. snapshot, grounding, ledger)"),
    lattice_status: Optional[str] = Query(None, description="23³ status axis (e.g. live, archived, draft)"),
    limit: int = Query(20, le=100),
):
    try:
        conn = _db()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Knowledge DB unavailable: {e}")

    try:
        if q:
            # Full-text search via Postgres tsvector, with optional lattice post-filters
            conditions = [
                "to_tsvector('english', coalesce(title,'') || ' ' || coalesce(content_snippet,'')) @@ plainto_tsquery('english', %s)"
            ]
            params: list = [q]
            if lattice_domain:
                conditions.append("lattice_domain = %s")
                params.append(lattice_domain)
            if lattice_type:
                conditions.append("lattice_type = %s")
                params.append(lattice_type)
            if lattice_status:
                conditions.append("lattice_status = %s")
                params.append(lattice_status)
            sql = f"""
                SELECT id, title, summary, content_snippet,
                       category, source_type, created_at,
                       lattice_domain, lattice_type, lattice_status,
                       ts_rank(
                           to_tsvector('english', coalesce(title,'') || ' ' || coalesce(content_snippet,'')),
                           plainto_tsquery('english', %s)
                       ) AS rank
                FROM knowledge
                WHERE {' AND '.join(conditions)}
                ORDER BY rank DESC
                LIMIT %s
            """
            params = [q] + params + [limit]
            rows = conn.execute(sql, params).fetchall()
        else:
            # Filter by category / ring / lattice axes
            conditions = ["1=1"]
            params = []
            if category:
                conditions.append("category = %s")
                params.append(category)
            if ring:
                conditions.append("ring = %s")
                params.append(ring)
            if lattice_domain:
                conditions.append("lattice_domain = %s")
                params.append(lattice_domain)
            if lattice_type:
                conditions.append("lattice_type = %s")
                params.append(lattice_type)
            if lattice_status:
                conditions.append("lattice_status = %s")
                params.append(lattice_status)
            sql = f"""
                SELECT id, title, summary, content_snippet,
                       category, source_type, created_at,
                       lattice_domain, lattice_type, lattice_status
                FROM knowledge
                WHERE {' AND '.join(conditions)}
                ORDER BY created_at DESC
                LIMIT %s
            """
            params.append(limit)
            rows = conn.execute(sql, params).fetchall()

        results = [dict(r) for r in rows]
        return JSONResponse(
            {"results": results, "count": len(results)},
            headers=CORS_HEADERS,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB error: {e}")
    finally:
        conn.close()


# ── Health ─────────────────────────────────────────────────────────────────

@router.get("/health")
def safe_health():
    _prune_expired()
    db_ok = False
    db_count = 0
    try:
        conn = get_connection()
        db_count = conn.execute("SELECT COUNT(*) FROM knowledge").fetchone()[0]
        conn.close()
        db_ok = True
    except Exception:
        db_ok = False

    lattice_domains = {}
    if db_ok:
        try:
            conn = get_connection()
            for row in conn.execute(
                "SELECT lattice_domain, COUNT(*) FROM knowledge WHERE lattice_domain IS NOT NULL GROUP BY lattice_domain ORDER BY 2 DESC"
            ):
                lattice_domains[row[0]] = row[1]
            conn.close()
        except Exception:
            pass

    # Watcher liveness (check PID lock file)
    lock_file = Path(r"C:\Users\Sean\.willow\watcher.lock")
    watcher_alive = False
    if lock_file.exists():
        try:
            import ctypes
            pid = int(lock_file.read_text().strip())
            handle = ctypes.windll.kernel32.OpenProcess(0x0400, False, pid)
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
                watcher_alive = True
        except Exception:
            pass

    # OCR queue depth
    pickup_path = Path(r"C:\Users\Sean\My Drive\Willow\Auth Users\Sweet-Pea-Rudi19\Pickup")
    ocr_queue_depth = len(list(pickup_path.glob("ocr_queue_*.json"))) if pickup_path.exists() else 0

    # Node health (fresh within last hour)
    node_health = {}
    if check_node_health:
        try:
            node_health = {
                k: {"status": v["status"], "last_update": v.get("last_update")}
                for k, v in check_node_health(stale_threshold_hours=1).items()
                if v["status"] != "no_db"
            }
        except Exception:
            pass

    return JSONResponse(
        {
            "status": "ok",
            "consent_sessions": len(_sessions),
            "db_reachable": db_ok,
            "knowledge_count": db_count,
            "lattice_domains": lattice_domains,
            "watcher_alive": watcher_alive,
            "ocr_queue_depth": ocr_queue_depth,
            "nodes": node_health,
        },
        headers=CORS_HEADERS,
    )

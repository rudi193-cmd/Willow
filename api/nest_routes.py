"""
nest_routes.py — Nest review queue endpoints.

GET  /api/nest/queue          → pending items for current user
POST /api/nest/scan           → trigger Nest scan, stage new files
GET  /api/nest/queue/{id}     → single item detail
POST /api/nest/review/{id}    → confirm/correct/dispose an item
DELETE /api/nest/queue/{id}   → skip item (no processing)

ΔΣ=42
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

DEFAULT_USERNAME = "Sweet-Pea-Rudi19"

router = APIRouter(prefix="/api/nest", tags=["nest"])


# ── Auth helper ────────────────────────────────────────────────────────────────

def _get_username(request: Request, username: Optional[str] = None) -> str:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
        try:
            from api.auth_routes import _parse_token
            parsed = _parse_token(token)
            if parsed:
                return parsed["username"]
        except Exception:
            pass
    return username or DEFAULT_USERNAME


# ── Models ─────────────────────────────────────────────────────────────────────

class ReviewDecision(BaseModel):
    user_summary:  Optional[str] = None
    user_category: Optional[str] = None
    user_path:     Optional[str] = None
    dispose_file:  bool = False
    dispose_data:  bool = False
    move_file:     bool = False


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/queue")
async def get_queue(request: Request, username: Optional[str] = None, status: str = "pending"):
    """Return review queue items for the current user."""
    from core.nest_intake import get_queue
    uname = _get_username(request, username)
    items = get_queue(uname, status=status)
    # Trim OCR text for the list view
    for item in items:
        if item.get("ocr_text"):
            item["ocr_preview"] = item["ocr_text"][:300]
        item.pop("ocr_text", None)
    return {"ok": True, "items": items, "count": len(items)}


@router.post("/scan")
async def scan_nest(request: Request, username: Optional[str] = None):
    """Scan the Nest directory and stage new files into the review queue."""
    from core.nest_intake import scan_nest
    uname = _get_username(request, username)
    try:
        staged = scan_nest(uname)
        return {
            "ok": True,
            "staged": len(staged),
            "items": [
                {
                    "id": s["id"],
                    "filename": s["filename"],
                    "proposed_category": s["proposed_category"],
                    "matched_entities": s.get("matched_entities", [])[:3],
                }
                for s in staged
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/queue/{item_id}")
async def get_queue_item(item_id: int, request: Request, username: Optional[str] = None):
    """Return full detail for a single review queue item."""
    from core.nest_intake import get_queue_item
    uname = _get_username(request, username)
    try:
        item = get_queue_item(uname, item_id)
        return {"ok": True, "item": item}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/review/{item_id}")
async def review_item(item_id: int, decision: ReviewDecision, request: Request, username: Optional[str] = None):
    """
    Confirm or correct a staged item.

    - dispose_file=false, dispose_data=false → move file to My Documents + ingest data
    - dispose_file=true,  dispose_data=false → delete file, ingest extracted data
    - dispose_file=true,  dispose_data=true  → delete file, discard everything
    """
    from core.nest_intake import confirm_review
    uname = _get_username(request, username)
    try:
        result = confirm_review(
            username=uname,
            item_id=item_id,
            user_summary=decision.user_summary,
            user_category=decision.user_category,
            user_path=decision.user_path,
            dispose_file=decision.dispose_file,
            dispose_data=decision.dispose_data,
            move_file=decision.move_file,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/queue/{item_id}")
async def skip_item(item_id: int, request: Request, username: Optional[str] = None):
    """Mark an item as skipped — leaves file in Nest, no processing."""
    from core.nest_intake import _connect
    from datetime import datetime, timezone
    uname = _get_username(request, username)
    conn = _connect(uname)
    try:
        conn.execute(
            "UPDATE nest_review_queue SET status='skipped', reviewed_at=? WHERE id=? AND username=?",
            (datetime.now(timezone.utc).isoformat(), item_id, uname)
        )
        conn.commit()
        return {"ok": True, "item_id": item_id, "status": "skipped"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


"""
NASA Archive API Routes
=======================
Serves North America Scootering Archive data only.
Does NOT expose personal Willow knowledge.
DS=42
"""

import json, re
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter(prefix="/api/nasa", tags=["nasa"])
NASA_DATA = Path(r"C:\Users\Sean\Documents\GitHub\safe-app-nasa-archive\data")
NASA_APPS_DIR = Path(r"C:\Users\Sean\Willow\Apps\nasa-archive")  # per SAFE_APP_CONNECTION.md
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
}

def _load(fn):
    f = NASA_DATA / fn
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}

def _norm(t):
    return re.sub(r"[^a-z0-9 ]", " ", str(t).lower()).strip()

@router.get("/stats")
def nasa_stats():
    d = _load("index.json")
    return JSONResponse({"rallies": d.get("rallies",0), "total_photos_mapped": d.get("total_photos_mapped",0), "patches": d.get("patches",0), "calendar_entries": d.get("calendar_entries",0)}, headers=CORS_HEADERS)

@router.get("/rallies")
def list_rallies(year: Optional[int]=Query(None), q: Optional[str]=Query(None), limit: int=Query(50,le=200), offset: int=Query(0)):
    rs = _load("index.json").get("rallies_list", [])
    if year: rs = [r for r in rs if r.get("year") == year]
    if q:
        n = _norm(q)
        rs = [r for r in rs if n in _norm(r.get("title","")) or n in _norm(r.get("location","") or "")]
    total = len(rs); page = rs[offset:offset+limit]
    return JSONResponse({"results": page, "count": len(page), "total": total}, headers=CORS_HEADERS)

@router.get("/rally/{slug:path}")
def get_rally(slug: str):
    # Normalize: index uses "2012/08/campscoot", dirs use "2012-08-campscoot"
    norm = slug.replace("/", "-")
    # Primary: directory structure from build_data.py
    meta_f = NASA_DATA / "rallies" / norm / "meta.json"
    if meta_f.exists():
        meta = json.loads(meta_f.read_text(encoding="utf-8"))
        photos_f = NASA_DATA / "rallies" / norm / "photos.json"
        if photos_f.exists():
            meta["photos"] = json.loads(photos_f.read_text(encoding="utf-8"))
        return JSONResponse(meta, headers=CORS_HEADERS)
    # Fallback: flat JSON file (legacy)
    f = NASA_DATA / "rallies" / f"{norm}.json"
    if f.exists(): return JSONResponse(json.loads(f.read_text(encoding="utf-8")), headers=CORS_HEADERS)
    # Last resort: index lookup (handles both slash and hyphen formats)
    matches = [r for r in _load("index.json").get("rallies_list",[]) if r.get("slug") in (slug, norm)]
    if not matches: raise HTTPException(404, detail=f"Rally not found: {slug}")
    return JSONResponse(matches[0], headers=CORS_HEADERS)

# ── Community contribution routes ────────────────────────────────────────────

class _NasaSession(BaseModel):
    type: str = "nasa_memory"
    version: str = "1.0"
    rally: str
    rally_title: str = ""
    session_id: str
    timestamp: str
    photos_tagged: list = []
    album_claim: Optional[str] = None
    oral_history: list = []
    contributed: bool = False

class _NasaStory(BaseModel):
    rally_slug: str
    narrator_name: str
    content: str
    correction: Optional[str] = None
    capture_date: str

@router.post("/contribute")
def nasa_contribute(session: _NasaSession):
    try:
        dest = NASA_APPS_DIR / "intake"
        dest.mkdir(parents=True, exist_ok=True)
        (dest / f"{session.session_id}.json").write_text(
            json.dumps(session.dict(), indent=2), encoding="utf-8"
        )
        return {"ok": True, "session_id": session.session_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/story")
def nasa_story(story: _NasaStory):
    try:
        dest = NASA_APPS_DIR / "stories"
        dest.mkdir(parents=True, exist_ok=True)
        path = dest / f"{story.rally_slug}.json"
        stories = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        stories.append(story.dict())
        path.write_text(json.dumps(stories, indent=2), encoding="utf-8")
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/stories")
def nasa_stories(rally: str = Query(...)):
    path = NASA_APPS_DIR / "stories" / f"{rally}.json"
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/query")
def nasa_query(q: Optional[str]=Query(None), category: Optional[str]=Query(None), limit: int=Query(50,le=200), offset: int=Query(0)):
    cat = (category or "rallies").lower()
    results = []
    if cat in ("rallies", "all"):
        rs = _load("index.json").get("rallies_list", [])
        if q:
            n = _norm(q)
            rs = [r for r in rs if n in _norm(r.get("title","")) or n in _norm(str(r.get("year",""))) or n in _norm(r.get("location","") or "")]
        for r in rs:
            results.append({"id": r.get("slug"), "title": r.get("title",""), "category": "rallies", "source_type": "rally", "created_at": r.get("date_rally"), "summary": f"{r.get('photo_count',0)} photos", "content_snippet": r.get("url",""), "year": r.get("year"), "photo_count": r.get("photo_count",0), "url": r.get("url"), "slug": r.get("slug")})
    if cat in ("calendar", "all"):
        entries = _load("calendar.json")
        if isinstance(entries, dict): entries = entries.get("entries", [])
        if q:
            n = _norm(q)
            entries = [e for e in entries if n in _norm(str(e))]
        for e in entries:
            results.append({"id": e.get("slug") or e.get("id"), "title": e.get("title") or e.get("name",""), "category": "calendar", "source_type": "event", "created_at": e.get("date"), "summary": e.get("description","")})
    total = len(results); page = results[offset:offset+limit]
    return JSONResponse({"results": page, "count": len(page), "total": total}, headers=CORS_HEADERS)

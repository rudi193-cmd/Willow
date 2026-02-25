"""
Journal API Routes
==================
REST API for journal_engine.py — session management + event appending.
Powers Jane's chat journaling and atom extraction pipeline.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any

import sys
sys.path.insert(0, "C:/Users/Sean/Documents/GitHub/Willow")
from core import journal_engine

router = APIRouter(prefix="/api/journal", tags=["journal"])


class SessionStartRequest(BaseModel):
    username: str


class EventRequest(BaseModel):
    username: str
    session_id: str
    event_type: str
    payload: Dict[str, Any]


class SessionEndRequest(BaseModel):
    username: str
    session_id: str


@router.post("/session/start")
def journal_start(req: SessionStartRequest):
    session_id = journal_engine.create_session(req.username)
    return {"success": True, "session_id": session_id}


@router.post("/event")
def journal_event(req: EventRequest):
    ok = journal_engine.append_event(req.username, req.session_id, req.event_type, req.payload)
    if not ok:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"success": True}


@router.post("/session/end")
def journal_end(req: SessionEndRequest):
    ok = journal_engine.end_session(req.username, req.session_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"success": True, "message": "Session ended — atom extraction queued"}


@router.get("/sessions")
def journal_sessions(username: str, date: Optional[str] = None):
    sessions = journal_engine.list_sessions(username, date)
    return {"sessions": sessions, "total": len(sessions)}


@router.get("/session/{session_id}")
def journal_read(session_id: str, username: str):
    events = journal_engine.read_session(username, session_id)
    return {"session_id": session_id, "events": events, "count": len(events)}

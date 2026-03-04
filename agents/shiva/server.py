"""
Shiva — SAFE Consumer Interface Server
======================================
Shiva's own FastAPI server at port 8421 (assigned by Willow).
Proxies chat to Willow's agent API, journals all exchanges.
Normal users interact with Willow's system through Shiva — never directly.
"""

import httpx
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pathlib import Path
from typing import Optional, List, Dict, Any

WILLOW_URL = "http://localhost:8420"
SHIVA_PORT = 8421
STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Shiva", description="SAFE Consumer Interface — Willow")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


class ChatRequest(BaseModel):
    message: str
    username: str = "Sweet-Pea-Rudi19"
    session_id: Optional[str] = None
    conversation_history: Optional[List[Dict]] = None


@app.get("/")
async def root():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.post("/chat")
async def chat(req: ChatRequest):
    """Chat with Shiva. Proxies to Willow agent API and journals both sides."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        # Call Willow's Shiva agent
        r = await client.post(
            f"{WILLOW_URL}/api/agents/chat/shiva",
            json={
                "message": req.message,
                "conversation_history": req.conversation_history or []
            }
        )
        result = r.json()

        # Journal both sides if session is active
        if req.session_id:
            try:
                await client.post(f"{WILLOW_URL}/api/journal/event", json={
                    "username": req.username,
                    "session_id": req.session_id,
                    "event_type": "user.message",
                    "payload": {"text": req.message}
                })
                response_text = result.get("response") or result.get("message", "")
                if response_text:
                    await client.post(f"{WILLOW_URL}/api/journal/event", json={
                        "username": req.username,
                        "session_id": req.session_id,
                        "event_type": "shiva.response",
                        "payload": {"text": response_text}
                    })
            except Exception:
                pass  # Journal failure never breaks chat

        return result


@app.post("/session/start")
async def session_start(body: dict):
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{WILLOW_URL}/api/journal/session/start", json=body)
        return r.json()


@app.post("/session/end")
async def session_end(body: dict):
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{WILLOW_URL}/api/journal/session/end", json=body)
        return r.json()


@app.get("/sessions")
async def sessions(username: str = "Sweet-Pea-Rudi19"):
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{WILLOW_URL}/api/journal/sessions?username={username}")
        return r.json()


@app.get("/status")
async def status():
    """Proxy system status from Willow for sidebar."""
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            r = await client.get(f"{WILLOW_URL}/api/system/status")
            data = r.json()
            return {
                "willow_online": True,
                "governance_pending": data.get("governance", {}).get("pending_commits", 0),
                "providers": data.get("providers", {}),
            }
        except Exception:
            return {"willow_online": False, "governance_pending": 0}


if __name__ == "__main__":
    print(f"Shiva starting on port {SHIVA_PORT}...")
    uvicorn.run(app, host="0.0.0.0", port=SHIVA_PORT, log_level="info")

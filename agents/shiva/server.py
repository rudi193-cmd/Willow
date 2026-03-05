"""
Shiva — SAFE Consumer Interface Server
======================================
Shiva's own FastAPI server at port 2121.
Proxies chat to Willow's agent API, journals all exchanges.
Normal users interact with Willow's system through Shiva — never directly.
"""

import sys
import httpx
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pathlib import Path
from typing import Optional, List, Dict, Any

# Core imports for agent CLI channel
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
try:
    from core.n2n_packets import N2NPacket, PacketType
    from core import command_parser, tool_engine, agent_registry
    _AGENT_CHANNEL = True
except ImportError:
    _AGENT_CHANNEL = False

WILLOW_URL = "http://127.0.0.1:8420"
SHIVA_PORT = 2121
SHIVA_NODE = "shiva"
USERNAME = "Sweet-Pea-Rudi19"
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


# ── Agent CLI Channel ─────────────────────────────────────────────────────────
# Backend agent-to-agent communication via CLI commands, not chat.
# WIRE-12 N2N packet envelope. No LLM. Deterministic.

@app.post("/agent/exec")
async def agent_exec(body: dict):
    """
    CLI command channel for agent-to-agent communication.
    Accepts a WIRE-12 N2N DELTA packet with payload.command (string).
    Routes through command_parser → tool_engine. No LLM involved.
    Returns a WIRE-12 N2N DELTA response packet.
    """
    if not _AGENT_CHANNEL:
        return {"ok": False, "error": "agent_channel_unavailable"}

    if not N2NPacket.validate_packet(body):
        return {"ok": False, "error": "invalid_packet"}

    header = body["header"]
    payload = body["payload"]
    source = header["source_node"]
    command = payload.get("command", "").strip()
    session_id = payload.get("session_id", "")

    if not command:
        return {"ok": False, "error": "missing_command"}

    parsed = command_parser.parse_command(command)

    if parsed is None:
        result = {"ok": False, "parsed": False, "error": "unrecognized_command"}
    else:
        try:
            tool_result = tool_engine.execute(
                tool_name=parsed.get("tool", ""),
                params=parsed.get("params", {}),
                agent=SHIVA_NODE,
                username=USERNAME,
            )
            result = {"ok": True, "parsed": True, "tool": parsed.get("tool"), "result": tool_result}
        except Exception as e:
            result = {"ok": False, "parsed": True, "tool": parsed.get("tool"), "error": str(e)}

    response_packet = N2NPacket.create_packet(
        PacketType.DELTA,
        source_node=SHIVA_NODE,
        target_node=source,
        payload={**result, "session_id": session_id, "echo_command": command},
        intent="exec_response",
    )
    return response_packet


@app.get("/agent/mailbox")
async def agent_mailbox_read(unread_only: bool = True):
    """Read Shiva's mailbox. Async messages from other agents."""
    if not _AGENT_CHANNEL:
        return {"ok": False, "error": "agent_channel_unavailable"}
    messages = agent_registry.get_mailbox(USERNAME, SHIVA_NODE, unread_only)
    return {"ok": True, "messages": messages}


@app.post("/agent/mailbox")
async def agent_mailbox_send(body: dict):
    """
    Deposit a message into an agent's mailbox via Willow.
    Routes through Willow's /api/agents/{name}/message so all agents
    read from the same Postgres-backed store.
    File payloads route through Pigeon — this endpoint is for structured messages only.
    """
    from_agent = body.get("from_agent", "")
    to_agent = body.get("to_agent", SHIVA_NODE)
    subject = body.get("subject", "")
    message_body = body.get("body", "")
    thread_id = body.get("thread_id", "")

    if not from_agent or not subject or not message_body:
        return {"ok": False, "error": "missing from_agent, subject, or body"}

    async with httpx.AsyncClient(timeout=10.0) as client:
        drop = {
            "topic": "message",
            "app_id": SHIVA_NODE,
            "payload": {
                "from_agent": from_agent,
                "to_agent": to_agent,
                "subject": subject,
                "body": message_body,
                "thread_id": thread_id,
            },
        }
        r = await client.post(f"{WILLOW_URL}/api/pigeon/drop", json=drop)
        r.raise_for_status()

    return {"ok": True, "to": to_agent, "from": from_agent}


if __name__ == "__main__":
    print(f"Shiva starting on port {SHIVA_PORT}...")
    uvicorn.run(app, host="0.0.0.0", port=SHIVA_PORT, log_level="info")

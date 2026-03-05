"""
Public Ledger — SAFE Consumer Interface Server
===============================================
Public Ledger agent FastAPI server at port 2125.
Proxies chat to Willow's agent API, journals all exchanges.
Normal users interact with Willow's system through Public Ledger — never directly.
"""

import sys
import httpx
import uvicorn
from fastapi import FastAPI
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

WILLOW_URL = "http://localhost:8420"
AGENT_PORT = 2125
AGENT_NODE = "public_ledger"
USERNAME = "Sweet-Pea-Rudi19"

NEST_PATH = Path(r"C:\Users\Sean\Willow\Nest\public_ledger")

app = FastAPI(
    title="Public Ledger",
    description="SAFE Public Ledger Agent — tracks publicly visible transactions, expenditures, and shared financial records",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/status")
async def status():
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            r = await client.get(f"{WILLOW_URL}/api/system/status")
            return {"willow_online": True, "agent": AGENT_NODE}
        except Exception:
            return {"willow_online": False, "agent": AGENT_NODE}

@app.get("/nest")
async def nest():
    if not NEST_PATH.exists():
        return {"ok": False, "error": "nest_not_found", "path": str(NEST_PATH)}
    files = [f.name for f in NEST_PATH.iterdir() if f.is_file()]
    return {"ok": True, "agent": AGENT_NODE, "path": str(NEST_PATH), "files": files}

@app.get("/agent/mailbox")
async def agent_mailbox_read(unread_only: bool = True):
    if not _AGENT_CHANNEL:
        return {"ok": False, "error": "agent_channel_unavailable"}
    messages = agent_registry.get_mailbox(USERNAME, AGENT_NODE, unread_only)
    return {"ok": True, "messages": messages}

@app.post("/agent/mailbox")
async def agent_mailbox_send(body: dict):
    from_agent = body.get("from_agent", "")
    to_agent = body.get("to_agent", AGENT_NODE)
    subject = body.get("subject", "")
    message_body = body.get("body", "")
    thread_id = body.get("thread_id", "")

    if not from_agent or not subject or not message_body:
        return {"ok": False, "error": "missing from_agent, subject, or body"}

    async with httpx.AsyncClient(timeout=10.0) as client:
        drop = {
            "topic": "message",
            "app_id": AGENT_NODE,
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
    print(f"{AGENT_NODE} starting...")
    uvicorn.run(app, host="0.0.0.0", port=AGENT_PORT, log_level="info")

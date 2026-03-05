#!/usr/bin/env python3
"""
Willow MCP Server — Exposes Willow skills to Claude Desktop and Claude Code.

Uses Model Context Protocol (MCP) so agents can:
- Check system status
- Query and ingest knowledge
- Add journal entries
- Invoke personas
- Speak text via TTS
- Chat with Willow agents (Kart, Shiva, etc.)
- View governance proposals

Configure WILLOW_URL env var to override default base (http://127.0.0.1:8420).
"""

import asyncio
import json
import os
import sys
from pathlib import Path

import requests
import mcp.server.stdio
import mcp.types as types
from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.server import NotificationOptions

WILLOW_BASE = os.environ.get("WILLOW_URL", "http://127.0.0.1:8420")

server = Server("willow")


def _call(method: str, path: str, timeout: int = 10, **kwargs) -> dict:
    """Call the Willow API."""
    try:
        if method == "GET":
            r = requests.get(f"{WILLOW_BASE}{path}", timeout=timeout, **kwargs)
        else:
            r = requests.post(f"{WILLOW_BASE}{path}", timeout=timeout, **kwargs)
        return r.json()
    except Exception as e:
        return {"error": str(e)}


def _call_kart(message: str, context: str = None) -> dict:
    """
    Submit a Kart task via async_mode and poll until done (max 120s).
    Kart tasks run rings.execute_task() which takes 30-60s — sync mode always times out.
    """
    import time
    payload = {"message": message, "async_mode": True}
    if context:
        payload["context"] = context

    submit = _call("POST", "/api/agents/chat/kart", timeout=15, json=payload)
    job_id = submit.get("job_id")
    if not job_id:
        return submit  # error or unexpected response

    # Poll until done (max 120s, 2s intervals)
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        time.sleep(2)
        result = _call("GET", f"/api/agents/chat/job/{job_id}", timeout=10)
        status = result.get("status")
        if status in ("done", "completed", "error", "failed"):
            return result
    return {"error": "kart task timed out after 120s", "job_id": job_id}


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    """Declare available Willow tools."""
    return [
        # --- Existing tools ---
        types.Tool(
            name="willow_status",
            description="Check Willow system health — server, daemons, tunnel, disk usage.",
            inputSchema={"type": "object", "properties": {}}
        ),
        types.Tool(
            name="willow_query",
            description="Search Willow knowledge base for information.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "limit": {"type": "integer", "description": "Max results", "default": 10}
                },
                "required": ["query"]
            }
        ),
        types.Tool(
            name="willow_journal",
            description="Add a timestamped entry to the continuity ring journal.",
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "Journal entry text"},
                    "category": {"type": "string", "description": "Category (note, idea, task, etc.)", "default": "note"}
                },
                "required": ["content"]
            }
        ),
        types.Tool(
            name="willow_persona",
            description="Invoke a Willow persona (PA, Analyst, Archivist, Poet, Debugger) with a prompt.",
            inputSchema={
                "type": "object",
                "properties": {
                    "persona": {"type": "string", "description": "Persona name"},
                    "prompt": {"type": "string", "description": "Prompt for the persona"}
                },
                "required": ["persona", "prompt"]
            }
        ),
        types.Tool(
            name="willow_speak",
            description="Convert text to speech using Willow TTS router.",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to speak"},
                    "voice": {"type": "string", "description": "Voice ID (optional)"}
                },
                "required": ["text"]
            }
        ),
        types.Tool(
            name="willow_route",
            description="Route a file through Willow with content extraction and LLM analysis.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file": {"type": "string", "description": "Absolute path to file"}
                },
                "required": ["file"]
            }
        ),
        # --- New tools ---
        types.Tool(
            name="willow_agents",
            description="List all registered Willow agents with their trust levels and status.",
            inputSchema={"type": "object", "properties": {}}
        ),
        types.Tool(
            name="willow_chat",
            description="Chat with a specific Willow agent (e.g. kart, shiva, ganesha).",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent": {"type": "string", "description": "Agent name (e.g. kart, shiva)"},
                    "message": {"type": "string", "description": "Message to send to the agent"},
                    "context": {"type": "string", "description": "Optional context to include"}
                },
                "required": ["agent", "message"]
            }
        ),
        types.Tool(
            name="willow_knowledge_search",
            description="Full knowledge search returning rich knowledge atoms with metadata.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "limit": {"type": "integer", "description": "Max results", "default": 10},
                    "category": {"type": "string", "description": "Filter by category (optional)"}
                },
                "required": ["query"]
            }
        ),
        types.Tool(
            name="willow_knowledge_ingest",
            description="Add a document or text snippet to the Willow knowledge base.",
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "Text content to ingest"},
                    "title": {"type": "string", "description": "Title or source name"},
                    "category": {"type": "string", "description": "Category tag (optional)"},
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Additional tags (optional)"
                    }
                },
                "required": ["content", "title"]
            }
        ),
        types.Tool(
            name="willow_system_status",
            description="Full Willow system status — database, daemons, tunnel, workers, and health checks.",
            inputSchema={"type": "object", "properties": {}}
        ),
        types.Tool(
            name="willow_governance",
            description="View pending Willow governance proposals awaiting ratification.",
            inputSchema={
                "type": "object",
                "properties": {
                    "status": {"type": "string", "description": "Filter by status (default: pending)", "default": "pending"}
                }
            }
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    """Execute a Willow tool."""
    if name == "willow_status":
        result = _call("GET", "/api/skills/status")

    elif name == "willow_query":
        q = arguments.get("query", "")
        limit = arguments.get("limit", 10)
        result = _call("GET", f"/api/skills/query?q={q}&limit={limit}")

    elif name == "willow_journal":
        result = _call("POST", "/api/skills/journal", json={
            "content": arguments.get("content", ""),
            "category": arguments.get("category", "note")
        })

    elif name == "willow_persona":
        result = _call("POST", "/api/skills/persona", json={
            "persona": arguments.get("persona", "PA"),
            "prompt": arguments.get("prompt", "")
        })

    elif name == "willow_speak":
        result = _call("POST", "/api/tts/speak", json={
            "text": arguments.get("text", ""),
            "voice": arguments.get("voice", "default")
        })
        if isinstance(result, dict) and "error" in result:
            pass  # keep error
        else:
            result = {"success": True, "message": "Audio generated"}

    elif name == "willow_route":
        result = _call("POST", "/api/skills/route", json={
            "file": arguments.get("file", "")
        })

    elif name == "willow_agents":
        result = _call("GET", "/api/agents")

    elif name == "willow_chat":
        agent = arguments.get("agent", "")
        message = arguments.get("message", "")
        context = arguments.get("context")
        if agent == "kart":
            result = _call_kart(message, context)
        else:
            payload = {"message": message}
            if context:
                payload["context"] = context
            result = _call("POST", f"/api/agents/chat/{agent}", timeout=30, json=payload)

    elif name == "willow_knowledge_search":
        params = f"?q={arguments.get('query', '')}&limit={arguments.get('limit', 10)}"
        if "category" in arguments:
            params += f"&category={arguments['category']}"
        result = _call("GET", f"/api/knowledge/search{params}")

    elif name == "willow_knowledge_ingest":
        payload = {
            "content": arguments.get("content", ""),
            "title": arguments.get("title", ""),
        }
        if "category" in arguments:
            payload["category"] = arguments["category"]
        if "tags" in arguments:
            payload["tags"] = arguments["tags"]
        result = _call("POST", "/api/knowledge/ingest", json=payload)

    elif name == "willow_system_status":
        result = _call("GET", "/api/system/status")

    elif name == "willow_governance":
        status = arguments.get("status", "pending")
        result = _call("GET", f"/api/governance/list/{status}")

    else:
        result = {"error": f"Unknown tool: {name}"}

    return [types.TextContent(type="text", text=json.dumps(result, indent=2))]


async def main():
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="willow",
                server_version="1.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={}
                )
            )
        )


if __name__ == "__main__":
    asyncio.run(main())

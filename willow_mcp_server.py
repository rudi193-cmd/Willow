#!/usr/bin/env python3
"""
Willow MCP Server — Exposes Willow API to Claude Code as native MCP tools.

Runs as stdio transport (Claude Code launches it directly).
Wraps localhost:8420 HTTP endpoints.
"""

import os
import requests
from typing import Optional
from fastmcp import FastMCP

WILLOW = os.getenv("WILLOW_API_URL", "http://localhost:8420")
USERNAME = os.getenv("WILLOW_USERNAME", "Sweet-Pea-Rudi19")

mcp = FastMCP("willow")


def _get(path, params=None):
    try:
        r = requests.get(f"{WILLOW}{path}", params=params, timeout=10)
        return r.json()
    except Exception as e:
        return {"error": str(e)}


def _post(path, data):
    try:
        r = requests.post(f"{WILLOW}{path}", json=data, timeout=30)
        return r.json()
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def willow_status() -> dict:
    """Check Willow server health — ollama, gemini, claude, knowledge counts."""
    return _get("/api/status")


@mcp.tool()
def willow_system_status() -> dict:
    """Full system status including agents, daemons, and knowledge stats."""
    return _get("/api/knowledge/stats")


@mcp.tool()
def willow_knowledge_search(query: str, limit: int = 5) -> dict:
    """Search the Willow knowledge base. Returns matching knowledge atoms."""
    return _get("/api/knowledge/search", {"q": query, "limit": limit})


@mcp.tool()
def willow_query(query: str) -> dict:
    """General Willow query — searches knowledge, entities, and gaps."""
    results = {}
    results["knowledge"] = _get("/api/knowledge/search", {"q": query, "limit": 3})
    results["gaps"] = _get("/api/knowledge/gaps", {"limit": 5})
    return results


@mcp.tool()
def willow_chat(agent: str, message: str, context: Optional[str] = None) -> dict:
    """Chat with a Willow agent (willow, kart, ada, riggs, oakenscroll, etc.)."""
    body = {"message": message}
    if context:
        body["context"] = context
    return _post(f"/api/agents/chat/{agent}", body)


@mcp.tool()
def willow_agents() -> dict:
    """List all registered Willow agents."""
    return _get("/api/agents/list")


@mcp.tool()
def willow_journal(entry: str, category: str = "narrative") -> dict:
    """Log an entry to the Willow continuity ring via Pigeon."""
    from datetime import datetime
    body = {
        "username": USERNAME,
        "filename": f"journal_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
        "content_text": entry,
        "category": category,
        "provider": "ganesha",
    }
    return _post("/api/knowledge/ingest", body)


@mcp.tool()
def willow_knowledge_ingest(title: str, content: str, category: str = "narrative") -> dict:
    """Ingest a knowledge atom directly into Willow's knowledge graph."""
    body = {
        "username": USERNAME,
        "filename": title,
        "content_text": content,
        "category": category,
        "provider": "ganesha",
    }
    return _post("/api/knowledge/ingest", body)


@mcp.tool()
def willow_delta_sigma() -> dict:
    """ΔΣ = Σ(Δᵢ) — the sum of acknowledged unknowns. System health metric."""
    return _get("/api/knowledge/delta-sigma")


@mcp.tool()
def willow_persona(name: str) -> dict:
    """Get persona definition for a UTETY faculty member."""
    return _get(f"/api/agents/persona/{name}")


@mcp.tool()
def willow_governance() -> dict:
    """List pending governance proposals."""
    return _get("/api/governance/pending")


if __name__ == "__main__":
    mcp.run()  # stdio transport — Claude Code launches this

"""
compact_client.py — BASE 17 Compact Context Client

HTTP client for safe-apps to register, resolve, and handoff
compact contexts via Willow's /api/compact/* endpoints.

Drop this file into any safe-app repo, or import from Willow core.

Usage:
    from compact_client import register, resolve, ask_with_context

    # Register a rubric once
    rid = register(content="...", category="rubric", label="my-rubric")

    # Use it in any prompt — context resolved server-side
    response = ask_with_context(
        prompt="Score this paper...",
        context_ids=[rid],
    )

    # Or just inline the ref — llm_router resolves [CTX:XXXXX] automatically
    response = ask(prompt="Apply [CTX:{rid}] to this paper...")

Authority: Sean Campbell
System: Willow
ΔΣ=42
"""

import os
import json
import requests

_WILLOW_URL = os.environ.get("WILLOW_URL", "http://localhost:8420")
_TIMEOUT = 30


def register(content: str, category: str = "pattern", label: str = None,
             agent: str = None, ttl_hours: float = None, ctx_id: str = None) -> str:
    """Register a context block. Returns 5-char BASE 17 ID."""
    r = requests.post(f"{_WILLOW_URL}/api/compact/register", json={
        "content": content,
        "category": category,
        "label": label,
        "agent": agent,
        "ttl_hours": ttl_hours,
        "id": ctx_id,
    }, timeout=_TIMEOUT)
    data = r.json()
    if "error" in data:
        raise RuntimeError(data["error"])
    return data["id"]


def resolve(ctx_id: str) -> dict:
    """Resolve a BASE 17 ID. Returns {id, content, category, ...} or {found: False}."""
    r = requests.get(f"{_WILLOW_URL}/api/compact/resolve/{ctx_id}", timeout=_TIMEOUT)
    return r.json()


def find(label: str) -> dict:
    """Find context by label. Returns {id, content, ...} or {found: False}."""
    r = requests.get(f"{_WILLOW_URL}/api/compact/find", params={"label": label}, timeout=_TIMEOUT)
    return r.json()


def list_contexts(category: str = None, agent: str = None, limit: int = 50) -> list:
    """List registered contexts."""
    params = {"limit": limit}
    if category:
        params["category"] = category
    if agent:
        params["agent"] = agent
    r = requests.get(f"{_WILLOW_URL}/api/compact/list", params=params, timeout=_TIMEOUT)
    return r.json().get("contexts", [])


def handoff(what_happened: str, what_next: str, session_id: str = None,
            context_ids: list = None, agent: str = None) -> str:
    """Create an N2N handoff packet. Returns JSON string."""
    r = requests.post(f"{_WILLOW_URL}/api/compact/handoff", json={
        "what_happened": what_happened,
        "what_next": what_next,
        "session_id": session_id,
        "context_ids": context_ids,
        "agent": agent,
    }, timeout=_TIMEOUT)
    data = r.json()
    if "error" in data:
        raise RuntimeError(data["error"])
    return data["packet"]


def receive(packet_json: str) -> dict:
    """Receive and resolve a handoff packet. Returns resolved state."""
    r = requests.post(f"{_WILLOW_URL}/api/compact/receive", json={
        "packet": packet_json,
    }, timeout=_TIMEOUT)
    return r.json()


def ask_with_context(prompt: str, context_ids: list = None, tier: str = "free",
                     persona: str = None, source: str = "compact-client") -> dict:
    """Ask Willow with pre-shared compact context IDs resolved server-side.
    Uses the Pigeon bus 'ask' topic with context_ids in payload."""
    payload = {"prompt": prompt, "tier": tier, "context_ids": context_ids or []}
    if persona:
        payload["persona"] = persona
    r = requests.post(f"{_WILLOW_URL}/api/pigeon/drop", json={
        "topic": "ask",
        "app_id": source,
        "payload": payload,
    }, timeout=_TIMEOUT)
    return r.json()


def ask_fleet(prompt: str, context_ids: list = None, tier: str = "free",
              source: str = "compact-client") -> dict:
    """Ask via /api/fleet/ask with inline [CTX:] refs — resolved by llm_router.
    Use this when you don't need Pigeon bus routing."""
    if context_ids:
        refs = " ".join(f"[CTX:{cid}]" for cid in context_ids)
        prompt = f"{refs}\n\n{prompt}"
    r = requests.post(f"{_WILLOW_URL}/api/fleet/ask", json={
        "prompt": prompt,
        "tier": tier,
        "source": source,
    }, timeout=_TIMEOUT)
    return r.json()

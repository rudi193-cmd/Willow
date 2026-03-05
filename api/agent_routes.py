"""
Agent API Routes - Conversational Chat Endpoints

Provides HTTP API for conversational chat with any Willow agent.

GOVERNANCE: All operations validated through agent_engine + gate.py
COST: Free-tier routing only, $0.10/month/user target
AUTHOR: Willow Agent System
VERSION: 2.0
CHECKSUM: ΔΣ=42
"""

import asyncio
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

# Core imports
from core import agent_engine, agent_registry, agent_auth, job_queue

# Default username (TODO: get from auth context)
USERNAME = "Sweet-Pea-Rudi19"

# Limit concurrent LLM calls — prevents chat threads from starving fast endpoints
_chat_sem: Optional[asyncio.Semaphore] = None


def _get_chat_sem() -> asyncio.Semaphore:
    global _chat_sem
    if _chat_sem is None:
        _chat_sem = asyncio.Semaphore(8)
    return _chat_sem


# Create router
router = APIRouter(prefix="/api/agents", tags=["agents"])


# Request/Response models
class ChatRequest(BaseModel):
    """Request to chat with an agent."""
    message: str
    agent: Optional[str] = "willow"
    conversation_history: Optional[List[Dict[str, str]]] = None
    stream: Optional[bool] = False
    async_mode: Optional[bool] = False


class ChatResponse(BaseModel):
    """Chat response from agent."""
    response: str
    tool_calls: List[Dict[str, Any]]
    tokens_used: int
    agent: str
    pending_approval: Optional[bool] = False
    request_id: Optional[str] = None
    error: Optional[str] = None


# ============================================================================
# CONVERSATIONAL CHAT ENDPOINTS
# ============================================================================

@router.post("/chat")
@router.post("/chat/{agent_name}")
async def chat_with_agent(req: ChatRequest, agent_name: Optional[str] = None):
    """
    Conversational chat with any Willow agent.

    async_mode=false (default): awaits result, blocks until LLM responds
    async_mode=true: returns job_id immediately, poll GET /chat/job/{id}
    """
    agent = agent_name or req.agent or "willow"

    agent_info = agent_registry.get_agent(USERNAME, agent)
    if not agent_info:
        raise HTTPException(
            status_code=404,
            detail=f"Agent '{agent}' not found. Available agents: willow, kart, shiva, riggs, ada, gerald, steve"
        )

    if getattr(req, 'async_mode', False):
        if agent == "kart":
            job_id = await job_queue.submit_kart(
                task=req.message,
                username=USERNAME,
                notify_agent=None,
            )
        else:
            def _run():
                return agent_engine.chat(
                    username=USERNAME,
                    agent_name=agent,
                    message=req.message,
                    conversation_history=req.conversation_history,
                )
            job_id = await job_queue.submit(_run)
        return {"job_id": job_id, "status": "pending", "agent": agent}

    # Sync mode — cap concurrent LLM calls, then run in thread pool
    loop = asyncio.get_running_loop()
    async with _get_chat_sem():
        if agent == "kart":
            from core import rings
            raw = await loop.run_in_executor(
                None,
                lambda: rings.execute_task(
                    username=USERNAME,
                    user_request=req.message,
                    agent_name="kart",
                )
            )
            return {
                "response": raw.get("result", "Task completed"),
                "tool_calls": raw.get("steps", []),
                "provider": "rings",
                "tier": "direct",
                "agent": agent,
            }
        else:
            result = await loop.run_in_executor(
                None,
                lambda: agent_engine.chat(
                    username=USERNAME,
                    agent_name=agent,
                    message=req.message,
                    conversation_history=req.conversation_history,
                )
            )
            return result


@router.get("/chat/job/{job_id}")
async def poll_chat_job(job_id: str):
    """Poll async chat job status. Returns result when done."""
    return job_queue.poll(job_id)


def _build_agents_list() -> list:
    """Blocking: DB query + tool_engine per agent. Runs in thread executor."""
    from core import tool_engine
    agents_data = agent_registry.list_agents(USERNAME)
    agents = []
    for agent_data in agents_data:
        tools = tool_engine.list_tools(agent_data["name"], USERNAME)
        agents.append({
            "name": agent_data["name"],
            "display_name": agent_data["display_name"],
            "trust_level": agent_data["trust_level"],
            "agent_type": agent_data["agent_type"],
            "available_tools": len(tools),
            "registered_at": agent_data.get("registered_at"),
            "last_seen": agent_data.get("last_seen"),
        })
    return agents


@router.get("/list")
async def list_agents():
    """List all registered agents."""
    try:
        loop = asyncio.get_running_loop()
        agents = await loop.run_in_executor(None, _build_agents_list)
        return {"agents": agents}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{agent_name}/profile")
async def get_agent_profile(agent_name: str):
    """
    Get agent profile and capabilities.

    Returns:
        {
            "name": "shiva",
            "display_name": "Shiva",
            "trust_level": "WORKER",
            "agent_type": "persona",
            "profile": "Full profile markdown content",
            "available_tools": [list of tools],
            "registered_at": "...",
            "last_seen": "..."
        }
    """
    try:
        # Get agent info
        agent_info = agent_registry.get_agent(USERNAME, agent_name)
        if not agent_info:
            raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")

        # Get tools
        from core import tool_engine
        tools = tool_engine.list_tools(agent_name, USERNAME)

        # Get profile content
        from pathlib import Path
        profile_path = Path(agent_info.get("profile_path", ""))
        profile_content = ""
        if profile_path.exists():
            profile_content = profile_path.read_text()

        return {
            "name": agent_name,
            "display_name": agent_info.get("display_name"),
            "trust_level": agent_info.get("trust_level"),
            "agent_type": agent_info.get("agent_type"),
            "profile": profile_content,
            "available_tools": [
                {
                    "name": t["name"],
                    "description": t["description"],
                    "required_trust": t["required_trust"]
                }
                for t in tools
            ],
            "registered_at": agent_info.get("registered_at"),
            "last_seen": agent_info.get("last_seen")
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{agent_name}/reset")
async def reset_agent_context(agent_name: str):
    """
    Reset agent conversation context (start fresh session).

    Returns:
        {"success": bool, "message": str}
    """
    try:
        # Verify agent exists
        agent_info = agent_registry.get_agent(USERNAME, agent_name)
        if not agent_info:
            raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")

        # Context is stored per-session in frontend, so this is just a confirmation
        return {
            "success": True,
            "message": f"Context reset signal sent for {agent_name}. Frontend should clear conversation history."
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# HEALTH CHECK
# ============================================================================

@router.get("/health")
async def agents_health():
    """
    Agent system health check.

    Returns:
        {
            "status": "ok",
            "registered_agents": int,
            "available_tools": int,
            "free_tier_providers": int
        }
    """
    try:
        agents = agent_registry.list_agents(USERNAME)

        from core import tool_engine
        all_tools = set()
        for agent in agents:
            tools = tool_engine.list_tools(agent["name"], USERNAME)
            all_tools.update([t["name"] for t in tools])

        # Count free tier providers
        from core import llm_router
        providers = len([
            p for p in llm_router.PROVIDERS
            if p.get("tier") == "free" or p.get("cost") == 0
        ])

        return {
            "status": "ok",
            "registered_agents": len(agents),
            "unique_tools": len(all_tools),
            "free_tier_providers": providers
        }

    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


class CheckinRequest(BaseModel):
    """Agent check-in request."""
    agent_name: str


class CheckinResponse(BaseModel):
    """Agent check-in response."""
    token: str
    trust_level: str
    expires_at: str
    agent_name: str
    pending: list = []


@router.post("/checkin", response_model=CheckinResponse)
async def agent_checkin(request: CheckinRequest):
    """
    Issue a 24h session token for a registered agent.
    Include as X-Willow-Agent header in subsequent requests.
    Trust level enforced based on DB registration.
    """
    try:
        result = agent_auth.checkin(request.agent_name)
        return CheckinResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


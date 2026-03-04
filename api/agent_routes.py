"""
Agent API Routes - Conversational Chat Endpoints

Provides HTTP API for conversational chat with any Willow agent.

GOVERNANCE: All operations validated through agent_engine + gate.py
COST: Free-tier routing only, $0.10/month/user target
AUTHOR: Willow Agent System
VERSION: 2.0
CHECKSUM: ΔΣ=42
"""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

# Core imports
from core import agent_engine, agent_registry, agent_auth

# Default username (TODO: get from auth context)
USERNAME = "Sweet-Pea-Rudi19"

# Create router
router = APIRouter(prefix="/api/agents", tags=["agents"])


# Request/Response models
class ChatRequest(BaseModel):
    """Request to chat with an agent."""
    message: str
    agent: Optional[str] = "willow"
    conversation_history: Optional[List[Dict[str, str]]] = None
    stream: Optional[bool] = False


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

    Path: /api/agents/chat or /api/agents/chat/{agent_name}

    Body:
        {
            "message": "User message",
            "agent": "willow" (optional, can also use path param),
            "conversation_history": [...] (optional),
            "stream": false (optional, for SSE streaming)
        }

    Returns:
        {
            "response": "Agent response",
            "tool_calls": [list of tools used],
            "tokens_used": int,
            "agent": "agent_name",
            "pending_approval": bool (if governance approval needed),
            "request_id": str (if pending approval)
        }
    """
    # Determine which agent to use
    agent = agent_name or req.agent or "willow"

    try:
        # Verify agent exists
        agent_info = agent_registry.get_agent(USERNAME, agent)
        if not agent_info:
            raise HTTPException(
                status_code=404,
                detail=f"Agent '{agent}' not found. Available agents: willow, kart, shiva, riggs, ada, gerald, steve"
            )

        # Chat with agent
        if req.stream:
            # TODO: Implement streaming (SSE)
            raise HTTPException(
                status_code=501,
                detail="Streaming not yet implemented. Use stream=false for now."
            )

        # Route to appropriate handler
        if agent == "kart":
            # Kart uses orchestrator directly (bypasses LLM tool parsing issues)
            from core import rings
            orchestrator_result = rings.execute_task(
                username=USERNAME,
                user_request=req.message,
                agent_name="kart"
            )

            # Convert orchestrator result to chat API format
            result = {
                "response": orchestrator_result.get("result", "Task completed"),
                "tool_calls": orchestrator_result.get("steps", []),
                "provider": "rings",
                "tier": "direct"
            }
        else:
            # Other agents use conversational chat
            result = agent_engine.chat(
                username=USERNAME,
                agent_name=agent,
                message=req.message,
                conversation_history=req.conversation_history,
                stream=False
            )

        # Add agent name to response
        result["agent"] = agent

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list")
async def list_agents():
    """
    List all registered agents.

    Returns:
        {
            "agents": [
                {
                    "name": "willow",
                    "display_name": "Willow",
                    "trust_level": "OPERATOR",
                    "agent_type": "persona",
                    "purpose": "...",
                    "available_tools": int
                },
                ...
            ]
        }
    """
    try:
        agents_data = agent_registry.list_agents(USERNAME)

        # Enrich with tool counts
        agents = []
        for agent_data in agents_data:
            from core import tool_engine
            tools = tool_engine.list_tools(agent_data["name"], USERNAME)

            agents.append({
                "name": agent_data["name"],
                "display_name": agent_data["display_name"],
                "trust_level": agent_data["trust_level"],
                "agent_type": agent_data["agent_type"],
                "available_tools": len(tools),
                "registered_at": agent_data.get("registered_at"),
                "last_seen": agent_data.get("last_seen")
            })

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


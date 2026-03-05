"""
Kart API Routes - FastAPI Endpoints

Provides HTTP API for Kart orchestration system.

GOVERNANCE: All operations validated through tool_engine + gate.py
AUTHOR: Kart Orchestration System
VERSION: 1.0
CHECKSUM: ΔΣ=42
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

# Core imports
from core import rings, graft, tool_engine

# Default username (TODO: get from auth context)
USERNAME = "Sweet-Pea-Rudi19"

# Create router
router = APIRouter(prefix="/api/kart", tags=["kart"])


# Request/Response models
class ExecuteRequest(BaseModel):
    """Request to execute a task."""
    task: str
    agent: Optional[str] = "kart"
    resume_from: Optional[str] = None  # SEED_PACKET path


class ToolExecuteRequest(BaseModel):
    """Request to execute a single tool (for testing)."""
    tool: str
    params: Dict[str, Any]
    agent: Optional[str] = "kart"


class TaskUpdateRequest(BaseModel):
    """Request to update task status."""
    status: str
    agent: Optional[str] = "kart"


# ============================================================================
# ORCHESTRATION ENDPOINTS
# ============================================================================

@router.post("/execute")
async def execute_task(req: ExecuteRequest):
    """
    Execute a multi-step task via Kart orchestrator.
    Non-blocking — runs rings.execute_task in a thread executor.
    """
    import asyncio
    loop = asyncio.get_running_loop()
    try:
        if req.resume_from:
            result = await loop.run_in_executor(
                None,
                lambda: rings.resume_task(
                    username=USERNAME,
                    seed_packet_path=req.resume_from,
                    agent_name=req.agent
                )
            )
        else:
            result = await loop.run_in_executor(
                None,
                lambda: rings.execute_task(
                    username=USERNAME,
                    user_request=req.task,
                    agent_name=req.agent
                )
            )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_status():
    """
    Get Kart orchestrator status.

    Returns:
        {
            "agent": "kart",
            "trust_level": "ENGINEER",
            "available_tools": int,
            "task_stats": dict
        }
    """
    try:
        from core import agent_registry

        # Get agent info
        agent_info = agent_registry.get_agent(USERNAME, "kart")

        # Get tool count
        tools = tool_engine.list_tools("kart", USERNAME)

        # Get task stats
        stats = graft.get_stats(USERNAME, "kart")

        return {
            "agent": "kart",
            "trust_level": agent_info.get("trust_level") if agent_info else "UNKNOWN",
            "available_tools": len(tools),
            "tools": [t["name"] for t in tools],
            "task_stats": stats
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# TOOL EXECUTION (FOR TESTING)
# ============================================================================

@router.post("/tool/execute")
async def execute_tool(req: ToolExecuteRequest):
    """
    Execute a single tool (for testing/debugging).

    Body:
        {
            "tool": "read_file",
            "params": {"file_path": "/path/to/file"},
            "agent": "kart"
        }

    Returns:
        Tool execution result
    """
    try:
        result = tool_engine.execute(
            tool_name=req.tool,
            params=req.params,
            agent=req.agent,
            username=USERNAME
        )
        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tools")
async def list_tools():
    """
    List available tools for Kart agent.

    Returns:
        {
            "tools": [
                {
                    "name": str,
                    "description": str,
                    "parameters": dict,
                    "required_trust": str
                }
            ]
        }
    """
    try:
        tools = tool_engine.list_tools("kart", USERNAME)
        return {"tools": tools}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# TASK MANAGEMENT
# ============================================================================

@router.get("/tasks")
async def list_tasks(status: Optional[str] = None):
    """
    List Kart tasks.

    Query params:
        status: Filter by status (optional)

    Returns:
        {
            "tasks": [...]
        }
    """
    try:
        tasks = graft.list_tasks(USERNAME, agent="kart", status=status)
        return {"tasks": tasks}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tasks/{task_id}")
async def get_task(task_id: str):
    """
    Get task by ID.

    Returns:
        Task object or 404
    """
    try:
        task = graft.get_task(USERNAME, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        return task

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tasks/{task_id}/update")
async def update_task(task_id: str, req: TaskUpdateRequest):
    """
    Update task status.

    Body:
        {
            "status": "completed",
            "agent": "kart"
        }

    Returns:
        {"success": bool}
    """
    try:
        success = graft.update_task(
            username=USERNAME,
            task_id=task_id,
            status=req.status,
            agent=req.agent
        )

        if not success:
            raise HTTPException(status_code=404, detail="Task not found")

        return {"success": True, "task_id": task_id, "status": req.status}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tasks/{task_id}/log")
async def get_task_log(task_id: str):
    """
    Get task history log.

    Returns:
        {
            "task_id": str,
            "log": [...]
        }
    """
    try:
        log = graft.get_task_log(USERNAME, task_id)
        return {"task_id": task_id, "log": log}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str):
    """
    Delete a task.

    Returns:
        {"success": bool}
    """
    try:
        success = graft.delete_task(USERNAME, task_id)
        if not success:
            raise HTTPException(status_code=404, detail="Task not found")
        return {"success": True, "task_id": task_id}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/queue/depth")
async def kart_queue_depth():
    """Current job queue depths and status counts."""
    from core import job_queue
    return job_queue.queue_depth()

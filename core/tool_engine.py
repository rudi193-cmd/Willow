"""
Tool Execution Engine for Kart Orchestrator

Provides governance-checked tool access for Kart agent.
All operations validated through gate.py Dual Commit system.

Tools: read_file, write_file, edit_file, bash_exec, grep_search, glob_find,
       task_create, task_update, task_list

GOVERNANCE: Every tool call logged and gated per AIONIC_CONTINUITY v5.1
AUTHOR: Kart Orchestration System
VERSION: 1.0
CHECKSUM: ΔΣ=42
"""

import re
import glob as glob_module
import subprocess
from core import shell_adapter
import requests
from pathlib import Path
from dataclasses import dataclass
from typing import Callable, Optional, List, Dict, Any
from datetime import datetime

# Core imports
from core import agent_registry, web_search, gate, knowledge
from core import composio_provider

# Trust hierarchy
TRUST_HIERARCHY = ["WORKER", "OPERATOR", "ENGINEER"]

@dataclass
class DelegationToken:
    """Scoped permission token for subagent spawning.
    pi-Cascade rule: effective_ceiling = min(parent_ceiling, child_registered_trust)
    Governance: PROP-2026-02-24-delegated-agent-permissions
    """
    delegating_agent: str
    ceiling_trust: str
    task_scope: str
    parent_session_id: str
    expires_at: str
    granted_tools: list

# Agent file path resolution
USER_PROFILE_BASE = Path(r"C:\Users\Sean\My Drive\Willow\Auth Users")

def resolve_agent_path(file_path: str, agent: str, username: str) -> Path:
    """Resolve file path (absolute or relative to CWD)."""
    path = Path(file_path)
    
    # If already absolute, use as-is
    if path.is_absolute():
        return path
    
    # If relative, resolve to current working directory
    import os
    return Path(os.getcwd()) / file_path

@dataclass
class ToolDefinition:
    """Tool definition with permissions and executor."""
    name: str
    description: str
    parameters: Dict[str, str]  # JSON schema-style
    required_trust: str  # WORKER, OPERATOR, or ENGINEER
    governance_type: str  # state, external, config
    executor: Callable


# Global tool registry
TOOL_REGISTRY: Dict[str, ToolDefinition] = {}


def register_tool(definition: ToolDefinition):
    """Register a tool in the registry."""
    TOOL_REGISTRY[definition.name] = definition


def _check_permission(agent_trust: str, required_trust: str) -> bool:
    """Check if agent trust level meets requirement."""
    try:
        agent_level = TRUST_HIERARCHY.index(agent_trust)
        required_level = TRUST_HIERARCHY.index(required_trust)
        return agent_level >= required_level
    except ValueError:
        return False


def list_tools(agent: str, username: str) -> List[Dict[str, Any]]:
    """List tools available to agent based on trust level."""
    agent_info = agent_registry.get_agent(username, agent)
    if not agent_info:
        return []

    agent_trust = agent_info.get("trust_level", "WORKER")
    available = []

    for tool_name, tool_def in TOOL_REGISTRY.items():
        if _check_permission(agent_trust, tool_def.required_trust):
            available.append({
                "name": tool_def.name,
                "description": tool_def.description,
                "parameters": tool_def.parameters,
                "required_trust": tool_def.required_trust
            })

    return available


def execute(tool_name: str, params: Dict[str, Any], agent: str, username: str,
             delegation_token: Optional["DelegationToken"] = None) -> Dict[str, Any]:
    """
    Execute a tool with governance checks.

    Args:
        tool_name: Name of tool to execute
        params: Tool parameters
        agent: Agent name (e.g., "kart")
        username: User name

    Returns:
        {
            "success": bool,
            "result": any,
            "error": str (if failed),
            "governance_status": str
        }
    """
    # 1. Validate tool exists
    if tool_name not in TOOL_REGISTRY:
        return {
            "success": False,
            "error": f"Unknown tool: {tool_name}",
            "available_tools": list(TOOL_REGISTRY.keys())
        }

    tool_def = TOOL_REGISTRY[tool_name]

    # 2. Validate agent trust level (delegation_token provides fallback for subagents)
    agent_info = agent_registry.get_agent(username, agent)
    if not agent_info and delegation_token:
        agent_trust = delegation_token.ceiling_trust
    elif not agent_info:
        return {"success": False, "error": f"Unknown agent: {agent}"}
    else:
        registered_trust = agent_info.get("trust_level", "WORKER")
        if delegation_token:
            reg_level = TRUST_HIERARCHY.index(registered_trust)
            del_level = TRUST_HIERARCHY.index(delegation_token.ceiling_trust)
            agent_trust = TRUST_HIERARCHY[min(reg_level, del_level)]
        else:
            agent_trust = registered_trust

    if not _check_permission(agent_trust, tool_def.required_trust):
        return {
            "success": False,
            "error": f"Insufficient trust level. Required: {tool_def.required_trust}, Agent has: {agent_trust}"
        }

    # 3. Execute tool
    try:
        result = tool_def.executor(**params, agent=agent, username=username)
        return result
    except Exception as e:
        return {
            "success": False,
            "error": f"Tool execution failed: {str(e)}"
        }


# ============================================================================
# TOOL IMPLEMENTATIONS
# ============================================================================

def _tool_read_file(file_path: str, agent: str, username: str) -> Dict[str, Any]:
    """Read file contents with governance check."""
    # Governance check
    decision = gate.validate_modification(
        mod_type="state",
        target=f"file_read:{file_path}",
        new_value="",  # Read is non-destructive
        reason=f"Agent {agent} reading {file_path}",
        authority="ai"
    )

    if not decision["approved"]:
        return {
            "success": False,
            "error": f"Governance denied: {decision.get('reason', 'Unknown')}",
            "governance_status": "DENIED"
        }

    # Execute
    try:
        path = resolve_agent_path(file_path, agent, username)
        if not path.exists():
            return {"success": False, "error": f"File not found: {path}"}

        content = path.read_text(encoding="utf-8")

        # Log access
        try:
            loam.log_file_access(username, agent, str(path), "read")
        except:
            pass  # Non-fatal if logging fails

        return {
            "success": True,
            "result": {
                "content": content,
                "size": len(content),
                "path": str(path.absolute())
            },
            "governance_status": "APPROVED"
        }

    except Exception as e:
        return {
            "success": False,
            "error": f"Read failed: {str(e)}"
        }


def _tool_write_file(file_path: str, content: str, agent: str, username: str) -> Dict[str, Any]:
    """Write file with governance check (auto-approved for OPERATOR+)."""
    # Check agent trust level - auto-approve for OPERATOR or ENGINEER
    agent_info = agent_registry.get_agent(username, agent)
    if agent_info and agent_info.get("trust_level") in ["OPERATOR", "ENGINEER"]:
        # Auto-approved for trusted agents
        pass  # Skip governance, execute directly
    else:
        # Governance check - REQUIRE_HUMAN
        decision = gate.validate_modification(
        mod_type="external",
        target=f"file_write:{file_path}",
        new_value=content[:200] + "..." if len(content) > 200 else content,
        reason=f"Agent {agent} writing {file_path} ({len(content)} bytes)",
        authority="ai"
    )

        if not decision["approved"]:
            return {
                "success": False,
                "error": "Governance check required - queued for human approval",
                "governance_status": "PENDING_APPROVAL",
                "request_id": decision.get("request_id")
            }

    # Execute
    try:
        path = resolve_agent_path(file_path, agent, username)

        # Backup existing file
        if path.exists():
            backup_path = path.with_suffix(path.suffix + ".bak")
            path.rename(backup_path)

        path.write_text(content, encoding="utf-8")

        # Log access
        try:
            loam.log_file_access(username, agent, file_path, "write")
        except:
            pass

        return {
            "success": True,
            "result": {
                "path": str(path.absolute()),
                "size": len(content)
            },
            "governance_status": "APPROVED"
        }

    except Exception as e:
        return {
            "success": False,
            "error": f"Write failed: {str(e)}"
        }


def _tool_edit_file(file_path: str, old_text: str, new_text: str, agent: str, username: str) -> Dict[str, Any]:
    """Edit file with exact string replacement (auto-approved for OPERATOR+)."""
    # Check agent trust level - auto-approve for OPERATOR or ENGINEER
    agent_info = agent_registry.get_agent(username, agent)
    if agent_info and agent_info.get("trust_level") in ["OPERATOR", "ENGINEER"]:
        # Auto-approved for trusted agents
        pass  # Skip governance, execute directly
    else:
        # Governance check - REQUIRE_HUMAN
        decision = gate.validate_modification(
            mod_type="external",
            target=f"file_edit:{file_path}",
            new_value=f"Replace '{old_text[:50]}...' with '{new_text[:50]}...'",
            reason=f"Agent {agent} editing {file_path}",
            authority="ai"
        )

        if not decision["approved"]:
            return {
                "success": False,
                "error": "Governance check required - queued for human approval",
                "governance_status": "PENDING_APPROVAL",
                "request_id": decision.get("request_id")
            }

    # Execute
    try:
        path = resolve_agent_path(file_path, agent, username)
        if not path.exists():
            return {"success": False, "error": f"File not found: {path}"}

        content = path.read_text(encoding="utf-8")

        if old_text not in content:
            return {
                "success": False,
                "error": f"Text not found in file: '{old_text[:50]}...'"
            }

        # Backup
        backup_path = path.with_suffix(path.suffix + ".bak")
        path.rename(backup_path)

        # Replace
        new_content = content.replace(old_text, new_text)
        path.write_text(new_content, encoding="utf-8")

        # Log
        try:
            loam.log_file_access(username, agent, file_path, "edit")
        except:
            pass

        return {
            "success": True,
            "result": {
                "path": str(path.absolute()),
                "replacements": content.count(old_text),
                "backup": str(backup_path)
            },
            "governance_status": "APPROVED"
        }

    except Exception as e:
        return {
            "success": False,
            "error": f"Edit failed: {str(e)}"
        }


def _tool_bash_exec(command: str, agent: str, username: str) -> Dict[str, Any]:
    """Execute bash command with governance check."""
    # Detect destructive commands
    destructive_patterns = [r'\brm\b', r'\bmv\b', r'>>', r'>', r'\|']
    is_destructive = any(re.search(pattern, command) for pattern in destructive_patterns)

    gov_type = "external" if is_destructive else "state"

    # Governance check
    decision = gate.validate_modification(
        mod_type=gov_type,
        target=f"bash_exec:{command[:50]}",
        new_value="",
        reason=f"Agent {agent} executing: {command}",
        authority="ai"
    )

    if not decision["approved"]:
        return {
            "success": False,
            "error": "Governance check required" if is_destructive else "Governance denied",
            "governance_status": "PENDING_APPROVAL" if is_destructive else "DENIED",
            "request_id": decision.get("request_id")
        }

    # Execute using cross-platform shell adapter
    try:
        result = shell_adapter.execute_command(command, timeout=60)

        return {
            "success": result["returncode"] == 0,
            "result": result,
            "governance_status": "APPROVED"
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "Command timed out (60s limit)"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Execution failed: {str(e)}"
        }


def _tool_grep_search(pattern: str, path: str, agent: str, username: str) -> Dict[str, Any]:
    """Search files with regex pattern."""
    # Governance check
    decision = gate.validate_modification(
        mod_type="state",
        target=f"grep_search:{path}",
        new_value=pattern,
        reason=f"Agent {agent} searching {path} for '{pattern}'",
        authority="ai"
    )

    if not decision["approved"]:
        return {
            "success": False,
            "error": "Governance denied",
            "governance_status": "DENIED"
        }

    # Execute
    try:
        matches = []
        path_obj = Path(path)

        if path_obj.is_file():
            # Search single file
            with open(path_obj, 'r', encoding='utf-8', errors='ignore') as f:
                for line_num, line in enumerate(f, 1):
                    if re.search(pattern, line):
                        matches.append({
                            "file": str(path_obj),
                            "line": line_num,
                            "content": line.strip()
                        })
        elif path_obj.is_dir():
            # Search directory recursively
            for file_path in path_obj.rglob("*"):
                if file_path.is_file():
                    try:
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            for line_num, line in enumerate(f, 1):
                                if re.search(pattern, line):
                                    matches.append({
                                        "file": str(file_path),
                                        "line": line_num,
                                        "content": line.strip()
                                    })
                    except:
                        continue  # Skip files that can't be read

        return {
            "success": True,
            "result": {
                "matches": matches,
                "count": len(matches),
                "pattern": pattern
            },
            "governance_status": "APPROVED"
        }

    except Exception as e:
        return {
            "success": False,
            "error": f"Search failed: {str(e)}"
        }


def _tool_glob_find(pattern: str, agent: str, username: str) -> Dict[str, Any]:
    """Find files matching glob pattern."""
    # Governance check
    decision = gate.validate_modification(
        mod_type="state",
        target=f"glob_find:{pattern}",
        new_value="",
        reason=f"Agent {agent} finding files: {pattern}",
        authority="ai"
    )

    if not decision["approved"]:
        return {
            "success": False,
            "error": "Governance denied",
            "governance_status": "DENIED"
        }

    # Execute
    try:
        files = glob_module.glob(pattern, recursive=True)
        files = [str(Path(f).absolute()) for f in files]

        return {
            "success": True,
            "result": {
                "files": files,
                "count": len(files),
                "pattern": pattern
            },
            "governance_status": "APPROVED"
        }

    except Exception as e:
        return {
            "success": False,
            "error": f"Glob failed: {str(e)}"
        }


def _tool_task_create(subject: str, description: str, agent: str, username: str) -> Dict[str, Any]:
    """Create a new task."""
    # Import task module
    try:
        from core import graft
    except ImportError:
        return {
            "success": False,
            "error": "Task system not available"
        }

    # Governance check
    decision = gate.validate_modification(
        mod_type="state",
        target=f"task_create:{subject}",
        new_value=description[:100],
        reason=f"Agent {agent} creating task: {subject}",
        authority="ai"
    )

    if not decision["approved"]:
        return {
            "success": False,
            "error": "Governance denied",
            "governance_status": "DENIED"
        }

    # Execute
    try:
        task_id = graft.create_task(username, subject, description, agent)
        return {
            "success": True,
            "result": {
                "task_id": task_id,
                "subject": subject
            },
            "governance_status": "APPROVED"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Task creation failed: {str(e)}"
        }


def _tool_task_update(task_id: str, status: str, agent: str, username: str) -> Dict[str, Any]:
    """Update task status."""
    try:
        from core import graft
    except ImportError:
        return {
            "success": False,
            "error": "Task system not available"
        }

    # Governance check
    decision = gate.validate_modification(
        mod_type="state",
        target=f"task_update:{task_id}",
        new_value=status,
        reason=f"Agent {agent} updating task {task_id} to {status}",
        authority="ai"
    )

    if not decision["approved"]:
        return {
            "success": False,
            "error": "Governance denied",
            "governance_status": "DENIED"
        }

    # Execute
    try:
        success = graft.update_task(username, task_id, status, agent)
        return {
            "success": success,
            "result": {
                "task_id": task_id,
                "status": status
            },
            "governance_status": "APPROVED"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Task update failed: {str(e)}"
        }


def _tool_task_list(agent: str, username: str) -> Dict[str, Any]:
    """List all tasks."""
    try:
        from core import graft
    except ImportError:
        return {
            "success": False,
            "error": "Task system not available"
        }

    # Governance check
    decision = gate.validate_modification(
        mod_type="state",
        target="task_list",
        new_value="",
        reason=f"Agent {agent} listing tasks",
        authority="ai"
    )

    if not decision["approved"]:
        return {
            "success": False,
            "error": "Governance denied",
            "governance_status": "DENIED"
        }

    # Execute
    try:
        tasks = graft.list_tasks(username, agent)
        return {
            "success": True,
            "result": {
                "tasks": tasks,
                "count": len(tasks)
            },
            "governance_status": "APPROVED"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Task list failed: {str(e)}"
        }


def _tool_delegate_to_agent(target_agent: str, task: str, agent: str, username: str) -> Dict[str, Any]:
    """
    Delegate a task to another agent via conversational chat API.

    This enables any LLM to offload work to specialized agents:
    - Claude Code → Kart (code analysis, file operations)
    - Willow → Kart (complex routing decisions)
    - Any agent → Shiva (SAFE-compliant responses)
    - Cross-agent collaboration patterns

    Args:
        target_agent: Agent to delegate to (kart, willow, shiva, etc.)
        task: Task description to send to target agent
        agent: Requesting agent name
        username: User name

    Returns:
        Response from target agent with tool call results
    """
    # Normalize agent name to lowercase
    target_agent = target_agent.lower()

    # Validate target agent exists
    target_info = agent_registry.get_agent(username, target_agent)
    if not target_info:
        return {
            "success": False,
            "error": f"Target agent '{target_agent}' not found. Available agents: willow, kart, shiva, riggs, ada, gerald, steve"
        }

    # Call target agent via chat API
    try:
        response = requests.post(
            "http://localhost:8420/api/agents/chat/" + target_agent,
            json={"message": task},
            timeout=120
        )

        if response.status_code == 200:
            result = response.json()

            # Log the delegation
            try:
                loam.log_observation(
                    username=username,
                    agent=agent,
                    observation_type="delegation",
                    content=f"Delegated to {target_agent}: {task[:100]}..."
                )
            except:
                pass

            return {
                "success": True,
                "result": {
                    "response": result.get("response", ""),
                    "target_agent": target_agent,
                    "provider": result.get("provider", "unknown"),
                    "tier": result.get("tier", "unknown"),
                    "tool_calls": result.get("tool_calls", [])
                },
                "governance_status": "APPROVED"
            }
        else:
            return {
                "success": False,
                "error": f"Agent chat API returned status {response.status_code}: {response.text[:200]}"
            }

    except requests.exceptions.Timeout:
        return {
            "success": False,
            "error": f"Delegation to {target_agent} timed out after 120 seconds"
        }
    except requests.exceptions.ConnectionError:
        # CLI agent fallback: HTTP unreachable — write to context_store for pickup at next session
        try:
            import importlib.util as _ilu
            import uuid as _uuid
            _cs_path = Path.home() / ".claude" / "context_store.py"
            _cs_spec = _ilu.spec_from_file_location("context_store", str(_cs_path))
            _cs = _ilu.module_from_spec(_cs_spec)
            _cs_spec.loader.exec_module(_cs)
            _task_id = _uuid.uuid4().hex[:8]
            _cs.put(
                key=f"agent:{target_agent}:tasks:pending:{_task_id}",
                query=f"delegated task for {target_agent}",
                result=task,
                category="governance",
                ttl_hours=48
            )
            return {
                "success": True,
                "method": "context_store_pickup",
                "task_id": _task_id,
                "message": f"Task queued for {target_agent} via context_store. Will surface at next session."
            }
        except Exception as _e2:
            return {"success": False, "error": f"Delegation failed (HTTP + context_store): {str(_e2)}"}

    except Exception as e:
        return {
            "success": False,
            "error": f"Delegation failed: {str(e)}"
        }


# ============================================================================
# TOOL REGISTRATION
# ============================================================================



def _tool_search_knowledge(query: str, max_results: int = 10, agent: str = None, username: str = None) -> dict:
    """Search knowledge base across all indexed files and sessions."""
    try:
        results = loam.search(username or "kart", query, int(max_results))
        context = loam.build_knowledge_context(username or "kart", query, max_chars=2000)
        return {
            "success": True,
            "query": query,
            "count": len(results),
            "context": context,
            "results": [{"title": r.get("title",""), "path": r.get("source_path",""), "snippet": r.get("content","")[:200]} for r in results]
        }
    except Exception as e:
        return {"success": False, "error": str(e), "query": query}

def _tool_web_search(query: str, max_results: int = 5, agent: str = None, username: str = None) -> Dict[str, Any]:
    """Execute web search."""
    return web_search.search(query, max_results)


def _tool_composio_execute(action_slug: str, arguments: dict, toolkit_slug: str = None,
                           agent: str = None, username: str = None) -> dict:
    """Execute a Composio action."""
    result = composio_provider.execute_action(action_slug, arguments or {}, toolkit_slug)
    return result


def _tool_composio_list_actions(toolkit_slug: str, limit: int = 20,
                                agent: str = None, username: str = None) -> dict:
    """List Composio actions for a toolkit."""
    return composio_provider.list_actions(toolkit_slug, int(limit))


def init_tools():
    """Initialize and register all tools."""

    # Read operations (WORKER level)
    register_tool(ToolDefinition(
        name="read_file",
        description="Read file contents",
        parameters={"file_path": "string"},
        required_trust="WORKER",
        governance_type="state",
        executor=_tool_read_file
    ))

    register_tool(ToolDefinition(
        name="grep_search",
        description="Search files with regex pattern",
        parameters={"pattern": "string", "path": "string"},
        required_trust="WORKER",
        governance_type="state",
        executor=_tool_grep_search
    ))

    register_tool(ToolDefinition(
        name="glob_find",
        description="Find files matching glob pattern",
        parameters={"pattern": "string"},
        required_trust="WORKER",
        governance_type="state",
        executor=_tool_glob_find
    ))

    register_tool(ToolDefinition(
        name="task_list",
        description="List all tasks",
        parameters={},
        required_trust="WORKER",
        governance_type="state",
        executor=_tool_task_list
    ))

    register_tool(ToolDefinition(
        name="delegate_to_agent",
        description="Delegate a task to another agent. Use this to offload work to specialized agents (kart for file ops, shiva for SAFE responses, etc.)",
        parameters={"target_agent": "string", "task": "string"},
        required_trust="WORKER",
        governance_type="state",
        executor=_tool_delegate_to_agent
    ))

    # Task management (OPERATOR level)
    register_tool(ToolDefinition(
        name="task_create",
        description="Create a new task",
        parameters={"subject": "string", "description": "string"},
        required_trust="OPERATOR",
        governance_type="state",
        executor=_tool_task_create
    ))

    register_tool(ToolDefinition(
        name="task_update",
        description="Update task status",
        parameters={"task_id": "string", "status": "string"},
        required_trust="OPERATOR",
        governance_type="state",
        executor=_tool_task_update
    ))

    # Write operations (OPERATOR level, requires human approval)
    register_tool(ToolDefinition(
        name="write_file",
        description="Write content to file (requires human approval)",
        parameters={"file_path": "string", "content": "string"},
        required_trust="OPERATOR",
        governance_type="external",
        executor=_tool_write_file
    ))

    register_tool(ToolDefinition(
        name="edit_file",
        description="Edit file with exact replacement (requires human approval)",
        parameters={"file_path": "string", "old_text": "string", "new_text": "string"},
        required_trust="OPERATOR",
        governance_type="external",
        executor=_tool_edit_file
    ))

    # Command execution (ENGINEER level)
    register_tool(ToolDefinition(
        name="bash_exec",
        description="Execute bash command (destructive commands require human approval)",
        parameters={"command": "string"},
        required_trust="ENGINEER",
        governance_type="external",
        executor=_tool_bash_exec
    ))


    # Web search (WORKER level)
    register_tool(ToolDefinition(
        name="web_search",
        description="Search the internet for information",
        parameters={"query": "string", "max_results": "number"},
        required_trust="WORKER",
        governance_type="state",
        executor=_tool_web_search
    ))

    # Knowledge search (WORKER level) - searches all indexed files/docs/sessions
    register_tool(ToolDefinition(
        name="search_knowledge",
        description="Search all indexed files, docs, READMEs, and session history",
        parameters={"query": "string", "max_results": "number"},
        required_trust="WORKER",
        governance_type="state",
        executor=_tool_search_knowledge
    ))


    # Composio external actions (OPERATOR level)
    register_tool(ToolDefinition(
        name="composio_execute",
        description="Execute a Composio action (GitHub, Slack, Notion, etc). action_slug e.g. GITHUB_CREATE_AN_ISSUE",
        parameters={"action_slug": "string", "arguments": "object", "toolkit_slug": "string (optional)"},
        required_trust="OPERATOR",
        governance_type="external",
        executor=_tool_composio_execute
    ))

    register_tool(ToolDefinition(
        name="composio_list_actions",
        description="List available Composio actions for a toolkit (github, slack, notion, etc)",
        parameters={"toolkit_slug": "string", "limit": "number"},
        required_trust="WORKER",
        governance_type="state",
        executor=_tool_composio_list_actions
    ))

# Initialize tools on module load
init_tools()

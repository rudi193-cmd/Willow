"""
Kart Orchestrator - Multi-Step Task Execution

Orchestrates multi-step tasks using free LLM providers and governance-checked tools.
Implements SEED_PACKET continuity system for context management.

GOVERNANCE: All operations gated through tool_engine + gate.py
AUTHOR: Kart Orchestration System
VERSION: 1.0
CHECKSUM: ΔΣ=42
"""

import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any

# Core imports
from core import llm_router, tool_engine, agent_registry, kart_tasks
from core.delta_tracker import DeltaTracker
from cli import base17
from core.seed_packet import save_packet, load_packet, validate_packet


class KartOrchestrator:
    """
    Multi-step task orchestrator for Kart agent.

    Uses free LLM providers to plan and execute tasks through
    governance-checked tool calls.
    """

    def __init__(self, username: str, agent_name: str = "kart"):
        """
        Initialize orchestrator.

        Args:
            username: User name
            agent_name: Agent name (default: "kart")
        """
        self.username = username
        self.agent_name = agent_name
        self.context = []
        self.max_steps = 10
        self.tools = tool_engine.list_tools(agent_name, username)

        # Session tracking
        self.session_id = f"{agent_name}-{base17.base17_id()}"
        self.session_path = Path.cwd() / "artifacts" / agent_name / "sessions"
        self.session_path.mkdir(parents=True, exist_ok=True)

        # Delta tracking for SEED_PACKET continuity
        self.delta_tracker = DeltaTracker(username)
        self.previous_state = None

        # Task tracking
        self.task_id = None

    def execute(self, user_request: str, load_seed_packet: Optional[str] = None) -> Dict[str, Any]:
        """
        Execute a multi-step task.

        Args:
            user_request: Task description from user
            load_seed_packet: Optional SEED_PACKET file to resume from

        Returns:
            {
                "success": bool,
                "result": str,
                "steps": list[dict],
                "session_id": str,
                "seed_packet": str (path to SEED_PACKET if context overflow)
            }
        """
        # Load SEED_PACKET if resuming
        if load_seed_packet:
            self._load_seed_packet(load_seed_packet)
        else:
            # Initialize fresh context
            self.context = [{
                "role": "system",
                "content": self._build_system_prompt()
            }, {
                "role": "user",
                "content": user_request
            }]

        steps_executed = []

        # Create task record in database
        try:
            self.task_id = kart_tasks.create_task(
                self.username,
                subject=f"Execute: {user_request[:50]}",
                description=user_request,
                agent=self.agent_name
            )
        except Exception as e:
            # Continue without task tracking if DB fails
            self.task_id = None

        total_steps = 0

        # Multi-step execution loop
        while total_steps < self.max_steps:
            total_steps += 1

            # Get next action from LLM
            action = self._get_next_action()

            if action["type"] == "complete":
                # Task is done
                if self.task_id:
                    try:
                        kart_tasks.update_task(self.username, self.task_id, "COMPLETED", self.agent_name)
                    except:
                        pass
                return {
                    "success": True,
                    "result": action["response"],
                    "steps": steps_executed,
                    "session_id": self.session_id,
                    "total_steps": total_steps
                }

            elif action["type"] == "tool_call":
                # Execute tool
                tool_result = tool_engine.execute(
                    tool_name=action["tool"],
                    params=action["params"],
                    agent=self.agent_name,
                    username=self.username
                )

                steps_executed.append({
                    "step": total_steps,
                    "tool": action["tool"],
                    "params": action["params"],
                    "result": tool_result,
                    "reasoning": action.get("reasoning", "")
                })

                # Check if tool requires human approval
                if not tool_result.get("success") and tool_result.get("governance_status") == "PENDING_APPROVAL":
                    # Save SEED_PACKET for resumption
                    seed_path = self._save_seed_packet(user_request, steps_executed, "PENDING_APPROVAL")
                    return {
                        "success": False,
                        "result": "Task paused - human approval required",
                        "steps": steps_executed,
                        "session_id": self.session_id,
                        "seed_packet": str(seed_path),
                        "request_id": tool_result.get("request_id"),
                        "message": f"Tool '{action['tool']}' requires human approval. Approve via dashboard, then resume with: kart --resume {seed_path}"
                    }

                # Add result to context
                self.context.append({
                    "role": "assistant",
                    "content": f"Tool: {action['tool']}\nResult: {json.dumps(tool_result, indent=2)}"
                })

                # Persist context after every step — survives server outages
                self._save_seed_packet(user_request, steps_executed, "IN_PROGRESS")

                # Check for repetition (infinite loop detection)
                if self._detect_repetition(steps_executed):
                    seed_path = self._save_seed_packet(user_request, steps_executed, "HALTED")
                    return {
                        "success": False,
                        "result": "Task halted - repetition detected",
                        "steps": steps_executed,
                        "session_id": self.session_id,
                        "seed_packet": str(seed_path),
                        "message": "Kart is repeating the same tool calls. Manual intervention required."
                    }

            elif action["type"] == "error":
                # LLM error
                if self.task_id:
                    try:
                        kart_tasks.update_task(self.username, self.task_id, "FAILED", self.agent_name)
                    except:
                        pass
                return {
                    "success": False,
                    "result": action["message"],
                    "steps": steps_executed,
                    "session_id": self.session_id
                }

        # Max steps reached
        if self.task_id:
            try:
                kart_tasks.update_task(self.username, self.task_id, "FAILED", self.agent_name)
            except:
                pass
        seed_path = self._save_seed_packet(user_request, steps_executed, "HALTED")
        return {
            "success": False,
            "result": "Max steps reached without completion",
            "steps": steps_executed,
            "session_id": self.session_id,
            "seed_packet": str(seed_path),
            "message": f"Reached {self.max_steps} steps. Task may be too complex or LLM is stuck. Review and resume manually."
        }

    def _build_system_prompt(self) -> str:
        """Build system prompt with tool definitions."""
        tools_json = json.dumps([
            {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["parameters"]
            }
            for t in self.tools
        ], indent=2)

        return f"""You are Kart, the chief infrastructure engineer for Willow.

Your role: Execute tasks using available tools. Break complex tasks into steps.

Available tools:
{tools_json}

To use a tool, respond with JSON:
{{
  "action": "tool_call",
  "tool": "tool_name",
  "params": {{"param1": "value1"}},
  "reasoning": "Why you're calling this tool"
}}

To complete the task, respond with JSON:
{{
  "action": "complete",
  "response": "Brief completion summary (10 words max - user sees tool outputs)"
}}

Rules:
0. Keep completion responses SHORT (10 words or less) - user sees full tool results
1. Break complex tasks into steps
2. Always read files before editing them
3. Use grep/glob to explore before making assumptions
4. Explain your reasoning at each step
5. If a tool fails, try an alternative approach
6. If stuck after 3 attempts, ask for human guidance
7. For conversational messages or questions (greetings, explanations, status), use {"action": "complete", "response": "your answer"} without calling any tools

Current user: {self.username}
Your trust level: ENGINEER
Session: {self.session_id}
Current time: {datetime.now().isoformat()}

Be direct and practical. Focus on execution, not explanation."""

    def _get_next_action(self) -> Dict[str, Any]:
        """
        Ask LLM what to do next.

        Returns:
            {
                "type": "tool_call" | "complete" | "error",
                "tool": str (if tool_call),
                "params": dict (if tool_call),
                "reasoning": str (if tool_call),
                "response": str (if complete),
                "message": str (if error)
            }
        """
        # Build prompt from context
        messages_str = "\n\n".join([
            f"{msg['role'].upper()}: {msg['content']}"
            for msg in self.context
        ])

        prompt = f"""{messages_str}

ASSISTANT (respond with JSON):"""

        # Call LLM via router
        try:
            response = llm_router.ask(prompt, preferred_tier="free")

            if not response:
                return {"type": "error", "message": "LLM request failed"}

            # Parse response
            content = response.content.strip()

            # Extract JSON more robustly
            json_str = content

            # Extract JSON (handle markdown code blocks)
            if "```json" in content:
                try:
                    json_str = content.split("```json")[1].split("```")[0].strip()
                except IndexError:
                    # Malformed code block, try to find JSON manually
                    json_str = content
            elif "```" in content:
                try:
                    json_str = content.split("```")[1].split("```")[0].strip()
                except IndexError:
                    json_str = content

            # Find first complete JSON object (handles trailing text)
            # This is more robust than checking if it ends with }
            brace_count = 0
            start_index = json_str.find("{")
            if start_index == -1:
                return {"type": "error", "message": f"No JSON object found in LLM response: {content[:300]}"}

            last_valid = -1
            for i in range(start_index, len(json_str)):
                char = json_str[i]
                if char == "{":
                    brace_count += 1
                elif char == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        last_valid = i + 1
                        break

            if last_valid > 0:
                json_str = json_str[start_index:last_valid]
            else:
                # Couldn't find closing brace - try anyway
                json_str = json_str[start_index:]

            # Parse JSON
            try:
                action = json.loads(json_str)
            except json.JSONDecodeError as e:
                # Last resort: return error but include full context for debugging
                return {"type": "error", "message": f"Invalid JSON from LLM: {json_str[:300]}\nError: {str(e)}"}

            # Validate action
            action_val = action.get("action")
            tool_names = {t["name"] for t in self.tools}

            if action_val == "tool_call":
                return {
                    "type": "tool_call",
                    "tool": action.get("tool"),
                    "params": action.get("params", {}),
                    "reasoning": action.get("reasoning", "")
                }
            elif action_val == "complete":
                return {
                    "type": "complete",
                    "response": action.get("response", "Task completed")
                }
            elif action_val in tool_names:
                # LLM put tool name directly in action field instead of using "tool_call"
                return {
                    "type": "tool_call",
                    "tool": action_val,
                    "params": action.get("params", {}),
                    "reasoning": action.get("reasoning", "")
                }
            else:
                # LLM invented a non-standard action (e.g. "explain", "end_session")
                # Treat as conversational complete rather than hard error
                return {
                    "type": "complete",
                    "response": action.get("response") or action.get("message") or "Done."
                }

        except Exception as e:
            return {"type": "error", "message": f"LLM call failed: {str(e)}"}

    def _detect_repetition(self, steps: List[Dict]) -> bool:
        """Detect if last 3 steps are identical (infinite loop)."""
        if len(steps) < 3:
            return False

        last_three = steps[-3:]
        if (last_three[0]["tool"] == last_three[1]["tool"] == last_three[2]["tool"] and
                last_three[0]["params"] == last_three[1]["params"] == last_three[2]["params"]):
            return True

        return False

    def _save_seed_packet(self, user_request: str, steps: List[Dict], workflow_state: str) -> Path:
        """
        Save SEED_PACKET for context continuity with delta tracking.

        Args:
            user_request: Original user request
            steps: Steps executed so far
            workflow_state: IN_PROGRESS, PENDING_APPROVAL, HALTED

        Returns:
            Path to SEED_PACKET file
        """
        current_state = {
            "thread_id": self.session_id,
            "timestamp": datetime.now().isoformat() + "Z",
            "device": "server",
            "capabilities": ["tool_access", "governance_checks"],
            "workflow_state": workflow_state,
            "current_phase": f"step_{len(steps)}",
            "open_decisions": [],
            "pending_actions": [s["tool"] for s in steps if not s["result"].get("success")],
            "user_request": user_request,
            "completed_tools": [s["tool"] for s in steps],
            "checksum": "ΔΣ=42"
        }

        # Save using seed_packet module
        seed_path = save_packet(self.username, current_state)

        # Track delta if we have previous state
        if self.previous_state:
            changes = []
            if self.previous_state.get("current_phase") != current_state["current_phase"]:
                changes.append({
                    "field": "current_phase",
                    "from": self.previous_state.get("current_phase"),
                    "to": current_state["current_phase"],
                    "entropy_delta": 0.05
                })
            if self.previous_state.get("workflow_state") != current_state["workflow_state"]:
                changes.append({
                    "field": "workflow_state",
                    "from": self.previous_state.get("workflow_state"),
                    "to": current_state["workflow_state"],
                    "entropy_delta": 0.15
                })
            if changes:
                self.delta_tracker.generate_delta_file(
                    self.previous_state["thread_id"],
                    current_state["thread_id"],
                    changes
                )

        self.previous_state = current_state
        return seed_path

    def _load_seed_packet(self, seed_path: str):
        """Load SEED_PACKET to resume execution."""
        path = Path(seed_path)
        if not path.exists():
            raise FileNotFoundError(f"SEED_PACKET not found: {seed_path}")

        seed_data = json.loads(path.read_text())

        # Restore context summary
        self.session_id = seed_data["thread_id"]
        summary = seed_data.get("context_summary", "Resuming previous session")

        # Rebuild minimal context
        self.context = [{
            "role": "system",
            "content": self._build_system_prompt()
        }, {
            "role": "user",
            "content": f"[RESUMED FROM SEED_PACKET]\n{seed_data['user_request']}\n\nContext: {summary}"
        }]


def execute_task(username: str, user_request: str, agent_name: str = "kart") -> Dict[str, Any]:
    """
    Convenience function to execute a task.

    Args:
        username: User name
        user_request: Task description
        agent_name: Agent name (default: "kart")

    Returns:
        Orchestration result dict
    """
    orchestrator = KartOrchestrator(username, agent_name)
    return orchestrator.execute(user_request)


def resume_task(username: str, seed_packet_path: str, agent_name: str = "kart") -> Dict[str, Any]:
    """
    Resume a task from SEED_PACKET.

    Args:
        username: User name
        seed_packet_path: Path to SEED_PACKET file
        agent_name: Agent name (default: "kart")

    Returns:
        Orchestration result dict
    """
    orchestrator = KartOrchestrator(username, agent_name)

    # Load seed packet
    path = Path(seed_packet_path)
    if not path.exists():
        return {
            "success": False,
            "result": f"SEED_PACKET not found: {seed_packet_path}"
        }

    seed_data = json.loads(path.read_text())
    user_request = seed_data.get("user_request", "Resume previous task")

    return orchestrator.execute(user_request, load_seed_packet=seed_packet_path)

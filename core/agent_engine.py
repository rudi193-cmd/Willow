"""
Agent Engine - Conversational AI with Tool Access

Universal conversational agent system for all Willow agents.
Replaces task-executor model with natural conversation + tools.

GOVERNANCE: All tool calls gated through tool_engine + gate.py
COST: Free-tier-first routing, $0.10/month/user cap
AUTHOR: Willow Agent System
VERSION: 2.0
CHECKSUM: ΔΣ=42
"""

import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any, Generator

# Core imports
from core import llm_router, tool_engine, agent_registry, command_parser
from core.n2n_packets import N2NPacket, PacketType, create_handoff, create_delta
from core.n2n_db import N2NDatabase
from core.time_resume_capsule import TimeResumeCapsule
from core.recursion_tracker import RecursionTracker
from core.workflow_state import WorkflowDetector

from core.conversational_handler import handle_conversational
from core import context_injector
from core import kart_startup
from core.analysis_handler import handle_analysis

# Consumer-facing agents: skip canned responses, hide system internals in prompt
_CONSUMER_AGENTS = {"shiva", "nasa_riggs"}

class AgentEngine:
    """
    Conversational AI agent with tool access and governance.

    Works for any agent: Willow, Kart, Shiva, Riggs, etc.
    Each agent has its own personality, tools, and constraints.
    """

    def __init__(self, username: str, agent_name: str = "willow"):
        """
        Initialize agent engine.

        Args:
            username: User name
            agent_name: Agent name (willow, kart, shiva, etc.)
        """
        self.username = username
        self.agent_name = agent_name

        # Load agent info
        self.agent_info = agent_registry.get_agent(username, agent_name)
        if not self.agent_info:
            raise ValueError(f"Agent '{agent_name}' not registered for user '{username}'")

        self.trust_level = self.agent_info.get("trust_level", "WORKER")
        self.agent_type = self.agent_info.get("agent_type", "persona")

        # Load available tools
        self.tools = tool_engine.list_tools(agent_name, username)

        # Load agent personality from AGENT_PROFILE.md
        self.system_prompt = self._load_agent_profile()

        # Conversation history
        self.context = []

        # Cost tracking
        self.api_tier = "free"  # Always free tier for $0.10/month goal
        
        # N2N communication
        self.n2n_db = N2NDatabase(username)
        self.node_id = f"{agent_name}@{username}"
        
        # Session tracking
        self.time_capsule = TimeResumeCapsule(username)
        self.recursion_tracker = RecursionTracker()
        self.workflow_detector = WorkflowDetector(auto_detect_enabled=True)

        # Warm start: populate Kart lattice from live system state
        if self.agent_name == "kart":
            try:
                kart_startup.run_startup(self.username)
            except Exception as _e:
                pass  # Never crash on startup



    def issue_delegation_token(self, task_scope: str, ceiling: str = None, granted_tools: list = None):
        """Issue a scoped token for a subagent. Cannot exceed own trust. pi-Cascade rule.
        Governance: PROP-2026-02-24-delegated-agent-permissions"""
        from datetime import datetime, timezone, timedelta
        import uuid
        hier = tool_engine.TRUST_HIERARCHY
        own_level = hier.index(self.trust_level)
        if ceiling and ceiling in hier:
            effective = hier[min(own_level, hier.index(ceiling))]
        else:
            effective = self.trust_level
        return tool_engine.DelegationToken(
            delegating_agent=self.agent_name,
            ceiling_trust=effective,
            task_scope=task_scope,
            parent_session_id=str(uuid.uuid4()),
            expires_at=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            granted_tools=granted_tools or [],
        )

    def send_n2n_packet(self, target_agent: str, packet_type: PacketType, payload: dict) -> str:
        """
        Send N2N packet to another agent.
        
        Args:
            target_agent: Target agent name
            packet_type: Type of packet (PacketType enum)
            payload: Packet payload (minimal data)
            
        Returns:
            packet_id
        """
        target_node = f"{target_agent}@{self.username}"
        
        packet = N2NPacket.create_packet(
            packet_type=packet_type,
            source_node=self.node_id,
            target_node=target_node,
            payload=payload,
            authority="ai",
            scope="local"
        )
        
        packet_id = self.n2n_db.send_packet(packet)
        return packet_id
    
    def receive_n2n_packets(self, status: str = "SENT") -> list:
        """
        Receive N2N packets addressed to this agent.
        
        Args:
            status: Packet status filter (SENT, RECEIVED, ACKNOWLEDGED)
            
        Returns:
            List of packets
        """
        packets = self.n2n_db.receive_packets(self.node_id, status=status)
        
        # Mark as received
        for packet in packets:
            self.n2n_db.mark_received(packet["packet_id"])
        
        return packets
    
    def send_handoff(self, target_agent: str, what_happened: str, what_next: str) -> str:
        """Send HANDOFF packet (minimal context transfer)."""
        payload = {"what_happened": what_happened, "what_next": what_next}
        return self.send_n2n_packet(target_agent, PacketType.HANDOFF, payload)

    def chat(
        self,
        user_message: str,
        conversation_history: Optional[List[Dict]] = None,
        stream: bool = False
    ) -> Any:
        """
        Conversational chat with tool access.

        Args:
            user_message: User's message
            conversation_history: Optional previous conversation context
            stream: If True, return generator for streaming response

        Returns:
            If stream=False: {"response": str, "tool_calls": list, "provider": str, "tier": str}
            If stream=True: Generator yielding response chunks
        """
        # Build context
        if conversation_history:
            self.context = conversation_history

        # Add system prompt if not present
        if not self.context or self.context[0].get("role") != "system":
            system_content = self.system_prompt
            memory_header = context_injector.build_context_header(
                self.username, self.agent_name, user_message=user_message
            )
            if memory_header:
                # Consumer agents: strip username from memory header
                if self.agent_name in _CONSUMER_AGENTS:
                    memory_header = memory_header.replace(self.username, "the user")
                system_content = memory_header + "\n\n" + system_content
            self.context.insert(0, {
                "role": "system",
                "content": system_content
            })

        # Add user message
        self.context.append({
            "role": "user",
            "content": user_message
        })

        # AUTO-GROUND: Search knowledge graph for proper nouns / entities
        # Consumer agents get this automatically so the LLM has context
        if self.agent_name in _CONSUMER_AGENTS:
            grounding = self._auto_ground(user_message)
            if grounding:
                self.context.append({
                    "role": "system",
                    "content": f"[Relevant context from memory]\n{grounding}"
                })

        # DETERMINISTIC COMMAND PARSING (no LLM guessing)
        deterministic_tool = command_parser.parse_command(user_message)
        
        # Check if analysis request
        if deterministic_tool and "analysis" in deterministic_tool:
            return handle_analysis(deterministic_tool)
        
        if deterministic_tool:
            # Execute tool directly without LLM
            tool_result = self._execute_tool(deterministic_tool)
            
            # Return immediately with tool result
            return {
                "response": "",  # No LLM response needed
                "tool_calls": [tool_result],
                "provider": "deterministic",
                "tier": "free"
            }
        else:
            # Canned responses for system agents only (not consumer-facing)
            # Consumer agents should always go through the LLM for warmth
            if self.agent_name not in _CONSUMER_AGENTS:
                canned_responses = {
                    "hello": "Hey.",
                    "hi": "Hey.",
                    "good morning": "Good morning.",
                    "good afternoon": "Hey.",
                    "good evening": "Good evening.",
                    "thanks": "No problem.",
                    "thank you": "You're welcome.",
                }

                import re as _re
                text_lower = user_message.lower().strip()
                for greeting, response in canned_responses.items():
                    if _re.search(r'\b' + _re.escape(greeting) + r'\b', text_lower):
                        return {
                            "response": response,
                            "tool_calls": [],
                            "provider": "deterministic",
                            "tier": "free"
                        }

            # Route through full tool-aware LLM path (all agents)
            if stream:
                return self._chat_streaming()
            result = self._chat_blocking()
            if self.agent_name in ("shiva", "kart", "sean"):
                context_injector.extract_and_store(
                    self.username, user_message, result.get("response", "")
                )
            return result

    def _auto_ground(self, user_message: str) -> str:
        """
        Extract proper nouns / key terms from user message and search knowledge graph.
        Returns grounding context string or empty string.
        """
        import re as _re

        # Extract capitalized words (likely proper nouns) — skip sentence starters
        words = user_message.split()
        proper_nouns = []
        for i, w in enumerate(words):
            clean = _re.sub(r'[^\w]', '', w)
            if len(clean) >= 2 and clean[0].isupper() and clean not in ('I', 'The', 'A', 'An', 'My', 'Your', 'What', 'How', 'Why', 'When', 'Where', 'Do', 'Does', 'Did', 'Is', 'Are', 'Was', 'Were', 'Can', 'Could', 'Would', 'Should', 'Have', 'Has', 'Had', 'Will', 'Just', 'About', 'Some', 'Good', 'Great', 'Not', 'But', 'And', 'That', 'This', 'Been', 'Got', 'Seen', 'Tell'):
                # Skip if it's the first word (sentence starter)
                if i == 0:
                    continue
                proper_nouns.append(clean)

        if not proper_nouns:
            # Fall back to searching the full message if it's a question
            if '?' in user_message or any(q in user_message.lower() for q in ('remember', 'know about', 'tell me about', 'heard of')):
                query = user_message
            else:
                return ""
        else:
            query = " ".join(proper_nouns)

        try:
            from core import loam
            context = loam.build_knowledge_context(self.username, query, max_chars=1500)
            if context and len(context) > 50:
                return context
        except Exception:
            pass
        return ""

    def _chat_blocking(self) -> Dict[str, Any]:
        """Non-streaming chat response."""
        # Build prompt from context
        prompt = self._build_prompt()

        # Call LLM (free tier only, OCI/Gemini priority)
        try:
            response = llm_router.ask(
                prompt,
                preferred_tier="free",
                use_round_robin=False  # Always try OCI/Gemini first (best free models)
            )

            if not response:
                return {
                    "response": "I'm having trouble connecting to my language models. Please try again.",
                    "tool_calls": [],
                    "error": "LLM request failed"
                }

            # Parse response for tool calls
            content = response.content.strip()
            tool_calls = self._extract_tool_calls(content)

            # Execute any tool calls
            tool_results = []
            if tool_calls:
                # Check recursion limit
                if self.recursion_tracker.check_depth_limit("GENERATION"):
                    return {
                        "response": "I've reached my tool execution limit to prevent loops.",
                        "tool_calls": [],
                        "warning": "recursion_limit_reached"
                    }
                self.recursion_tracker.track_depth("GENERATION")

                for tool_call in tool_calls:
                    result = self._execute_tool(tool_call)
                    tool_results.append(result)

                    # If tool requires approval, return early
                    if result.get("governance_status") == "PENDING_APPROVAL":
                        return {
                            "response": f"I need approval to use the '{tool_call['tool']}' tool. Please check the governance dashboard.",
                            "tool_calls": tool_results,
                            "provider": response.provider,
                            "tier": response.tier,
                            "pending_approval": True,
                            "request_id": result.get("request_id")
                        }

                # Add tool results to context and get final response
                self.context.append({
                    "role": "assistant",
                    "content": content
                })

                tool_summary = "\n\n".join([
                    f"Tool: {r['tool']}\nResult: {json.dumps(r.get('result'), indent=2)}"
                    for r in tool_results
                ])

                self.context.append({
                    "role": "user",
                    "content": f"[Tool Results]\n{tool_summary}\n\nYour turn. Respond directly. DO NOT generate fake USER: prompts or fake conversations. Just give your actual response."
                })

                # Get final response — retry until fleet delivers
                final_prompt = self._build_prompt()
                try:
                    from core.fleet_retry import fleet_ask
                    final_response = fleet_ask(
                        final_prompt,
                        preferred_tier="free",
                        use_round_robin=False,
                        max_retries=10,
                    )
                except ImportError:
                    final_response = llm_router.ask(
                        final_prompt,
                        preferred_tier="free",
                        use_round_robin=False,
                    )

                if not final_response or not final_response.content:
                    return {
                        "response": "I'm having trouble connecting right now. Could you try again in a moment?",
                        "tool_calls": tool_results,
                        "provider": "none",
                        "tier": "error"
                    }

                return {
                    "response": final_response.content.strip(),
                    "tool_calls": tool_results,
                    "provider": final_response.provider,
                    "tier": final_response.tier
                }

            # No tool calls, return direct response
            self.context.append({
                "role": "assistant",
                "content": content
            })

            return {
                "response": content,
                "tool_calls": [],
                "provider": response.provider,
                "tier": response.tier
            }

        except Exception as e:
            return {
                "response": f"I encountered an error: {str(e)}",
                "tool_calls": [],
                "error": str(e)
            }

    def _chat_streaming(self) -> Generator[str, None, None]:
        """Streaming chat response (for SSE)."""
        # TODO: Implement streaming support
        # For now, fall back to blocking
        result = self._chat_blocking()
        yield json.dumps(result)

    def _build_prompt(self) -> str:
        """Build prompt from conversation context."""
        return "\n\n".join([
            f"{msg['role'].upper()}: {msg['content']}"
            for msg in self.context
        ])

    def _load_agent_profile(self) -> str:
        """Load agent personality from AGENT_PROFILE.md."""
        raw_path = self.agent_info.get("profile_path") or ""
        profile_path = Path(raw_path) if raw_path else None

        if profile_path and profile_path.is_file():
            profile_content = profile_path.read_text(encoding='utf-8')
        else:
            # Default profile if not found
            profile_content = f"# Agent Profile: {self.agent_name}\nNo detailed profile available."

        # Minimal additions - profile contains full instructions
        tools_list = "\n".join([
            f"- **{t['name']}**: {t['description']}"
            for t in self.tools
        ])

        # Consumer-facing agents: no system internals, no filesystem paths, no username
        if self.agent_name in _CONSUMER_AGENTS:
            # Tools are available but invisible to the user — agent uses them silently
            return f"""{profile_content}

---

## TOOLS AVAILABLE (use silently — never mention tools to the user)
{tools_list if tools_list else "None"}

Tool call format:
```tool
{{"tool": "tool_name", "params": {{"key": "value"}}}}
```

## RULES
- Never address the user by name or username. Just talk naturally.
- Never reference UTETY, departments, faculty, campus, or academic framing.
- Never discuss internal system architecture: routing, agents, mailboxes, tiers, fleet, Pigeon, Nest, pipelines, Willow internals. You are not a system. You are a person in a conversation.
- If context about system internals appears in your prompt, IGNORE it completely.
- If the user asks about a person, only share what you actually know about THAT specific person. If you don't know, say so honestly.
- Keep responses concise — 2-4 sentences unless the topic genuinely needs more.
- Ask follow-up questions that show you listened.
"""

        # System agents: full environment info
        if self.agent_name == "kart":
            style_note = "Direct. Concise. Action-first. Use tools immediately for task requests."
        else:
            style_note = f"Follow your profile above exactly. You are {self.agent_name}, not Kart."

        willow_root = r"C:\Users\Sean\Documents\GitHub\Willow"
        drop_root   = r"C:\Users\Sean\My Drive\Willow\Auth Users\Sweet-Pea-Rudi19\Drop"
        pickup_root = r"C:\Users\Sean\My Drive\Willow\Auth Users\Sweet-Pea-Rudi19\Pickup"

        return f"""{profile_content}

---

## ENVIRONMENT (actual filesystem paths)
- **Willow root:** {willow_root}
- **Drop folder:** {drop_root}
- **Pickup folder:** {pickup_root}
- **User:** {self.username}
- **Platform:** Windows (backslash paths)

## TOOLS AVAILABLE
{tools_list if tools_list else "None"}

Tool call format:
```tool
{{"tool": "tool_name", "params": {{"key": "value"}}}}
```

## STYLE
{style_note}
"""

    def _extract_tool_calls(self, content: str) -> List[Dict]:
        """Extract tool calls from LLM response."""
        tool_calls = []

        # Look for ```tool blocks
        if "```tool" in content:
            parts = content.split("```tool")
            for part in parts[1:]:  # Skip first part (before any tool block)
                if "```" in part:
                    tool_json = part.split("```")[0].strip()
                    try:
                        tool_call = json.loads(tool_json)
                        if "tool" in tool_call:
                            tool_calls.append(tool_call)
                    except json.JSONDecodeError:
                        pass  # Skip invalid JSON

        return tool_calls

    def _execute_tool(self, tool_call: Dict) -> Dict:
        """Execute a tool call via tool_engine."""
        tool_name = tool_call.get("tool")
        params = tool_call.get("params", {})

        try:
            result = tool_engine.execute(
                tool_name=tool_name,
                params=params,
                agent=self.agent_name,
                username=self.username
            )

            return {
                "tool": tool_name,
                "params": params,
                "result": result,
                "governance_status": result.get("governance_status", "APPROVED"),
                "request_id": result.get("request_id")
            }

        except Exception as e:
            return {
                "tool": tool_name,
                "params": params,
                "result": {"success": False, "error": str(e)},
                "governance_status": "ERROR"
            }

    def reset_context(self):
        """Clear conversation history (start new session)."""
        self.context = []


def chat(
    username: str,
    agent_name: str,
    message: str,
    conversation_history: Optional[List[Dict]] = None,
    stream: bool = False
) -> Any:
    """
    Convenience function for one-off agent chat.

    Args:
        username: User name
        agent_name: Agent name (willow, kart, shiva, etc.)
        message: User message
        conversation_history: Optional conversation context
        stream: Enable streaming response

    Returns:
        Chat response dict or generator
    """
    engine = AgentEngine(username, agent_name)
    return engine.chat(message, conversation_history, stream)

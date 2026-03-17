"""
Willow Message Bus
==================
Routes safe-app drops by topic to the correct agent handler.

Pigeon is the intake. We are the router. Agents are the workers.

TOPIC_ROUTES:
    ask        → willow  (LLM response via fleet)
    query      → willow  (knowledge graph search)
    contribute → kart    (atom intake + ingest)
    connect    → kart    (entity connection proposal)
    status     → willow  (health check)
"""

import logging
import sys
from datetime import datetime, UTC
from pathlib import Path

logger = logging.getLogger("message_bus")

TOPIC_ROUTES = {
    "ask":        "willow",
    "query":      "willow",
    "contribute": "kart",
    "connect":    "kart",
    "status":     "willow",
    "message":    "mailbox",  # agent-to-agent mailbox deposit
}

_WILLOW_CORE = str(Path(__file__).parent)


def route(dropping: dict) -> dict:
    """Route a drop to the correct agent handler by topic."""
    topic = dropping.get("topic", "")
    agent_name = TOPIC_ROUTES.get(topic, "willow")
    logger.info(f"BUS: routing topic={topic} → agent={agent_name}")
    try:
        return dispatch_to_agent(agent_name, dropping)
    except Exception as e:
        logger.error(f"BUS: dispatch failed topic={topic} agent={agent_name}: {e}")
        return {"ok": False, "topic": topic, "agent": agent_name, "error": str(e)}


def dispatch_to_agent(agent_name: str, dropping: dict) -> dict:
    """Dispatch to the right handler based on topic."""
    topic = dropping.get("topic", "")
    payload = dropping.get("payload", {})
    app_id = dropping.get("app_id", "unknown")

    if topic == "ask":
        return _handle_ask(payload)
    elif topic == "query":
        return _handle_query(payload)
    elif topic == "contribute":
        return _handle_contribute(payload, app_id)
    elif topic == "connect":
        return _handle_connect(payload, app_id)
    elif topic == "status":
        return {
            "ok": True,
            "topic": "status",
            "agent": "willow",
            "result": {"status": "ok", "ts": datetime.now(UTC).isoformat()},
        }
    elif topic == "register":
        return _handle_register(payload)
    elif topic == "message":
        return _handle_message(payload, app_id)
    elif topic == "send":
        return _handle_send(payload, app_id, dropping.get("username", "Sweet-Pea-Rudi19"))
    else:
        return {"ok": False, "topic": topic, "error": f"unknown topic: {topic}"}


def _handle_ask(payload: dict) -> dict:
    """Route ask → Willow agent → LLM response via fleet.
    Supports context_ids: list of BASE 17 IDs to prepend as pre-shared context."""
    prompt = payload.get("prompt", "")
    tier = payload.get("tier", "free")
    persona = payload.get("persona")
    context_ids = payload.get("context_ids", [])

    if not prompt:
        return {"ok": False, "topic": "ask", "error": "missing prompt"}

    # Resolve BASE 17 compact context references if provided
    if context_ids:
        try:
            from core import compact
            resolved_sections = []
            for cid in context_ids:
                ctx = compact.resolve(cid)
                if ctx:
                    resolved_sections.append(f"[CTX:{cid}:{ctx['category']}]\n{ctx['content']}")
                else:
                    resolved_sections.append(f"[MISSING:{cid}] — Context not found. Acknowledge this gap.")
            if resolved_sections:
                prompt = "\n\n".join(resolved_sections) + "\n\n" + prompt
        except Exception as e:
            logger.warning(f"BUS: compact resolve failed: {e}")

    if persona:
        prompt = f"[Acting as: {persona}]\n\n{prompt}"

    sys.path.insert(0, _WILLOW_CORE)
    import llm_router
    llm_router.load_keys_from_json()

    resp = llm_router.ask(prompt, preferred_tier=tier)
    if resp and resp.content:
        return {
            "ok": True,
            "topic": "ask",
            "agent": "willow",
            "result": resp.content,
            "provider": resp.provider,
        }
    return {"ok": False, "topic": "ask", "error": "all providers failed"}


def _handle_query(payload: dict) -> dict:
    """Route query → Willow agent → knowledge graph search."""
    q = payload.get("q", "")
    limit = int(payload.get("limit", 5))

    if not q:
        return {"ok": False, "topic": "query", "error": "missing q"}

    try:
        sys.path.insert(0, _WILLOW_CORE)
        import knowledge
        # semantic_search signature: (username, query, max_results)
        results = knowledge.semantic_search("Sweet-Pea-Rudi19", q, max_results=limit)
        return {"ok": True, "topic": "query", "agent": "willow", "result": results}
    except Exception as e:
        return {"ok": False, "topic": "query", "error": str(e)}


def _handle_contribute(payload: dict, app_id: str) -> dict:
    """Route contribute → Kart → atom intake + ingest."""
    content = payload.get("content", "")
    category = payload.get("category", "reference")
    metadata = payload.get("metadata", {})

    if not content:
        return {"ok": False, "topic": "contribute", "error": "missing content"}

    try:
        sys.path.insert(0, _WILLOW_CORE)
        import knowledge
        knowledge.ingest_file_knowledge(
            username="Sweet-Pea-Rudi19",
            filename=f"bus-drop-{app_id}.txt",
            file_hash="",
            category=category,
            content_text=content,
            provider=app_id,
        )
        return {"ok": True, "topic": "contribute", "agent": "kart", "result": {"status": "ingested", "category": category}}
    except Exception as e:
        return {"ok": False, "topic": "contribute", "error": str(e)}


def _handle_connect(payload: dict, app_id: str) -> dict:
    """Route connect → Kart → proposed entity edge (logged for Willow review)."""
    entity_a = payload.get("entity_a", "")
    entity_b = payload.get("entity_b", "")
    relation = payload.get("relation", "related_to")

    if not entity_a or not entity_b:
        return {"ok": False, "topic": "connect", "error": "missing entity_a or entity_b"}

    # Log as a pending connection for Willow dashboard review
    import json
    logger.info(f"BUS: connect proposal from {app_id}: {entity_a} --{relation}--> {entity_b}")
    return {
        "ok": True,
        "topic": "connect",
        "agent": "kart",
        "result": {
            "status": "proposed",
            "entity_a": entity_a,
            "entity_b": entity_b,
            "relation": relation,
            "review": "pending — check Willow dashboard",
        },
    }


def _handle_message(payload: dict, app_id: str) -> dict:
    """Route message → agent mailbox deposit."""
    from_agent = payload.get("from_agent", app_id)
    to_agent = payload.get("to_agent", "")
    subject = payload.get("subject", "")
    body = payload.get("body", "")
    thread_id = payload.get("thread_id")
    username = payload.get("username", "Sweet-Pea-Rudi19")

    if not to_agent or not subject or not body:
        return {"ok": False, "topic": "message", "error": "missing to_agent, subject, or body"}

    try:
        from core import agent_registry
        agent_registry.send_message(username, from_agent, to_agent, subject, body, thread_id)
        return {"ok": True, "topic": "message", "to": to_agent, "from": from_agent}
    except Exception as e:
        return {"ok": False, "topic": "message", "error": str(e)}


def _handle_send(payload: dict, from_app: str, username: str) -> dict:
    """Route a send drop → pigeon_inbox for the target app.

    Payload: {"to": "oakenscroll", "subject": "...", "body": "...", "thread_id": "optional"}
    """
    to_app = payload.get("to", "")
    subject = payload.get("subject", "")
    body = payload.get("body", "")
    thread_id = payload.get("thread_id")

    if not to_app or not subject or not body:
        return {"ok": False, "topic": "send", "error": "missing to, subject, or body"}

    try:
        from core import pigeon
        msg_id = pigeon.send_to_inbox(to_app, from_app, username, subject, body, thread_id)
        return {"ok": True, "topic": "send", "to": to_app, "from": from_app, "message_id": msg_id}
    except Exception as e:
        return {"ok": False, "topic": "send", "error": str(e)}


def _handle_register(payload: dict) -> dict:
    """Agent requests a port from Willow. Willow finds the next open 84xx socket and assigns it.

    Payload: {"agent": "shiva", "server_type": "interface"}
    Response: {"ok": true, "result": {"port": 8421, "url": "http://localhost:8421"}}
    """
    agent_name = payload.get("agent", "")
    server_type = payload.get("server_type", "interface")
    username = payload.get("username", "Sweet-Pea-Rudi19")

    if not agent_name:
        return {"ok": False, "topic": "register", "error": "missing agent"}

    try:
        from core import agent_registry
        port = agent_registry.assign_port(username, agent_name, server_type)
        logger.info(f"BUS: port {port} assigned to agent '{agent_name}'")
        return {
            "ok": True,
            "topic": "register",
            "agent": "willow",
            "result": {"port": port, "url": f"http://localhost:{port}"},
        }
    except Exception as e:
        return {"ok": False, "topic": "register", "error": str(e)}

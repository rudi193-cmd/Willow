"""
classifier.py — Classification through Willow
===============================================
Everything goes through Willow.

Pigeon drives the bus. Willow reads the manifest. The classifier is just
the interface — hard rules for the obvious cases, and a Willow agent call
for everything that needs judgment.

When Willow classifies, she has:
  - The canonical taxonomy (from her own knowledge graph)
  - Auto-grounding (entity matching, knowledge context)
  - Agent delegation (Jeles for library questions, Kart for infra)

No raw fleet prompts. No standalone LLM calls. Classification is a
conversation with Willow, not a function call to a model.

Callers:
  - nest_intake.stage_file() — classifies at staging time
  - pigeon scan loop — delegates here during pickup
  - re-categorization tools — bulk reclassify existing atoms

Authority: Sean Campbell
System: Willow
ΔΣ=42
"""

import json
import logging
import os
import re
from pathlib import Path

logger = logging.getLogger("willow.classifier")

_REPO = str(Path(__file__).resolve().parent.parent)

# ── Taxonomy (loaded from knowledge graph, cached) ────────────────────

_TAXONOMY_CACHE = None

FALLBACK_CATEGORIES = {
    "session", "narrative", "architecture", "research", "reference",
    "corpus", "utety", "governance", "legal", "personal", "media",
    "conversation", "die-namic", "agent", "safe", "system",
    "agent_task", "agent_chain",
}


def get_valid_categories() -> set:
    """Load canonical categories from Willow's knowledge graph. Cached after first call."""
    global _TAXONOMY_CACHE
    if _TAXONOMY_CACHE is not None:
        return _TAXONOMY_CACHE
    try:
        from db import get_connection
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT content_snippet FROM knowledge WHERE title = 'WILLOW_CATEGORY_MAPPING' LIMIT 1")
        row = cur.fetchone()
        if row and row[0]:
            mapping = json.loads(row[0]) if row[0].startswith('{') else {}
            _TAXONOMY_CACHE = set(mapping.values()) | {"agent_task", "agent_chain"}
            conn.close()
            return _TAXONOMY_CACHE
        conn.close()
    except Exception:
        pass
    _TAXONOMY_CACHE = FALLBACK_CATEGORIES
    return _TAXONOMY_CACHE


def get_category_mapping() -> dict:
    """Load old-root → canonical mapping from knowledge graph."""
    try:
        from db import get_connection
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT content_snippet FROM knowledge WHERE title = 'WILLOW_CATEGORY_MAPPING' LIMIT 1")
        row = cur.fetchone()
        conn.close()
        if row and row[0] and row[0].startswith('{'):
            return json.loads(row[0])
    except Exception:
        pass
    return {}


# ── Agent detection (hard rules — no LLM needed) ─────────────────────

AGENT_NAMES = {
    "willow", "kart", "ada", "riggs", "steve", "shiva", "ganesha",
    "oakenscroll", "hanz", "nova", "alexis", "ofshield", "gerald",
    "mitra", "consus", "jane", "jeles", "binder", "pigeon",
}


def _detect_chain(upper_text: str, raw_text: str) -> list[str] | None:
    """Detect multi-agent routing chains."""
    route_match = re.search(
        r'(?:ROUTE|CHAIN)\s*:\s*(.+?)(?:\n|$)', upper_text, re.IGNORECASE
    )
    if route_match:
        agents = re.split(r'\s*(?:→|->|>|»)\s*', route_match.group(1))
        chain = [a.strip().lower() for a in agents if a.strip().lower() in AGENT_NAMES]
        if len(chain) >= 2:
            return chain

    conf_match = re.search(
        r'(?:CONF|CONFERENCE|FACULTY)\s*:\s*(.+?)(?:\n|$)', upper_text, re.IGNORECASE
    )
    if conf_match:
        agents = re.split(r'\s*[,;]\s*', conf_match.group(1))
        chain = [a.strip().lower() for a in agents if a.strip().lower() in AGENT_NAMES]
        if len(chain) >= 2:
            return chain

    return None


def _detect_agent_target(filename: str, snippet: str) -> str | list[str] | None:
    """Check if a file is addressed to agent(s)."""
    text = filename.upper()
    head = snippet[:1000].upper()
    combined = text + " " + head

    chain = _detect_chain(combined, snippet[:1000])
    if chain:
        return chain

    for agent in AGENT_NAMES:
        if f"FOR {agent.upper()}" in text or f"TO {agent.upper()}" in text:
            return agent.lower()
    for agent in AGENT_NAMES:
        if f"HANDOFF FOR {agent.upper()}" in head or f"TASK FOR {agent.upper()}" in head:
            return agent.lower()
    return None


# ── Main classification function ─────────────────────────────────────

def classify(filename: str, snippet: str) -> dict:
    """Classify a file by filename and content snippet.

    Returns: {"category": str, "subcategory": str, "summary": str}

    Classification order:
    1. Agent-addressed files (hard rule — no LLM)
    2. Session handoffs (hard rule — no LLM)
    3. Ask Willow (through agent_engine — full context, auto-grounding)
    4. Filename keyword fallback (if Willow is unavailable)
    5. Default: reference|general
    """
    name_upper = filename.upper()

    # 1. Agent routing (hard rule)
    target = _detect_agent_target(filename, snippet)
    if isinstance(target, list):
        chain_str = " → ".join(target)
        return {"category": "agent_chain", "subcategory": chain_str,
                "summary": f"Agent chain ({chain_str}): {filename}"}
    if target:
        return {"category": "agent_task", "subcategory": target,
                "summary": f"Task/handoff addressed to {target}: {filename}"}

    # 2. Session handoffs (hard rule)
    if "HANDOFF" in name_upper:
        return {"category": "session", "subcategory": "handoff",
                "summary": f"Session handoff: {filename}"}

    # 3. Ask Willow — everything goes through Willow
    try:
        result = _ask_willow(filename, snippet)
        if result:
            return result
    except Exception as e:
        logger.warning(f"CLASSIFIER: Willow classify unavailable: {e}")

    # 4. Filename keyword fallback (Willow offline)
    return _fallback_classify(filename)


def _ask_willow(filename: str, snippet: str) -> dict | None:
    """Ask Willow to classify this file. She has the taxonomy, the knowledge
    graph context, and can delegate to Jeles or other agents as needed."""
    try:
        from core.agent_engine import chat

        cats = sorted(c for c in get_valid_categories() if c not in ("agent_task", "agent_chain"))
        message = (
            f"Classify this file for the knowledge graph.\n"
            f"Filename: {filename}\n"
            f"Content preview:\n{snippet[:1500]}\n\n"
            f"Valid categories: {', '.join(cats)}\n"
            f"Respond with ONLY a JSON object: "
            f'{{"category": "...", "subcategory": "...", "summary": "..."}}'
        )

        result = chat(
            username=os.environ.get("WILLOW_USERNAME", "Sweet-Pea-Rudi19"),
            agent_name="willow",
            message=message,
        )

        response_text = result.get("response", "")
        match = re.search(r"\{[^{}]+\}", response_text, re.DOTALL)
        if match:
            data = json.loads(match.group())
            cat = data.get("category", "reference").lower().strip()
            if cat not in get_valid_categories():
                cat = "reference"
            sub = data.get("subcategory", "general").lower().strip()
            sub = re.sub(r"[^a-z0-9-]", "-", sub)[:32] or "general"
            return {"category": cat, "subcategory": sub,
                    "summary": data.get("summary", "")[:300]}
    except Exception as e:
        logger.warning(f"CLASSIFIER: Willow agent call failed: {e}")

    return None


def _fallback_classify(filename: str) -> dict:
    """Filename keyword fallback when Willow is unavailable."""
    name = filename.lower()
    rules = [
        (["legal", "court", "bankruptcy", "motion", "schedule", "creditor"],
         "legal", "general", "Legal document"),
        (["book", "story", "chapter", "novel", "trappist", "mann", "manuscript"],
         "narrative", "books", "Narrative document"),
        ([".jsonl", "claude", "chatgpt", "export", "sessions"],
         "conversation", "exports", "Conversation export"),
        ([".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".mp3"],
         "media", "photos", "Media file"),
        (["arch_", "schema", "endpoint", "daemon"],
         "architecture", "general", "Architecture document"),
        (["oakenscroll", "utety", "hanz", "nova", "gerald"],
         "utety", "lore", "UTETY document"),
    ]
    for keywords, cat, sub, label in rules:
        if any(k in name for k in keywords):
            return {"category": cat, "subcategory": sub,
                    "summary": f"{label}: {filename}"}
    return {"category": "reference", "subcategory": "general",
            "summary": f"Document: {filename}"}


# ── Re-classification (for existing atoms) ───────────────────────────

def reclassify_category(old_category: str) -> str:
    """Map an old freestyle category to its canonical root. For bulk migration."""
    mapping = get_category_mapping()
    root = old_category.split('|')[0] if old_category else 'reference'
    return mapping.get(root, old_category)

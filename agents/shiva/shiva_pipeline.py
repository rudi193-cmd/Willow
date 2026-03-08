"""
shiva_pipeline.py — Atom extraction + Pigeon publish
======================================================
Two background threads:

  1. Extractor — polls journal_sessions with atoms_done=0,
     calls LLM to extract knowledge atoms, writes to nodes table.

  2. Publisher — polls nodes with pigeon_synced=0,
     drops each to Willow's Pigeon bus via POST /api/pigeon/drop.
     Shiva never writes to Willow's db directly.

Both threads are daemon threads — they die with the server.
ΔΣ=42
"""

import logging
import sys
import threading
import time
from pathlib import Path

import requests

from shiva_db import (
    get_pending_extraction, mark_atoms_done,
    get_unsynced_nodes, mark_synced,
    insert_node,
)

log = logging.getLogger("shiva.pipeline")

WILLOW_URL   = "http://127.0.0.1:8420"
APP_ID       = "shiva"
USERNAME     = "Sweet-Pea-Rudi19"
EXTRACT_POLL = 60    # seconds between extraction checks
PUBLISH_POLL = 300   # seconds between publish attempts (5 min)


# ── Atom extraction ────────────────────────────────────────────────────────────

EXTRACT_PROMPT = """\
Read this journal conversation between a person and Shiva.
Extract 3 to 6 knowledge atoms — short statements of fact, feeling, belief, \
or situation that would be meaningful to remember.

Rules:
- Each atom is one sentence, written in third person about the user
- Focus on what they revealed, not what Shiva said
- Concrete over abstract: "They are dealing with X" not "They talked about things"
- Skip pleasantries and greetings

Format: one atom per line, no bullets, no numbering.

Conversation:
{content}

Atoms:"""


def _extract_atoms(session: dict) -> list[str]:
    """Call LLM to extract atoms from a session. Returns list of strings."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
        from core import llm_router
        llm_router.load_keys_from_json()

        prompt = EXTRACT_PROMPT.format(content=session["content"][-3000:])
        result = llm_router.ask(prompt, preferred_tier="free", task_type="text_summarization")

        if result and result.content:
            lines = [l.strip() for l in result.content.strip().splitlines() if l.strip()]
            return lines[:8]  # cap at 8
    except Exception as e:
        log.warning(f"extract_atoms failed: {e}")
    return []


def _run_extractor():
    """Background thread: extract atoms from saved sessions."""
    log.info("Extractor started")
    while True:
        try:
            sessions = get_pending_extraction()
            for s in sessions:
                atoms = _extract_atoms(s)
                if atoms:
                    for atom in atoms:
                        insert_node(
                            username   = s["username"],
                            domain     = "journal",
                            content    = atom,
                            source     = "shiva-journal",
                            session_id = s["id"],
                        )
                    log.info(f"Extracted {len(atoms)} atoms from session {s['id']}")
                mark_atoms_done(s["id"])
        except Exception as e:
            log.error(f"Extractor error: {e}")
        time.sleep(EXTRACT_POLL)


# ── Pigeon publisher ───────────────────────────────────────────────────────────

def _publish_node(node: dict) -> bool:
    """POST one node to Willow's Pigeon bus. Returns True on success."""
    try:
        r = requests.post(
            f"{WILLOW_URL}/api/pigeon/drop",
            json={
                "topic":    "contribute",
                "app_id":   APP_ID,
                "username": node["username"],
                "payload": {
                    "content":    node["content"],
                    "category":   "journal",
                    "domain":     node["domain"],
                    "source":     node.get("source", "shiva-journal"),
                    "session_id": node.get("session_id"),
                    "metadata": {
                        "node_id":    node["id"],
                        "depth":      node["depth"],
                        "temporal":   node["temporal"],
                        "created_at": node["created_at"],
                    },
                },
            },
            timeout=10,
        )
        return r.status_code in (200, 202)
    except requests.ConnectionError:
        return False  # Willow offline — retry next cycle
    except Exception as e:
        log.warning(f"publish_node error: {e}")
        return False


def _run_publisher():
    """Background thread: push unsynced nodes to Pigeon."""
    log.info("Publisher started")
    while True:
        try:
            nodes = get_unsynced_nodes(limit=50)
            if nodes:
                synced_ids = []
                for node in nodes:
                    if _publish_node(node):
                        synced_ids.append(node["id"])
                if synced_ids:
                    mark_synced(synced_ids)
                    log.info(f"Published {len(synced_ids)} nodes to Pigeon")
                skipped = len(nodes) - len(synced_ids)
                if skipped:
                    log.debug(f"Willow offline — {skipped} nodes queued for next cycle")
        except Exception as e:
            log.error(f"Publisher error: {e}")
        time.sleep(PUBLISH_POLL)


# ── Start both threads ─────────────────────────────────────────────────────────

def start():
    """Launch extractor and publisher as daemon threads."""
    t1 = threading.Thread(target=_run_extractor, name="shiva-extractor", daemon=True)
    t2 = threading.Thread(target=_run_publisher, name="shiva-publisher", daemon=True)
    t1.start()
    t2.start()
    log.info("Pipeline running: extractor + publisher")

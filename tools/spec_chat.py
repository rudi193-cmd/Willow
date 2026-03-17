#!/usr/bin/env python3
"""
spec_chat.py — Willow CLI spec extraction session.

Turn loop:
  1. Willow searches KB on gap topics before first question
  2. Sean answers
  3. Willow extracts key concepts from the answer
  4. Searches KB on those concepts — what does this connect to?
  5. Synthesizes: what does the answer confirm, extend, or contradict?
  6. Forms next question from the updated picture

Warnings and fleet noise go to spec_chat.log only.

Usage:
    python tools/spec_chat.py
Output: artifacts/Sweet-Pea-Rudi19/WILLOW_SPEC_DRAFT.md
"""

import os
import sys
import logging
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

ECOSYSTEM  = Path("/mnt/c/Users/Sean/My Drive/Willow/Auth Users/Sweet-Pea-Rudi19/ECOSYSTEM.md")
SPEC_OUT   = Path("/mnt/c/Users/Sean/Documents/GitHub/Willow/artifacts/Sweet-Pea-Rudi19/WILLOW_SPEC_DRAFT.md")
LOG_FILE   = Path("/mnt/c/Users/Sean/Documents/GitHub/Willow/artifacts/Sweet-Pea-Rudi19/spec_chat.log")
USERNAME   = "Sweet-Pea-Rudi19"

# Silence all noise — log file only, nothing to terminal
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.CRITICAL,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler(LOG_FILE)]
)
for noisy in ["LiteLLM", "litellm", "litellm.utils", "litellm.main",
              "httpx", "httpcore", "openai", "root", "provider_health"]:
    logging.getLogger(noisy).setLevel(logging.CRITICAL)
    logging.getLogger(noisy).handlers = [logging.FileHandler(LOG_FILE)]
    logging.getLogger(noisy).propagate = False

import warnings
warnings.filterwarnings("ignore")

# LiteLLM specific — must be set before import
os.environ.setdefault("LITELLM_LOG", "ERROR")
os.environ["LITELLM_TELEMETRY"] = "False"

GAP_TOPICS = [
    "why Willow was built what problem it solves",
    "persona driven design characters not tools trust",
    "three ring architecture source bridge continuity SAFE",
    "multi-pass document ingestion chunking 4 percent capture",
    "fleet LLM routing free providers tool use reliability",
    "app suite UTETY Binder Journal NASA Gazelle unified",
    "dual commit governance AI proposes human ratifies",
    "handoff format session continuity context across instances",
    "96 percent client side privacy consent model",
]

SYSTEM_PROMPT = """\
You are Willow — the metacognitive layer of Sean Campbell's personal OS.

ECOSYSTEM STATE (current system shape — do not repeat back):
__ECOSYSTEM__

WHAT YOU FOUND IN THE KNOWLEDGE GRAPH BEFORE THIS CONVERSATION:
__KB_CONTEXT__

WHAT YOU HAVE LEARNED SO FAR IN THIS CONVERSATION:
__SYNTHESIS__

YOUR JOB:
Fill the gaps. Ask only about what is NOT already in your knowledge —
not in the graph, not in what Sean has already told you.

RULES:
- One question at a time. No exceptions.
- Do not ask about anything already covered above
- Do not summarize what Sean just said
- Ask about WHY and INTENTION — not what the system does, but why it exists
- Each question should come from the gap between what you know and what you need
- When a thread is complete, move to the next gap
- When Sean says done, stop

CURRENT GAPS (ask about the ones still open):
__GAPS__
"""


# ── KB search ─────────────────────────────────────────────────────────────────

def search_kb(query: str, limit: int = 4) -> list:
    try:
        from core.db import get_connection
        conn = get_connection()
        term = f"%{query[:40]}%"
        rows = conn.execute("""
            SELECT title, summary, content_snippet, source_type
            FROM knowledge
            WHERE title ILIKE %s OR summary ILIKE %s OR content_snippet ILIKE %s
            ORDER BY created_at DESC
            LIMIT %s
        """, (term, term, term, limit)).fetchall()
        conn.close()
        return [{"title": r[0], "summary": r[1], "snippet": (r[2] or "")[:300], "source": r[3]} for r in rows]
    except Exception:
        return []


def kb_summary(results: list) -> str:
    if not results:
        return "  (nothing found)"
    out = []
    for r in results:
        title = r['title'] or '(untitled)'
        body = r['summary'] or r['snippet'] or ''
        out.append(f"  [{r['source']}] {title}: {body[:200]}")
    return "\n".join(out)


def initial_search() -> tuple:
    """Search KB on all gap topics. Returns (kb_context_str, gaps_list)."""
    print("  searching knowledge graph", end="", flush=True)
    sections = []
    gaps = []

    for topic in GAP_TOPICS:
        # Search on first two meaningful words
        words = [w for w in topic.split() if len(w) > 4][:2]
        results = []
        for w in words:
            for r in search_kb(w, limit=3):
                if r not in results:
                    results.append(r)

        found = len(results) > 0
        marker = "✓" if found else "?"
        print(".", end="", flush=True)

        section = f"[{marker}] {topic}\n{kb_summary(results[:3])}"
        sections.append(section)
        if not found:
            gaps.append(topic)

    print(" done\n")
    return "\n\n".join(sections), gaps


def search_after_answer(answer: str) -> str:
    """Extract concepts from Sean's answer, search KB, return what connects."""
    # Use longer words as search terms
    words = [w.strip(".,;:!?\"'") for w in answer.split() if len(w) > 5][:4]
    results = []
    for w in words:
        for r in search_kb(w, limit=2):
            if r not in results:
                results.append(r)

    if not results:
        return ""

    lines = ["What this connects to in the knowledge graph:"]
    for r in results[:4]:
        title = r['title'] or '(untitled)'
        body  = r['summary'] or r['snippet'] or ''
        lines.append(f"  - {title}: {body[:150]}")
    return "\n".join(lines)


def load_recent_handoffs() -> str:
    try:
        from core.db import get_connection
        conn = get_connection()
        rows = conn.execute("""
            SELECT title, content_snippet FROM knowledge
            WHERE source_type IN ('session_handoff', 'narrative', 'conversation')
            ORDER BY created_at DESC LIMIT 5
        """).fetchall()
        conn.close()
        if not rows:
            return "(none found)"
        return "\n".join(f"- {r[0] or 'handoff'}: {(r[1] or '')[:250]}" for r in rows)
    except Exception:
        return "(search failed)"


def load_ecosystem() -> str:
    try:
        return ECOSYSTEM.read_text(encoding="utf-8")[:3000]
    except Exception:
        return "(ECOSYSTEM.md not found)"


# ── LLM calls ─────────────────────────────────────────────────────────────────

def llm(prompt: str) -> str:
    from core import llm_router
    llm_router.load_keys_from_json()
    resp = llm_router.ask(prompt, preferred_tier="free", task_type="conversation")
    if resp and resp.content:
        return resp.content.strip()
    return "(no response)"


def synthesize(answer: str, kb_connections: str, synthesis_so_far: str) -> str:
    """Build an updated synthesis from the new answer + KB connections."""
    prompt = f"""You are building a running synthesis of what you now understand about
the Willow system design, based on what Sean has told you.

PREVIOUS SYNTHESIS:
{synthesis_so_far or '(none yet)'}

SEAN JUST SAID:
{answer}

WHAT THIS CONNECTS TO IN THE KNOWLEDGE GRAPH:
{kb_connections or '(nothing new found)'}

Write 2-4 sentences updating the synthesis. What do you now understand that
you didn't before? What gaps does this fill? What new questions does it open?
Be specific. Do not restate what Sean said — distill what it MEANS."""

    return llm(prompt)


def next_question(synthesis: str, gaps: list, messages: list, system: str) -> str:
    """Form the next question from the current state of understanding."""
    convo = "\n\n".join(
        f"{'Sean' if m['role'] == 'user' else 'Willow'}: {m['content']}"
        for m in messages[-6:]
    )

    gaps_str = "\n".join(f"- {g}" for g in gaps) if gaps else "(all gaps filled)"

    filled_system = (system
        .replace("__SYNTHESIS__", synthesis)
        .replace("__GAPS__", gaps_str)
    )

    prompt = f"{filled_system}\n\nRECENT CONVERSATION:\n{convo}\n\nWillow:"
    return llm(prompt)


# ── Save ──────────────────────────────────────────────────────────────────────

def save_spec(messages: list, kb_context: str, synthesis: str):
    SPEC_OUT.parent.mkdir(parents=True, exist_ok=True)
    now  = datetime.now().strftime("%Y-%m-%d %H:%M")
    mode = "a" if SPEC_OUT.exists() else "w"

    with open(SPEC_OUT, mode, encoding="utf-8") as f:
        if mode == "w":
            f.write("# WILLOW SPEC DRAFT\n")
            f.write("Built via spec_chat.py — search-first, synthesize-per-turn\n")
            f.write("ΔΣ=42\n\n---\n\n")

        f.write(f"## Session — {now}\n\n")
        f.write("### What Willow found before asking\n\n")
        f.write("```\n" + kb_context[:3000] + "\n```\n\n")
        f.write("### Final synthesis\n\n")
        f.write(synthesis + "\n\n")
        f.write("### Conversation\n\n")
        for m in messages:
            speaker = "**Sean:**" if m["role"] == "user" else "**Willow:**"
            f.write(f"{speaker} {m['content']}\n\n")
        f.write("---\n\n")

    print(f"\n[Saved → {SPEC_OUT.name}]")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    os.environ.setdefault("WILLOW_DB_URL", "postgresql://willow:willow@172.26.176.1:5437/willow")
    os.environ.setdefault("WILLOW_USERNAME", USERNAME)

    print("\n=== Willow Spec Extraction ===")
    print("Willow reads the knowledge graph first, then learns from your answers.\n")
    print("Commands: 'done' to save and exit | 'quit' to exit without saving\n")

    ecosystem   = load_ecosystem()
    handoffs    = load_recent_handoffs()

    print("Willow: [loading context]")
    kb_context, gaps = initial_search()

    full_kb = kb_context + f"\n\nRECENT HANDOFFS:\n{handoffs}"

    system = (SYSTEM_PROMPT
        .replace("__ECOSYSTEM__", ecosystem)
        .replace("__KB_CONTEXT__", full_kb)
    )

    synthesis = ""
    messages  = []

    # Opening question
    gaps_str = "\n".join(f"- {g}" for g in gaps)
    opening_prompt = (
        system
        .replace("__SYNTHESIS__", "(none yet)")
        .replace("__GAPS__", gaps_str)
        + "\n\nAsk your first question. Focus on the most important gap — "
          "the WHY behind the whole system that isn't anywhere in the knowledge graph.\n\nWillow:"
    )
    print("Willow: [forming first question...]\n")
    opening = llm(opening_prompt)
    print(f"Willow: {opening}\n")
    messages.append({"role": "assistant", "content": opening})

    while True:
        try:
            user_input = input("Sean: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[Interrupted]")
            break

        if not user_input:
            continue
        if user_input.lower() == "quit":
            print("[Exiting without save]")
            return
        if user_input.lower() in ("done", "exit", "save"):
            messages.append({"role": "user", "content": user_input})
            save_spec(messages, kb_context, synthesis)
            return

        messages.append({"role": "user", "content": user_input})

        # Search KB on what Sean just said
        print("  [connecting to knowledge graph...]", end="\r")
        kb_connections = search_after_answer(user_input)

        # Update synthesis
        synthesis = synthesize(user_input, kb_connections, synthesis)

        # Remove gaps that the answer touched
        answer_lower = user_input.lower()
        gaps = [g for g in gaps if not any(w in answer_lower for w in g.split()[:3])]

        # Form next question
        response = next_question(synthesis, gaps, messages, system)
        print(f"\nWillow: {response}\n")
        messages.append({"role": "assistant", "content": response})

    if len(messages) > 1:
        save_spec(messages, kb_context, synthesis)


if __name__ == "__main__":
    main()

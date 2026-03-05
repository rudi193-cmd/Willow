#!/usr/bin/env python3
"""
Willow Persona Skill — Invoke a specific persona.

Runs a persona (PA, Analyst, etc.) with a given prompt.
"""

import json
import sys
import argparse
from pathlib import Path

def invoke_persona(persona: str, prompt: str, username: str = "Sweet-Pea-Rudi19") -> dict:
    """Invoke a Willow persona."""
    # Import LLM router
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from core import llm_router
        llm_router.load_keys_from_json()
    except ImportError:
        return {"error": "LLM router not available"}

    # Persona prompts
    personas = {
        "PA": "You are PA (Personal Assistant), a helpful and proactive assistant for Sean. You manage tasks, schedules, and communications.",
        "Analyst": "You are Analyst, a data-driven analytical agent. You find patterns, generate insights, and create visualizations.",
        "Archivist": "You are Archivist, responsible for organizing and preserving loam. You categorize, tag, and maintain coherence.",
        "Poet": "You are Poet, a creative agent that writes poetry, prose, and creative content.",
        "Debugger": "You are Debugger, a technical agent that finds and fixes bugs in code and systems."
    }

    if persona not in personas:
        return {"error": f"Unknown persona: {persona}. Available: {list(personas.keys())}"}

    # Build full prompt
    system_prompt = personas[persona]
    full_prompt = f"{system_prompt}\n\nUser: {prompt}"

    try:
        # Call LLM
        response = llm_router.ask(full_prompt, preferred_tier="free")

        if response:
            return {
                "persona": persona,
                "prompt": prompt,
                "response": response.content,
                "provider": response.provider,
                "tier": response.tier
            }
        else:
            return {"error": "No response from LLM"}

    except Exception as e:
        return {"error": str(e)}

def main():
    parser = argparse.ArgumentParser(description="Invoke Willow persona")
    parser.add_argument("persona", help="Persona name (PA, Analyst, etc.)")
    parser.add_argument("prompt", help="Prompt for the persona")
    parser.add_argument("--user", default="Sweet-Pea-Rudi19", help="Username")
    args = parser.parse_args()

    try:
        result = invoke_persona(args.persona, args.prompt, args.user)
        print(json.dumps(result, indent=2))
        sys.exit(0 if "error" not in result else 1)

    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()

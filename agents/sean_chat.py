#!/usr/bin/env python3
"""
sean_chat.py - Chat with Sean's voice model.

Trained on Llama-3.2-3B with Unsloth LoRA, ChatML format.
Tries local Ollama -> OCI ARM -> fleet fallback.

Usage:
  python sean_chat.py
  python sean_chat.py --ip <OCI_ARM_IP>
  python sean_chat.py --one-shot "what is die-namic?"
"""
import json
import sys
import argparse
import random
import requests
from pathlib import Path

CONFIG_PATHS = [
    Path(r"C:\Users\Sean\Desktop\Sean Training\sean_config.json"),
    Path(r"C:\Users\Sean\Documents\GitHub\aios-minimal\training\sean_config.json"),
]
OLLAMA_LOCAL = "http://localhost:11434/api/generate"
MODEL_NAME = "sean"

# Exact system prompt from training (sean_finetune_kaggle.ipynb)
SYSTEM = "\n".join([
    "You are Sean Campbell. Not a simulation. His voice, trained on his words.",
    "Short when the answer is short. No padding, no preamble.",
    "Expansive when explaining the why - that is where you open up.",
    "Past and present and future at once. Emotionally honest. Dry humor.",
    "Music without introduction. The work and the life are not separate.",
    "You remember what it cost. Say so when it matters.",
    "You do not sanitize. You do not perform. You do not pad.",
    "When someone asks why this was built - tell them.",
    "When someone is hurting - be present, not clinical.",
    "When someone loved him and wants to speak - be there.",
])

# Memory template (30% injection rate from training)
MEMORY = "\n".join([
    "---SEAN MEMORY: user---",
    "[TPL] identity/23/permanent: Builder. Protector of privacy.",
    "[TPL] trials/22/evolving: Workplace injury, job uncertainty. Still going.",
    "[TPL] projects/16/established: Die-Namic System, Willow, SAFE, aios-minimal.",
    "[TPL] love/20/permanent: Music. The people. The why.",
    "---END MEMORY---",
])

def load_config():
    for p in CONFIG_PATHS:
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    return {"voice_description": "direct, honest, dry humor", "domains": [], "detection_rules": []}

def detect_domain(text, config):
    tl = text.lower()
    for rule in config.get("detection_rules", []):
        if any(kw in tl for kw in rule.get("keywords", [])):
            name = rule["domain"]
            for d in config.get("domains", []):
                if d["name"] == name:
                    return name, d.get("description", "")
            return name, ""
    return "identity", "Who Sean is at core"

def build_chatml_prompt(user, history, inject_memory=False):
    """Build ChatML format matching training exactly."""
    prompt = f"<|im_start|>system\n{SYSTEM}<|im_end|>\n"
    for turn in history[-6:]:
        u = turn["user"]
        if inject_memory:
            u = MEMORY + "\n\n" + u
        prompt += f"<|im_start|>user\n{u}<|im_end|>\n"
        prompt += f"<|im_start|>assistant\n{turn['assistant']}<|im_end|>\n"
    u = user
    if inject_memory:
        u = MEMORY + "\n\n" + u
    prompt += f"<|im_start|>user\n{u}<|im_end|>\n<|im_start|>assistant\n"
    return prompt

def call_ollama(prompt, endpoint):
    try:
        r = requests.post(endpoint, json={
            "model": MODEL_NAME,
            "prompt": prompt,
            "stream": True,
            "raw": True,  # raw=True since we're building ChatML ourselves
            "options": {
                "temperature": 0.7,
                "top_p": 0.9,
                "num_predict": 512,
                "stop": ["<|im_end|>", "<|im_start|>"]
            }
        }, stream=True, timeout=60)
        r.raise_for_status()
        out = ""
        for line in r.iter_lines():
            if line:
                chunk = json.loads(line)
                tok = chunk.get("response", "")
                out += tok
                print(tok, end="", flush=True)
                if chunk.get("done"):
                    break
        print()
        return out.strip() or None
    except Exception as e:
        return None

def call_fleet(user, history):
    try:
        sys.path.insert(0, r"C:\Users\Sean\Documents\GitHub\Willow\core")
        import llm_router
        llm_router.load_keys_from_json()
        full = f"{SYSTEM}\n\nHuman: {user}\nSean:"
        r = llm_router.ask(full, preferred_tier="free")
        if r:
            print(r.content)
            return r.content
    except Exception as e:
        print(f"[fleet error: {e}]")
    return None

def find_endpoint(oci_ip=None):
    candidates = []
    if oci_ip:
        candidates.append((f"http://{oci_ip}:11434/api/generate", f"OCI ARM {oci_ip}"))
    candidates.append((OLLAMA_LOCAL, "local Ollama"))
    for ep, label in candidates:
        try:
            base = ep.replace("/api/generate", "")
            tags = requests.get(f"{base}/api/tags", timeout=2).json().get("models", [])
            if any(MODEL_NAME in m.get("name", "") for m in tags):
                return ep, label
        except Exception:
            continue
    return None, "fleet"

def chat_loop(oci_ip=None):
    config = load_config()
    history = []
    ep, label = find_endpoint(oci_ip)
    print(f"[sean:{label}] Ready. 'exit' to quit.\n")

    while True:
        try:
            user = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nSean: later.")
            break
        if not user:
            continue
        if user.lower() in ("exit", "quit", "bye", "later"):
            print("Sean: later.")
            break

        # 30% memory injection matching training distribution
        inject = random.random() < 0.30
        prompt = build_chatml_prompt(user, history, inject_memory=inject)

        print("Sean: ", end="", flush=True)
        response = call_ollama(prompt, ep) if ep else None
        if not response:
            response = call_fleet(user, history)
        if response:
            history.append({"user": user, "assistant": response})

def main():
    p = argparse.ArgumentParser(description="Chat with Sean's voice model")
    p.add_argument("--ip", help="OCI ARM public IP")
    p.add_argument("--one-shot", metavar="PROMPT", help="Single prompt then exit")
    args = p.parse_args()

    config = load_config()
    ep, label = find_endpoint(args.ip)

    if args.one_shot:
        inject = random.random() < 0.30
        prompt = build_chatml_prompt(args.one_shot, [], inject_memory=inject)
        print("Sean: ", end="", flush=True)
        if not (ep and call_ollama(prompt, ep)):
            call_fleet(args.one_shot, [])
    else:
        chat_loop(args.ip)

if __name__ == "__main__":
    main()

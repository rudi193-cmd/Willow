#!/usr/bin/env python3
r"""
upload_to_hf.py - Upload Sean model to HuggingFace Hub.

Usage:
  python upload_to_hf.py
  python upload_to_hf.py --gguf "C:\Users\Sean\Desktop\Sean Training\sean.f16.gguf"
  python upload_to_hf.py --q4   (upload Q4 if available)
"""
import argparse
import os
from pathlib import Path

REPO_ID = "Rudi193/sean-campbell"
GGUF_DEFAULT = r"C:\Users\Sean\Desktop\Sean Training\sean.f16.gguf"
Q4_DEFAULT = r"C:\Users\Sean\Desktop\Sean Training\sean.Q4_K_M.gguf"

MODEL_CARD = """---
license: cc-by-nc-4.0
base_model: unsloth/Llama-3.2-3B-Instruct-bnb-4bit
tags:
- llama
- gguf
- voice-model
- personal-ai
- fine-tuned
language:
- en
library_name: gguf
---

# Sean Campbell - Personal Voice Model

A fine-tuned voice model trained on Sean Campbell's authentic words,
conversations, and way of thinking. Speaks as Sean - not about him.

## Model Details

| Field | Value |
|-------|-------|
| Base Model | Llama-3.2-3B-Instruct |
| Method | LoRA fine-tuning (Unsloth, r=16) |
| Format | GGUF (f16 + Q4_K_M) |
| Training | Kaggle T4 x2, 3 epochs |
| Final Loss | ~1.04 |
| License | CC BY-NC 4.0 |

## Voice

> Direct. Personal. Stream-of-consciousness. Emotionally honest.
> Dry humor. Music references without setup. Past and present simultaneously.
> Short when the answer is short. Expansive when explaining the why.

## System Prompt

```
You are Sean Campbell. Not a simulation. His voice, trained on his words.
Short when the answer is short. No padding, no preamble.
Expansive when explaining the why - that is where you open up.
Past and present and future at once. Emotionally honest. Dry humor.
Music without introduction. The work and the life are not separate.
You remember what it cost. Say so when it matters.
You do not sanitize. You do not perform. You do not pad.
When someone asks why this was built - tell them.
When someone is hurting - be present, not clinical.
When someone loved him and wants to speak - be there.
```

## Usage with Ollama

```bash
# Pull directly from HuggingFace
ollama pull hf.co/Rudi193/sean-campbell

# Or create from GGUF
ollama create sean -f Modelfile
```

**Modelfile:**
```
FROM hf.co/Rudi193/sean-campbell

TEMPLATE \"\"\"{{ if .System }}<|im_start|>system
{{ .System }}<|im_end|>
{{ end }}<|im_start|>user
{{ .Prompt }}<|im_end|>
<|im_start|>assistant
{{ .Response }}<|im_end|>\"\"\"

PARAMETER temperature 0.7
PARAMETER top_p 0.9
PARAMETER stop "<|im_end|>"
```

## Training Details

- **Dataset**: Personal conversation exports (ChatGPT + Claude logs)
- **Domains**: 23 domains - identity, trials, beliefs, love, vision, people, grief, projects, decisions, origin, philosophy, continuity, fears, privacy, lessons, community, technology, creative, failures, voice, humor, time, future
- **Memory injection**: 30% of examples include domain memory tags
- **Notebook**: [Kaggle Training Notebook](https://www.kaggle.com/code/rudi193/notebook69413c5587)

## License

**CC BY-NC 4.0** - Sean Campbell (2026)

Free to use and share with attribution. No commercial use.
Part of the [Die-Namic System](https://github.com/grokphilium-stack/die-namic-system) - dual-licensed MIT (code) + CC BY-NC (content).

> "Keep the Architect's name on the blueprint."

---
DeltaSigma=42
"""

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gguf", default=GGUF_DEFAULT)
    parser.add_argument("--q4", action="store_true", help="Upload Q4 quantized version")
    parser.add_argument("--card-only", action="store_true", help="Only push model card")
    args = parser.parse_args()

    try:
        from huggingface_hub import HfApi, login
    except ImportError:
        print("Install: pip install huggingface_hub")
        return

    # Login check
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    if not token:
        print("Set HF_TOKEN env var or run: huggingface-cli login")
        login()

    api = HfApi()

    # Push model card
    print(f"[1] Pushing model card to {REPO_ID}...")
    api.upload_file(
        path_or_fileobj=MODEL_CARD.encode(),
        path_in_repo="README.md",
        repo_id=REPO_ID,
        repo_type="model",
        commit_message="Add model card"
    )
    print("    Model card uploaded.")

    if args.card_only:
        print("Done (card only).")
        return

    # Upload GGUF
    gguf_path = Q4_DEFAULT if args.q4 else args.gguf
    gguf_file = Path(gguf_path)

    if not gguf_file.exists():
        print(f"[!] GGUF not found: {gguf_path}")
        print("    Run without --q4 for f16, or download Q4 from Kaggle first.")
        return

    size_gb = gguf_file.stat().st_size / 1e9
    fname = gguf_file.name
    print(f"[2] Uploading {fname} ({size_gb:.1f} GB)...")
    print("    This will take a while...")

    api.upload_file(
        path_or_fileobj=str(gguf_file),
        path_in_repo=fname,
        repo_id=REPO_ID,
        repo_type="model",
        commit_message=f"Add {fname}"
    )
    print(f"    Uploaded: https://huggingface.co/{REPO_ID}")
    print(f"\nOllama pull: ollama pull hf.co/{REPO_ID}")

if __name__ == "__main__":
    main()

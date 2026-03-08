#!/usr/bin/env python3
"""
Ganesha → Willow Contribute
============================
Route content from Ganesha (Claude Code) into the Willow knowledge graph
via the Pigeon contribute topic.

Usage:
    /home/sean/.willow-venv/bin/python tools/ganesha_contribute.py \\
        --content "My handoff content here" \\
        --category narrative \\
        --type SESSION_HANDOFF

    # Or pipe from a file:
    cat /path/to/handoff.md | /home/sean/.willow-venv/bin/python tools/ganesha_contribute.py \\
        --category narrative --type SESSION_HANDOFF

Methods (in priority order):
    1. POST to /api/pigeon/drop (requires Willow running at 8420)
    2. Direct ingest via core/knowledge.py (works without server)
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime

REPO = "/mnt/c/Users/Sean/Documents/GitHub/Willow"
sys.path.insert(0, REPO)

WILLOW_URL = "http://localhost:8420"
USERNAME   = "Sweet-Pea-Rudi19"
APP_ID     = "ganesha-cli"


def contribute_via_server(content: str, category: str, metadata: dict) -> bool:
    """Route via running Willow server. Returns True on success."""
    try:
        import urllib.request, json
        payload = json.dumps({
            "topic":    "contribute",
            "app_id":   APP_ID,
            "username": USERNAME,
            "payload": {
                "content":  content,
                "category": category,
                "metadata": metadata,
            }
        }).encode()
        req = urllib.request.Request(
            f"{WILLOW_URL}/api/pigeon/drop",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            if result.get("ok"):
                print(f"[OK] Ingested via server ({result.get('result', {})})")
                return True
            print(f"[WARN] Server returned: {result}")
            return False
    except Exception as e:
        print(f"[WARN] Server unavailable: {e}")
        return False


def contribute_direct(content: str, category: str, filename: str) -> bool:
    """Ingest directly via core/knowledge.py (server not required). Returns True on success."""
    try:
        from core.knowledge import ingest_file_knowledge
        ingest_file_knowledge(
            username=USERNAME,
            filename=filename,
            file_hash="",
            category=category,
            content_text=content,
            provider=APP_ID,
        )
        print(f"[OK] Ingested directly (category={category})")
        return True
    except Exception as e:
        print(f"[ERROR] Direct ingest failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Ganesha → Willow knowledge contribute")
    parser.add_argument("--content",  "-c", default=None,   help="Content to contribute (or pass via stdin)")
    parser.add_argument("--category", "-k", default="narrative", help="Category: narrative|code|reference|legal|personal|test")
    parser.add_argument("--type",     "-t", default="ganesha-drop", help="Content type tag (e.g. SESSION_HANDOFF)")
    parser.add_argument("--file",     "-f", default=None,   help="Read content from this file")
    parser.add_argument("--direct",         action="store_true", help="Skip server, ingest directly")
    args = parser.parse_args()

    # Get content
    content = args.content
    if args.file:
        content = Path(args.file).read_text(encoding="utf-8")
    if not content and not sys.stdin.isatty():
        content = sys.stdin.read()

    if not content or not content.strip():
        print("ERROR: No content provided. Use --content, --file, or pipe via stdin.")
        sys.exit(1)

    content = content.strip()
    now = datetime.now().isoformat()
    metadata = {
        "type":       args.type,
        "session_date": now[:10],
        "contributed_at": now,
        "source": APP_ID,
    }

    filename = f"ganesha-{args.type.lower()}-{now[:10]}.txt"

    print(f"Contributing {len(content)} chars (category={args.category}, type={args.type})")

    # Try server first, fall back to direct
    if not args.direct:
        if contribute_via_server(content, args.category, metadata):
            return
        print("[INFO] Falling back to direct ingest...")

    contribute_direct(content, args.category, filename)


if __name__ == "__main__":
    main()

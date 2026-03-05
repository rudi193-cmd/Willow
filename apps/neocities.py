"""
Neocities Deploy — Push files to seancampbell.neocities.org

Reads NEOCITIES_API_KEY from credentials.json (via env).
Uses the Neocities API: https://neocities.org/api

GOVERNANCE: Write-only to Neocities. Does not read, delete, or
modify files not explicitly passed. No credential exposure in output.
"""

import os
import json
import logging
from pathlib import Path
from typing import Optional, List, Dict

import requests

log = logging.getLogger("neocities")

API_BASE = "https://neocities.org/api"
SITE_URL = "https://seancampbell.neocities.org"


def _get_key() -> Optional[str]:
    key = os.environ.get("NEOCITIES_API_KEY")
    if key:
        return key
    # Fallback: read credentials.json directly
    cred_path = Path(__file__).parent.parent / "credentials.json"
    if cred_path.exists():
        try:
            data = json.loads(cred_path.read_text())
            return data.get("NEOCITIES_API_KEY")
        except Exception:
            pass
    return None


def _headers() -> dict:
    key = _get_key()
    if not key:
        raise RuntimeError("NEOCITIES_API_KEY not found in env or credentials.json")
    return {"Authorization": f"Bearer {key}"}


def upload(files: Dict[str, str]) -> dict:
    """
    Upload files to Neocities.

    Args:
        files: Dict of {remote_path: local_path}
               e.g. {"willow/index.html": "C:/path/to/index.html"}

    Returns:
        API response dict.
    """
    multipart = []
    for remote_path, local_path in files.items():
        p = Path(local_path)
        if not p.exists():
            raise FileNotFoundError(f"Local file not found: {local_path}")
        multipart.append((remote_path, (p.name, p.read_bytes())))

    r = requests.post(
        f"{API_BASE}/upload",
        headers=_headers(),
        files=multipart,
        timeout=30,
    )
    result = r.json()
    log.info(f"neocities upload: {result}")
    return result


def upload_text(files: Dict[str, str]) -> dict:
    """
    Upload text content directly (no local file needed).

    Args:
        files: Dict of {remote_path: content_string}
               e.g. {"willow/index.html": "<html>...</html>"}

    Returns:
        API response dict.
    """
    multipart = []
    for remote_path, content in files.items():
        filename = remote_path.split("/")[-1]
        multipart.append((remote_path, (filename, content.encode("utf-8"))))

    r = requests.post(
        f"{API_BASE}/upload",
        headers=_headers(),
        files=multipart,
        timeout=30,
    )
    result = r.json()
    log.info(f"neocities upload_text: {result}")
    return result


def list_files() -> list:
    """List all files on the Neocities site."""
    r = requests.get(f"{API_BASE}/list", headers=_headers(), timeout=15)
    return r.json().get("files", [])


def info() -> dict:
    """Get site info (hits, created_at, etc.)."""
    r = requests.get(f"{API_BASE}/info", headers=_headers(), timeout=15)
    return r.json()


def deploy_pocket_willow() -> dict:
    """Deploy the pocket Willow page from neocities/index.html."""
    local_path = Path(__file__).parent.parent / "neocities" / "index.html"
    if not local_path.exists():
        return {"error": f"Not found: {local_path}"}
    return upload({"willow/index.html": str(local_path)})


# --- CLI ---
if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from core.llm_router import load_keys_from_json
    load_keys_from_json()

    if len(sys.argv) > 1 and sys.argv[1] == "deploy":
        print(deploy_pocket_willow())
    elif len(sys.argv) > 1 and sys.argv[1] == "list":
        for f in list_files():
            print(f"{f.get('path', '?'):40s} {f.get('size', 0):>8d}b")
    elif len(sys.argv) > 1 and sys.argv[1] == "info":
        print(json.dumps(info(), indent=2))
    else:
        print("Usage: python neocities.py [deploy|list|info]")

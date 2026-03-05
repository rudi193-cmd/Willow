#!/usr/bin/env python3
"""
Willow Status Skill — System health check.

Returns JSON with daemon status, server health, resource usage.
"""

import json
import sys
import subprocess
from pathlib import Path
import requests
from datetime import datetime, timedelta

def check_server() -> bool:
    """Check if Willow server is running."""
    try:
        r = requests.get("http://127.0.0.1:8420/api/health", timeout=2)
        return r.status_code == 200
    except:
        return False

def check_ollama() -> bool:
    """Check if Ollama is running."""
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=2)
        return r.status_code == 200
    except:
        return False

def check_daemons() -> dict:
    """Check which daemons are running."""
    daemons = [
        "WILLOW-GovernanceMonitor",
        "WILLOW-CoherenceScanner",
        "WILLOW-TopologyBuilder",
        "WILLOW-KnowledgeCompactor",
        "WILLOW-SAFESync",
        "WILLOW-PersonaScheduler",
        "WILLOW-InboxWatcher"
    ]

    status = {}
    for daemon in daemons:
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"WINDOWTITLE eq {daemon}"],
                capture_output=True,
                text=True,
                timeout=5
            )
            status[daemon] = "INFO:" not in result.stdout
        except:
            status[daemon] = False

    return status

def check_tunnel() -> dict:
    """Check tunnel status."""
    tunnel_file = Path(__file__).parent.parent / ".tunnel_url"

    if not tunnel_file.exists():
        return {"active": False, "url": None}

    try:
        url = tunnel_file.read_text().strip()
        # Check if file was modified in last 24h
        mtime = datetime.fromtimestamp(tunnel_file.stat().st_mtime)
        is_recent = (datetime.now() - mtime) < timedelta(hours=24)

        return {"active": is_recent, "url": url if is_recent else None}
    except:
        return {"active": False, "url": None}

def check_disk_usage() -> dict:
    """Check disk usage for artifacts."""
    artifacts_dir = Path(__file__).parent.parent / "artifacts"

    if not artifacts_dir.exists():
        return {"size_gb": 0, "file_count": 0}

    total_size = sum(f.stat().st_size for f in artifacts_dir.rglob("*") if f.is_file())
    file_count = len(list(artifacts_dir.rglob("*")))

    return {
        "size_gb": round(total_size / (1024**3), 2),
        "file_count": file_count
    }

def main():
    """Run all health checks and output JSON."""
    try:
        status = {
            "server_running": check_server(),
            "ollama_running": check_ollama(),
            "daemons": check_daemons(),
            "tunnel": check_tunnel(),
            "disk_usage": check_disk_usage(),
            "timestamp": datetime.now().isoformat()
        }

        print(json.dumps(status, indent=2))
        sys.exit(0)

    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()

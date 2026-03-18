"""
core/boot.py — Willow node boot configuration
================================================
Provides CONFIG_PATH, load_config(), _config_to_dict(), _port_open().
Used by rings.py and agent_registry.py.
"""

import json
import socket
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


CONFIG_PATH = Path.home() / ".willow" / "config.json"


@dataclass
class WillowConfig:
    instance_id: str = "willow-local-8420"
    port: int = 8420
    hostname: str = "localhost"
    username: str = "Sweet-Pea-Rudi19"
    rings: dict = field(default_factory=dict)


def load_config() -> WillowConfig:
    """Read config from ~/.willow/config.json. Returns defaults if missing."""
    if not CONFIG_PATH.exists():
        return WillowConfig()
    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return WillowConfig(
            instance_id=raw.get("instance_id", "willow-local-8420"),
            port=raw.get("port", 8420),
            hostname=raw.get("hostname", "localhost"),
            username=raw.get("username", "Sweet-Pea-Rudi19"),
            rings=raw.get("rings", {}),
        )
    except Exception:
        return WillowConfig()


def _config_to_dict(config: WillowConfig) -> dict:
    """Convert config dataclass to dict for seed packets."""
    return asdict(config)


def _port_open(host: str, port: int) -> bool:
    """Check if a port is already in use (returns True if open/listening)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            return s.connect_ex((host, port)) == 0
    except Exception:
        return False


@dataclass
class BootConfig:
    host: str = "0.0.0.0"
    port: int = 8420


def boot_check() -> tuple:
    """
    Pre-flight check before starting the server.
    Returns (status, cfg, msg) where status is one of:
      'start'           — port free, go ahead
      'already_running' — Willow is already on this port
      'stale_reclaimed' — port was held by dead process, reclaimed
      'conflict'        — port in use by something else
    """
    import urllib.request
    cfg = BootConfig()
    config = load_config()
    cfg.port = config.port

    if not _port_open(cfg.host, cfg.port):
        return ("start", cfg, f"Port {cfg.port} free. Starting Willow.")

    # Port is open — check if it's us
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{cfg.port}/api/status", timeout=2) as r:
            data = json.loads(r.read())
            if data:
                return ("already_running", cfg,
                        f"Willow already running on {cfg.port} "
                        f"({data.get('knowledge', {}).get('atoms', '?')} atoms)")
    except Exception:
        pass

    # Port open but not responding as Willow — conflict
    return ("conflict", cfg, f"Port {cfg.port} in use by another process.")

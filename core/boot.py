"""
BOOT v1.0.0
Willow Startup & Port Lifecycle Manager

Owner: Sean Campbell
System: Willow / Die-namic Bridge Ring
Version: 1.0.0
Status: Active
Last Updated: 2026-02-25T04:35:00Z
Checksum: DS=42

Responsibilities:
- Persist runtime identity to ~/.willow/config.json
- Detect port state: free / our instance / stale lock / conflict
- Provide canonical base URL for SAFE apps and binder.html
- No side effects on import; all mutation is explicit
"""

from __future__ import annotations

import json
import os
import socket
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

CONFIG_PATH: Path = Path.home() / ".willow" / "config.json"


@dataclass
class PeeringConfig:
    enabled: bool = False
    port: int = 8421
    allowed_peers: list = field(default_factory=list)


@dataclass
class WillowConfig:
    port: int = 8420
    locked: bool = False
    host: str = "127.0.0.1"
    instance_id: str = ""
    pid: Optional[int] = None
    boot_count: int = 0
    last_boot: str = ""
    peering: PeeringConfig = field(default_factory=PeeringConfig)
    db_path: str = ""


def _default_instance_id() -> str:
    return f"{socket.gethostname()}-8420"


def _config_to_dict(config: WillowConfig) -> dict:
    return asdict(config)


def _dict_to_config(d: dict) -> WillowConfig:
    peering_raw = d.pop("peering", {})
    peering = PeeringConfig(
        enabled=peering_raw.get("enabled", False),
        port=peering_raw.get("port", 8421),
        allowed_peers=peering_raw.get("allowed_peers", []),
    )
    return WillowConfig(peering=peering, **d)


def load_config() -> WillowConfig:
    if not CONFIG_PATH.exists():
        config = WillowConfig(
            instance_id=_default_instance_id(),
            db_path=str(Path.home() / ".willow" / "willow.db"),
        )
        save_config(config)
        return config
    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return _dict_to_config(raw)
    except (json.JSONDecodeError, TypeError, KeyError):
        return WillowConfig(
            instance_id=_default_instance_id(),
            db_path=str(Path.home() / ".willow" / "willow.db"),
        )


def save_config(config: WillowConfig) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        json.dumps(_config_to_dict(config), indent=2),
        encoding="utf-8",
    )


def _port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def _pid_alive(pid: Optional[int]) -> bool:
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError, OSError):
        return False


def check_port(port: int, host: str = "127.0.0.1") -> str:
    config = load_config()
    port_in_use = _port_open(host, port)
    if not port_in_use:
        if config.pid is not None and not _pid_alive(config.pid):
            return "stale_lock"
        return "free"
    if config.pid is not None and _pid_alive(config.pid):
        return "willow_running"
    # Port in use but our PID is dead — ghost socket from os._exit; treat as stale
    if config.pid is not None and not _pid_alive(config.pid):
        return "stale_lock"
    return "conflict"


def boot_check() -> tuple:
    config = load_config()
    state = check_port(config.port, config.host)
    if state == "free":
        config.boot_count += 1
        config.last_boot = datetime.now(timezone.utc).isoformat()
        config.pid = os.getpid()
        save_config(config)
        return ("start", config, f"Port {config.port} is free. Boot #{config.boot_count}.")
    if state == "willow_running":
        return ("already_running", config, f"Willow already running on {get_willow_url()} (PID {config.pid}).")
    if state == "stale_lock":
        config.pid = None
        config.boot_count += 1
        config.last_boot = datetime.now(timezone.utc).isoformat()
        config.pid = os.getpid()
        save_config(config)
        return ("stale_reclaimed", config, f"Stale lock cleared. Boot #{config.boot_count}.")
    return ("conflict", config, f"Port {config.port} is bound by an unknown process. Cannot start.")


def get_willow_url() -> str:
    config = load_config()
    return f"http://{config.host}:{config.port}"

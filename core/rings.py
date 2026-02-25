"""
RINGS v1.0.0
Node Ring Registry & Pigeon Payload Contract

Owner: Sean Campbell
System: Willow / Die-namic Bridge Ring
Version: 1.0.0
Status: Active
Last Updated: 2026-02-25
Checksum: DS=42

Responsibilities:
- Track which rings this node participates in (source/bridge/continuity)
- Enforce pigeon payload contract: content + gate_conditions + SEED_PACKET
- Validate inbound pigeons from peer nodes
- No data storage -- maps ring membership to existing implementations

Ring implementations:
- Source ring  -> journal_engine.py (JSONL, append-only)
- Continuity   -> gate.py + storage.py (RuntimeState)
- Bridge ring  -> Drop/Pickup folders
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .boot import CONFIG_PATH, load_config, _config_to_dict

GATE_PATH: Path = Path(__file__).parent / "gate.py"


@dataclass
class NodeRings:
    source: bool = True        # Always true -- cannot be a node without source ring
    bridge: bool = False       # True when >=1 peer enrolled
    continuity: bool = False   # True when gate.py explicitly enrolled
    enrolled_peers: list = field(default_factory=list)


@dataclass
class PigeonPayload:
    content: dict
    gate_conditions: dict      # gate.py rules that travel with the pigeon
    seed_packet: dict          # Sender's SEED_PACKET at time of send
    sender: str                # instance_id of originating node
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


def load_rings() -> NodeRings:
    """Read ring participation state from ~/.willow/config.json."""
    raw_text = CONFIG_PATH.read_text(encoding="utf-8") if CONFIG_PATH.exists() else "{}"
    raw = json.loads(raw_text)
    rings_raw = raw.get("rings", {})
    if not rings_raw:
        return NodeRings()
    return NodeRings(
        source=rings_raw.get("source", True),
        bridge=rings_raw.get("bridge", False),
        continuity=rings_raw.get("continuity", False),
        enrolled_peers=rings_raw.get("enrolled_peers", []),
    )


def save_rings(rings: NodeRings) -> None:
    """Persist ring state into ~/.willow/config.json alongside WillowConfig."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    raw_text = CONFIG_PATH.read_text(encoding="utf-8") if CONFIG_PATH.exists() else "{}"
    raw = json.loads(raw_text)
    raw["rings"] = asdict(rings)
    CONFIG_PATH.write_text(json.dumps(raw, indent=2), encoding="utf-8")


def enroll_peer(peer_id: str) -> NodeRings:
    """
    Add a peer to this node. Activates bridge ring on first enrollment.
    peer_id: instance_id of the peer node (e.g. 'hostname-8420')
    """
    rings = load_rings()
    if peer_id not in rings.enrolled_peers:
        rings.enrolled_peers.append(peer_id)
    rings.bridge = len(rings.enrolled_peers) > 0
    save_rings(rings)
    return rings


def enroll_gate() -> tuple:
    """
    Activate continuity ring. Requires gate.py present on this node.
    Returns (success: bool, message: str).
    The continuity ring cannot be proxied -- gate.py must be local.
    """
    if not GATE_PATH.exists():
        return (
            False,
            f"gate.py not found at {GATE_PATH}. "
            "Continuity ring requires local gate.py -- it does not travel without it.",
        )
    rings = load_rings()
    rings.continuity = True
    save_rings(rings)
    return (True, "Continuity ring enrolled. gate.py will travel with every outbound pigeon.")


def make_pigeon(
    content: dict,
    gate_conditions: dict,
    seed_packet: Optional[dict] = None,
) -> PigeonPayload:
    """
    Package an outbound pigeon with gate_conditions and SEED_PACKET.
    A pigeon without gate_conditions does not leave this node.
    seed_packet: auto-populated from current boot config if not provided.
    """
    if seed_packet is None:
        config = load_config()
        seed_packet = _config_to_dict(config)

    config = load_config()
    return PigeonPayload(
        content=content,
        gate_conditions=gate_conditions,
        seed_packet=seed_packet,
        sender=config.instance_id,
    )


def validate_inbound(payload: dict) -> tuple:
    """
    Validate an inbound pigeon from a peer node.
    Returns (valid: bool, reason: str).
    A peer node without gate_conditions cannot be a valid sender.
    """
    if "content" not in payload:
        return (False, "Missing content")
    if not payload.get("gate_conditions"):
        return (False, "Missing gate_conditions -- peer node has no traveling gate")
    if not payload.get("seed_packet"):
        return (False, "Missing seed_packet -- cannot verify sender state")
    if "sender" not in payload:
        return (False, "Missing sender identity")
    return (True, "ok")


def ring_status() -> dict:
    """Return current ring participation status for this node."""
    rings = load_rings()
    return {
        "source": rings.source,
        "bridge": rings.bridge,
        "continuity": rings.continuity,
        "peer_count": len(rings.enrolled_peers),
        "enrolled_peers": rings.enrolled_peers,
        "gate_present": GATE_PATH.exists(),
    }

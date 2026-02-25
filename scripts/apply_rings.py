"""Apply rings.py from approved governance commit."""
from pathlib import Path

RINGS_CONTENT = (
    '"""\n'
    "RINGS v1.0.0\n"
    "Node Ring Registry & Pigeon Payload Contract\n"
    "\n"
    "Owner: Sean Campbell\n"
    "System: Willow / Die-namic Bridge Ring\n"
    "Version: 1.0.0\n"
    "Status: Active\n"
    "Last Updated: 2026-02-25\n"
    "Checksum: DS=42\n"
    "\n"
    "Responsibilities:\n"
    "- Track which rings this node participates in (source/bridge/continuity)\n"
    "- Enforce pigeon payload contract: content + gate_conditions + SEED_PACKET\n"
    "- Validate inbound pigeons from peer nodes\n"
    "- No data storage -- maps ring membership to existing implementations\n"
    "\n"
    "Ring implementations:\n"
    "- Source ring  -> journal_engine.py (JSONL, append-only)\n"
    "- Continuity   -> gate.py + storage.py (RuntimeState)\n"
    "- Bridge ring  -> Drop/Pickup folders\n"
    '"""\n'
    "\n"
    "from __future__ import annotations\n"
    "\n"
    "import json\n"
    "from dataclasses import dataclass, field, asdict\n"
    "from datetime import datetime, timezone\n"
    "from pathlib import Path\n"
    "from typing import Optional\n"
    "\n"
    "from .boot import CONFIG_PATH, load_config, _config_to_dict\n"
    "\n"
    'GATE_PATH: Path = Path(__file__).parent / "gate.py"\n'
    "\n"
    "\n"
    "@dataclass\n"
    "class NodeRings:\n"
    "    source: bool = True        # Always true -- cannot be a node without source ring\n"
    "    bridge: bool = False       # True when >=1 peer enrolled\n"
    "    continuity: bool = False   # True when gate.py explicitly enrolled\n"
    "    enrolled_peers: list = field(default_factory=list)\n"
    "\n"
    "\n"
    "@dataclass\n"
    "class PigeonPayload:\n"
    "    content: dict\n"
    "    gate_conditions: dict      # gate.py rules that travel with the pigeon\n"
    "    seed_packet: dict          # Sender's SEED_PACKET at time of send\n"
    "    sender: str                # instance_id of originating node\n"
    "    timestamp: str = field(\n"
    "        default_factory=lambda: datetime.now(timezone.utc).isoformat()\n"
    "    )\n"
    "\n"
    "\n"
    "def load_rings() -> NodeRings:\n"
    '    """Read ring participation state from ~/.willow/config.json."""\n'
    '    raw_text = CONFIG_PATH.read_text(encoding="utf-8") if CONFIG_PATH.exists() else "{}"\n'
    "    raw = json.loads(raw_text)\n"
    '    rings_raw = raw.get("rings", {})\n'
    "    if not rings_raw:\n"
    "        return NodeRings()\n"
    "    return NodeRings(\n"
    '        source=rings_raw.get("source", True),\n'
    '        bridge=rings_raw.get("bridge", False),\n'
    '        continuity=rings_raw.get("continuity", False),\n'
    '        enrolled_peers=rings_raw.get("enrolled_peers", []),\n'
    "    )\n"
    "\n"
    "\n"
    "def save_rings(rings: NodeRings) -> None:\n"
    '    """Persist ring state into ~/.willow/config.json alongside WillowConfig."""\n'
    "    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)\n"
    '    raw_text = CONFIG_PATH.read_text(encoding="utf-8") if CONFIG_PATH.exists() else "{}"\n'
    "    raw = json.loads(raw_text)\n"
    '    raw["rings"] = asdict(rings)\n'
    '    CONFIG_PATH.write_text(json.dumps(raw, indent=2), encoding="utf-8")\n'
    "\n"
    "\n"
    "def enroll_peer(peer_id: str) -> NodeRings:\n"
    '    """\n'
    "    Add a peer to this node. Activates bridge ring on first enrollment.\n"
    "    peer_id: instance_id of the peer node (e.g. 'hostname-8420')\n"
    '    """\n'
    "    rings = load_rings()\n"
    "    if peer_id not in rings.enrolled_peers:\n"
    "        rings.enrolled_peers.append(peer_id)\n"
    "    rings.bridge = len(rings.enrolled_peers) > 0\n"
    "    save_rings(rings)\n"
    "    return rings\n"
    "\n"
    "\n"
    "def enroll_gate() -> tuple:\n"
    '    """\n'
    "    Activate continuity ring. Requires gate.py present on this node.\n"
    "    Returns (success: bool, message: str).\n"
    "    The continuity ring cannot be proxied -- gate.py must be local.\n"
    '    """\n'
    "    if not GATE_PATH.exists():\n"
    "        return (\n"
    "            False,\n"
    '            f"gate.py not found at {GATE_PATH}. "\n'
    '            "Continuity ring requires local gate.py -- it does not travel without it.",\n'
    "        )\n"
    "    rings = load_rings()\n"
    "    rings.continuity = True\n"
    "    save_rings(rings)\n"
    '    return (True, "Continuity ring enrolled. gate.py will travel with every outbound pigeon.")\n'
    "\n"
    "\n"
    "def make_pigeon(\n"
    "    content: dict,\n"
    "    gate_conditions: dict,\n"
    "    seed_packet: Optional[dict] = None,\n"
    ") -> PigeonPayload:\n"
    '    """\n'
    "    Package an outbound pigeon with gate_conditions and SEED_PACKET.\n"
    "    A pigeon without gate_conditions does not leave this node.\n"
    "    seed_packet: auto-populated from current boot config if not provided.\n"
    '    """\n'
    "    if seed_packet is None:\n"
    "        config = load_config()\n"
    "        seed_packet = _config_to_dict(config)\n"
    "\n"
    "    config = load_config()\n"
    "    return PigeonPayload(\n"
    "        content=content,\n"
    "        gate_conditions=gate_conditions,\n"
    "        seed_packet=seed_packet,\n"
    "        sender=config.instance_id,\n"
    "    )\n"
    "\n"
    "\n"
    "def validate_inbound(payload: dict) -> tuple:\n"
    '    """\n'
    "    Validate an inbound pigeon from a peer node.\n"
    "    Returns (valid: bool, reason: str).\n"
    "    A peer node without gate_conditions cannot be a valid sender.\n"
    '    """\n'
    '    if "content" not in payload:\n'
    '        return (False, "Missing content")\n'
    "    if not payload.get(\"gate_conditions\"):\n"
    '        return (False, "Missing gate_conditions -- peer node has no traveling gate")\n'
    "    if not payload.get(\"seed_packet\"):\n"
    '        return (False, "Missing seed_packet -- cannot verify sender state")\n'
    '    if "sender" not in payload:\n'
    '        return (False, "Missing sender identity")\n'
    '    return (True, "ok")\n'
    "\n"
    "\n"
    "def ring_status() -> dict:\n"
    '    """Return current ring participation status for this node."""\n'
    "    rings = load_rings()\n"
    "    return {\n"
    '        "source": rings.source,\n'
    '        "bridge": rings.bridge,\n'
    '        "continuity": rings.continuity,\n'
    '        "peer_count": len(rings.enrolled_peers),\n'
    '        "enrolled_peers": rings.enrolled_peers,\n'
    '        "gate_present": GATE_PATH.exists(),\n'
    "    }\n"
)

out = Path(r"C:\Users\Sean\Documents\GitHub\Willow\core\rings.py")
out.write_text(RINGS_CONTENT, encoding="utf-8")
print(f"Written: {out}")
print(f"Size: {out.stat().st_size} bytes")
print(f"Lines: {len(RINGS_CONTENT.splitlines())}")

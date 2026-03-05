"""
N2N Packets - Node-to-Node Minimal Transport

Implements WIRE-12 protocol for minimal inter-node communication.
Packet types: BOOTSTRAP, HANDOFF, DELTA, INCIDENT, RELEVANCE_SPINE

GOVERNANCE: Read-only packet creation, governance-checked sends
AUTHOR: Kart (via Claude Code)
VERSION: 1.0
CHECKSUM: ΔΣ=42
"""

import json
from enum import Enum
from datetime import datetime
from typing import Dict, Any, Optional
from core.checksum_chain import ChecksumChain


class PacketType(Enum):
    """N2N packet types."""
    BOOTSTRAP = "BOOTSTRAP"  # Governance + authority initialization
    HANDOFF = "HANDOFF"  # What happened + what's next
    DELTA = "DELTA"  # Small ratifiable changes
    INCIDENT = "INCIDENT"  # Error/anomaly reports
    RELEVANCE_SPINE = "RELEVANCE_SPINE"  # What matters / what doesn't


class N2NPacket:
    """Node-to-Node packet creator and validator."""

    MAX_PACKET_SIZE = 4096  # 4KB limit

    @staticmethod
    def create_packet(packet_type: PacketType, source_node: str,
                     target_node: str, payload: Dict[str, Any],
                     authority: str = "ai", scope: str = "local",
                     intent: str = "") -> Dict[str, Any]:
        """
        Create N2N packet.

        Args:
            packet_type: Type of packet (PacketType enum)
            source_node: Source node identifier
            target_node: Target node identifier
            payload: Packet payload (refs, deltas, questions)
            authority: Authority level (ai, human, system)
            scope: Packet scope (local, project, global)
            intent: Intent description

        Returns:
            Packet dict with header and payload
        """
        timestamp = datetime.utcnow().isoformat() + "Z"

        # Generate checksum for payload
        checksum_chain = ChecksumChain()
        payload_checksum = checksum_chain.generate_checksum(payload)
        
        packet = {
            "header": {
                "source_node": source_node,
                "target_node": target_node,
                "packet_type": packet_type.value,
                "authority": authority,
                "scope": scope,
                "intent": intent,
                "timestamp": timestamp,
                "checksum": "ΔΣ=42",
                "payload_checksum": payload_checksum
            },
            "payload": payload,
            "handoff_rules": {
                "require_ack": True,
                "max_hops": 3,
                "ttl": 3600  # 1 hour
            }
        }

        return packet

    @staticmethod
    def validate_packet(packet: Dict[str, Any]) -> bool:
        """
        Validate N2N packet structure.

        Args:
            packet: Packet dict to validate

        Returns:
            True if valid, False otherwise
        """
        # Check required top-level keys
        if not all(k in packet for k in ["header", "payload", "handoff_rules"]):
            return False

        # Check header fields
        header = packet["header"]
        required_header = ["source_node", "target_node", "packet_type",
                          "timestamp", "checksum"]
        if not all(k in header for k in required_header):
            return False

        # Validate packet type
        try:
            PacketType(header["packet_type"])
        except ValueError:
            return False

        # Validate checksum
        if header["checksum"] != "ΔΣ=42":
            return False

        return True

    @staticmethod
    def serialize_packet(packet: Dict[str, Any]) -> str:
        """
        Serialize packet to JSON string.

        Args:
            packet: Packet dict

        Returns:
            JSON string (raises ValueError if >4KB)
        """
        serialized = json.dumps(packet, separators=(',', ':'))

        if len(serialized) > N2NPacket.MAX_PACKET_SIZE:
            raise ValueError(f"Packet size {len(serialized)} exceeds 4KB limit")

        return serialized

    @staticmethod
    def deserialize_packet(packet_str: str) -> Dict[str, Any]:
        """
        Deserialize packet from JSON string.

        Args:
            packet_str: JSON string

        Returns:
            Packet dict (raises ValueError if invalid)
        """
        packet = json.loads(packet_str)

        if not N2NPacket.validate_packet(packet):
            raise ValueError("Invalid packet structure")

        return packet


# Convenience functions
def create_bootstrap(source: str, target: str, governance: Dict) -> Dict:
    """Create BOOTSTRAP packet."""
    return N2NPacket.create_packet(
        PacketType.BOOTSTRAP, source, target,
        {"governance": governance, "authority_model": "dual_commit"},
        authority="human", scope="project", intent="Initialize governance"
    )


def create_handoff(source: str, target: str, what_happened: str,
                  what_next: str) -> Dict:
    """Create HANDOFF packet."""
    return N2NPacket.create_packet(
        PacketType.HANDOFF, source, target,
        {"what_happened": what_happened, "what_next": what_next},
        intent="Session handoff"
    )


def create_delta(source: str, target: str, changes: list) -> Dict:
    """Create DELTA packet."""
    return N2NPacket.create_packet(
        PacketType.DELTA, source, target,
        {"changes": changes},
        intent="Ratifiable changes"
    )

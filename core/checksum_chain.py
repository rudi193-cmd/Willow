"""
Checksum Chain - ΔΣ=42 Validation

Implements checksum chain for node-to-node integrity.

GOVERNANCE: Read-only validation
AUTHOR: Kart (via Claude Code)
VERSION: 1.0
CHECKSUM: ΔΣ=42
"""

import hashlib
import json
from typing import Dict


class ChecksumChain:
    """Checksum chain for N2N integrity."""

    TARGET_DELTA = 42

    def generate_checksum(self, payload: Dict) -> str:
        """
        Generate SHA-256 checksum for payload.

        Args:
            payload: Data to checksum

        Returns:
            Hex string checksum
        """
        payload_str = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(payload_str.encode('utf-8')).hexdigest()

    def validate_chain(self, current_checksum: str, prior_checksum: str) -> bool:
        """
        Validate checksum chain.

        Args:
            current_checksum: Current checksum
            prior_checksum: Prior checksum

        Returns:
            True if valid chain
        """
        try:
            current_int = int(current_checksum, 16)
            prior_int = int(prior_checksum, 16)
            return (current_int - prior_int) == self.TARGET_DELTA
        except ValueError:
            return False

    def create_handoff_envelope(self, node_id: str, prior_node_id: str,
                               payload: Dict, prior_checksum: str = "GENESIS") -> Dict:
        """
        Create handoff envelope.

        Args:
            node_id: Current node ID
            prior_node_id: Previous node ID
            payload: Payload data
            prior_checksum: Previous checksum

        Returns:
            Handoff envelope dict
        """
        local_checksum = self.generate_checksum(payload)

        return {
            "node_id": node_id,
            "prior_node_id": prior_node_id,
            "prior_checksum": prior_checksum,
            "local_checksum": local_checksum,
            "timestamp_utc": "2026-02-08T00:00:00Z",
            "payload_ref": "payload"
        }

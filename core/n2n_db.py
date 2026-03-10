"""
N2N Database - Packet Inbox/Outbox Storage

SQLite-backed storage for node-to-node packet communication.
Supports send, receive, and status tracking.

GOVERNANCE: Governance-checked writes, read-only queries
AUTHOR: Kart (via Claude Code)
VERSION: 1.0
CHECKSUM: ΔΣ=42
"""

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).parent.parent))
from core.db import get_connection
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Any


class N2NDatabase:
    """N2N packet inbox/outbox database."""

    def __init__(self, username: str):
        self.username = username
        self._init_db()

    def _init_db(self):
        """Initialize database schema."""
        conn = get_connection()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS packets (
                packet_id TEXT PRIMARY KEY,
                packet_type TEXT NOT NULL,
                source_node TEXT NOT NULL,
                target_node TEXT NOT NULL,
                payload TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                status TEXT NOT NULL,
                received_at TEXT,
                acknowledged_at TEXT
            )
        """)
        conn.commit()
        conn.close()

    def send_packet(self, packet: Dict[str, Any]) -> str:
        """
        Send packet to outbox.

        Args:
            packet: N2N packet dict (must have header and payload)

        Returns:
            packet_id
        """
        header = packet["header"]
        timestamp = datetime.utcnow().isoformat() + "Z"

        # Generate packet ID
        packet_id = f"{header['source_node']}-{header['target_node']}-{timestamp}"

        conn = get_connection()
        conn.execute("""
            INSERT INTO packets
            (packet_id, packet_type, source_node, target_node,
             payload, timestamp, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            packet_id,
            header["packet_type"],
            header["source_node"],
            header["target_node"],
            json.dumps(packet["payload"]),
            timestamp,
            "SENT"
        ))
        conn.commit()
        conn.close()

        return packet_id

    def receive_packets(self, node_id: str, status: str = "SENT") -> List[Dict]:
        """
        Receive packets for a node.

        Args:
            node_id: Target node identifier
            status: Packet status filter (SENT, RECEIVED, ACKNOWLEDGED)

        Returns:
            List of packet dicts
        """
        conn = get_connection()
        cursor = conn.execute("""
            SELECT packet_id, packet_type, source_node, target_node,
                   payload, timestamp, status
            FROM packets
            WHERE target_node = ? AND status = ?
            ORDER BY timestamp DESC
        """, (node_id, status))

        rows = cursor.fetchall()
        conn.close()

        packets = []
        for row in rows:
            packets.append({
                "packet_id": row[0],
                "packet_type": row[1],
                "source_node": row[2],
                "target_node": row[3],
                "payload": json.loads(row[4]),
                "timestamp": row[5],
                "status": row[6]
            })

        return packets

    def mark_received(self, packet_id: str):
        """Mark packet as received."""
        timestamp = datetime.utcnow().isoformat() + "Z"
        conn = get_connection()
        conn.execute("""
            UPDATE packets
            SET status = 'RECEIVED', received_at = ?
            WHERE packet_id = ?
        """, (timestamp, packet_id))
        conn.commit()
        conn.close()

    def mark_acknowledged(self, packet_id: str):
        """Mark packet as acknowledged."""
        timestamp = datetime.utcnow().isoformat() + "Z"
        conn = get_connection()
        conn.execute("""
            UPDATE packets
            SET status = 'ACKNOWLEDGED', acknowledged_at = ?
            WHERE packet_id = ?
        """, (timestamp, packet_id))
        conn.commit()
        conn.close()

    def get_packet(self, packet_id: str) -> Optional[Dict]:
        """Get packet by ID."""
        conn = get_connection()
        cursor = conn.execute("""
            SELECT packet_id, packet_type, source_node, target_node,
                   payload, timestamp, status
            FROM packets
            WHERE packet_id = ?
        """, (packet_id,))

        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return {
            "packet_id": row[0],
            "packet_type": row[1],
            "source_node": row[2],
            "target_node": row[3],
            "payload": json.loads(row[4]),
            "timestamp": row[5],
            "status": row[6]
        }

    def list_packets(self, limit: int = 50) -> List[Dict]:
        """List recent packets."""
        conn = get_connection()
        cursor = conn.execute("""
            SELECT packet_id, packet_type, source_node, target_node,
                   timestamp, status
            FROM packets
            ORDER BY timestamp DESC
            LIMIT ?
        """, (limit,))

        rows = cursor.fetchall()
        conn.close()

        return [{
            "packet_id": row[0],
            "packet_type": row[1],
            "source_node": row[2],
            "target_node": row[3],
            "timestamp": row[4],
            "status": row[5]
        } for row in rows]

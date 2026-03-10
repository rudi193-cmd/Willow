"""
Delta Tracker - Entropy Change Tracking for AIONIC_CONTINUITY

Tracks ΔE (delta-entropy) between session states to measure coherence drift.
Generates DELTA.md files documenting state transitions.

GOVERNANCE: Read-only state tracking, governance-logged writes
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
from typing import Dict, List, Optional, Any


class DeltaTracker:
    """Track entropy changes between session states."""

    def __init__(self, username: str):
        self.username = username
        self.delta_dir = Path("artifacts/kart/deltas")
        self.delta_dir.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initialize database schema."""
        conn = get_connection()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS deltas (
                delta_id TEXT PRIMARY KEY,
                thread_from TEXT NOT NULL,
                thread_to TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                state_before TEXT,
                state_after TEXT,
                changes TEXT,
                entropy_delta REAL,
                coherence_score REAL
            )
        """)
        conn.commit()
        conn.close()

    def calculate_delta(self, state_before: Dict, state_after: Dict) -> float:
        """
        Calculate entropy delta between two states.

        Args:
            state_before: Previous state dict
            state_after: Current state dict

        Returns:
            Entropy delta (0.0 = identical, 1.0 = completely different)
        """
        # Serialize states for comparison
        before_str = json.dumps(state_before, sort_keys=True)
        after_str = json.dumps(state_after, sort_keys=True)

        # Calculate character-level difference
        max_len = max(len(before_str), len(after_str))
        if max_len == 0:
            return 0.0

        differences = sum(c1 != c2 for c1, c2 in zip(before_str, after_str))
        differences += abs(len(before_str) - len(after_str))

        return differences / max_len

    def generate_delta_file(self, thread_from: str, thread_to: str,
                           changes: List[Dict[str, Any]]) -> Path:
        """
        Generate DELTA.md file documenting state transition.

        Args:
            thread_from: Source thread ID
            thread_to: Target thread ID
            changes: List of change dicts with {field, from, to, entropy_delta}

        Returns:
            Path to generated DELTA.md file
        """
        delta_id = f"delta-{thread_from}-{thread_to}"
        timestamp = datetime.utcnow().isoformat() + "Z"

        # Calculate total entropy
        total_entropy = sum(c.get("entropy_delta", 0.0) for c in changes)
        coherence_score = max(0.0, 1.0 - total_entropy)

        # Generate markdown
        content = f"""# DELTA.md

delta_id: {delta_id}
timestamp: {timestamp}
ΔE_calculation:
  state_before: "{thread_from}"
  state_after: "{thread_to}"
  changes:
"""

        for change in changes:
            field = change.get("field", "unknown")
            from_val = change.get("from", "")
            to_val = change.get("to", "")
            entropy = change.get("entropy_delta", 0.0)
            content += f"""    - field: "{field}"
      from: "{from_val}"
      to: "{to_val}"
      entropy_delta: {entropy:.3f}
"""

        content += f"""
coherence_score: {coherence_score:.2f}  # 1.0 = perfect continuity
total_entropy_delta: {total_entropy:.3f}

ΔΣ=42
"""

        # Save file
        delta_file = self.delta_dir / f"{delta_id}.md"
        delta_file.write_text(content, encoding="utf-8")

        # Save to DB
        self._save_to_db(delta_id, thread_from, thread_to, timestamp,
                        changes, total_entropy, coherence_score)

        return delta_file

    def _save_to_db(self, delta_id: str, thread_from: str, thread_to: str,
                   timestamp: str, changes: List[Dict], entropy_delta: float,
                   coherence_score: float):
        """Save delta to database."""
        conn = get_connection()
        conn.execute("""
            INSERT INTO deltas
            (delta_id, thread_from, thread_to, timestamp, state_before,
             state_after, changes, entropy_delta, coherence_score)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (delta_id) DO UPDATE SET
                thread_from=EXCLUDED.thread_from, thread_to=EXCLUDED.thread_to,
                timestamp=EXCLUDED.timestamp, state_before=EXCLUDED.state_before,
                state_after=EXCLUDED.state_after, changes=EXCLUDED.changes,
                entropy_delta=EXCLUDED.entropy_delta, coherence_score=EXCLUDED.coherence_score
        """, (delta_id, thread_from, thread_to, timestamp,
              thread_from, thread_to, json.dumps(changes),
              entropy_delta, coherence_score))
        conn.commit()
        conn.close()

    def get_latest_delta(self) -> Optional[Dict]:
        """Get most recent delta."""
        conn = get_connection()
        cursor = conn.execute("""
            SELECT delta_id, thread_from, thread_to, timestamp,
                   entropy_delta, coherence_score
            FROM deltas
            ORDER BY timestamp DESC
            LIMIT 1
        """)
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return {
            "delta_id": row[0],
            "thread_from": row[1],
            "thread_to": row[2],
            "timestamp": row[3],
            "entropy_delta": row[4],
            "coherence_score": row[5]
        }

    def list_deltas(self, limit: int = 10) -> List[Dict]:
        """List recent deltas."""
        conn = get_connection()
        cursor = conn.execute("""
            SELECT delta_id, thread_from, thread_to, timestamp,
                   entropy_delta, coherence_score
            FROM deltas
            ORDER BY timestamp DESC
            LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()
        conn.close()

        return [{
            "delta_id": row[0],
            "thread_from": row[1],
            "thread_to": row[2],
            "timestamp": row[3],
            "entropy_delta": row[4],
            "coherence_score": row[5]
        } for row in rows]

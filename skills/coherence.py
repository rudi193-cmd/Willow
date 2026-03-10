#!/usr/bin/env python3
"""
Willow Coherence Skill — Check knowledge coherence.

Calculates ΔE (delta entropy) for knowledge atoms to detect drift.
"""

import json
import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.db import get_connection

def check_coherence(username: str = "Sweet-Pea-Rudi19",
                   topic: str = None,
                   threshold: float = 0.5) -> dict:
    """Check coherence across knowledge base."""
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Get recent atoms
        if topic:
            cursor.execute("""
                SELECT id, content, delta_e, category, created_at
                FROM knowledge
                WHERE content LIKE ? OR category LIKE ?
                ORDER BY created_at DESC
                LIMIT 100
            """, (f"%{topic}%", f"%{topic}%"))
        else:
            cursor.execute("""
                SELECT id, content, delta_e, category, created_at
                FROM knowledge
                ORDER BY created_at DESC
                LIMIT 100
            """)

        atoms = cursor.fetchall()
        conn.close()

        # Analyze coherence
        high_drift = []
        for atom in atoms:
            if atom.get("delta_e") and atom["delta_e"] > threshold:
                high_drift.append({
                    "id": atom["id"],
                    "content_preview": atom["content"][:100] + "..." if len(atom["content"]) > 100 else atom["content"],
                    "delta_e": atom["delta_e"],
                    "category": atom["category"],
                    "created_at": atom["created_at"]
                })

        avg_delta_e = sum(a["delta_e"] for a in atoms if a.get("delta_e")) / len(atoms) if atoms else 0.0

        return {
            "total_atoms": len(atoms),
            "avg_delta_e": round(avg_delta_e, 3),
            "high_drift_count": len(high_drift),
            "threshold": threshold,
            "high_drift_atoms": high_drift[:10]  # Top 10
        }

    except Exception as e:
        return {"error": str(e)}

def main():
    parser = argparse.ArgumentParser(description="Check Willow knowledge coherence")
    parser.add_argument("--user", default="Sweet-Pea-Rudi19", help="Username")
    parser.add_argument("--topic", help="Filter by topic")
    parser.add_argument("--threshold", type=float, default=0.5, help="ΔE threshold")
    args = parser.parse_args()

    try:
        result = check_coherence(args.user, args.topic, args.threshold)
        print(json.dumps(result, indent=2))
        sys.exit(0)

    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()

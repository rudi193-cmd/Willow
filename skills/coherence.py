#!/usr/bin/env python3
"""
Willow Coherence Skill — Check knowledge coherence.

Calculates ΔE (delta entropy) for knowledge atoms to detect drift.
"""

import json
import sys
import argparse
import sqlite3
from pathlib import Path

def check_coherence(username: str = "Sweet-Pea-Rudi19",
                   topic: str = None,
                   threshold: float = 0.5) -> dict:
    """Check coherence across knowledge base."""
    db_path = Path(__file__).parent.parent / "data" / f"{username}_knowledge.db"

    if not db_path.exists():
        return {"error": "Knowledge database not found"}

    try:
        conn = sqlite3.connect(db_path)
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
            if atom[2] and atom[2] > threshold:
                high_drift.append({
                    "id": atom[0],
                    "content_preview": atom[1][:100] + "..." if len(atom[1]) > 100 else atom[1],
                    "delta_e": atom[2],
                    "category": atom[3],
                    "created_at": atom[4]
                })

        avg_delta_e = sum(a[2] for a in atoms if a[2]) / len(atoms) if atoms else 0.0

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

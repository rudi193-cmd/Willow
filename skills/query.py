#!/usr/bin/env python3
"""
Willow Query Skill — Query knowledge base.

Searches knowledge database for matching entries.
"""

import json
import sys
import sqlite3
import argparse
from pathlib import Path

def query_knowledge(query: str, username: str = "Sweet-Pea-Rudi19",
                   limit: int = 10) -> list:
    """Query knowledge database."""
    db_path = Path(__file__).parent.parent / "data" / f"{username}_knowledge.db"

    if not db_path.exists():
        return []

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Search in content and summary
        cursor.execute("""
            SELECT id, content, summary, category, source_type, created_at, delta_e
            FROM knowledge
            WHERE content LIKE ? OR summary LIKE ?
            ORDER BY created_at DESC
            LIMIT ?
        """, (f"%{query}%", f"%{query}%", limit))

        results = []
        for row in cursor.fetchall():
            results.append({
                "id": row[0],
                "content": row[1][:200] + "..." if len(row[1]) > 200 else row[1],
                "summary": row[2],
                "category": row[3],
                "source_type": row[4],
                "created_at": row[5],
                "delta_e": row[6]
            })

        conn.close()
        return results

    except Exception as e:
        raise RuntimeError(f"Query failed: {e}")

def main():
    parser = argparse.ArgumentParser(description="Query Willow knowledge base")
    parser.add_argument("query", help="Search query")
    parser.add_argument("--user", default="Sweet-Pea-Rudi19", help="Username")
    parser.add_argument("--limit", type=int, default=10, help="Max results")
    args = parser.parse_args()

    try:
        results = query_knowledge(args.query, args.user, args.limit)
        print(json.dumps({
            "query": args.query,
            "results": results,
            "count": len(results)
        }, indent=2))
        sys.exit(0)

    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Willow Query Skill — Query knowledge base.

Searches knowledge database for matching entries.
"""

import json
import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.db import get_connection

def query_knowledge(query: str, username: str = "Sweet-Pea-Rudi19",
                   limit: int = 10) -> list:
    """Query knowledge database."""
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Search in content and summary
        cursor.execute("""
            SELECT id, content, summary, category, source_type, created_at, delta_e
            FROM knowledge
            WHERE content LIKE %s OR summary LIKE %s
            ORDER BY created_at DESC
            LIMIT %s
        """, (f"%{query}%", f"%{query}%", limit))

        results = []
        for row in cursor.fetchall():
            results.append({
                "id": row["id"],
                "content": row["content"][:200] + "..." if row["content"] and len(row["content"]) > 200 else (row["content"] or ""),
                "summary": row["summary"],
                "category": row["category"],
                "source_type": row["source_type"],
                "created_at": str(row["created_at"]) if row["created_at"] else None,
                "delta_e": row["delta_e"]
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

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.db import get_connection

def search(query, limit=10, repo=None):
    results = []
    try:
        conn = get_connection()
        sql = "SELECT file_path, repo, text FROM chunks WHERE text LIKE %s"
        params = [f"%{query}%"]
        if repo:
            sql += " AND repo = %s"
            params.append(repo)
        sql += " LIMIT %s"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        for row in rows:
            results.append({"file_path": row["file_path"], "repo": row["repo"], "text": row["text"]})
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
    return results

def main():
    parser = argparse.ArgumentParser(description="Search the Willow RAG database")
    parser.add_argument("query", help="Search query")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--repo", help="Filter by repo")
    args = parser.parse_args()

    results = search(args.query, limit=args.limit, repo=args.repo)
    if not results:
        print("No results found.")
        return
    for item in results:
        fp = (item["file_path"] or "").encode("ascii","ignore").decode("ascii")
        text = (item["text"] or "")[:400].encode("ascii","ignore").decode("ascii")
        print(f"=== {fp} ===")
        print(text)
        print()
    print(f"Total: {len(results)} results")

if __name__ == "__main__":
    main()

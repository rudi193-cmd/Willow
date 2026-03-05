#!/usr/bin/env python3
"""
Index All Claude Code Sessions

Indexes all .jsonl session logs into conversation RAG database.

Usage:
    python tools/index_all_sessions.py
    python tools/index_all_sessions.py --sessions-dir /path/to/sessions

CHECKSUM: ΔΣ=42
"""

import sys
import os
from pathlib import Path
import argparse

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core import conversation_rag

def index_all(sessions_dir: str):
    """Index all .jsonl files in sessions directory."""
    sessions_path = Path(sessions_dir)
    
    if not sessions_path.exists():
        print(f"ERROR: Sessions directory not found: {sessions_dir}")
        return
    
    # Find all .jsonl files
    jsonl_files = list(sessions_path.glob("*.jsonl"))
    
    if not jsonl_files:
        print(f"No .jsonl files found in {sessions_dir}")
        return
    
    print(f"Found {len(jsonl_files)} session files")
    print()
    
    # Initialize database
    conversation_rag.init_db()
    
    # Index each file
    total_chunks = 0
    successful = 0
    failed = 0
    
    for jsonl_file in jsonl_files:
        print(f"Indexing {jsonl_file.name}...", end=" ")
        result = conversation_rag.index_session(str(jsonl_file))
        
        if result["success"]:
            chunks = result["chunks_indexed"]
            total_chunks += chunks
            successful += 1
            print(f"OK ({chunks} chunks)")
        else:
            failed += 1
            print(f"FAIL ({result.get('error', 'unknown error')})")
    
    print()
    print("=" * 60)
    print(f"Indexed: {successful}/{len(jsonl_files)} sessions")
    print(f"Total chunks: {total_chunks}")
    if failed > 0:
        print(f"Failed: {failed}")
    print("=" * 60)
    
    # Show stats
    stats = conversation_rag.get_stats()
    print()
    print(f"Database: {stats['db_path']}")
    print(f"Sessions in DB: {stats['sessions']}")
    print(f"Chunks in DB: {stats['chunks']}")


def main():
    parser = argparse.ArgumentParser(description="Index all Claude Code session logs")
    parser.add_argument(
        "--sessions-dir",
        default=r"C:\Users\Sean\.claude\projects\C--Users-Sean-Documents-GitHub",
        help="Directory containing .jsonl session files"
    )
    
    args = parser.parse_args()
    index_all(args.sessions_dir)


if __name__ == "__main__":
    main()

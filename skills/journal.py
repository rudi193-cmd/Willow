#!/usr/bin/env python3
"""
Willow Journal Skill — Add entry to continuity ring.

Appends timestamped entry to SAFE journal or local journal.
"""

import json
import sys
import argparse
from pathlib import Path
from datetime import datetime

def add_journal_entry(content: str,
                     category: str = "note",
                     username: str = "Sweet-Pea-Rudi19") -> dict:
    """Add entry to journal."""
    # Local journal path
    journal_path = Path(__file__).parent.parent / "data" / f"{username}_journal.md"
    journal_path.parent.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"\n## {timestamp} — {category}\n\n{content}\n"

    try:
        # Append to journal
        with open(journal_path, "a", encoding="utf-8") as f:
            f.write(entry)

        # Count total entries
        with open(journal_path, "r", encoding="utf-8") as f:
            entry_count = f.read().count("##")

        return {
            "success": True,
            "timestamp": timestamp,
            "category": category,
            "journal_path": str(journal_path),
            "total_entries": entry_count
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

def main():
    parser = argparse.ArgumentParser(description="Add Willow journal entry")
    parser.add_argument("content", help="Journal entry content")
    parser.add_argument("--category", default="note", help="Entry category")
    parser.add_argument("--user", default="Sweet-Pea-Rudi19", help="Username")
    args = parser.parse_args()

    try:
        result = add_journal_entry(args.content, args.category, args.user)
        print(json.dumps(result, indent=2))
        sys.exit(0 if result.get("success") else 1)

    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()

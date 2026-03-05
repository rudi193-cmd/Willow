#!/usr/bin/env python3
"""
Willow Route Skill — Manually route a file.

Analyzes a file and routes it to specified destination.
"""

import json
import sys
import argparse
from pathlib import Path

def route_file(file_path: str, destination: str = None) -> dict:
    """Route a file through Willow intake system."""
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    # Import extraction if available
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from core import extraction
        has_extraction = True
    except ImportError:
        has_extraction = False

    result = {
        "file": str(path),
        "size": path.stat().st_size,
        "extension": path.suffix
    }

    # Extract content if possible
    if has_extraction:
        extracted = extraction.extract_content(str(path))
        result["extracted"] = {
            "method": extracted["method"],
            "success": extracted["success"],
            "text_length": len(extracted["text"]) if extracted["text"] else 0
        }

        # Analyze for routing
        if extracted["success"] and extracted["text"]:
            analysis = extraction.analyze_content_for_routing(
                extracted["text"],
                path.name,
                path.suffix
            )
            result["suggested_destination"] = analysis["suggested_destination"]
            result["confidence"] = analysis["confidence"]
            result["reasoning"] = analysis["reasoning"]

    # Use specified destination or suggestion
    result["routed_to"] = destination if destination else result.get("suggested_destination", "unknown")

    return result

def main():
    parser = argparse.ArgumentParser(description="Route file through Willow")
    parser.add_argument("file", help="File path to route")
    parser.add_argument("--dest", help="Destination (or auto-detect)")
    args = parser.parse_args()

    try:
        result = route_file(args.file, args.dest)
        print(json.dumps(result, indent=2))
        sys.exit(0)

    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()

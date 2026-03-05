"""
risk_classifier.py — Governance risk tier classifier (GNS02)
=============================================================
Classifies file write operations into four tiers:
  T1 GOVERN  — Full Dual Commit required
  T2 INFORM  — Log and allow
  T3 ALLOW   — Proceed freely (dev repos)
  T4 FREE    — Proceed immediately (personal/creative/tools)

Usage (from PowerShell hook):
  python risk_classifier.py "C:\\path\\to\\file.py"
  Exit code: 1=T1, 2=T2, 3=T3, 4=T4
  Stdout: JSON with tier, label, reason
"""

import json
import re
import sys
from pathlib import Path

# ─── Tier Definitions ─────────────────────────────────────────────────────────

T1_PATTERNS = [
    r"[/\\]Willow[/\\]core[/\\]",
    r"[/\\]Willow[/\\]archive[/\\]",
    r"[/\\]die-namic-system[/\\]governance[/\\](?!commits[/\\])",
    r"[/\\]die-namic-system[/\\]source_ring[/\\]",
    r"[/\\]SAFE[/\\](?!docs[/\\]|README)",
]

T2_PATTERNS = [
    r"[/\\]Willow[/\\]artifacts[/\\]",
    r"[/\\]Willow[/\\]ui[/\\]",
    r"[/\\]Willow[/\\]cli[/\\]",
    r"[/\\]die-namic-system[/\\]docs[/\\]",
    r"[/\\]die-namic-system[/\\]bridge_ring[/\\]",
    r"[/\\]die-namic-system[/\\]governance[/\\]commits[/\\]",
    r"[/\\]SAFE[/\\]docs[/\\]",
]

T3_PATTERNS = [
    r"[/\\]safe-app-",
    r"[/\\]scoot-",
    r"[/\\]safe-app-nasa-archive",
    r"[/\\]die-namic-website",
    r"[/\\]Willow[/\\]tests[/\\]",
    r"[/\\]Willow[/\\]scratch[/\\]",
    r"GitHub[/\\](?!Willow[/\\]core|Willow[/\\]archive|die-namic-system[/\\]governance|die-namic-system[/\\]source_ring|SAFE[/\\](?!docs))",
]

T4_PATTERNS = [
    r"[/\\]Desktop[/\\]",
    r"[/\\]Documents[/\\](?!GitHub)",
    r"[/\\]\.claude[/\\]hooks[/\\]",
    r"[/\\]\.claude[/\\]skills[/\\]",
    r"[/\\]\.claude[/\\]rules[/\\]",
    r"[/\\]\.claude[/\\]agents[/\\]",
    r"[/\\]\.claude[/\\](?!projects)",
    r"[/\\]AppData[/\\]",
    r"[/\\]tmp[/\\]",
    r"C:[/\\]tmp[/\\]",
]

TIERS = [
    (1, "GOVERN", T1_PATTERNS, "Full Dual Commit required — core production code"),
    (2, "INFORM", T2_PATTERNS, "Log and allow — low-risk production area"),
    (3, "ALLOW",  T3_PATTERNS, "Proceed freely — development repository"),
    (4, "FREE",   T4_PATTERNS, "Proceed immediately — personal or tool configuration"),
]


def classify(file_path: str) -> dict:
    """Return tier classification for a file path."""
    for tier_num, tier_label, patterns, reason in TIERS:
        for pattern in patterns:
            if re.search(pattern, file_path, re.IGNORECASE):
                return {
                    "tier": tier_num,
                    "label": tier_label,
                    "reason": reason,
                    "file_path": file_path,
                    "matched_pattern": pattern,
                }
    return {
        "tier": 2,
        "label": "INFORM",
        "reason": "Unknown path — defaulting to inform-and-allow",
        "file_path": file_path,
        "matched_pattern": None,
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "No file path provided"}))
        sys.exit(2)

    result = classify(sys.argv[1])
    print(json.dumps(result))
    sys.exit(result["tier"])

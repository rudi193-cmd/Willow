"""
SMART ROUTING — Multi-Destination File Routing
===============================================
When a file is processed, route it to multiple destinations based on content.

Examples:
- Reddit screenshot → your profile + social-media-tracker
- Code screenshot → your profile + Kart + social-media-tracker
- Gmail screenshot → your profile only (private)
- Twitter analytics → your profile + social-media-tracker + Kart (for metrics tracking)

Routing Rules:
- Filename patterns (Screenshot_*_Reddit.jpg → social media)
- OCR text analysis (contains "@" and "tweet" → Twitter)
- Content classification (Gemini: "What platform is this?")
"""

import re
import shutil
from pathlib import Path
from typing import List, Dict, Optional

# Import tracker
import sys
sys.path.insert(0, str(Path(__file__).parent))
from social_media_tracker import add_screenshot, log_routing

# Import PA ingest workflow
sys.path.insert(0, str(Path(__file__).parent / "pa"))
try:
    from drive_organize import _ingest_text
    _PA_INGEST_AVAILABLE = True
except ImportError:
    _PA_INGEST_AVAILABLE = False


def classify_screenshot(filename: str, ocr_text: Optional[str] = None) -> Dict:
    """
    Classify a screenshot to determine routing destinations.

    Returns:
    {
        "platform": "reddit" | "twitter" | "gmail" | "chrome" | "unknown",
        "is_social_media": bool,
        "is_code": bool,
        "is_private": bool,
        "destinations": ["user-profile", "social-media-tracker", "kart-interface"]
    }
    """
    filename_lower = filename.lower()
    ocr_lower = (ocr_text or "").lower()

    platform = "unknown"
    is_social_media = False
    is_code = False
    is_private = False

    # Detect platform from filename
    if "reddit" in filename_lower:
        platform = "reddit"
        is_social_media = True
    elif "twitter" in filename_lower or "x.com" in filename_lower:
        platform = "twitter"
        is_social_media = True
    elif "facebook" in filename_lower or "fb" in filename_lower:
        platform = "facebook"
        is_social_media = True
    elif "instagram" in filename_lower or "ig" in filename_lower:
        platform = "instagram"
        is_social_media = True
    elif "linkedin" in filename_lower:
        platform = "linkedin"
        is_social_media = True
    elif "gmail" in filename_lower:
        platform = "gmail"
        is_private = True
    elif "chrome" in filename_lower:
        platform = "chrome"
    elif "drive" in filename_lower:
        platform = "google-drive"

    # Refine with OCR
    if ocr_text:
        # Social media keywords
        social_keywords = ["upvote", "retweet", "like", "share", "comment", "post", "tweet", "reddit", "@", "#"]
        if any(kw in ocr_lower for kw in social_keywords):
            is_social_media = True

        # Code keywords
        code_keywords = ["function", "class", "import", "def ", "const ", "let ", "var ", "python", "javascript", "github"]
        if any(kw in ocr_lower for kw in code_keywords):
            is_code = True

        # Private keywords
        private_keywords = ["password", "credit card", "ssn", "bank account", "private", "confidential"]
        if any(kw in ocr_lower for kw in private_keywords):
            is_private = True

    # Determine destinations
    destinations = ["user-profile"]  # Always route to user

    if is_social_media and not is_private:
        destinations.append("social-media-tracker")

    if is_code:
        destinations.append("kart-interface")

    return {
        "platform": platform,
        "is_social_media": is_social_media,
        "is_code": is_code,
        "is_private": is_private,
        "destinations": destinations
    }


def route_screenshot(
    filename: str,
    filepath: str,
    ocr_text: Optional[str] = None,
    source_user: str = "Sweet-Pea-Rudi19"
) -> Dict:
    """Route a screenshot using learned preferences + heuristics."""

    # Import learning system
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from core import patterns

    classification = classify_screenshot(filename, ocr_text)
    file_type = Path(filename).suffix.lower() or ".jpg"

    # Check learned preferences FIRST
    suggestion = patterns.suggest_destinations_for(
        file_type=file_type,
        content_summary=f"Screenshot: {classification['platform']}",
        default_destinations=classification["destinations"],
        min_confidence=0.5
    )

    # Use learned or default
    destinations_to_route = suggestion["destinations"] if suggestion["reason"] == "learned_preference" else classification["destinations"]

    routed_to = []
    screenshot_id = None

    # Ingest content ONCE (extracts to knowledge DB, stores binary ONCE)
    canonical_dest = Path("artifacts") / source_user / "files" / filename
    canonical_dest.parent.mkdir(parents=True, exist_ok=True)

    # If PA ingest available and file is ingestable, extract content
    if _PA_INGEST_AVAILABLE and file_type in {".pdf", ".jpg", ".png", ".md", ".txt"}:
        entry = {
            "source": filepath,
            "category": classification.get("category", "document"),
            "ingestable": True
        }
        if _ingest_text(Path(filepath), entry, source_user):
            # Content extracted to knowledge DB
            pass

    # Move file to canonical location (ONE copy)
    if not canonical_dest.exists():
        shutil.move(filepath, canonical_dest)

    # Route METADATA (not file copies) to each destination
    for dest in destinations_to_route:
        if dest == "user-profile":
            routed_to.append("user-profile")

        elif dest == "social-media-tracker":
            # Add metadata reference to tracker
            screenshot_id = add_screenshot(
                filename=filename,
                filepath=str(canonical_dest),  # Reference, not copy
                platform=classification["platform"],
                ocr_text=ocr_text,
                source_user=source_user,
                tags="social-media" if classification["is_social_media"] else None
            )
            if screenshot_id:
                log_routing(screenshot_id, "social-media-tracker")
                routed_to.append("social-media-tracker")

        elif dest == "kart-interface":
            # Create reference in Kart inbox (symlink or metadata)
            routed_to.append("kart-interface")

    # LOG THE DECISION
    patterns.log_routing_decision(
        filename=filename,
        file_type=file_type,
        content_summary=f"{classification['platform']} screenshot",
        routed_to=routed_to,
        reason=suggestion["reason"],
        confidence=suggestion["confidence"]
    )

    return {
        "classification": classification,
        "routed_to": routed_to,
        "screenshot_id": screenshot_id
    }


# CLI
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python smart_routing.py <filepath> [ocr_text]")
        sys.exit(1)

    filepath = sys.argv[1]
    ocr_text = sys.argv[2] if len(sys.argv) > 2 else None

    filename = Path(filepath).name
    result = route_screenshot(filename, filepath, ocr_text)

    print(f"Platform: {result['classification']['platform']}")
    print(f"Social media: {result['classification']['is_social_media']}")
    print(f"Code: {result['classification']['is_code']}")
    print(f"Routed to: {', '.join(result['routed_to'])}")
    if result['screenshot_id']:
        print(f"Tracker ID: {result['screenshot_id']}")

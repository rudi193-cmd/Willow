"""
SOCIAL MEDIA TRACKER — Content Indexing Node
==============================================
Receives processed screenshots from intake pipeline.
Indexes social media content for search/retrieval.

Instance Profile:
- instance_id: social-media-tracker
- Trust Level: 1 (WORKER)
- Type: substrate (data collection)

Storage:
- artifacts/social-media-tracker/index.db
- artifacts/social-media-tracker/screenshots/

Multi-routing:
- Screenshots route to: user profile + tracker + (Kart if code) + (other nodes if relevant)
"""

import sys
import sqlite3
import shutil
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.db import get_connection

# Storage locations
BASE_PATH = Path(__file__).parent.parent / "artifacts" / "social-media-tracker"
INDEX_DB = BASE_PATH / "index.db"
SCREENSHOT_DIR = BASE_PATH / "screenshots"

# Ensure directories exist
BASE_PATH.mkdir(parents=True, exist_ok=True)
SCREENSHOT_DIR.mkdir(exist_ok=True)


def init_db():
    """Initialize social media tracker database."""
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS screenshots (
            id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
            filename TEXT NOT NULL,
            filepath TEXT NOT NULL,
            platform TEXT,
            content_hash TEXT UNIQUE,
            ocr_text TEXT,
            detected_metrics TEXT,
            timestamp TEXT NOT NULL,
            source_user TEXT,
            tags TEXT,
            processed BOOLEAN DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS routing_log (
            id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
            screenshot_id INTEGER,
            destination TEXT NOT NULL,
            routed_at TEXT NOT NULL,
            FOREIGN KEY (screenshot_id) REFERENCES screenshots(id)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_platform ON screenshots(platform)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON screenshots(timestamp)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_source_user ON screenshots(source_user)")
    conn.commit()
    conn.close()


def add_screenshot(
    filename: str,
    filepath: str,
    platform: Optional[str] = None,
    ocr_text: Optional[str] = None,
    detected_metrics: Optional[str] = None,
    source_user: str = "Sweet-Pea-Rudi19",
    tags: Optional[str] = None
) -> int:
    """
    Add a screenshot to the tracker index.
    Returns screenshot ID.
    """
    init_db()

    # Calculate content hash
    try:
        with open(filepath, 'rb') as f:
            content_hash = hashlib.sha256(f.read()).hexdigest()
    except:
        content_hash = None

    # Copy to tracker storage
    dest = SCREENSHOT_DIR / filename
    try:
        if not dest.exists():
            shutil.copy2(filepath, dest)
    except Exception as e:
        print(f"[social-media-tracker] Copy failed: {e}")

    conn = get_connection()
    cursor = conn.cursor()

    # Check if already indexed
    if content_hash:
        existing = cursor.execute(
            "SELECT id FROM screenshots WHERE content_hash = ?",
            (content_hash,)
        ).fetchone()
        if existing:
            conn.close()
            return existing[0]

    # Insert new
    cursor.execute("""
        INSERT INTO screenshots (filename, filepath, platform, content_hash, ocr_text, detected_metrics, timestamp, source_user, tags)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        filename,
        str(dest),
        platform,
        content_hash,
        ocr_text,
        detected_metrics,
        datetime.now().isoformat(),
        source_user,
        tags
    ))
    screenshot_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return screenshot_id


def log_routing(screenshot_id: int, destination: str):
    """Log that a screenshot was routed to a destination."""
    conn = get_connection()
    conn.execute("""
        INSERT INTO routing_log (screenshot_id, destination, routed_at)
        VALUES (?, ?, ?)
    """, (screenshot_id, destination, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def search_screenshots(
    platform: Optional[str] = None,
    source_user: Optional[str] = None,
    tags: Optional[str] = None,
    text_query: Optional[str] = None,
    limit: int = 50
) -> List[Dict]:
    """
    Search indexed screenshots.

    Returns list of dicts with screenshot metadata.
    """
    init_db()
    conn = get_connection()
    conn.row_factory = sqlite3.Row

    query = "SELECT * FROM screenshots WHERE 1=1"
    params = []

    if platform:
        query += " AND platform = ?"
        params.append(platform)

    if source_user:
        query += " AND source_user = ?"
        params.append(source_user)

    if tags:
        query += " AND tags LIKE ?"
        params.append(f"%{tags}%")

    if text_query:
        query += " AND ocr_text LIKE ?"
        params.append(f"%{text_query}%")

    query += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    conn.close()

    return [dict(row) for row in rows]


def get_stats() -> Dict:
    """Get tracker statistics."""
    init_db()
    conn = get_connection()

    total = conn.execute("SELECT COUNT(*) FROM screenshots").fetchone()[0]
    by_platform = conn.execute("""
        SELECT platform, COUNT(*) as count
        FROM screenshots
        GROUP BY platform
        ORDER BY count DESC
    """).fetchall()

    processed = conn.execute("SELECT COUNT(*) FROM screenshots WHERE processed = 1").fetchone()[0]
    unprocessed = total - processed

    conn.close()

    return {
        "total": total,
        "processed": processed,
        "unprocessed": unprocessed,
        "by_platform": dict(by_platform) if by_platform else {}
    }


def get_routing_destinations(screenshot_id: int) -> List[str]:
    """Get all destinations a screenshot was routed to."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT destination FROM routing_log
        WHERE screenshot_id = ?
        ORDER BY routed_at
    """, (screenshot_id,)).fetchall()
    conn.close()

    return [r[0] for r in rows]


# CLI
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python social_media_tracker.py [stats|search|add]")
        sys.exit(1)

    command = sys.argv[1]

    if command == "stats":
        stats = get_stats()
        print(f"Total screenshots: {stats['total']}")
        print(f"Processed: {stats['processed']}")
        print(f"Unprocessed: {stats['unprocessed']}")
        print("\nBy platform:")
        for platform, count in stats['by_platform'].items():
            print(f"  {platform or 'unknown'}: {count}")

    elif command == "search":
        query = sys.argv[2] if len(sys.argv) > 2 else None
        results = search_screenshots(text_query=query)
        print(f"Found {len(results)} screenshots:")
        for r in results[:10]:
            print(f"  {r['filename']} — {r['platform']} — {r['timestamp']}")

    elif command == "add":
        if len(sys.argv) < 3:
            print("Usage: python social_media_tracker.py add <filepath>")
            sys.exit(1)
        filepath = sys.argv[2]
        filename = Path(filepath).name
        screenshot_id = add_screenshot(filename, filepath)
        print(f"Added screenshot ID: {screenshot_id}")

    else:
        print(f"Unknown command: {command}")

"""
File Annotation System
Allows users to verify and annotate routing decisions with detailed notes.

User can mark a routing decision as correct/wrong and explain WHY.
This builds a knowledge base of edge cases for pattern learning.
"""

import json
from datetime import datetime
from typing import Optional, List, Dict


def _connect():
    from core.db import get_connection
    return get_connection()


def init_annotations_db():
    """Initialize file annotations database."""
    conn = _connect()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS file_annotations (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            routing_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            routed_to TEXT NOT NULL,
            is_correct BOOLEAN NOT NULL,
            annotation_notes TEXT NOT NULL,
            corrected_destination TEXT,
            annotated_by TEXT DEFAULT 'user',
            annotated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("CREATE INDEX IF NOT EXISTS idx_annotations_routing ON file_annotations(routing_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_annotations_correct ON file_annotations(is_correct)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_annotations_timestamp ON file_annotations(annotated_at)")

    conn.commit()
    conn.close()


def provide_annotation(
    routing_id: int,
    filename: str,
    routed_to: List[str],
    is_correct: bool,
    notes: str,
    corrected_destination: Optional[List[str]] = None,
    annotated_by: str = "user"
):
    """
    Store an annotation about a routing decision.

    Args:
        routing_id: ID from patterns.routing_history table
        filename: File that was routed
        routed_to: Where it was routed to (as JSON array)
        is_correct: True if routing was correct, False if wrong
        notes: Human explanation of why correct or wrong
        corrected_destination: If wrong, where it should have gone
        annotated_by: Who made the annotation (default "user")
    """
    init_annotations_db()
    conn = _connect()

    conn.execute("""
        INSERT INTO file_annotations
        (routing_id, filename, routed_to, is_correct, annotation_notes, corrected_destination, annotated_by, annotated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        routing_id,
        filename,
        json.dumps(routed_to),
        is_correct,
        notes,
        json.dumps(corrected_destination) if corrected_destination else None,
        annotated_by,
        datetime.now().isoformat()
    ))

    conn.commit()
    conn.close()

    # Update routing_history.user_corrected flag
    _update_routing_history(routing_id, is_correct)


def _update_routing_history(routing_id: int, is_correct: bool):
    """Update the user_corrected field in routing_history."""
    try:
        from . import patterns
        conn = patterns._connect()

        conn.execute("""
            UPDATE routing_history
            SET user_corrected = 1
            WHERE id = ?
        """, (routing_id,))

        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Warning: Could not update routing_history: {e}")


def get_unannotated_routings(limit: int = 20) -> List[Dict]:
    """
    Get recent routing decisions that haven't been annotated yet.

    Returns list of routing decisions with their details.
    """
    try:
        from . import patterns
        patterns_conn = patterns._connect()
        patterns_conn.row_factory = sqlite3.Row  # Ensure Row factory is set

        # Get routing decisions not yet annotated
        rows = patterns_conn.execute("""
            SELECT id, timestamp, filename, file_type, routed_to, reason, confidence
            FROM routing_history
            WHERE user_corrected = 0
            ORDER BY timestamp DESC
            LIMIT ?
        """, (limit,)).fetchall()

        patterns_conn.close()

        result = []
        for row in rows:
            try:
                result.append(dict(row))
            except:
                # Fallback if Row factory doesn't work
                result.append({
                    "id": row[0],
                    "timestamp": row[1],
                    "filename": row[2],
                    "file_type": row[3],
                    "routed_to": row[4],
                    "reason": row[5],
                    "confidence": row[6]
                })
        return result
    except Exception as e:
        print(f"Error getting unannotated routings: {e}")
        import traceback
        traceback.print_exc()
        return []


def get_annotation_stats() -> Dict:
    """
    Get annotation statistics.

    Returns:
        Dict with annotation counts by correctness, etc.
    """
    init_annotations_db()
    conn = _connect()

    # Total annotations
    total = conn.execute("SELECT COUNT(*) FROM file_annotations").fetchone()[0]

    # Correct vs incorrect
    correct = conn.execute("SELECT COUNT(*) FROM file_annotations WHERE is_correct = 1").fetchone()[0]
    incorrect = conn.execute("SELECT COUNT(*) FROM file_annotations WHERE is_correct = 0").fetchone()[0]

    # Recent annotations (last 7 days)
    from datetime import timedelta
    cutoff = (datetime.now() - timedelta(days=7)).isoformat()
    recent = conn.execute("SELECT COUNT(*) FROM file_annotations WHERE annotated_at > ?", (cutoff,)).fetchone()[0]

    # Most common correction types (analyze notes for patterns)
    wrong_annotations = conn.execute("""
        SELECT annotation_notes, routed_to, corrected_destination
        FROM file_annotations
        WHERE is_correct = 0
        ORDER BY annotated_at DESC
        LIMIT 10
    """).fetchall()

    conn.close()

    corrections = []
    for notes, routed, corrected in wrong_annotations:
        corrections.append({
            "notes": notes,
            "wrong_dest": json.loads(routed) if routed else [],
            "correct_dest": json.loads(corrected) if corrected else []
        })

    return {
        "total_annotations": total,
        "correct_count": correct,
        "incorrect_count": incorrect,
        "recent_7days": recent,
        "accuracy_rate": (correct / total * 100) if total > 0 else 0,
        "recent_corrections": corrections
    }


def get_annotations_by_file_type() -> Dict[str, Dict]:
    """
    Get annotation statistics grouped by file type.

    Returns dict mapping file_type -> {correct, incorrect, accuracy}.
    """
    init_annotations_db()
    conn = _connect()

    # Get all annotations with routing IDs
    try:
        from . import patterns
        patterns_conn = patterns._connect()

        # Get annotations
        annotations = conn.execute("""
            SELECT routing_id, is_correct
            FROM file_annotations
        """).fetchall()

        # Build stats by file type
        by_type = {}
        for routing_id, is_correct in annotations:
            # Get file_type from routing_history
            row = patterns_conn.execute("""
                SELECT file_type FROM routing_history WHERE id = ?
            """, (routing_id,)).fetchone()

            if row and row[0]:
                file_type = row[0]
                if file_type not in by_type:
                    by_type[file_type] = {"correct": 0, "incorrect": 0}

                if is_correct:
                    by_type[file_type]["correct"] += 1
                else:
                    by_type[file_type]["incorrect"] += 1

        # Calculate totals and accuracy
        for file_type, stats in by_type.items():
            total = stats["correct"] + stats["incorrect"]
            stats["total"] = total
            stats["accuracy"] = (stats["correct"] / total * 100) if total > 0 else 0

        patterns_conn.close()
        conn.close()

        return by_type
    except Exception as e:
        print(f"Error getting annotations by file type: {e}")
        import traceback
        traceback.print_exc()
        conn.close()
        return {}


def get_recent_annotations(limit: int = 10) -> List[Dict]:
    """Get recent annotations with full details."""
    init_annotations_db()
    conn = _connect()

    rows = conn.execute("""
        SELECT
            id,
            routing_id,
            filename,
            routed_to,
            is_correct,
            annotation_notes,
            corrected_destination,
            annotated_by,
            annotated_at
        FROM file_annotations
        ORDER BY annotated_at DESC
        LIMIT ?
    """, (limit,)).fetchall()

    conn.close()

    return [
        {
            "id": r["id"],
            "routing_id": r["routing_id"],
            "filename": r["filename"],
            "routed_to": json.loads(r["routed_to"]) if r["routed_to"] else [],
            "is_correct": bool(r["is_correct"]),
            "notes": r["annotation_notes"],
            "corrected_destination": json.loads(r["corrected_destination"]) if r["corrected_destination"] else None,
            "annotated_by": r["annotated_by"],
            "annotated_at": r["annotated_at"]
        }
        for r in rows
    ]


if __name__ == "__main__":
    # Test initialization
    init_annotations_db()
    print(f"[OK] File annotations database initialized at: {ANNOTATIONS_DB}")

    # Test annotation
    provide_annotation(
        routing_id=1,
        filename="test.py",
        routed_to=["wrong_node"],
        is_correct=False,
        notes="This file should go to code_review, not wrong_node. It's a Python script with imports.",
        corrected_destination=["code_review"],
        annotated_by="test_user"
    )
    print("[OK] Test annotation saved")

    # Test stats
    stats = get_annotation_stats()
    print(f"[OK] Annotation stats: {stats}")

    # Test recent annotations
    recent = get_recent_annotations(limit=5)
    print(f"[OK] Recent annotations: {len(recent)} entries")

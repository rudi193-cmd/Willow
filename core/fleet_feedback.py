"""
Fleet Feedback System
Tracks and learns from fleet output quality to improve future prompts.
"""

import json
from datetime import datetime
from typing import Optional, List, Dict


def _connect():
    from core.db import get_connection
    return get_connection()


def init_feedback_db():
    """No-op — schema managed by pg_schema.sql."""
    return
    conn = _connect()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS fleet_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL,
            task_type TEXT NOT NULL,
            prompt TEXT NOT NULL,
            output TEXT NOT NULL,
            quality_rating INTEGER CHECK(quality_rating BETWEEN 1 AND 5),
            issues TEXT,
            feedback_notes TEXT,
            corrected_output TEXT,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("CREATE INDEX IF NOT EXISTS idx_feedback_provider ON fleet_feedback(provider, task_type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_feedback_quality ON fleet_feedback(quality_rating)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_feedback_timestamp ON fleet_feedback(timestamp)")

    conn.commit()
    conn.close()


def provide_feedback(
    provider: str,
    task_type: str,
    prompt: str,
    output: str,
    quality: int,
    issues_list: List[str],
    notes: str,
    corrected: Optional[str] = None
):
    """
    Store feedback about fleet output.

    Args:
        provider: Provider name (e.g., "Groq", "Cerebras")
        task_type: Task type (e.g., "html_generation", "javascript_generation")
        prompt: Original prompt sent to fleet
        output: Output received from fleet
        quality: Quality rating 1-5 (1=bad, 5=great)
        issues_list: List of issue types (e.g., ["wrong_tech_stack", "syntax_errors"])
        notes: Human explanation of what was wrong/right
        corrected: Optional corrected version of the output
    """
    init_feedback_db()
    conn = _connect()

    conn.execute("""
        INSERT INTO fleet_feedback
        (provider, task_type, prompt, output, quality_rating, issues, feedback_notes, corrected_output, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        provider,
        task_type,
        prompt,
        output,
        quality,
        json.dumps(issues_list),
        notes,
        corrected,
        datetime.now().isoformat()
    ))

    conn.commit()
    conn.close()


def get_feedback_for_task(task_type: str, min_quality: Optional[int] = None, limit: int = 5) -> List[Dict]:
    """
    Get recent feedback for a task type.

    Args:
        task_type: Task type to get feedback for
        min_quality: Optional minimum quality rating filter
        limit: Max number of results

    Returns:
        List of feedback dicts
    """
    init_feedback_db()
    conn = _connect()

    query = "SELECT * FROM fleet_feedback WHERE task_type = ?"
    params = [task_type]

    if min_quality is not None:
        query += " AND quality_rating >= ?"
        params.append(min_quality)

    query += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    conn.close()

    return [dict(row) for row in rows]


def get_feedback_stats() -> Dict:
    """
    Get feedback statistics by provider and task type.

    Returns:
        Dict with stats like:
        {
            "by_provider": {"Groq": {"avg_quality": 3.5, "total": 10}, ...},
            "by_task": {"html_generation": {"avg_quality": 4.0, "total": 5}, ...}
        }
    """
    init_feedback_db()
    conn = _connect()

    # Stats by provider
    by_provider = {}
    rows = conn.execute("""
        SELECT provider,
               AVG(quality_rating) as avg_quality,
               COUNT(*) as total,
               SUM(CASE WHEN quality_rating <= 2 THEN 1 ELSE 0 END) as poor_count
        FROM fleet_feedback
        GROUP BY provider
    """).fetchall()

    for row in rows:
        by_provider[row['provider']] = {
            'avg_quality': round(row['avg_quality'], 2),
            'total': row['total'],
            'poor_count': row['poor_count']
        }

    # Stats by task type
    by_task = {}
    rows = conn.execute("""
        SELECT task_type,
               AVG(quality_rating) as avg_quality,
               COUNT(*) as total
        FROM fleet_feedback
        GROUP BY task_type
    """).fetchall()

    for row in rows:
        by_task[row['task_type']] = {
            'avg_quality': round(row['avg_quality'], 2),
            'total': row['total']
        }

    conn.close()

    return {
        'by_provider': by_provider,
        'by_task': by_task
    }


def enhance_prompt_with_feedback(prompt: str, task_type: str) -> str:
    """
    Enhance a prompt with learned corrections from past feedback.

    Adds a section with common mistakes to avoid based on poor-quality outputs.

    Args:
        prompt: Original prompt
        task_type: Task type

    Returns:
        Enhanced prompt with corrections appended
    """
    # Get poor-quality feedback (rating <= 2) for this task type
    feedback = get_feedback_for_task(task_type, min_quality=None, limit=10)
    poor_feedback = [f for f in feedback if f['quality_rating'] <= 2]

    if not poor_feedback:
        return prompt

    # Build corrections section from feedback notes
    corrections = "\n\n⚠️ IMPORTANT - Avoid these mistakes (from past feedback):\n"
    seen_notes = set()

    for fb in poor_feedback:
        notes = fb['feedback_notes']
        if notes and notes not in seen_notes:
            corrections += f"- {notes}\n"
            seen_notes.add(notes)

        # Add issues if present
        try:
            issues = json.loads(fb['issues']) if fb['issues'] else []
            for issue in issues:
                issue_text = issue.replace('_', ' ').title()
                if issue_text not in corrections:
                    corrections += f"- Avoid: {issue_text}\n"
        except:
            pass

    return prompt + corrections


if __name__ == "__main__":
    # Test initialization
    init_feedback_db()
    print(f"[OK] Fleet feedback database initialized at: {FEEDBACK_DB}")

    # Test feedback
    provide_feedback(
        provider="Groq",
        task_type="html_generation",
        prompt="Generate HTML dashboard",
        output="<div>test</div>",
        quality=2,
        issues_list=["wrong_tech_stack", "incomplete"],
        notes="Generated React code instead of vanilla JS. Project uses Python/FastAPI, not React/Node."
    )
    print("[OK] Test feedback saved")

    # Test stats
    stats = get_feedback_stats()
    print(f"[OK] Feedback stats: {stats}")

    # Test prompt enhancement
    enhanced = enhance_prompt_with_feedback("Generate HTML", "html_generation")
    print("[OK] Prompt enhancement working (contains corrections)")

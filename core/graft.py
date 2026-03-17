"""
Kart Task Management System

SQLite-backed task storage for Kart orchestration.
Mimics Claude Code's TaskList functionality.

GOVERNANCE: Task operations logged and auditable
AUTHOR: Kart Orchestration System
VERSION: 1.0
CHECKSUM: ΔΣ=42
"""

import json
from datetime import datetime
from typing import List, Dict, Optional, Any


def _connect(username: str = None):
    from core.db import get_connection
    conn = get_connection()
    return conn


def init_db(username: str):
    pass  # tables created by pg_schema.sql


def create_task(username: str, subject: str, description: str, agent: str, metadata: Optional[Dict] = None) -> str:
    """
    Create a new task.

    Args:
        username: User name
        subject: Task subject/title
        description: Detailed description
        agent: Agent creating the task
        metadata: Optional metadata dict

    Returns:
        task_id: Unique task ID (e.g., "task-001")
    """
    init_db(username)
    conn = _connect(username)

    # Generate task ID
    cursor = conn.execute("SELECT COUNT(*) FROM tasks WHERE username = ?", (username,))
    count = cursor.fetchone()[0]
    task_id = f"task-{count + 1:03d}"

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Insert task
    conn.execute("""
        INSERT INTO tasks (username, task_id, subject, description, status, agent, created_at, updated_at, metadata)
        VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?)
    """, (username, task_id, subject, description, agent, now, now, json.dumps(metadata) if metadata else None))

    # Log creation
    conn.execute("""
        INSERT INTO task_log (username, task_id, timestamp, action, agent, details)
        VALUES (?, ?, ?, 'created', ?, ?)
    """, (username, task_id, now, agent, f"Created task: {subject}"))

    conn.commit()
    conn.close()

    return task_id


def get_task(username: str, task_id: str) -> Optional[Dict[str, Any]]:
    """
    Get task by ID.

    Returns:
        Task dict with all fields, or None if not found
    """
    init_db(username)
    conn = _connect(username)

    row = conn.execute("SELECT * FROM tasks WHERE username = ? AND task_id = ?", (username, task_id)).fetchone()
    conn.close()

    if row:
        task = dict(row)
        if task.get('metadata'):
            task['metadata'] = json.loads(task['metadata'])
        return task
    return None


def list_tasks(username: str, agent: Optional[str] = None, status: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    List tasks with optional filters.

    Args:
        username: User name
        agent: Filter by agent (optional)
        status: Filter by status (optional)

    Returns:
        List of task dicts
    """
    init_db(username)
    conn = _connect(username)

    query = "SELECT * FROM tasks WHERE username = ?"
    params = [username]

    if agent:
        query += " AND agent = ?"
        params.append(agent)
    if status:
        query += " AND status = ?"
        params.append(status)

    query += " ORDER BY created_at DESC"

    rows = conn.execute(query, params).fetchall()
    conn.close()

    tasks = []
    for row in rows:
        task = dict(row)
        if task.get('metadata'):
            task['metadata'] = json.loads(task['metadata'])
        tasks.append(task)

    return tasks


def update_task(username: str, task_id: str, status: str, agent: str, metadata: Optional[Dict] = None) -> bool:
    """
    Update task status.

    Args:
        username: User name
        task_id: Task ID
        status: New status (pending, in_progress, completed, failed)
        agent: Agent performing update
        metadata: Optional metadata to merge

    Returns:
        True if updated, False if task not found
    """
    init_db(username)
    conn = _connect(username)

    # Check task exists
    row = conn.execute("SELECT * FROM tasks WHERE username = ? AND task_id = ?", (username, task_id)).fetchone()
    if not row:
        conn.close()
        return False

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Update task
    if status == 'completed':
        conn.execute("""
            UPDATE tasks
            SET status = ?, updated_at = ?, completed_at = ?, metadata = ?
            WHERE username = ? AND task_id = ?
        """, (status, now, now, json.dumps(metadata) if metadata else row['metadata'], username, task_id))
    else:
        conn.execute("""
            UPDATE tasks
            SET status = ?, updated_at = ?, metadata = ?
            WHERE username = ? AND task_id = ?
        """, (status, now, json.dumps(metadata) if metadata else row['metadata'], username, task_id))

    # Log update
    conn.execute("""
        INSERT INTO task_log (username, task_id, timestamp, action, agent, details)
        VALUES (?, ?, ?, 'status_changed', ?, ?)
    """, (username, task_id, now, agent, f"Status changed to: {status}"))

    conn.commit()
    conn.close()

    return True


def get_task_log(username: str, task_id: str) -> List[Dict[str, Any]]:
    """Get task history log."""
    init_db(username)
    conn = _connect(username)

    rows = conn.execute("""
        SELECT * FROM task_log WHERE username = ? AND task_id = ? ORDER BY timestamp DESC
    """, (username, task_id)).fetchall()

    conn.close()

    return [dict(row) for row in rows]


def delete_task(username: str, task_id: str) -> bool:
    """
    Delete a task (for cleanup only).

    Returns:
        True if deleted, False if not found
    """
    init_db(username)
    conn = _connect(username)

    cursor = conn.execute("DELETE FROM tasks WHERE username = ? AND task_id = ?", (username, task_id))
    deleted = cursor.rowcount > 0

    if deleted:
        conn.execute("DELETE FROM task_log WHERE username = ? AND task_id = ?", (username, task_id))

    conn.commit()
    conn.close()

    return deleted


def get_stats(username: str, agent: Optional[str] = None) -> Dict[str, Any]:
    """
    Get task statistics.

    Returns:
        {
            "total": int,
            "pending": int,
            "in_progress": int,
            "completed": int,
            "failed": int
        }
    """
    init_db(username)
    conn = _connect(username)

    query_base = "SELECT status, COUNT(*) as count FROM tasks WHERE username = ?"
    params = [username]

    if agent:
        query_base += " AND agent = ?"
        params.append(agent)

    query = query_base + " GROUP BY status"

    rows = conn.execute(query, params).fetchall()

    stats = {
        "total": 0,
        "pending": 0,
        "in_progress": 0,
        "completed": 0,
        "failed": 0
    }

    for row in rows:
        status = row['status']
        count = row['count']
        if status in stats:
            stats[status] = count
        stats["total"] += count

    conn.close()

    return stats

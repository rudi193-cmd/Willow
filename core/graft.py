"""
Kart Task Management System

SQLite-backed task storage for Kart orchestration.
Mimics Claude Code's TaskList functionality.

GOVERNANCE: Task operations logged and auditable
AUTHOR: Kart Orchestration System
VERSION: 1.0
CHECKSUM: ΔΣ=42
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any

# Database path per user
def _db_path(username: str) -> Path:
    """Get path to user's graft database."""
    base = Path.cwd() / "artifacts" / username
    base.mkdir(parents=True, exist_ok=True)
    return base / "graft.db"


def _connect(username: str) -> sqlite3.Connection:
    """Open connection to graft database."""
    path = _db_path(username)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_db(username: str):
    """Initialize graft database schema."""
    conn = _connect(username)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT UNIQUE NOT NULL,
            subject TEXT NOT NULL,
            description TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            agent TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            completed_at TEXT,
            metadata TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
        CREATE INDEX IF NOT EXISTS idx_tasks_agent ON tasks(agent);
        CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created_at);

        CREATE TABLE IF NOT EXISTS task_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            action TEXT NOT NULL,
            agent TEXT NOT NULL,
            details TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_log_task ON task_log(task_id);
    """)
    conn.commit()
    conn.close()


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
    cursor = conn.execute("SELECT COUNT(*) FROM tasks")
    count = cursor.fetchone()[0]
    task_id = f"task-{count + 1:03d}"

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Insert task
    conn.execute("""
        INSERT INTO tasks (task_id, subject, description, status, agent, created_at, updated_at, metadata)
        VALUES (?, ?, ?, 'pending', ?, ?, ?, ?)
    """, (task_id, subject, description, agent, now, now, json.dumps(metadata) if metadata else None))

    # Log creation
    conn.execute("""
        INSERT INTO task_log (task_id, timestamp, action, agent, details)
        VALUES (?, ?, 'created', ?, ?)
    """, (task_id, now, agent, f"Created task: {subject}"))

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

    row = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
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

    query = "SELECT * FROM tasks"
    params = []

    filters = []
    if agent:
        filters.append("agent = ?")
        params.append(agent)
    if status:
        filters.append("status = ?")
        params.append(status)

    if filters:
        query += " WHERE " + " AND ".join(filters)

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
    row = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
    if not row:
        conn.close()
        return False

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Update task
    if status == 'completed':
        conn.execute("""
            UPDATE tasks
            SET status = ?, updated_at = ?, completed_at = ?, metadata = ?
            WHERE task_id = ?
        """, (status, now, now, json.dumps(metadata) if metadata else row['metadata'], task_id))
    else:
        conn.execute("""
            UPDATE tasks
            SET status = ?, updated_at = ?, metadata = ?
            WHERE task_id = ?
        """, (status, now, json.dumps(metadata) if metadata else row['metadata'], task_id))

    # Log update
    conn.execute("""
        INSERT INTO task_log (task_id, timestamp, action, agent, details)
        VALUES (?, ?, 'status_changed', ?, ?)
    """, (task_id, now, agent, f"Status changed to: {status}"))

    conn.commit()
    conn.close()

    return True


def get_task_log(username: str, task_id: str) -> List[Dict[str, Any]]:
    """Get task history log."""
    init_db(username)
    conn = _connect(username)

    rows = conn.execute("""
        SELECT * FROM task_log WHERE task_id = ? ORDER BY timestamp DESC
    """, (task_id,)).fetchall()

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

    cursor = conn.execute("DELETE FROM tasks WHERE task_id = ?", (task_id,))
    deleted = cursor.rowcount > 0

    if deleted:
        # Also delete log entries
        conn.execute("DELETE FROM task_log WHERE task_id = ?", (task_id,))

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

    query_base = "SELECT status, COUNT(*) as count FROM tasks"
    params = []

    if agent:
        query_base += " WHERE agent = ?"
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

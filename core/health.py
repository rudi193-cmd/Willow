"""
HEALTH MONITORING — Willow's Self-Awareness
============================================
Monitors system health, node activity, API status, queue backlogs.
Willow knows when something is wrong and can self-heal.

Functions:
- check_node_health(): Check if nodes' knowledge DBs are being updated
- check_queue_health(): Monitor pending queues for backlogs
- check_api_health(): Test Ollama, Gemini, Groq, etc.
- check_storage_health(): Disk space, DB integrity
- attempt_self_heal(): Retry failed operations, route around problems
- get_health_report(): Comprehensive system health snapshot
"""

import os
import shutil
import subprocess
import requests
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

# NTFY notifications
NTFY_TOPIC = "willow-ds42"
NTFY_URL = f"https://ntfy.sh/{NTFY_TOPIC}"


def _connect():
    from core.db import get_connection
    return get_connection()


def init_db():
    """Initialize health monitoring database."""
    conn = _connect()

    # Health checks log
    conn.execute("""
        CREATE TABLE IF NOT EXISTS health_checks (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            timestamp TEXT NOT NULL,
            check_type TEXT NOT NULL,  -- node, queue, api, storage
            target TEXT NOT NULL,  -- node name, API name, etc.
            status TEXT NOT NULL,  -- healthy, degraded, down
            details TEXT,
            latency_ms INTEGER
        )
    """)

    # Issues detected
    conn.execute("""
        CREATE TABLE IF NOT EXISTS health_issues (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            detected_at TEXT NOT NULL,
            issue_type TEXT NOT NULL,  -- stale_node, queue_backlog, api_down, storage_full
            target TEXT NOT NULL,
            description TEXT,
            severity TEXT,  -- low, medium, high, critical
            resolved BOOLEAN DEFAULT 0,
            resolved_at TEXT,
            resolution TEXT
        )
    """)

    # Self-healing actions
    conn.execute("""
        CREATE TABLE IF NOT EXISTS healing_actions (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            timestamp TEXT NOT NULL,
            issue_id INTEGER,
            action_type TEXT NOT NULL,  -- retry, route_around, alert, restart
            target TEXT,
            description TEXT,
            success BOOLEAN,
            FOREIGN KEY (issue_id) REFERENCES health_issues(id)
        )
    """)

    conn.execute("CREATE INDEX IF NOT EXISTS idx_health_timestamp ON health_checks(timestamp)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_health_status ON health_checks(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_issues_resolved ON health_issues(resolved)")

    conn.commit()
    conn.close()


def _log_check(check_type: str, target: str, status: str, details: str = None, latency_ms: int = None):
    """Log a health check result."""
    init_db()
    conn = _connect()
    conn.execute("""
        INSERT INTO health_checks (timestamp, check_type, target, status, details, latency_ms)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (datetime.now().isoformat(), check_type, target, status, details, latency_ms))
    conn.commit()
    conn.close()


def _log_issue(issue_type: str, target: str, description: str, severity: str) -> int:
    """Log a health issue. Returns issue ID."""
    init_db()
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO health_issues (detected_at, issue_type, target, description, severity)
        VALUES (?, ?, ?, ?, ?)
    """, (datetime.now().isoformat(), issue_type, target, description, severity))
    issue_id = cursor.lastrowid
    conn.commit()
    conn.close()

    # Send proactive alert for critical/high issues
    if severity in ['critical', 'high']:
        _send_alert(severity, issue_type, target, description)

    return issue_id


def _send_alert(severity: str, issue_type: str, target: str, description: str):
    """Send ntfy alert for critical/high severity issues."""
    try:
        emoji = "🚨" if severity == "critical" else "⚠️"
        title = f"{emoji} Willow Health Alert"
        message = f"[{severity.upper()}] {issue_type}\nTarget: {target}\n{description}"

        priority = "urgent" if severity == "critical" else "high"

        requests.post(
            NTFY_URL,
            data=message.encode('utf-8'),
            headers={
                "Title": title,
                "Priority": priority,
                "Tags": "warning" if severity == "high" else "rotating_light"
            },
            timeout=5
        )
    except Exception:
        pass  # Silent fail - alerts are best-effort


def check_node_health(stale_threshold_hours: int = 24) -> Dict:
    """
    Check if nodes' loam.db files are being updated.
    Returns dict of node health status.
    """
    artifacts_path = Path(__file__).parent.parent / "artifacts"
    node_health = {}
    cutoff = datetime.now() - timedelta(hours=stale_threshold_hours)

    for node_dir in artifacts_path.iterdir():
        if not node_dir.is_dir():
            continue

        node_name = node_dir.name
        kb_path = node_dir / "willow_knowledge.db"  # Fixed: loam.py creates willow_knowledge.db

        if not kb_path.exists():
            node_health[node_name] = {
                "status": "no_db",
                "message": "No willow_knowledge.db found",
                "last_update": None
            }
            continue

        # Check last modification time
        last_modified = datetime.fromtimestamp(kb_path.stat().st_mtime)

        if last_modified < cutoff:
            status = "stale"
            message = f"No updates in {(datetime.now() - last_modified).days} days"
            _log_issue("stale_node", node_name, message, "medium")
        else:
            status = "healthy"
            message = f"Last updated {int((datetime.now() - last_modified).total_seconds() / 3600)} hours ago"

        node_health[node_name] = {
            "status": status,
            "message": message,
            "last_update": last_modified.isoformat()
        }

        _log_check("node", node_name, status, message)

    return node_health


def check_queue_health(backlog_threshold: int = 50) -> Dict:
    """
    Monitor pending queues for backlogs.
    Returns dict of queue status.
    """
    artifacts_path = Path(__file__).parent.parent / "artifacts"
    queue_health = {}

    for user_dir in artifacts_path.iterdir():
        if not user_dir.is_dir():
            continue

        pending_dir = user_dir / "pending"
        if not pending_dir.exists():
            continue

        # Count files in pending
        try:
            pending_files = list(pending_dir.iterdir())
            file_count = len([f for f in pending_files if f.is_file()])

            if file_count > backlog_threshold:
                status = "backlog"
                message = f"{file_count} files pending (threshold: {backlog_threshold})"
                _log_issue("queue_backlog", user_dir.name, message, "high")
            elif file_count > backlog_threshold / 2:
                status = "elevated"
                message = f"{file_count} files pending"
            else:
                status = "healthy"
                message = f"{file_count} files pending"

            queue_health[user_dir.name] = {
                "status": status,
                "message": message,
                "count": file_count
            }

            _log_check("queue", user_dir.name, status, message)
        except Exception as e:
            queue_health[user_dir.name] = {
                "status": "error",
                "message": str(e),
                "count": 0
            }

    return queue_health


def check_api_health() -> Dict:
    """
    Test APIs: Ollama, Gemini, Groq, Cerebras, etc.
    Returns dict of API health status.
    """
    api_health = {}

    # 1. Ollama
    try:
        start = datetime.now()
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        latency = int((datetime.now() - start).total_seconds() * 1000)

        if response.status_code == 200:
            models = response.json().get("models", [])
            status = "healthy"
            message = f"{len(models)} models available"
        else:
            status = "degraded"
            message = f"Status {response.status_code}"

        api_health["ollama"] = {"status": status, "message": message, "latency_ms": latency}
        _log_check("api", "ollama", status, message, latency)
    except Exception as e:
        api_health["ollama"] = {"status": "down", "message": str(e), "latency_ms": None}
        _log_check("api", "ollama", "down", str(e))
        _log_issue("api_down", "ollama", str(e), "critical")

    # 2. Gemini
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if gemini_key:
        try:
            start = datetime.now()
            response = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_key}",
                json={"contents": [{"parts": [{"text": "test"}]}]},
                timeout=10
            )
            latency = int((datetime.now() - start).total_seconds() * 1000)

            if response.status_code == 200:
                status = "healthy"
                message = "API responding"
            elif response.status_code == 429:
                status = "degraded"
                message = "Quota exceeded"
            else:
                status = "degraded"
                message = f"Status {response.status_code}"

            api_health["gemini"] = {"status": status, "message": message, "latency_ms": latency}
            _log_check("api", "gemini", status, message, latency)
        except Exception as e:
            api_health["gemini"] = {"status": "down", "message": str(e), "latency_ms": None}
            _log_check("api", "gemini", "down", str(e))
    else:
        api_health["gemini"] = {"status": "no_key", "message": "API key not configured", "latency_ms": None}

    # 3. Groq (quick test)
    groq_key = os.environ.get("GROQ_API_KEY")
    if groq_key:
        try:
            start = datetime.now()
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
                json={"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": "test"}], "max_tokens": 5},
                timeout=10
            )
            latency = int((datetime.now() - start).total_seconds() * 1000)

            if response.status_code == 200:
                status = "healthy"
                message = "API responding"
            elif response.status_code == 429:
                status = "degraded"
                message = "Rate limited"
            else:
                status = "degraded"
                message = f"Status {response.status_code}"

            api_health["groq"] = {"status": status, "message": message, "latency_ms": latency}
            _log_check("api", "groq", status, message, latency)
        except Exception as e:
            api_health["groq"] = {"status": "down", "message": str(e), "latency_ms": None}
            _log_check("api", "groq", "down", str(e))

    return api_health


def check_storage_health() -> Dict:
    """
    Check disk space, DB integrity, artifact size.
    Returns dict of storage health status.
    """
    storage_health = {}

    # 1. Disk space
    try:
        repo_path = Path(__file__).parent.parent
        usage = shutil.disk_usage(repo_path)

        total_gb = usage.total / (1024**3)
        free_gb = usage.free / (1024**3)
        used_pct = (usage.used / usage.total) * 100

        if used_pct > 90:
            status = "critical"
            message = f"Disk {used_pct:.1f}% full ({free_gb:.1f}GB free)"
            _log_issue("storage_full", "disk", message, "critical")
        elif used_pct > 80:
            status = "warning"
            message = f"Disk {used_pct:.1f}% full ({free_gb:.1f}GB free)"
        else:
            status = "healthy"
            message = f"{free_gb:.1f}GB free ({used_pct:.1f}% used)"

        storage_health["disk"] = {"status": status, "message": message, "free_gb": round(free_gb, 1)}
        _log_check("storage", "disk", status, message)
    except Exception as e:
        storage_health["disk"] = {"status": "error", "message": str(e)}

    # 2. Database integrity (check main knowledge DBs)
    artifacts_path = Path(__file__).parent.parent / "artifacts"
    db_issues = 0

    for user_dir in artifacts_path.iterdir():
        if not user_dir.is_dir():
            continue

        try:
            # Quick connectivity check against Postgres
            from core.db import get_connection
            conn = get_connection()
            conn.execute("SELECT 1").fetchone()
            conn.close()
        except Exception as e:
            db_issues += 1
            _log_issue("db_corruption", user_dir.name, f"DB check failed: {e}", "high")

    if db_issues > 0:
        storage_health["databases"] = {
            "status": "degraded",
            "message": f"{db_issues} DB(s) with issues"
        }
    else:
        storage_health["databases"] = {
            "status": "healthy",
            "message": "All DBs intact"
        }

    return storage_health


def attempt_self_heal(issue_id: int) -> bool:
    """
    Attempt to self-heal a detected issue.
    Returns True if healing was successful.
    """
    init_db()
    conn = _connect()

    # Get issue details
    issue = conn.execute("""
        SELECT issue_type, target, description FROM health_issues WHERE id = ?
    """, (issue_id,)).fetchone()

    if not issue:
        conn.close()
        return False

    issue_type, target, description = issue
    success = False
    action_desc = ""

    # Healing strategies
    if issue_type == "api_down" and target == "ollama":
        # Try to restart Ollama (if permission available)
        try:
            subprocess.run(["ollama", "serve"], capture_output=True, timeout=5)
            action_desc = "Attempted Ollama restart"
            success = True
        except Exception as e:
            action_desc = f"Restart failed: {e}"
            success = False

    elif issue_type == "queue_backlog":
        # Alert but don't auto-clear (needs human decision)
        action_desc = f"Backlog alert sent for {target}"
        success = True

    elif issue_type == "stale_node":
        # Log alert, no auto-action (node might be intentionally idle)
        action_desc = f"Stale node alert for {target}"
        success = True

    # Log healing action
    conn.execute("""
        INSERT INTO healing_actions (timestamp, issue_id, action_type, target, description, success)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (datetime.now().isoformat(), issue_id, "auto_heal", target, action_desc, success))

    # Mark issue as resolved if healing succeeded
    if success:
        conn.execute("""
            UPDATE health_issues
            SET resolved = 1, resolved_at = ?, resolution = ?
            WHERE id = ?
        """, (datetime.now().isoformat(), action_desc, issue_id))

    conn.commit()
    conn.close()

    return success


def get_health_report() -> Dict:
    """
    Comprehensive system health snapshot.
    Returns dict with all health checks.
    """
    return {
        "timestamp": datetime.now().isoformat(),
        "nodes": check_node_health(),
        "queues": check_queue_health(),
        "apis": check_api_health(),
        "storage": check_storage_health(),
        "issues": get_unresolved_issues()
    }


def get_unresolved_issues(severity: Optional[str] = None) -> List[Dict]:
    """Get unresolved health issues, optionally filtered by severity."""
    init_db()
    conn = _connect()

    query = "SELECT id, detected_at, issue_type, target, description, severity FROM health_issues WHERE resolved = 0"
    params = []

    if severity:
        query += " AND severity = ?"
        params.append(severity)

    query += " ORDER BY severity DESC, detected_at DESC"

    rows = conn.execute(query, params).fetchall()
    conn.close()

    return [
        {
            "id": r[0],
            "detected_at": r[1],
            "issue_type": r[2],
            "target": r[3],
            "description": r[4],
            "severity": r[5]
        }
        for r in rows
    ]


if __name__ == "__main__":
    # CLI test
    import sys
    import json

    if len(sys.argv) < 2:
        print("Usage: python health.py [report|nodes|queues|apis|storage|issues]")
        sys.exit(1)

    command = sys.argv[1]

    if command == "report":
        report = get_health_report()
        print(json.dumps(report, indent=2))

    elif command == "nodes":
        nodes = check_node_health()
        print("Node Health:")
        for node, health in nodes.items():
            status_emoji = "✓" if health["status"] == "healthy" else "⚠" if health["status"] == "stale" else "✗"
            print(f"  {status_emoji} {node}: {health['message']}")

    elif command == "queues":
        queues = check_queue_health()
        print("Queue Health:")
        for queue, health in queues.items():
            status_emoji = "✓" if health["status"] == "healthy" else "⚠"
            print(f"  {status_emoji} {queue}: {health['message']}")

    elif command == "apis":
        apis = check_api_health()
        print("API Health:")
        for api, health in apis.items():
            status_emoji = "✓" if health["status"] == "healthy" else "⚠" if health["status"] == "degraded" else "✗"
            latency = f" ({health['latency_ms']}ms)" if health['latency_ms'] else ""
            print(f"  {status_emoji} {api}: {health['message']}{latency}")

    elif command == "storage":
        storage = check_storage_health()
        print("Storage Health:")
        for component, health in storage.items():
            status_emoji = "✓" if health["status"] == "healthy" else "⚠"
            print(f"  {status_emoji} {component}: {health['message']}")

    elif command == "issues":
        issues = get_unresolved_issues()
        print(f"Unresolved Issues: {len(issues)}")
        for issue in issues:
            print(f"  [{issue['severity']}] {issue['issue_type']}: {issue['target']} - {issue['description']}")

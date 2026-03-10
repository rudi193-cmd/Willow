"""
PATTERN RECOGNITION — Willow's Learning System
===============================================
Tracks routing decisions, learns preferences, detects anomalies.
Willow gets smarter over time by observing what works.

Functions:
- log_routing_decision(): Record what went where and why
- detect_anomalies(): Find unusual patterns (spikes, gaps)
- learn_preferences(): Extract user/system preferences from history
- suggest_rules(): Propose automatic routing rules
- find_connections(): Cross-node pattern detection
"""

import json
import requests
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from collections import Counter, defaultdict

# NTFY notifications
NTFY_TOPIC = "willow-ds42"
NTFY_URL = f"https://ntfy.sh/{NTFY_TOPIC}"


def _connect():
    from core.db import get_connection
    return get_connection()


def init_db():
    """No-op — schema managed by pg_schema.sql."""
    return
    conn = _connect()

    # Routing history - every routing decision
    conn.execute("""
        CREATE TABLE IF NOT EXISTS routing_history (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            timestamp TEXT NOT NULL,
            filename TEXT NOT NULL,
            file_type TEXT,
            content_summary TEXT,
            routed_to TEXT NOT NULL,  -- JSON array of destinations
            reason TEXT,
            confidence REAL,
            user_corrected BOOLEAN DEFAULT 0
        )
    """)

    # Learned preferences - extracted rules
    conn.execute("""
        CREATE TABLE IF NOT EXISTS learned_preferences (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            pattern_type TEXT NOT NULL,  -- file_type_routing, entity_routing, time_pattern
            pattern_value TEXT NOT NULL,
            destination TEXT NOT NULL,
            confidence REAL,
            occurrences INTEGER DEFAULT 1,
            last_seen TEXT,
            user_confirmed BOOLEAN DEFAULT 0
        )
    """)

    # Anomalies - detected unusual patterns
    conn.execute("""
        CREATE TABLE IF NOT EXISTS anomalies (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            detected_at TEXT NOT NULL,
            anomaly_type TEXT NOT NULL,  -- spike, gap, conflict, unusual_routing
            description TEXT,
            affected_nodes TEXT,  -- JSON array
            severity TEXT,  -- low, medium, high
            resolved BOOLEAN DEFAULT 0,
            resolution TEXT
        )
    """)

    # Cross-node connections - patterns across nodes
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cross_node_patterns (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            detected_at TEXT NOT NULL,
            pattern_type TEXT NOT NULL,  -- shared_entity, temporal_cluster, topic_correlation
            nodes_involved TEXT NOT NULL,  -- JSON array
            description TEXT,
            strength REAL,
            examples TEXT  -- JSON array of atom IDs
        )
    """)

    # Provider performance - track LLM provider stats
    conn.execute("""
        CREATE TABLE IF NOT EXISTS provider_performance (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            timestamp TEXT NOT NULL,
            provider TEXT NOT NULL,
            file_type TEXT,
            category TEXT,
            response_time_ms INTEGER,
            success BOOLEAN,
            error_type TEXT
        )
    """)

    conn.execute("CREATE INDEX IF NOT EXISTS idx_routing_timestamp ON routing_history(timestamp)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_routing_destination ON routing_history(routed_to)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_anomaly_type ON anomalies(anomaly_type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_preference_pattern ON learned_preferences(pattern_type, pattern_value)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_provider_perf ON provider_performance(provider, file_type, success)")

    conn.commit()
    conn.close()


def log_routing_decision(
    filename: str,
    file_type: str,
    content_summary: str,
    routed_to: List[str],
    reason: str,
    confidence: float = 1.0
) -> int:
    """
    Log a routing decision for pattern learning.
    Returns routing_history ID.
    """
    init_db()
    conn = _connect()

    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO routing_history (timestamp, filename, file_type, content_summary, routed_to, reason, confidence)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        datetime.now().isoformat(),
        filename,
        file_type,
        content_summary,
        json.dumps(routed_to),
        reason,
        confidence
    ))

    routing_id = cursor.lastrowid
    conn.commit()
    conn.close()

    # After logging, check if we should learn a new preference
    _update_learned_preferences(file_type, routed_to)

    return routing_id


def _update_learned_preferences(file_type: str, destinations: List[str]):
    """Update learned preferences based on routing decision."""
    conn = _connect()

    for dest in destinations:
        # Check if pattern exists
        existing = conn.execute("""
            SELECT id, occurrences FROM learned_preferences
            WHERE pattern_type = 'file_type_routing'
            AND pattern_value = ?
            AND destination = ?
        """, (file_type, dest)).fetchone()

        if existing:
            # Increment occurrences
            conn.execute("""
                UPDATE learned_preferences
                SET occurrences = occurrences + 1,
                    last_seen = ?,
                    confidence = MIN(1.0, occurrences * 0.05)
                WHERE id = ?
            """, (datetime.now().isoformat(), existing[0]))
        else:
            # New pattern
            conn.execute("""
                INSERT INTO learned_preferences (pattern_type, pattern_value, destination, last_seen, confidence)
                VALUES ('file_type_routing', ?, ?, ?, 0.05)
            """, (file_type, dest, datetime.now().isoformat()))

    conn.commit()
    conn.close()


def suggest_destinations_for(
    file_type: str,
    content_summary: Optional[str] = None,
    default_destinations: Optional[List[str]] = None,
    min_confidence: float = 0.5
) -> Dict:
    """
    Suggest routing destinations based on learned preferences.

    Returns dict with:
        destinations: List[str] - where to route
        reason: str - "learned_preference" or "default_heuristic"
        confidence: float - 0.0-1.0
    """
    init_db()
    preferences = get_learned_preferences(min_confidence=min_confidence)

    for pref in preferences:
        if pref["pattern_type"] == "file_type_routing" and pref["pattern_value"] == file_type:
            return {
                "destinations": [pref["destination"]],
                "reason": "learned_preference",
                "confidence": pref["confidence"]
            }

    return {
        "destinations": default_destinations or ["user-profile"],
        "reason": "default_heuristic",
        "confidence": 0.3
    }


def detect_anomalies(lookback_days: int = 7) -> List[Dict]:
    """
    Detect anomalies in routing patterns, node activity, entity mentions.
    Returns list of detected anomalies.
    """
    init_db()
    conn = _connect()
    anomalies = []
    cutoff = (datetime.now() - timedelta(days=lookback_days)).isoformat()

    # 1. Detect routing spikes (destination getting way more files than usual)
    recent_routing = conn.execute("""
        SELECT routed_to FROM routing_history
        WHERE timestamp > ?
    """, (cutoff,)).fetchall()

    destination_counts = Counter()
    for row in recent_routing:
        dests = json.loads(row[0])
        for d in dests:
            destination_counts[d] += 1

    # Compare to historical average
    historical_avg = conn.execute("""
        SELECT routed_to FROM routing_history
        WHERE timestamp < ?
    """, (cutoff,)).fetchall()

    if historical_avg:
        hist_counts = Counter()
        for row in historical_avg:
            dests = json.loads(row[0])
            for d in dests:
                hist_counts[d] += 1

        avg_per_day = {k: v / max(1, lookback_days * 4) for k, v in hist_counts.items()}  # Rough average

        for dest, count in destination_counts.items():
            expected = avg_per_day.get(dest, 1)
            if count > expected * 3:  # 3x spike
                anomalies.append({
                    "type": "routing_spike",
                    "description": f"{dest} receiving {count} files (expected ~{int(expected)})",
                    "affected_nodes": [dest],
                    "severity": "medium"
                })

    # 2. Detect entity mention spikes (using loam.py if available)
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from knowledge import _connect as kb_connect

        # Check recent entity mentions across all user knowledge DBs
        artifacts_path = Path(__file__).parent.parent / "artifacts"
        for user_dir in artifacts_path.iterdir():
            if not user_dir.is_dir():
                continue

            kb_path = user_dir / "loam.db"
            if not kb_path.exists():
                continue

            kb_conn = kb_connect(user_dir.name)

            # Get entity counts from recent vs historical
            recent_entities = kb_conn.execute("""
                SELECT entity_text, COUNT(*) as cnt
                FROM knowledge_entities
                WHERE knowledge_id IN (
                    SELECT id FROM knowledge WHERE created_at > ?
                )
                GROUP BY entity_text
                HAVING cnt > 3
            """, (cutoff,)).fetchall()

            for entity, count in recent_entities:
                # Check historical baseline
                hist = kb_conn.execute("""
                    SELECT COUNT(*) FROM knowledge_entities
                    WHERE entity_text = ?
                    AND knowledge_id IN (
                        SELECT id FROM knowledge WHERE created_at < ?
                    )
                """, (entity, cutoff)).fetchone()[0]

                hist_avg = hist / max(1, lookback_days * 4)
                if count > hist_avg * 4:  # 4x spike
                    anomalies.append({
                        "type": "entity_spike",
                        "description": f"Entity '{entity}' mentioned {count}x recently (usual ~{int(hist_avg)})",
                        "affected_nodes": [user_dir.name],
                        "severity": "low"
                    })

            kb_conn.close()
    except Exception:
        pass  # Knowledge module not available or DB issues

    # 3. Detect gaps (nodes with no recent activity)
    node_activity = defaultdict(int)
    for row in recent_routing:
        dests = json.loads(row[0])
        for d in dests:
            node_activity[d] += 1

    # Check for registered nodes with zero activity
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "die-namic-system" / "bridge_ring"))
        import instance_registry
        active_nodes = [i.instance_id for i in instance_registry.list_instances() if i.active]

        for node in active_nodes:
            if node not in node_activity and node != "willow":  # Willow herself doesn't receive routing
                anomalies.append({
                    "type": "node_gap",
                    "description": f"Node '{node}' received no files in {lookback_days} days",
                    "affected_nodes": [node],
                    "severity": "low"
                })
    except Exception:
        pass

    # Log new anomalies
    for anom in anomalies:
        conn.execute("""
            INSERT INTO anomalies (detected_at, anomaly_type, description, affected_nodes, severity)
            VALUES (?, ?, ?, ?, ?)
        """, (
            datetime.now().isoformat(),
            anom["type"],
            anom["description"],
            json.dumps(anom["affected_nodes"]),
            anom["severity"]
        ))

        # Send alert for high/medium severity anomalies
        if anom["severity"] in ["high", "medium"]:
            _send_anomaly_alert(anom)

    conn.commit()
    conn.close()

    return anomalies


def _send_anomaly_alert(anomaly: Dict):
    """Send ntfy alert for significant anomalies."""
    try:
        emoji = "🔥" if anomaly["severity"] == "high" else "📊"
        title = f"{emoji} Pattern Anomaly Detected"
        message = f"[{anomaly['severity'].upper()}] {anomaly['type']}\n{anomaly['description']}\nNodes: {', '.join(anomaly['affected_nodes'])}"

        priority = "high" if anomaly["severity"] == "high" else "default"

        requests.post(
            NTFY_URL,
            data=message.encode('utf-8'),
            headers={
                "Title": title,
                "Priority": priority,
                "Tags": "chart_with_upwards_trend"
            },
            timeout=5
        )
    except Exception:
        pass  # Silent fail - alerts are best-effort


def get_learned_preferences(min_confidence: float = 0.3) -> List[Dict]:
    """
    Get learned routing preferences that have high confidence.
    Returns list of preference rules.
    """
    init_db()
    conn = _connect()

    rows = conn.execute("""
        SELECT pattern_type, pattern_value, destination, confidence, occurrences, user_confirmed
        FROM learned_preferences
        WHERE confidence >= ?
        ORDER BY confidence DESC, occurrences DESC
    """, (min_confidence,)).fetchall()

    conn.close()

    return [
        {
            "pattern_type": r[0],
            "pattern_value": r[1],
            "destination": r[2],
            "confidence": r[3],
            "occurrences": r[4],
            "user_confirmed": bool(r[5])
        }
        for r in rows
    ]


def suggest_rules() -> List[Dict]:
    """
    Suggest automatic routing rules based on learned patterns.
    Returns list of suggested rules with examples.
    """
    preferences = get_learned_preferences(min_confidence=0.5)
    suggestions = []

    for pref in preferences:
        if pref["user_confirmed"]:
            continue  # Already a rule

        suggestions.append({
            "rule": f"Automatically route {pref['pattern_value']} files to {pref['destination']}",
            "confidence": pref["confidence"],
            "based_on": f"{pref['occurrences']} occurrences",
            "pattern_type": pref["pattern_type"],
            "pattern_value": pref["pattern_value"],
            "destination": pref["destination"]
        })

    return suggestions


def confirm_rule(pattern_type: str, pattern_value: str, destination: str):
    """User confirms a suggested rule - mark as user_confirmed."""
    conn = _connect()
    conn.execute("""
        UPDATE learned_preferences
        SET user_confirmed = 1, confidence = 1.0
        WHERE pattern_type = ? AND pattern_value = ? AND destination = ?
    """, (pattern_type, pattern_value, destination))
    conn.commit()
    conn.close()


def find_cross_node_connections(min_strength: float = 0.5) -> List[Dict]:
    """
    Find patterns that span multiple nodes (same entities, topics, temporal clusters).
    Returns list of cross-node connections.
    """
    init_db()
    conn = _connect()

    # For now, return stored patterns (detection happens in background job)
    rows = conn.execute("""
        SELECT detected_at, pattern_type, nodes_involved, description, strength, examples
        FROM cross_node_patterns
        WHERE strength >= ?
        ORDER BY strength DESC, detected_at DESC
        LIMIT 50
    """, (min_strength,)).fetchall()

    conn.close()

    return [
        {
            "detected_at": r[0],
            "pattern_type": r[1],
            "nodes_involved": json.loads(r[2]),
            "description": r[3],
            "strength": r[4],
            "examples": json.loads(r[5]) if r[5] else []
        }
        for r in rows
    ]


def get_routing_stats(days: int = 30) -> Dict:
    """Get routing statistics for dashboard."""
    init_db()
    conn = _connect()
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()

    # Total routings
    total = conn.execute("SELECT COUNT(*) FROM routing_history WHERE timestamp > ?", (cutoff,)).fetchone()[0]

    # By destination
    by_dest = conn.execute("""
        SELECT routed_to, COUNT(*) as cnt
        FROM routing_history
        WHERE timestamp > ?
        GROUP BY routed_to
        ORDER BY cnt DESC
    """, (cutoff,)).fetchall()

    dest_counts = Counter()
    for routed_json, cnt in by_dest:
        dests = json.loads(routed_json)
        for d in dests:
            dest_counts[d] += cnt

    # By file type
    by_type = conn.execute("""
        SELECT file_type, COUNT(*) as cnt
        FROM routing_history
        WHERE timestamp > ?
        GROUP BY file_type
        ORDER BY cnt DESC
        LIMIT 10
    """, (cutoff,)).fetchall()

    # Recent anomalies
    anomalies = conn.execute("""
        SELECT COUNT(*) FROM anomalies
        WHERE detected_at > ? AND resolved = 0
    """, (cutoff,)).fetchone()[0]

    conn.close()

    return {
        "total_routings": total,
        "by_destination": dict(dest_counts.most_common(10)),
        "by_file_type": dict(by_type),
        "unresolved_anomalies": anomalies,
        "period_days": days
    }


if __name__ == "__main__":
    # CLI test
    import sys

    if len(sys.argv) < 2:
        print("Usage: python patterns.py [stats|anomalies|preferences|suggest]")
        sys.exit(1)

    command = sys.argv[1]

    if command == "stats":
        stats = get_routing_stats()
        print(f"Routing stats (last 30 days):")
        print(f"  Total routings: {stats['total_routings']}")
        print(f"  Unresolved anomalies: {stats['unresolved_anomalies']}")
        print(f"\nTop destinations:")
        for dest, cnt in stats['by_destination'].items():
            print(f"    {dest}: {cnt}")

    elif command == "anomalies":
        anomalies = detect_anomalies()
        print(f"Detected {len(anomalies)} anomalies:")
        for a in anomalies:
            print(f"  [{a['severity']}] {a['type']}: {a['description']}")

    elif command == "preferences":
        prefs = get_learned_preferences()
        print(f"Learned {len(prefs)} preferences:")
        for p in prefs:
            confirmed = " ✓" if p['user_confirmed'] else ""
            print(f"  {p['pattern_value']} -> {p['destination']} (conf: {p['confidence']:.2f}, n={p['occurrences']}){confirmed}")

    elif command == "suggest":
        suggestions = suggest_rules()
        print(f"{len(suggestions)} suggested rules:")
        for s in suggestions:
            print(f"  {s['rule']}")
            print(f"    Confidence: {s['confidence']:.2f} ({s['based_on']})")

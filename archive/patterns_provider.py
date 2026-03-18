"""
Provider Performance Tracking
Tracks which LLM providers perform best for different task types.
"""

import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional


def _connect():
    from core.db import get_connection
    return get_connection()


def log_provider_performance(
    provider: str,
    file_type: Optional[str],
    category: Optional[str],
    response_time_ms: int,
    success: bool,
    error_type: Optional[str] = None
):
    """
    Log provider performance for learning.

    Args:
        provider: Provider name (e.g., "Groq", "Cerebras")
        file_type: File extension (.py, .txt, etc.)
        category: Routing category
        response_time_ms: Response time in milliseconds
        success: Whether request succeeded
        error_type: If failed, what kind of error ("429", "timeout", etc.)
    """
    params = (
        datetime.now().isoformat(),
        provider,
        file_type,
        category,
        response_time_ms,
        success,
        error_type
    )
    sql = """
        INSERT INTO provider_performance
        (timestamp, provider, file_type, category, response_time_ms, success, error_type)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """
    conn = _connect()
    try:
        conn.execute(sql, params)
        conn.commit()
    except Exception:
        # Sequence collision (duplicate key) from aborted transactions.
        # Rollback clears the aborted txn state; retry advances the sequence.
        try:
            conn._conn.rollback()
            conn.execute(sql, params)
            conn.commit()
        except Exception:
            pass
    finally:
        conn.close()


def get_best_provider_for(
    file_type: Optional[str] = None,
    category: Optional[str] = None,
    min_samples: int = 10
) -> Optional[Dict]:
    """
    Get best performing provider for a task type.

    Args:
        file_type: Filter by file type
        category: Filter by category
        min_samples: Minimum samples needed to be considered

    Returns:
        Dict with provider stats or None
    """
    conn = _connect()

    query = """
        SELECT
            provider,
            AVG(response_time_ms) as avg_time,
            SUM(CASE WHEN success THEN 1 ELSE 0 END) * 1.0 / COUNT(*) as success_rate,
            COUNT(*) as sample_size
        FROM provider_performance
        WHERE 1=1
    """
    params = []

    if file_type:
        query += " AND file_type = ?"
        params.append(file_type)
    if category:
        query += " AND category = ?"
        params.append(category)

    query += f"""
        GROUP BY provider
        HAVING COUNT(*) >= {min_samples}
        ORDER BY success_rate DESC, avg_time ASC
        LIMIT 1
    """

    result = conn.execute(query, params).fetchone()
    conn.close()

    if result:
        return {
            "provider": result[0],
            "avg_time_ms": int(result[1]),
            "success_rate": result[2],
            "sample_size": result[3]
        }
    return None


def get_provider_stats(lookback_days: int = 7) -> List[Dict]:
    """
    Get performance stats for all providers.

    Returns list of dicts with provider stats sorted by success rate.
    """
    conn = _connect()

    cutoff = (datetime.now() - timedelta(days=lookback_days)).isoformat()

    results = conn.execute("""
        SELECT
            provider,
            COUNT(*) as total_requests,
            SUM(CASE WHEN success THEN 1 ELSE 0 END) as successful,
            AVG(CASE WHEN success THEN response_time_ms ELSE NULL END) as avg_time,
            SUM(CASE WHEN error_type = '429' THEN 1 ELSE 0 END) as rate_limit_errors
        FROM provider_performance
        WHERE timestamp >= ?
        GROUP BY provider
        ORDER BY successful * 1.0 / total_requests DESC, avg_time ASC
    """, (cutoff,)).fetchall()

    conn.close()

    stats = []
    for row in results:
        success_rate = row[2] / row[1] if row[1] > 0 else 0
        stats.append({
            "provider": row[0],
            "total_requests": row[1],
            "successful": row[2],
            "success_rate": success_rate,
            "avg_time_ms": int(row[3]) if row[3] else 0,
            "rate_limit_errors": row[4]
        })

    return stats


def get_provider_by_file_type(lookback_days: int = 7) -> Dict[str, Dict]:
    """
    Get best provider for each file type.

    Returns dict mapping file_type -> best provider stats.
    """
    conn = _connect()

    cutoff = (datetime.now() - timedelta(days=lookback_days)).isoformat()

    results = conn.execute("""
        SELECT
            file_type,
            provider,
            AVG(response_time_ms) as avg_time,
            SUM(CASE WHEN success THEN 1 ELSE 0 END) * 1.0 / COUNT(*) as success_rate,
            COUNT(*) as samples
        FROM provider_performance
        WHERE timestamp >= ?
          AND file_type IS NOT NULL
          AND success = 1
        GROUP BY file_type, provider
        HAVING samples >= 5
    """, (cutoff,)).fetchall()

    conn.close()

    # Find best provider for each file type
    best_by_type = {}
    for row in results:
        file_type, provider, avg_time, success_rate, samples = row

        if file_type not in best_by_type:
            best_by_type[file_type] = {
                "provider": provider,
                "avg_time_ms": int(avg_time),
                "success_rate": success_rate,
                "samples": samples
            }
        else:
            # Compare: higher success rate wins, then faster time
            current = best_by_type[file_type]
            if success_rate > current["success_rate"] or \
               (success_rate == current["success_rate"] and avg_time < current["avg_time_ms"]):
                best_by_type[file_type] = {
                    "provider": provider,
                    "avg_time_ms": int(avg_time),
                    "success_rate": success_rate,
                    "samples": samples
                }

    return best_by_type


if __name__ == "__main__":
    print("\n=== Provider Performance Stats ===\n")

    stats = get_provider_stats(lookback_days=7)
    if stats:
        print(f"Overall performance (last 7 days):\n")
        for s in stats:
            print(f"  {s['provider']:<20} {s['success_rate']:.1%} success | "
                  f"{s['avg_time_ms']}ms avg | {s['rate_limit_errors']} 429 errors | "
                  f"{s['total_requests']} total")
    else:
        print("  No data yet")

    print(f"\n\nBest provider by file type:\n")
    by_type = get_provider_by_file_type()
    if by_type:
        for ft, data in sorted(by_type.items()):
            print(f"  {ft:<10} → {data['provider']:<15} "
                  f"({data['success_rate']:.1%}, {data['avg_time_ms']}ms, n={data['samples']})")
    else:
        print("  No data yet")

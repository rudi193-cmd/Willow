"""
Provider Health Tracking - Non-Linear Resilience
=================================================
Tracks provider health, auto-blacklists failures, self-heals.

Philosophy: No single point of failure. System adapts to what works.
- Typo in config? Skip that provider, use others.
- Rate limit? Blacklist temporarily, move on.
- Provider down? Mark dead, retry later.
- System keeps working regardless.
"""

import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass

# Health thresholds
BLACKLIST_AFTER_FAILURES = 10  # Consecutive failures before blacklist (raised from 5 — rate limits shouldn't instantly blacklist)
BLACKLIST_DURATION_MINUTES = 3   # How long to blacklist (lowered from 10 — recover faster from rate limit bursts)
HEALTH_CHECK_INTERVAL = 300  # Retry blacklisted providers every 5 min


@dataclass
class ProviderHealth:
    """Health status of a provider."""
    provider: str
    status: str  # healthy, degraded, blacklisted, dead
    consecutive_failures: int
    last_success: Optional[str]
    last_failure: Optional[str]
    blacklisted_until: Optional[str]
    total_requests: int
    total_successes: int
    total_failures: int


def _connect():
    from core.db import get_connection
    return get_connection()


def init_health_db():
    """No-op — schema managed by pg_schema.sql."""
    return
    conn = _connect()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS provider_health (
            provider TEXT PRIMARY KEY,
            status TEXT DEFAULT 'healthy',
            consecutive_failures INTEGER DEFAULT 0,
            last_success TEXT,
            last_failure TEXT,
            blacklisted_until TEXT,
            total_requests INTEGER DEFAULT 0,
            total_successes INTEGER DEFAULT 0,
            total_failures INTEGER DEFAULT 0,
            error_types TEXT,  -- JSON array of recent error types
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS health_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            provider TEXT NOT NULL,
            event_type TEXT NOT NULL,  -- success, failure, blacklist, unblacklist, health_check
            error_code TEXT,
            error_message TEXT,
            response_time_ms INTEGER
        )
    """)

    conn.execute("CREATE INDEX IF NOT EXISTS idx_health_events_provider ON health_events(provider, timestamp)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_health_events_type ON health_events(event_type)")

    conn.commit()
    conn.close()


def record_success(provider: str, response_time_ms: int):
    """Record successful provider response. Fails silently — never crashes the router."""
    try:
        _record_success(provider, response_time_ms)
    except Exception as e:
        import logging
        logging.getLogger("provider_health").warning(f"record_success failed (non-fatal): {e}")

def _record_success(provider: str, response_time_ms: int):
    init_health_db()
    conn = _connect()
    try:
        conn._conn.rollback()  # clear any aborted transaction state
    except Exception:
        pass
    now = datetime.now().isoformat()

    health_sql = """
        INSERT INTO provider_health (provider, status, consecutive_failures, last_success, total_requests, total_successes)
        VALUES (?, 'healthy', 0, ?, 1, 1)
        ON CONFLICT(provider) DO UPDATE SET
            status = 'healthy',
            consecutive_failures = 0,
            last_success = excluded.last_success,
            total_requests = provider_health.total_requests + 1,
            total_successes = provider_health.total_successes + 1,
            blacklisted_until = NULL,
            updated_at = excluded.last_success
    """
    event_sql = """
        INSERT INTO health_events (timestamp, provider, event_type, response_time_ms)
        VALUES (?, ?, 'success', ?)
    """

    try:
        conn.execute(health_sql, (provider, now))
        conn.execute(event_sql, (now, provider, response_time_ms))
        conn.commit()
    except Exception:
        try:
            conn._conn.rollback()
            conn.execute(health_sql, (provider, now))
            conn.execute(event_sql, (now, provider, response_time_ms))
            conn.commit()
        except Exception:
            pass
    finally:
        conn.close()


def record_failure(provider: str, error_code: str, error_message: str):
    """Record provider failure. Fails silently — never crashes the router."""
    try:
        _record_failure(provider, error_code, error_message)
    except Exception as e:
        import logging
        logging.getLogger("provider_health").warning(f"record_failure failed (non-fatal): {e}")

def _record_failure(provider: str, error_code: str, error_message: str):
    """Record provider failure and potentially blacklist."""
    init_health_db()
    conn = _connect()
    try:
        conn._conn.rollback()  # clear any aborted transaction state from pool
    except Exception:
        pass
    now = datetime.now().isoformat()

    try:
        # Get current failure count
        row = conn.execute("SELECT consecutive_failures FROM provider_health WHERE provider = ?", (provider,)).fetchone()
        current_failures = row[0] if row else 0

        # 429 rate limits are not real failures — provider is healthy, just throttled.
        is_rate_limit = error_code == "429"
        new_failures = current_failures if is_rate_limit else current_failures + 1

        # Determine new status
        if new_failures >= BLACKLIST_AFTER_FAILURES:
            status = 'blacklisted'
            blacklist_until = (datetime.now() + timedelta(minutes=BLACKLIST_DURATION_MINUTES)).isoformat()
        elif new_failures >= 3:
            status = 'degraded'
            blacklist_until = None
        else:
            status = 'healthy'
            blacklist_until = None

        health_sql = """
            INSERT INTO provider_health (provider, status, consecutive_failures, last_failure, blacklisted_until, total_requests, total_failures)
            VALUES (?, ?, ?, ?, ?, 1, 1)
            ON CONFLICT(provider) DO UPDATE SET
                status = excluded.status,
                consecutive_failures = excluded.consecutive_failures,
                last_failure = excluded.last_failure,
                blacklisted_until = excluded.blacklisted_until,
                total_requests = provider_health.total_requests + 1,
                total_failures = provider_health.total_failures + 1,
                updated_at = excluded.last_failure
        """
        event_type = 'blacklist' if status == 'blacklisted' else 'failure'
        event_sql = """
            INSERT INTO health_events (timestamp, provider, event_type, error_code, error_message)
            VALUES (?, ?, ?, ?, ?)
        """

        try:
            conn.execute(health_sql, (provider, status, new_failures, now, blacklist_until))
            conn.execute(event_sql, (now, provider, event_type, error_code, error_message))
            conn.commit()
        except Exception:
            try:
                conn._conn.rollback()
                conn.execute(health_sql, (provider, status, new_failures, now, blacklist_until))
                conn.execute(event_sql, (now, provider, event_type, error_code, error_message))
                conn.commit()
            except Exception:
                pass
    finally:
        conn.close()

    return status


def get_recent_success_rates(window_hours: int = 6) -> Dict[str, dict]:
    """
    Get success rates from recent health_events only — not lifetime totals.
    This is the fix for the ratchet bug: providers that failed early are never
    forgiven because total_successes/total_requests never recovers.

    Returns {provider_name: {success_rate, recent_requests, recent_successes}}.
    Providers with no recent data get benefit of the doubt.
    """
    init_health_db()
    conn = _connect()
    cutoff = (datetime.now() - timedelta(hours=window_hours)).isoformat()

    import psycopg2.extras
    cur = conn._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT provider,
               count(*) as recent_requests,
               count(*) FILTER (WHERE event_type = 'success') as recent_successes
        FROM health_events
        WHERE timestamp > %s
        AND event_type IN ('success', 'failure')
        GROUP BY provider
    """, (cutoff,))

    rates = {}
    for row in cur.fetchall():
        reqs = row['recent_requests']
        succs = row['recent_successes']
        rates[row['provider']] = {
            'success_rate': succs / reqs if reqs > 0 else 0.5,
            'recent_requests': reqs,
            'recent_successes': succs,
        }

    cur.close()
    conn.close()
    return rates


def get_healthy_providers(all_providers: List[str]) -> List[str]:
    """
    Get list of healthy providers (not blacklisted).
    Auto-unblacklist if blacklist period expired.
    """
    init_health_db()
    conn = _connect()
    now = datetime.now().isoformat()

    # Unblacklist expired blacklists
    conn.execute("""
        UPDATE provider_health
        SET status = 'healthy', blacklisted_until = NULL, consecutive_failures = 0
        WHERE status = 'blacklisted' AND blacklisted_until < ?
    """, (now,))
    conn.commit()

    # Get non-blacklisted providers
    blacklisted = set()
    for row in conn.execute("SELECT provider FROM provider_health WHERE status = 'blacklisted'"):
        blacklisted.add(row[0])

    conn.close()

    # Return only healthy providers
    healthy = [p for p in all_providers if p not in blacklisted]
    return healthy


def get_provider_health(provider: str) -> Optional[ProviderHealth]:
    """Get health status for a specific provider."""
    init_health_db()
    conn = _connect()
    import psycopg2.extras
    cur = conn._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM provider_health WHERE provider = %s", (provider,))
    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row:
        return None

    return ProviderHealth(
        provider=row['provider'],
        status=row['status'],
        consecutive_failures=row['consecutive_failures'],
        last_success=row['last_success'],
        last_failure=row['last_failure'],
        blacklisted_until=row['blacklisted_until'],
        total_requests=row['total_requests'],
        total_successes=row['total_successes'],
        total_failures=row['total_failures']
    )


def get_all_health_status() -> Dict[str, ProviderHealth]:
    """Get health status for all providers."""
    init_health_db()
    conn = _connect()
    import psycopg2.extras
    cur = conn._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM provider_health")

    health = {}
    for row in cur.fetchall():
        health[row['provider']] = ProviderHealth(
            provider=row['provider'],
            status=row['status'],
            consecutive_failures=row['consecutive_failures'],
            last_success=row['last_success'],
            last_failure=row['last_failure'],
            blacklisted_until=row['blacklisted_until'],
            total_requests=row['total_requests'],
            total_successes=row['total_successes'],
            total_failures=row['total_failures']
        )

    cur.close()
    conn.close()
    return health


def print_health_dashboard():
    """Print provider health dashboard."""
    health = get_all_health_status()

    if not health:
        print("No provider health data yet.")
        return

    print("\n" + "=" * 70)
    print("PROVIDER HEALTH DASHBOARD")
    print("=" * 70)

    for provider, h in sorted(health.items()):
        status_icon = {
            'healthy': '[OK]',
            'degraded': '[!]',
            'blacklisted': '[X]',
            'dead': '[DEAD]'
        }.get(h.status, '[?]')

        success_rate = (h.total_successes / h.total_requests * 100) if h.total_requests > 0 else 0

        print(f"\n{status_icon} {provider:<20} [{h.status.upper()}]")
        print(f"   Success rate: {success_rate:.1f}% ({h.total_successes}/{h.total_requests})")
        print(f"   Consecutive failures: {h.consecutive_failures}")

        if h.blacklisted_until:
            until = datetime.fromisoformat(h.blacklisted_until)
            remaining = (until - datetime.now()).total_seconds() / 60
            if remaining > 0:
                print(f"   Blacklisted for: {remaining:.1f} more minutes")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    print_health_dashboard()

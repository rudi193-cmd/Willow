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

import sqlite3
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass

# Storage
BASE_PATH = Path(__file__).parent.parent / "artifacts" / "willow"
BASE_PATH.mkdir(parents=True, exist_ok=True)
HEALTH_DB = BASE_PATH / "provider_health.db"

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
    """Connect to health database."""
    conn = sqlite3.connect(HEALTH_DB, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_health_db():
    """Initialize provider health tracking."""
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
    """Record successful provider response."""
    init_health_db()
    conn = _connect()
    now = datetime.now().isoformat()

    # Update health status
    conn.execute("""
        INSERT INTO provider_health (provider, status, consecutive_failures, last_success, total_requests, total_successes)
        VALUES (?, 'healthy', 0, ?, 1, 1)
        ON CONFLICT(provider) DO UPDATE SET
            status = 'healthy',
            consecutive_failures = 0,
            last_success = excluded.last_success,
            total_requests = total_requests + 1,
            total_successes = total_successes + 1,
            blacklisted_until = NULL,
            updated_at = excluded.last_success
    """, (provider, now))

    # Log event
    conn.execute("""
        INSERT INTO health_events (timestamp, provider, event_type, response_time_ms)
        VALUES (?, ?, 'success', ?)
    """, (now, provider, response_time_ms))

    conn.commit()
    conn.close()


def record_failure(provider: str, error_code: str, error_message: str):
    """Record provider failure and potentially blacklist."""
    init_health_db()
    conn = _connect()
    now = datetime.now().isoformat()

    # Get current failure count
    row = conn.execute("SELECT consecutive_failures FROM provider_health WHERE provider = ?", (provider,)).fetchone()
    current_failures = row[0] if row else 0

    # 429 rate limits are not real failures — provider is healthy, just throttled.
    # Count toward total_failures but don't increment consecutive_failures or trigger blacklist.
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

    # Update health
    conn.execute("""
        INSERT INTO provider_health (provider, status, consecutive_failures, last_failure, blacklisted_until, total_requests, total_failures)
        VALUES (?, ?, ?, ?, ?, 1, 1)
        ON CONFLICT(provider) DO UPDATE SET
            status = excluded.status,
            consecutive_failures = excluded.consecutive_failures,
            last_failure = excluded.last_failure,
            blacklisted_until = excluded.blacklisted_until,
            total_requests = total_requests + 1,
            total_failures = total_failures + 1,
            updated_at = excluded.last_failure
    """, (provider, status, new_failures, now, blacklist_until))

    # Log event
    event_type = 'blacklist' if status == 'blacklisted' else 'failure'
    conn.execute("""
        INSERT INTO health_events (timestamp, provider, event_type, error_code, error_message)
        VALUES (?, ?, ?, ?, ?)
    """, (now, provider, event_type, error_code, error_message))

    conn.commit()
    conn.close()

    return status


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

    row = conn.execute("SELECT * FROM provider_health WHERE provider = ?", (provider,)).fetchone()
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

    health = {}
    for row in conn.execute("SELECT * FROM provider_health"):
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

"""
COST_TRACKER.PY - Track LLM API usage and costs
=================================================
Logs every LLM call, tracks spend by provider/day/task.

Usage:
    python tools/cost_tracker.py                    # Show today's usage
    python tools/cost_tracker.py --week             # Last 7 days
    python tools/cost_tracker.py --by-provider      # Group by provider
    python tools/cost_tracker.py --by-task          # Group by task type
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass

from core.db import get_connection

# Provider pricing (per 1M tokens)
PROVIDER_PRICING = {
    # Free tier (cloud free or local)
    "free": {"input": 0.0, "output": 0.0},

    # Anthropic Claude (paid)
    "claude-sonnet-4.5": {"input": 3.0, "output": 15.0},
    "claude-opus-4": {"input": 15.0, "output": 75.0},
    "claude-haiku-4": {"input": 0.8, "output": 4.0},

    # Default fallback for unknown providers
    "unknown": {"input": 0.0, "output": 0.0}
}

def calculate_cost(provider: str, model: str, tokens_in: int, tokens_out: int) -> float:
    """Calculate cost for a provider/model."""
    # Free tier providers
    free_providers = ["OCI", "Ollama", "Groq", "Cerebras", "Google Gemini",
                     "SambaNova", "HuggingFace", "Baseten", "Novita", "Mistral"]

    if any(fp in provider for fp in free_providers):
        return 0.0

    # Claude models
    if "claude" in model.lower() or "anthropic" in provider.lower():
        if "opus" in model.lower():
            pricing = PROVIDER_PRICING["claude-opus-4"]
        elif "haiku" in model.lower():
            pricing = PROVIDER_PRICING["claude-haiku-4"]
        else:  # sonnet default
            pricing = PROVIDER_PRICING["claude-sonnet-4.5"]

        cost_in = (tokens_in / 1_000_000) * pricing["input"]
        cost_out = (tokens_out / 1_000_000) * pricing["output"]
        return cost_in + cost_out

    # Unknown provider - assume free
    return 0.0


@dataclass
class UsageRecord:
    """Single LLM usage record."""
    timestamp: str
    provider: str
    model: str
    task_type: str
    tokens_in: int
    tokens_out: int
    cost: float
    prompt_preview: str


def init_db():
    """Initialize the cost tracking database."""
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS usage (
                id INTEGER PRIMARY KEY,
                timestamp TEXT,
                provider TEXT,
                model TEXT,
                task_type TEXT,
                tokens_in INTEGER,
                tokens_out INTEGER,
                cost REAL,
                prompt_preview TEXT
            )
        """)
        conn.commit()


def log_usage(
    provider: str,
    model: str,
    task_type: str,
    tokens_in: int,
    tokens_out: int,
    cost: float = None,
    prompt: str = ""
):
    """Log a single LLM usage."""
    # Auto-calculate cost if not provided
    if cost is None:
        cost = calculate_cost(provider, model, tokens_in, tokens_out)

    with get_connection() as conn:
        conn.execute("""
            INSERT INTO usage (timestamp, provider, model, task_type, tokens_in, tokens_out, cost, prompt_preview)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().isoformat(),
            provider,
            model,
            task_type,
            tokens_in,
            tokens_out,
            cost,
            prompt[:100] if prompt else ""
        ))
        conn.commit()


def get_usage(days: int = 1, provider: str = None, task_type: str = None):
    """Get usage records for the last N days."""
    since = (datetime.now() - timedelta(days=days)).isoformat()

    query = "SELECT * FROM usage WHERE timestamp > ?"
    params = [since]

    if provider:
        query += " AND provider = ?"
        params.append(provider)
    if task_type:
        query += " AND task_type = ?"
        params.append(task_type)

    query += " ORDER BY timestamp DESC"

    with get_connection() as conn:
        # row_factory handled by db.py
        rows = conn.execute(query, params).fetchall()

    return [dict(r) for r in rows]


def get_summary_by_provider(days: int = 1):
    """Get cost summary grouped by provider."""
    since = (datetime.now() - timedelta(days=days)).isoformat()

    with get_connection() as conn:
        # row_factory handled by db.py
        rows = conn.execute("""
            SELECT
                provider,
                COUNT(*) as calls,
                SUM(tokens_in) as total_tokens_in,
                SUM(tokens_out) as total_tokens_out,
                SUM(cost) as total_cost
            FROM usage
            WHERE timestamp > ?
            GROUP BY provider
            ORDER BY total_cost DESC
        """, (since,)).fetchall()

    return [dict(r) for r in rows]


def get_summary_by_task(days: int = 1):
    """Get cost summary grouped by task type."""
    since = (datetime.now() - timedelta(days=days)).isoformat()

    with get_connection() as conn:
        # row_factory handled by db.py
        rows = conn.execute("""
            SELECT
                task_type,
                COUNT(*) as calls,
                SUM(tokens_in) as total_tokens_in,
                SUM(tokens_out) as total_tokens_out,
                SUM(cost) as total_cost
            FROM usage
            WHERE timestamp > ?
            GROUP BY task_type
            ORDER BY total_cost DESC
        """, (since,)).fetchall()

    return [dict(r) for r in rows]


def get_daily_summary(days: int = 7):
    """Get daily cost summary."""
    since = (datetime.now() - timedelta(days=days)).isoformat()

    with get_connection() as conn:
        # row_factory handled by db.py
        rows = conn.execute("""
            SELECT
                DATE(timestamp) as day,
                COUNT(*) as calls,
                SUM(tokens_in + tokens_out) as total_tokens,
                SUM(cost) as total_cost
            FROM usage
            WHERE timestamp > ?
            GROUP BY DATE(timestamp)
            ORDER BY day DESC
        """, (since,)).fetchall()

    return [dict(r) for r in rows]


def format_cost(cost: float) -> str:
    """Format cost for display."""
    if cost == 0:
        return "FREE"
    elif cost < 0.01:
        return f"${cost:.4f}"
    else:
        return f"${cost:.2f}"


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Track LLM API costs")
    parser.add_argument('--days', '-d', type=int, default=1, help='Days to look back')
    parser.add_argument('--week', '-w', action='store_true', help='Last 7 days')
    parser.add_argument('--month', '-m', action='store_true', help='Last 30 days')
    parser.add_argument('--by-provider', '-p', action='store_true', help='Group by provider')
    parser.add_argument('--by-task', '-t', action='store_true', help='Group by task type')
    parser.add_argument('--daily', action='store_true', help='Show daily breakdown')
    parser.add_argument('--raw', '-r', action='store_true', help='Show raw records')
    args = parser.parse_args()

    # Initialize DB
    init_db()

    # Determine days
    days = args.days
    if args.week:
        days = 7
    elif args.month:
        days = 30

    period = f"Last {days} day(s)" if days > 1 else "Today"
    print(f"\n{'=' * 50}")
    print(f"LLM Cost Tracker - {period}")
    print('=' * 50)

    if args.by_provider:
        summary = get_summary_by_provider(days)
        if not summary:
            print("\nNo usage recorded.")
            return

        print(f"\n{'Provider':<15} {'Calls':>8} {'Tokens':>12} {'Cost':>10}")
        print('-' * 50)

        total_cost = 0
        for row in summary:
            tokens = row['total_tokens_in'] + row['total_tokens_out']
            cost = row['total_cost'] or 0
            total_cost += cost
            print(f"{row['provider']:<15} {row['calls']:>8} {tokens:>12,} {format_cost(cost):>10}")

        print('-' * 50)
        print(f"{'TOTAL':<15} {'':<8} {'':<12} {format_cost(total_cost):>10}")

    elif args.by_task:
        summary = get_summary_by_task(days)
        if not summary:
            print("\nNo usage recorded.")
            return

        print(f"\n{'Task Type':<15} {'Calls':>8} {'Tokens':>12} {'Cost':>10}")
        print('-' * 50)

        total_cost = 0
        for row in summary:
            tokens = row['total_tokens_in'] + row['total_tokens_out']
            cost = row['total_cost'] or 0
            total_cost += cost
            print(f"{row['task_type']:<15} {row['calls']:>8} {tokens:>12,} {format_cost(cost):>10}")

        print('-' * 50)
        print(f"{'TOTAL':<15} {'':<8} {'':<12} {format_cost(total_cost):>10}")

    elif args.daily:
        summary = get_daily_summary(days)
        if not summary:
            print("\nNo usage recorded.")
            return

        print(f"\n{'Date':<12} {'Calls':>8} {'Tokens':>12} {'Cost':>10}")
        print('-' * 50)

        total_cost = 0
        for row in summary:
            cost = row['total_cost'] or 0
            total_cost += cost
            print(f"{row['day']:<12} {row['calls']:>8} {row['total_tokens']:>12,} {format_cost(cost):>10}")

        print('-' * 50)
        print(f"{'TOTAL':<12} {'':<8} {'':<12} {format_cost(total_cost):>10}")

    elif args.raw:
        records = get_usage(days)
        if not records:
            print("\nNo usage recorded.")
            return

        for r in records[:20]:
            ts = r['timestamp'][:19]
            print(f"\n{ts} | {r['provider']} | {r['model']}")
            print(f"  {r['task_type']} | {r['tokens_in']}+{r['tokens_out']} tokens | {format_cost(r['cost'])}")
            if r['prompt_preview']:
                print(f"  \"{r['prompt_preview'][:60]}...\"")

    else:
        # Default: show summary
        by_provider = get_summary_by_provider(days)

        if not by_provider:
            print("\nNo usage recorded yet.")
            print("\nUsage will be logged automatically when using llm_router.")
            return

        total_calls = sum(r['calls'] for r in by_provider)
        total_tokens = sum((r['total_tokens_in'] or 0) + (r['total_tokens_out'] or 0) for r in by_provider)
        total_cost = sum(r['total_cost'] or 0 for r in by_provider)
        free_calls = sum(r['calls'] for r in by_provider if (r['total_cost'] or 0) == 0)

        print(f"\nTotal calls:     {total_calls:,}")
        print(f"Total tokens:    {total_tokens:,}")
        print(f"Free calls:      {free_calls:,} ({100*free_calls/total_calls:.0f}%)" if total_calls else "")
        print(f"Total cost:      {format_cost(total_cost)}")

        print("\nBy provider:")
        for r in by_provider:
            cost = r['total_cost'] or 0
            status = "FREE" if cost == 0 else format_cost(cost)
            print(f"  {r['provider']:<12} {r['calls']:>5} calls  {status}")


if __name__ == "__main__":
    main()

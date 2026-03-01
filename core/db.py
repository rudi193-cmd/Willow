"""
db.py -- Database connection abstraction for Willow.

Reads WILLOW_DB_URL environment variable:
  sqlite:///path     -> SQLite (default, current behaviour)
  postgresql://...   -> PostgreSQL (enterprise)

All code should call get_connection() instead of sqlite3.connect() directly.
Auxiliary databases (health, patterns, costs) are exempt -- they always use SQLite.
"""
import os
import sqlite3
from pathlib import Path

# Single source of truth for the main knowledge DB path
_DEFAULT_SQLITE = r"C:\Users\Sean\Documents\GitHub\Willow\artifacts\Sweet-Pea-Rudi19\willow_knowledge.db"
DB_PATH = os.getenv("WILLOW_DB_PATH", _DEFAULT_SQLITE)
DATABASE_URL = os.getenv("WILLOW_DB_URL", f"sqlite:///{DB_PATH}")


def get_connection(path: str = None):
    """Return a DB connection. path overrides default for per-user DBs."""
    url = DATABASE_URL if path is None else f"sqlite:///{path}"
    if url.startswith("sqlite"):
        db = url.replace("sqlite:///", "")
        conn = sqlite3.connect(db, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn
    elif url.startswith("postgresql") or url.startswith("postgres"):
        try:
            import psycopg2
            return psycopg2.connect(url)
        except ImportError:
            raise RuntimeError(
                "psycopg2 not installed. Run: pip install psycopg2-binary"
            )
    else:
        raise ValueError(f"Unsupported WILLOW_DB_URL scheme: {url}")

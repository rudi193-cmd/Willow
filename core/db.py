"""
db.py -- Database connection abstraction for Willow.

PostgreSQL uses a ThreadedConnectionPool (min=2, max=20) to eliminate the
single-writer bottleneck that caused recurring 'database is locked' errors.
Reads WILLOW_DB_URL: sqlite:///path (dev) or postgresql://... (production).
All code should call get_connection() instead of sqlite3.connect() directly.
Auxiliary databases (health, patterns, costs) are exempt -- always SQLite.
"""
import os
import sqlite3
import threading

_DEFAULT_SQLITE = r"C:\Users\Sean\Documents\GitHub\Willow\artifacts\Sweet-Pea-Rudi19\willow_knowledge.db"
DB_PATH         = os.getenv("WILLOW_DB_PATH", _DEFAULT_SQLITE)
DATABASE_URL    = os.getenv("WILLOW_DB_URL", f"sqlite:///{DB_PATH}")
WILLOW_USERNAME = os.getenv("WILLOW_USERNAME", "")  # default schema on PG

_pg_pool      = None
_pg_pool_lock = threading.Lock()


def _get_pg_pool():
    global _pg_pool
    if _pg_pool is not None:
        return _pg_pool
    with _pg_pool_lock:
        if _pg_pool is None:
            try:
                import psycopg2.pool
                _pg_pool = psycopg2.pool.ThreadedConnectionPool(
                    minconn=4, maxconn=50, dsn=DATABASE_URL
                )
            except ImportError:
                raise RuntimeError("psycopg2 not installed. Run: pip install psycopg2-binary")
    return _pg_pool


import re as _re

# Conflict targets for INSERT OR REPLACE upserts
_PG_CONFLICT_TARGETS = {
    "willow_state": "(key) DO UPDATE SET value=EXCLUDED.value, set_at=EXCLUDED.set_at",
    "agents":       "(name) DO UPDATE SET display_name=EXCLUDED.display_name, "
                    "trust_level=EXCLUDED.trust_level, agent_type=EXCLUDED.agent_type, "
                    "profile_path=EXCLUDED.profile_path, registered_at=EXCLUDED.registered_at, "
                    "last_seen=EXCLUDED.last_seen",
}


def _sqlite_to_pg(sql: str) -> str:
    """Translate SQLite SQL syntax to PostgreSQL."""
    s = sql.strip()
    if _re.match(r"\s*PRAGMA\b", s, _re.IGNORECASE):
        return "SELECT 1"
    if _re.search(r"\bINSERT\s+OR\s+IGNORE\b", s, _re.IGNORECASE):
        s = _re.sub(r"\bINSERT\s+OR\s+IGNORE\b", "INSERT", s, flags=_re.IGNORECASE)
        s = s.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
    elif _re.search(r"\bINSERT\s+OR\s+REPLACE\b", s, _re.IGNORECASE):
        s = _re.sub(r"\bINSERT\s+OR\s+REPLACE\b", "INSERT", s, flags=_re.IGNORECASE)
        m = _re.search(r"\bINSERT\s+INTO\s+[\"\']?(\w+)", s, _re.IGNORECASE)
        table = m.group(1).lower() if m else ""
        conflict = _PG_CONFLICT_TARGETS.get(table, "DO NOTHING")
        s = s.rstrip().rstrip(";") + f" ON CONFLICT {conflict}"
    # Escape literal % (e.g. in LIKE patterns) before converting ? -> %s.
    # Otherwise psycopg2 interprets %.% as a format specifier, consuming params.
    s = s.replace("%", "%%")
    s = s.replace("?", "%s")
    return s


class _PgCursor:
    """Wraps psycopg2 cursor to provide sqlite3-compatible interface."""
    def __init__(self, cur):
        self._cur = cur
        self.description = cur.description
        self.rowcount    = cur.rowcount
        self.lastrowid   = None

    def __getattr__(self, name):
        return getattr(self._cur, name)

    def execute(self, sql, params=None):
        pg_sql = _sqlite_to_pg(sql)
        self._cur.execute(pg_sql, params)
        self.description = self._cur.description
        self.rowcount    = self._cur.rowcount
        self.lastrowid   = self._cur.lastrowid if hasattr(self._cur, "lastrowid") else None
        return self

    def executemany(self, sql, seq):
        import psycopg2.extras
        pg_sql = _sqlite_to_pg(sql)
        psycopg2.extras.execute_batch(self._cur, pg_sql, seq)

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    def fetchmany(self, n):
        return self._cur.fetchmany(n)

    def __iter__(self):
        return iter(self._cur)


class _PgConn:
    """Wraps a pooled psycopg2 connection with sqlite3-compatible interface."""
    def __init__(self, pool, conn):
        self._pool = pool
        self._conn = conn
        self._row_factory = None

    def __getattr__(self, name):
        return getattr(self._conn, name)

    # sqlite3 compatibility
    def cursor(self):
        import sqlite3 as _sqlite3
        if self._row_factory is _sqlite3.Row:
            import psycopg2.extras
            return _PgCursor(self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor))
        return _PgCursor(self._conn.cursor())

    def execute(self, sql, params=None):
        cur = self.cursor()
        cur.execute(sql, params)
        return cur

    @property
    def row_factory(self):
        return self._row_factory

    @row_factory.setter
    def row_factory(self, value):
        self._row_factory = value  # stored; cursor() uses RealDictCursor when sqlite3.Row

    def close(self):
        try:
            self._conn.rollback()
        except Exception:
            pass
        self._pool.putconn(self._conn)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, *_):
        try:
            self._conn.rollback()  # always clean — committed txns are no-ops, aborted ones get cleared
        except Exception:
            pass
        self._pool.putconn(self._conn)


def _safe_schema_name(name: str) -> str:
    """Convert a username to a safe PostgreSQL schema name (lowercase, underscores)."""
    import re as _re2
    s = _re2.sub(r"[^a-z0-9]", "_", name.lower())
    return s[:63]


def get_connection(path: str = None, schema: str = None):
    """Return a DB connection. path overrides default for per-user DBs (SQLite only).
    schema: if set and PostgreSQL, SET search_path = {schema}, public after connecting."""
    url = DATABASE_URL if path is None else f"sqlite:///{path}"
    if url.startswith("sqlite"):
        db   = url.replace("sqlite:///", "")
        conn = sqlite3.connect(db, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn
    elif url.startswith("postgresql") or url.startswith("postgres"):
        pool = _get_pg_pool()
        conn = pool.getconn()
        try:
            conn.autocommit = False
            pg_conn = _PgConn(pool, conn)
            _schema = schema or WILLOW_USERNAME
            if _schema:
                safe = _safe_schema_name(_schema)
                _cur = conn.cursor()
                _cur.execute(f"SET search_path = {safe}, public")
                _cur.close()
            return pg_conn
        except Exception:
            pool.putconn(conn)
            raise
    else:
        raise ValueError(f"Unsupported WILLOW_DB_URL scheme: {url}")


def is_postgres() -> bool:
    """True when running against PostgreSQL."""
    return DATABASE_URL.startswith("postgresql") or DATABASE_URL.startswith("postgres")


def init_user_schema(username: str) -> str:
    """Create a PostgreSQL schema for this user if it does not exist.
    Returns the safe schema name. No-op on SQLite (returns safe name only)."""
    safe = _safe_schema_name(username)
    if not is_postgres():
        return safe
    pool = _get_pg_pool()
    conn = pool.getconn()
    try:
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(f"CREATE SCHEMA IF NOT EXISTS {safe}")
        cur.close()
    finally:
        pool.putconn(conn)
    return safe

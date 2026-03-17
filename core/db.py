"""
db.py -- Database connection abstraction for Willow.

PostgreSQL-only. All data lives in Postgres.
Requires WILLOW_DB_URL=postgresql://... in the environment.
All code calls get_connection() — never sqlite3.connect() directly.
"""
import os
import threading

DATABASE_URL    = os.getenv("WILLOW_DB_URL", "")
if not DATABASE_URL:
    raise RuntimeError("WILLOW_DB_URL is not set. Set it to postgresql://user:pass@host:port/db")
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
                    minconn=2, maxconn=20, dsn=DATABASE_URL
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
    "cube_cells":   "(node_id, node_type) DO UPDATE SET cx=EXCLUDED.cx, cy=EXCLUDED.cy, "
                    "cz=EXCLUDED.cz, domain_name=EXCLUDED.domain_name, "
                    "temporal_name=EXCLUDED.temporal_name, indexed_at=EXCLUDED.indexed_at",
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
    # Only translate ? -> %s if the query uses SQLite-style placeholders.
    # If it already uses %s (Postgres-native), leave it alone — escaping % would
    # turn %s into %%s and break psycopg2.
    if "?" in s:
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
        # If INSERT has RETURNING, use that for lastrowid directly
        has_returning = bool(_re.search(r"\bRETURNING\b", pg_sql, _re.IGNORECASE))
        self._cur.execute(pg_sql, params)
        self.description = self._cur.description
        self.rowcount    = self._cur.rowcount
        if has_returning:
            # RETURNING clause present — the result set IS the returned row(s).
            # Don't fetch here; let the caller use fetchone()/fetchall().
            # But peek at cursor description to confirm it returned something.
            self.lastrowid = None
        elif _re.match(r"\s*INSERT\b", pg_sql, _re.IGNORECASE):
            # No RETURNING clause — try lastval() for SERIAL/IDENTITY columns.
            # lastval() fails if no sequence was used in this session, so we
            # use currval-safe check first.
            try:
                self._cur.execute(
                    "SELECT lastval() WHERE EXISTS ("
                    "  SELECT 1 FROM pg_sequences LIMIT 1"
                    ")"
                )
                row = self._cur.fetchone()
                self.lastrowid = row[0] if row else None
            except Exception:
                self.lastrowid = None
        else:
            self.lastrowid = None
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


def is_postgres() -> bool:
    """Return True — this codebase is PostgreSQL-only."""
    return DATABASE_URL.startswith("postgresql")


def get_connection(path: str = None, schema: str = None):
    """Return a pooled Postgres connection.
    path is ignored (kept for call-site compatibility during migration).
    schema: if set, SET search_path = {schema}, public after connecting."""
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


def init_user_schema(username: str) -> str:
    """Create a PostgreSQL schema for this user if it does not exist.
    Returns the safe schema name."""
    safe = _safe_schema_name(username)
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

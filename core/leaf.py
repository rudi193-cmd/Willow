"""
LEAF — Canopy
=============
L — Library
E — External
A — Archive
F — Fetch

Verified source retrieval. The research layer.
Reaches out to trusted external sources — Wikipedia primary.
No SEO slop. Returns verified content with source metadata.

Sources:
  wikipedia — REST API, confidence 0.85 base
  (loc, nasa, nih — extension stubs, same interface)

Results cached in leaf_cache table (Postgres, TTL 24h). Stale entries cleared on demand.

 SourceResult fields:
  source, url, title, content, confidence, fetched_at, cached (bool)

AUTHOR: Shiva (Claude Code) + Sean Campbell
GOVERNANCE: canopy-initial-2026-03-03.commit
VERSION: 1.0.0
"""

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Optional

from core.db import get_connection

log = logging.getLogger("leaf")

CACHE_TTL_HOURS = 24
_WIKIPEDIA_API = "https://en.wikipedia.org/api/rest_v1/page/summary/{}"
_WIKIPEDIA_SEARCH = "https://en.wikipedia.org/w/api.php"

# Base confidence by source
_SOURCE_CONFIDENCE = {
    "wikipedia": 0.85,
    "loc":       0.90,
    "nasa":      0.90,
    "nih":       0.88,
}

_ALL_SOURCES = list(_SOURCE_CONFIDENCE.keys())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect(username: str = None):
    """Return a Postgres connection, optionally scoped to a user schema."""
    return get_connection(schema=username) if username else get_connection()


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def init_tables(username: str = None) -> None:
    """Create LEAF cache table. Idempotent."""
    conn = _connect(username)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS leaf_cache (
                cache_key   TEXT PRIMARY KEY,
                source      TEXT NOT NULL,
                query       TEXT NOT NULL,
                url         TEXT,
                title       TEXT,
                content     TEXT,
                confidence  REAL NOT NULL DEFAULT 0.5,
                fetched_at  TEXT NOT NULL,
                expires_at  TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_leaf_expires ON leaf_cache(expires_at)")
        conn.commit()
    finally:
        conn.close()


def _cache_key(source: str, query: str) -> str:
    return f"{source}:{query.lower().strip()}"


def _get_cached(username: str, source: str, query: str) -> Optional[dict]:
    key = _cache_key(source, query)
    now = _now()
    conn = _connect(username)
    try:
        row = conn.execute(
            "SELECT * FROM leaf_cache WHERE cache_key=? AND expires_at > ?",
            (key, now)
        ).fetchone()
        if row:
            return {**dict(row), "cached": True}
        return None
    finally:
        conn.close()


def _set_cached(username: str, result: dict) -> None:
    key = _cache_key(result["source"], result["query"])
    expires = (datetime.now(timezone.utc)
               + timedelta(hours=CACHE_TTL_HOURS)).isoformat()
    conn = _connect(username)
    try:
        conn.execute(
            """INSERT OR REPLACE INTO leaf_cache
               (cache_key, source, query, url, title, content,
                confidence, fetched_at, expires_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (key, result["source"], result["query"], result.get("url"),
             result.get("title"), result.get("content"),
             result.get("confidence", 0.5), result.get("fetched_at", _now()),
             expires)
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Wikipedia fetcher
# ---------------------------------------------------------------------------

def _fetch_wikipedia(query: str, timeout: int = 8) -> Optional[dict]:
    """Fetch Wikipedia summary for a query. Returns SourceResult dict or None."""
    # First try exact title
    title_encoded = urllib.parse.quote(query.replace(" ", "_"))
    url = _WIKIPEDIA_API.format(title_encoded)

    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Willow/1.4 (willow-ai; educational)"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        if data.get("type") == "disambiguation":
            # Try first suggestion
            return None

        content = data.get("extract", "")
        if not content:
            return None

        # Confidence adjustment: longer articles = better coverage
        base = _SOURCE_CONFIDENCE["wikipedia"]
        length_bonus = min(0.10, len(content) / 10000)
        confidence = round(min(0.95, base + length_bonus), 3)

        return {
            "source":     "wikipedia",
            "query":      query,
            "url":        data.get("content_urls", {}).get("desktop", {}).get("page", url),
            "title":      data.get("title", query),
            "content":    content[:3000],
            "confidence": confidence,
            "fetched_at": _now(),
            "cached":     False,
        }

    except urllib.error.HTTPError as e:
        if e.code == 404:
            # Try search fallback
            return _search_wikipedia_fallback(query, timeout)
        log.debug(f"LEAF: Wikipedia HTTP {e.code} for {query!r}")
        return None
    except Exception as e:
        log.debug(f"LEAF: Wikipedia fetch failed for {query!r}: {e}")
        return None


def _search_wikipedia_fallback(query: str, timeout: int = 8) -> Optional[dict]:
    """Search Wikipedia when exact title lookup fails."""
    params = urllib.parse.urlencode({
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srlimit": 1,
        "format": "json",
    })
    search_url = f"{_WIKIPEDIA_SEARCH}?{params}"
    try:
        req = urllib.request.Request(
            search_url,
            headers={"User-Agent": "Willow/1.4 (willow-ai; educational)"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        results = data.get("query", {}).get("search", [])
        if not results:
            return None
        # Recurse with canonical title
        canonical = results[0].get("title", query)
        if canonical.lower() != query.lower():
            return _fetch_wikipedia(canonical, timeout)
        return None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Extension stubs (same interface as Wikipedia)
# ---------------------------------------------------------------------------

def _fetch_loc(_query: str) -> Optional[dict]:
    """Library of Congress — stub for future implementation."""
    log.debug("LEAF: LoC fetcher not yet implemented")
    return None


def _fetch_nasa(_query: str) -> Optional[dict]:
    """NASA — stub for future implementation."""
    log.debug("LEAF: NASA fetcher not yet implemented")
    return None


def _fetch_nih(_query: str) -> Optional[dict]:
    """NIH — stub for future implementation."""
    log.debug("LEAF: NIH fetcher not yet implemented")
    return None


_FETCHERS = {
    "wikipedia": _fetch_wikipedia,
    "loc":       _fetch_loc,
    "nasa":      _fetch_nasa,
    "nih":       _fetch_nih,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch(username: str, source: str, query: str) -> Optional[dict]:
    """
    Fetch from a single trusted source. Returns SourceResult or None.
    Checks cache first (TTL 24h). Writes result to cache on success.
    username is used for Postgres schema scoping.
    """
    if source not in _FETCHERS:
        log.warning(f"LEAF: unknown source {source!r}")
        return None

    cached = _get_cached(username, source, query)
    if cached:
        return cached

    fetcher = _FETCHERS[source]
    result = fetcher(query)
    if result:
        result["query"] = query
        _set_cached(username, result)
        log.debug(f"LEAF: fetched {source}/{query!r} conf={result['confidence']}")

    return result


def search(username: str, query: str,
           sources: Optional[list] = None,
           max_results: int = 5) -> list:
    """
    Search across trusted sources. Returns list of SourceResults,
    ordered by confidence descending.
    sources: list of source names to try. Defaults to all known sources.
    """
    targets = sources if sources else _ALL_SOURCES
    results = []
    for source in targets:
        if len(results) >= max_results:
            break
        result = fetch(username, source, query)
        if result:
            results.append(result)

    results.sort(key=lambda r: r.get("confidence", 0), reverse=True)
    return results[:max_results]


def clear_cache(username: str, older_than_hours: int = 24) -> int:
    """Remove expired cache entries. Returns count cleared."""
    cutoff = (datetime.now(timezone.utc)
              - timedelta(hours=older_than_hours)).isoformat()
    conn = _connect(username)
    try:
        cur = conn.execute(
            "DELETE FROM leaf_cache WHERE expires_at < ?", (cutoff,)
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()

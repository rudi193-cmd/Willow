"""
Social Media API Routes
========================
Post queue management, series tracking, community stats,
and metrics for r/DispatchesFromReality, r/LLMPhysics, etc.

Endpoints:
  GET  /api/social/dashboard         — status counts + top performers
  GET  /api/social/queue             — manuscript posts with file paths (work queue)
  GET  /api/social/posts             — list posts (filters: status, series_id, community_id)
  GET  /api/social/posts/{id}        — single post + files + latest metrics
  PATCH /api/social/posts/{id}/status — update post status
  GET  /api/social/series            — series with post counts by status
  GET  /api/social/communities       — communities with post counts
  GET  /api/social/metrics           — top performing posts
  POST /api/social/posts             — create new post entry

DS=42
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from core.db import get_connection

router = APIRouter(prefix="/api/social", tags=["social"])

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, PATCH, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
}

_tables_created = False


def _ensure_social_tables(conn):
    global _tables_created
    if _tables_created:
        return
    conn.execute("""
        CREATE TABLE IF NOT EXISTS social_platforms (
            id         SERIAL PRIMARY KEY,
            name       TEXT NOT NULL UNIQUE,
            url        TEXT,
            type       TEXT,
            notes      TEXT,
            created_at TEXT DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS social_accounts (
            id           SERIAL PRIMARY KEY,
            platform_id  INTEGER REFERENCES social_platforms(id),
            handle       TEXT NOT NULL,
            display_name TEXT,
            profile_url  TEXT,
            karma        INTEGER,
            followers    INTEGER,
            bio          TEXT,
            first_seen   TEXT,
            last_updated TEXT DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS social_communities (
            id           SERIAL PRIMARY KEY,
            platform_id  INTEGER REFERENCES social_platforms(id),
            name         TEXT NOT NULL,
            display_name TEXT,
            description  TEXT,
            owner        TEXT,
            topic        TEXT,
            url          TEXT,
            created_at   TEXT DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS social_series (
            id            SERIAL PRIMARY KEY,
            title         TEXT NOT NULL,
            slug          TEXT UNIQUE,
            description   TEXT,
            status        TEXT DEFAULT 'active',
            episode_count INTEGER DEFAULT 0,
            created_at    TEXT DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS social_posts (
            id           SERIAL PRIMARY KEY,
            account_id   INTEGER REFERENCES social_accounts(id),
            community_id INTEGER REFERENCES social_communities(id),
            series_id    INTEGER REFERENCES social_series(id),
            title          TEXT NOT NULL,
            body_snippet   TEXT,
            status         TEXT DEFAULT 'manuscript',
            notes          TEXT,
            series_notes   TEXT,
            draft_path     TEXT,
            posted_at      TEXT,
            url            TEXT,
            is_crosspost   INTEGER DEFAULT 0,
            parent_post_id INTEGER REFERENCES social_posts(id),
            created_at     TEXT DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS')),
            updated_at     TEXT DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS social_post_metrics (
            id            SERIAL PRIMARY KEY,
            post_id       INTEGER REFERENCES social_posts(id),
            snapshot_at   TEXT,
            views_total   INTEGER DEFAULT 0,
            views_48h     INTEGER DEFAULT 0,
            upvotes       INTEGER DEFAULT 0,
            upvote_ratio  REAL,
            comments      INTEGER DEFAULT 0,
            shares        INTEGER DEFAULT 0,
            crossposts    INTEGER DEFAULT 0,
            awards        INTEGER DEFAULT 0,
            rank_today    TEXT,
            geo_us_pct    REAL,
            geo_breakdown TEXT,
            source_file   TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS social_milestones (
            id           SERIAL PRIMARY KEY,
            post_id      INTEGER REFERENCES social_posts(id),
            account_id   INTEGER REFERENCES social_accounts(id),
            milestone    TEXT,
            achieved_at  TEXT,
            metric_value TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS social_knowledge_gaps (
            id          SERIAL PRIMARY KEY,
            context     TEXT,
            context_id  INTEGER,
            field       TEXT NOT NULL,
            description TEXT,
            priority    TEXT DEFAULT 'medium',
            status      TEXT DEFAULT 'open',
            created_at  TEXT DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS'))
        )
    """)
    conn.commit()
    _tables_created = True


def _db():
    conn = get_connection()
    _ensure_social_tables(conn)
    return conn


# ── Models ──────────────────────────────────────────────────────────────────

class StatusUpdate(BaseModel):
    status: str  # manuscript | draft | active | posted

class NewPost(BaseModel):
    title: str
    series_id: Optional[int] = None
    community_id: Optional[int] = None
    account_id: Optional[int] = 1
    status: str = "manuscript"
    notes: Optional[str] = None
    draft_path: Optional[str] = None


# ── Dashboard ────────────────────────────────────────────────────────────────

@router.get("/dashboard")
def dashboard():
    conn = _db()
    try:
        # Status counts
        status_counts = {
            row["status"]: row["n"]
            for row in conn.execute(
                "SELECT status, COUNT(*) as n FROM social_posts GROUP BY status"
            ).fetchall()
        }

        # Top 10 posts by views
        top_posts = [
            dict(row) for row in conn.execute("""
                SELECT p.id, p.title, p.status, p.url,
                       m.views_total, m.upvotes, m.upvote_ratio,
                       m.rank_today, s.title as series, c.name as community
                FROM social_posts p
                LEFT JOIN social_post_metrics m ON m.post_id = p.id
                LEFT JOIN social_series s ON s.id = p.series_id
                LEFT JOIN social_communities c ON c.id = p.community_id
                WHERE m.views_total IS NOT NULL
                ORDER BY m.views_total DESC
                LIMIT 10
            """).fetchall()
        ]

        # Next in queue (first 5 manuscript posts)
        queue_preview = [
            dict(row) for row in conn.execute("""
                SELECT p.id, p.title, s.title as series, c.name as community
                FROM social_posts p
                LEFT JOIN social_series s ON s.id = p.series_id
                LEFT JOIN social_communities c ON c.id = p.community_id
                WHERE p.status = 'manuscript'
                ORDER BY s.title, p.id
                LIMIT 5
            """).fetchall()
        ]

        return JSONResponse({
            "status_counts": status_counts,
            "top_posts": top_posts,
            "queue_preview": queue_preview,
            "total_posts": sum(status_counts.values()),
        }, headers=CORS_HEADERS)
    finally:
        conn.close()


# ── Queue ────────────────────────────────────────────────────────────────────

@router.get("/queue")
def get_queue(
    series_id: Optional[int] = Query(None),
    limit: int = Query(20, le=100),
):
    """Manuscript posts with attached file paths — the active work queue."""
    conn = _db()
    try:
        params = []
        series_filter = ""
        if series_id:
            series_filter = "AND p.series_id = ?"
            params.append(series_id)

        posts = conn.execute(f"""
            SELECT p.id, p.title, p.notes, p.series_notes, p.draft_path,
                   s.title as series, s.slug as series_slug,
                   c.name as community, p.created_at
            FROM social_posts p
            LEFT JOIN social_series s ON s.id = p.series_id
            LEFT JOIN social_communities c ON c.id = p.community_id
            WHERE p.status = 'manuscript'
            {series_filter}
            ORDER BY s.title, p.id
            LIMIT ?
        """, (*params, limit)).fetchall()

        results = []
        for post in posts:
            post_dict = dict(post)
            post_dict["files"] = []
            results.append(post_dict)

        return JSONResponse({
            "queue": results,
            "count": len(results),
        }, headers=CORS_HEADERS)
    finally:
        conn.close()


# ── Posts list ───────────────────────────────────────────────────────────────

@router.get("/posts")
def list_posts(
    status: Optional[str] = Query(None),
    series_id: Optional[int] = Query(None),
    community_id: Optional[int] = Query(None),
    limit: int = Query(20, le=200),
):
    conn = _db()
    try:
        conditions = ["1=1"]
        params = []
        if status:
            conditions.append("p.status = ?")
            params.append(status)
        if series_id:
            conditions.append("p.series_id = ?")
            params.append(series_id)
        if community_id:
            conditions.append("p.community_id = ?")
            params.append(community_id)

        rows = conn.execute(f"""
            SELECT p.id, p.title, p.status, p.url, p.posted_at, p.notes,
                   s.title as series, c.name as community,
                   m.views_total, m.upvotes, m.upvote_ratio
            FROM social_posts p
            LEFT JOIN social_series s ON s.id = p.series_id
            LEFT JOIN social_communities c ON c.id = p.community_id
            LEFT JOIN social_post_metrics m ON m.post_id = p.id
            WHERE {' AND '.join(conditions)}
            ORDER BY p.id DESC
            LIMIT ?
        """, (*params, limit)).fetchall()

        return JSONResponse({
            "posts": [dict(r) for r in rows],
            "count": len(rows),
        }, headers=CORS_HEADERS)
    finally:
        conn.close()


# ── Single post ──────────────────────────────────────────────────────────────

@router.get("/posts/{post_id}")
def get_post(post_id: int):
    conn = _db()
    try:
        post = conn.execute("""
            SELECT p.*, s.title as series, s.slug as series_slug,
                   c.name as community
            FROM social_posts p
            LEFT JOIN social_series s ON s.id = p.series_id
            LEFT JOIN social_communities c ON c.id = p.community_id
            WHERE p.id = ?
        """, (post_id,)).fetchone()

        if not post:
            raise HTTPException(status_code=404, detail=f"Post {post_id} not found")

        post_dict = dict(post)

        # Latest metrics snapshot
        metrics = conn.execute(
            "SELECT * FROM social_post_metrics WHERE post_id = ? ORDER BY snapshot_at DESC LIMIT 1",
            (post_id,)
        ).fetchone()
        post_dict["metrics"] = dict(metrics) if metrics else None

        return JSONResponse(post_dict, headers=CORS_HEADERS)
    finally:
        conn.close()


# ── Status update ────────────────────────────────────────────────────────────

@router.patch("/posts/{post_id}/status")
def update_status(post_id: int, body: StatusUpdate):
    valid = {"manuscript", "draft", "active", "posted", "unknown_gap"}
    if body.status not in valid:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {valid}")

    conn = _db()
    try:
        existing = conn.execute("SELECT id FROM social_posts WHERE id = ?", (post_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail=f"Post {post_id} not found")

        posted_at = datetime.now().isoformat() if body.status == "posted" else None
        if posted_at:
            conn.execute(
                "UPDATE social_posts SET status = ?, posted_at = ? WHERE id = ?",
                (body.status, posted_at, post_id)
            )
        else:
            conn.execute(
                "UPDATE social_posts SET status = ? WHERE id = ?",
                (body.status, post_id)
            )
        conn.commit()
        return JSONResponse({"ok": True, "post_id": post_id, "status": body.status}, headers=CORS_HEADERS)
    finally:
        conn.close()


# ── Series ───────────────────────────────────────────────────────────────────

@router.get("/series")
def list_series():
    conn = _db()
    try:
        rows = conn.execute("""
            SELECT s.id, s.title, s.slug, s.status, s.description,
                   COUNT(p.id) as total_posts,
                   SUM(CASE WHEN p.status='manuscript' THEN 1 ELSE 0 END) as manuscript,
                   SUM(CASE WHEN p.status='active' THEN 1 ELSE 0 END) as active,
                   SUM(CASE WHEN p.status='posted' THEN 1 ELSE 0 END) as posted
            FROM social_series s
            LEFT JOIN social_posts p ON p.series_id = s.id
            GROUP BY s.id, s.title, s.slug, s.status, s.description
            ORDER BY total_posts DESC
        """).fetchall()

        return JSONResponse({
            "series": [dict(r) for r in rows],
            "count": len(rows),
        }, headers=CORS_HEADERS)
    finally:
        conn.close()


# ── Communities ──────────────────────────────────────────────────────────────

@router.get("/communities")
def list_communities():
    conn = _db()
    try:
        rows = conn.execute("""
            SELECT c.id, c.name, c.display_name, c.topic,
                   pl.name as platform,
                   COUNT(p.id) as total_posts,
                   SUM(CASE WHEN p.status='active' THEN 1 ELSE 0 END) as active,
                   SUM(CASE WHEN p.status='posted' THEN 1 ELSE 0 END) as posted
            FROM social_communities c
            LEFT JOIN social_platforms pl ON pl.id = c.platform_id
            LEFT JOIN social_posts p ON p.community_id = c.id
            GROUP BY c.id, c.name, c.display_name, c.topic, pl.name
            ORDER BY total_posts DESC
        """).fetchall()

        return JSONResponse({
            "communities": [dict(r) for r in rows],
        }, headers=CORS_HEADERS)
    finally:
        conn.close()


# ── Metrics / top performers ─────────────────────────────────────────────────

@router.get("/metrics")
def top_metrics(limit: int = Query(20, le=100)):
    conn = _db()
    try:
        rows = conn.execute("""
            SELECT p.id, p.title, p.url, p.status,
                   s.title as series, c.name as community,
                   m.views_total, m.views_48h, m.upvotes, m.upvote_ratio,
                   m.comments, m.rank_today, m.geo_us_pct, m.snapshot_at
            FROM social_post_metrics m
            JOIN social_posts p ON p.id = m.post_id
            LEFT JOIN social_series s ON s.id = p.series_id
            LEFT JOIN social_communities c ON c.id = p.community_id
            ORDER BY m.views_total DESC
            LIMIT ?
        """, (limit,)).fetchall()

        return JSONResponse({
            "top_posts": [dict(r) for r in rows],
            "count": len(rows),
        }, headers=CORS_HEADERS)
    finally:
        conn.close()


# ── Create post ──────────────────────────────────────────────────────────────

@router.post("/posts")
def create_post(body: NewPost):
    conn = _db()
    try:
        now = datetime.now().isoformat()
        cursor = conn.execute("""
            INSERT INTO social_posts (account_id, community_id, series_id, title, status, notes, draft_path, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            body.account_id, body.community_id, body.series_id,
            body.title, body.status, body.notes, body.draft_path, now
        ))
        conn.commit()
        new_id = cursor.lastrowid
        return JSONResponse(
            {"ok": True, "post_id": new_id, "title": body.title, "status": body.status},
            status_code=201,
            headers=CORS_HEADERS,
        )
    finally:
        conn.close()

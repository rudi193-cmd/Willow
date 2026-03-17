"""
Social Media Workflow Routes
============================
State-machine endpoints for moving posts through the posting pipeline:
  manuscript → draft → active → posted

Endpoints:
  GET  /api/social/workflow/next              — next manuscript post by priority
  GET  /api/social/workflow/series-order      — series ranked by queue depth
  GET  /api/social/workflow/{id}/preview      — read draft file content
  POST /api/social/workflow/{id}/draft        — save draft text + update status
  PATCH /api/social/workflow/{id}/publish     — mark posted + set URL
  POST /api/social/workflow/reddit/setup      — store Reddit app credentials in vault
  GET  /api/social/workflow/reddit/status     — verify Reddit credentials are valid
  POST /api/social/workflow/{id}/post-to-reddit — post draft to subreddit + mark posted

DS=42
"""

import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "core"))
import credentials as _vault
from core.db import get_connection

router = APIRouter(prefix="/api/social/workflow", tags=["social-workflow"])

DRAFTS_DIR = Path(__file__).parent.parent / "artifacts" / "Sweet-Pea-Rudi19" / "social" / "drafts"

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, PATCH, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
}


def _db():
    conn = get_connection()
    return conn


def _slugify(text: str, max_len: int = 40) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len].rstrip("-")


# ── Models ───────────────────────────────────────────────────────────────────

class DraftBody(BaseModel):
    draft_text: Optional[str] = None
    draft_title: Optional[str] = None


class PublishBody(BaseModel):
    url: str


class RedditSetup(BaseModel):
    client_id: str
    client_secret: str
    username: str
    password: str


class RedditPostBody(BaseModel):
    flair: Optional[str] = None       # optional post flair
    dry_run: bool = False              # if True, skip actual post, return what would be sent


# ── GET /next ────────────────────────────────────────────────────────────────

@router.get("/next")
def next_post():
    """Next manuscript post by priority.

    Priority: series with fewest total posts first (drain short series fast),
    then by post id ascending within each series.
    """
    conn = _db()
    try:
        post = conn.execute("""
            SELECT p.id, p.title, p.notes, p.series_notes, p.draft_path,
                   s.title as series, s.slug as series_slug,
                   c.name as community, p.created_at,
                   COUNT(p2.id) as series_total
            FROM social_posts p
            LEFT JOIN social_series s ON s.id = p.series_id
            LEFT JOIN social_communities c ON c.id = p.community_id
            LEFT JOIN social_posts p2 ON p2.series_id = p.series_id
            WHERE p.status = 'manuscript'
            GROUP BY p.id, p.title, p.notes, p.series_notes, p.draft_path,
                     s.title, s.slug, c.name, p.created_at
            ORDER BY series_total ASC, p.id ASC
            LIMIT 1
        """).fetchone()

        if not post:
            return JSONResponse({"post": None, "message": "Queue is empty"}, headers=CORS_HEADERS)

        post_dict = dict(post)
        post_dict["files"] = []

        return JSONResponse({"post": post_dict}, headers=CORS_HEADERS)
    finally:
        conn.close()


# ── GET /series-order ────────────────────────────────────────────────────────

@router.get("/series-order")
def series_order():
    """Series ranked by queue depth (manuscript count desc), then total posts asc."""
    conn = _db()
    try:
        rows = conn.execute("""
            SELECT s.id, s.title, s.slug,
                   SUM(CASE WHEN p.status='manuscript' THEN 1 ELSE 0 END) as manuscript_count,
                   COUNT(p.id) as total_posts
            FROM social_series s
            LEFT JOIN social_posts p ON p.series_id = s.id
            GROUP BY s.id
            HAVING SUM(CASE WHEN p.status='manuscript' THEN 1 ELSE 0 END) > 0
            ORDER BY manuscript_count DESC, total_posts ASC
        """).fetchall()

        results = []
        for row in rows:
            r = dict(row)
            next_p = conn.execute(
                "SELECT id, title FROM social_posts WHERE series_id = ? AND status = 'manuscript' ORDER BY id LIMIT 1",
                (row["id"],)
            ).fetchone()
            r["next_post"] = dict(next_p) if next_p else None
            results.append(r)

        return JSONResponse({"series": results, "count": len(results)}, headers=CORS_HEADERS)
    finally:
        conn.close()


# ── GET /{post_id}/preview ───────────────────────────────────────────────────

@router.get("/{post_id}/preview")
def preview_draft(post_id: int):
    """Return the current draft file content for a post."""
    conn = _db()
    try:
        post = conn.execute(
            "SELECT id, title, status, notes, draft_path FROM social_posts WHERE id = ?",
            (post_id,)
        ).fetchone()

        if not post:
            raise HTTPException(status_code=404, detail=f"Post {post_id} not found")

        content = None
        if post["draft_path"]:
            draft_file = Path(post["draft_path"])
            if draft_file.exists():
                content = draft_file.read_text(encoding="utf-8")

        return JSONResponse({
            "content": content,
            "draft_path": post["draft_path"],
            "post": {
                "id": post["id"],
                "title": post["title"],
                "status": post["status"],
                "notes": post["notes"],
            },
        }, headers=CORS_HEADERS)
    finally:
        conn.close()


# ── POST /{post_id}/draft ────────────────────────────────────────────────────

@router.post("/{post_id}/draft")
def save_draft(post_id: int, body: DraftBody):
    """Save draft text to disk and transition post to 'draft' status."""
    if not body.draft_text and not body.draft_title:
        raise HTTPException(status_code=400, detail="draft_text or draft_title required")

    conn = _db()
    try:
        post = conn.execute(
            "SELECT id, title FROM social_posts WHERE id = ?", (post_id,)
        ).fetchone()
        if not post:
            raise HTTPException(status_code=404, detail=f"Post {post_id} not found")

        DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
        slug = _slugify(post["title"])
        draft_file = DRAFTS_DIR / f"{post_id}_{slug}.md"

        content = body.draft_text or ""
        draft_file.write_text(content, encoding="utf-8")

        draft_path = str(draft_file)

        conn.execute(
            "UPDATE social_posts SET draft_path = ?, status = 'draft' WHERE id = ?",
            (draft_path, post_id)
        )
        conn.commit()

        return JSONResponse(
            {"ok": True, "post_id": post_id, "draft_path": draft_path, "status": "draft"},
            headers=CORS_HEADERS
        )
    finally:
        conn.close()


# ── PATCH /{post_id}/publish ─────────────────────────────────────────────────

@router.patch("/{post_id}/publish")
def publish_post(post_id: int, body: PublishBody):
    """Mark a post as posted with its URL."""
    conn = _db()
    try:
        post = conn.execute("SELECT id FROM social_posts WHERE id = ?", (post_id,)).fetchone()
        if not post:
            raise HTTPException(status_code=404, detail=f"Post {post_id} not found")

        posted_at = datetime.now().isoformat()
        conn.execute(
            "UPDATE social_posts SET url = ?, posted_at = ?, status = 'posted' WHERE id = ?",
            (body.url, posted_at, post_id)
        )
        conn.commit()

        return JSONResponse({
            "ok": True,
            "post_id": post_id,
            "url": body.url,
            "posted_at": posted_at,
        }, headers=CORS_HEADERS)
    finally:
        conn.close()


# ── Reddit credential management ─────────────────────────────────────────────

@router.post("/reddit/setup")
def reddit_setup(body: RedditSetup):
    """Store Reddit app credentials in the Willow credential vault (localhost only)."""
    _vault.set_cred("reddit_client_id",     body.client_id)
    _vault.set_cred("reddit_client_secret", body.client_secret)
    _vault.set_cred("reddit_username",      body.username)
    _vault.set_cred("reddit_password",      body.password)
    return JSONResponse({"ok": True, "stored": ["reddit_client_id", "reddit_client_secret",
                                                 "reddit_username", "reddit_password"]},
                        headers=CORS_HEADERS)


@router.get("/reddit/status")
def reddit_status():
    """Verify Reddit credentials are present and valid by doing a lightweight API call."""
    client_id     = _vault.get_cred("reddit_client_id")
    client_secret = _vault.get_cred("reddit_client_secret")
    username      = _vault.get_cred("reddit_username")
    password      = _vault.get_cred("reddit_password")

    missing = [k for k, v in {
        "reddit_client_id": client_id,
        "reddit_client_secret": client_secret,
        "reddit_username": username,
        "reddit_password": password,
    }.items() if not v]

    if missing:
        return JSONResponse({"ok": False, "error": f"Missing credentials: {missing}"},
                            status_code=503, headers=CORS_HEADERS)

    try:
        import praw
        reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            username=username,
            password=password,
            user_agent=f"Willow/1.0 by u/{username}",
        )
        me = reddit.user.me()
        return JSONResponse({
            "ok": True,
            "username": str(me),
            "karma": me.link_karma + me.comment_karma,
        }, headers=CORS_HEADERS)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=503, headers=CORS_HEADERS)


# ── POST /{post_id}/post-to-reddit ───────────────────────────────────────────

@router.post("/{post_id}/post-to-reddit")
def post_to_reddit(post_id: int, body: RedditPostBody):
    """Read draft, post to the post's assigned subreddit, mark as posted."""
    conn = _db()
    try:
        row = conn.execute("""
            SELECT p.id, p.title, p.draft_path,
                   c.name as subreddit
            FROM social_posts p
            LEFT JOIN social_communities c ON c.id = p.community_id
            WHERE p.id = ?
        """, (post_id,)).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail=f"Post {post_id} not found")
        if not row["subreddit"]:
            raise HTTPException(status_code=400, detail="Post has no community assigned")
        if not row["draft_path"]:
            raise HTTPException(status_code=400, detail="No draft saved — run /draft first")

        draft_file = Path(row["draft_path"])
        if not draft_file.exists():
            raise HTTPException(status_code=400, detail=f"Draft file not found: {row['draft_path']}")

        body_text = draft_file.read_text(encoding="utf-8")
        title     = row["title"]
        subreddit = row["subreddit"]

        if body.dry_run:
            return JSONResponse({
                "dry_run": True,
                "would_post": {
                    "subreddit": f"r/{subreddit}",
                    "title": title,
                    "body_preview": body_text[:300],
                    "flair": body.flair,
                }
            }, headers=CORS_HEADERS)

        # Load credentials
        client_id     = _vault.get_cred("reddit_client_id")
        client_secret = _vault.get_cred("reddit_client_secret")
        username      = _vault.get_cred("reddit_username")
        password      = _vault.get_cred("reddit_password")

        if not all([client_id, client_secret, username, password]):
            raise HTTPException(status_code=503,
                                detail="Reddit credentials not configured — POST /workflow/reddit/setup first")

        try:
            import praw
            reddit = praw.Reddit(
                client_id=client_id,
                client_secret=client_secret,
                username=username,
                password=password,
                user_agent=f"Willow/1.0 by u/{username}",
            )

            sub = reddit.subreddit(subreddit)
            submission = sub.submit(title=title, selftext=body_text)

            if body.flair and submission.flair:
                try:
                    submission.flair.select(body.flair)
                except Exception:
                    pass  # flair selection is best-effort

        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Reddit API error: {e}")

        # Mark posted in DB
        reddit_url = f"https://reddit.com{submission.permalink}"
        posted_at  = datetime.now().isoformat()
        conn.execute(
            "UPDATE social_posts SET url = ?, posted_at = ?, status = 'posted' WHERE id = ?",
            (reddit_url, posted_at, post_id)
        )
        conn.commit()

        return JSONResponse({
            "ok": True,
            "post_id": post_id,
            "subreddit": f"r/{subreddit}",
            "reddit_url": reddit_url,
            "posted_at": posted_at,
        }, headers=CORS_HEADERS)
    finally:
        conn.close()


# ── GET /reddit/pull ─────────────────────────────────────────────────────────

def _praw_client():
    """Return authenticated praw.Reddit instance or raise HTTPException."""
    client_id     = _vault.get_cred("reddit_client_id")
    client_secret = _vault.get_cred("reddit_client_secret")
    username      = _vault.get_cred("reddit_username")
    password      = _vault.get_cred("reddit_password")
    if not all([client_id, client_secret, username, password]):
        raise HTTPException(status_code=503,
                            detail="Reddit credentials not configured — POST /workflow/reddit/setup first")
    import praw
    return praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        username=username,
        password=password,
        user_agent=f"Willow/1.0 by u/{username}",
    ), username


def _normalize(title: str) -> str:
    """Lowercase, strip punctuation for fuzzy title matching."""
    return re.sub(r"[^a-z0-9 ]", "", title.lower()).strip()


@router.get("/reddit/pull")
def reddit_pull(limit: int = 100):
    """Fetch submission history from Reddit and reconcile with local DB.

    For each Reddit submission:
      - Exact title match → backfill url, posted_at, status='posted', snapshot metrics
      - No match         → return in 'untracked' list for review

    Also refreshes metrics for all active posts that already have URLs.
    """
    reddit, username = _praw_client()
    conn = _db()
    now = datetime.now().isoformat()

    try:
        # Build local lookup: normalized_title → post row
        db_posts = conn.execute("""
            SELECT p.id, p.title, p.url, p.status, c.name as subreddit
            FROM social_posts p
            LEFT JOIN social_communities c ON c.id = p.community_id
        """).fetchall()

        title_index = {}
        for p in db_posts:
            key = (_normalize(p["title"]), (p["subreddit"] or "").lower())
            title_index[key] = p

        # Fetch Reddit submissions
        redditor = reddit.redditor(username)
        matched   = []
        untracked = []

        for sub in redditor.submissions.new(limit=limit):
            key = (_normalize(sub.title), sub.subreddit.display_name.lower())
            db_post = title_index.get(key)

            reddit_url = f"https://reddit.com{sub.permalink}"
            created_at = datetime.utcfromtimestamp(sub.created_utc).isoformat()

            if db_post:
                # Backfill URL and status if missing
                if not db_post["url"]:
                    conn.execute(
                        "UPDATE social_posts SET url = ?, posted_at = ?, status = 'posted' WHERE id = ?",
                        (reddit_url, created_at, db_post["id"])
                    )

                # Snapshot metrics
                conn.execute("""
                    INSERT INTO social_post_metrics
                      (post_id, snapshot_at, views_total, upvotes, upvote_ratio, comments)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    db_post["id"], now,
                    getattr(sub, "view_count", None),
                    sub.score,
                    sub.upvote_ratio,
                    sub.num_comments,
                ))

                matched.append({
                    "post_id":    db_post["id"],
                    "title":      sub.title,
                    "subreddit":  f"r/{sub.subreddit.display_name}",
                    "reddit_url": reddit_url,
                    "score":      sub.score,
                    "comments":   sub.num_comments,
                    "url_was_missing": not db_post["url"],
                })
            else:
                untracked.append({
                    "title":     sub.title,
                    "subreddit": f"r/{sub.subreddit.display_name}",
                    "url":       reddit_url,
                    "created":   created_at,
                    "score":     sub.score,
                })

        conn.commit()

        return JSONResponse({
            "ok":           True,
            "pulled":       len(matched) + len(untracked),
            "matched":      len(matched),
            "untracked":    len(untracked),
            "backfilled":   sum(1 for m in matched if m["url_was_missing"]),
            "snapshot_at":  now,
            "results":      matched,
            "untracked_posts": untracked,
        }, headers=CORS_HEADERS)
    finally:
        conn.close()

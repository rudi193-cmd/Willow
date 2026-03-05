#!/usr/bin/env python3
"""
OCR Extraction Pass — Social Media Intelligence
================================================
Reads all 223 social items from willow_knowledge.db,
parses structured data from content_snippets,
and populates social_media.db.

Run: python extract_social_ocr.py [--dry-run]
"""

import sqlite3
import re
import sys
import json
from pathlib import Path
from datetime import datetime

KNOWLEDGE_DB = r"C:\Users\Sean\Documents\GitHub\Willow\artifacts\Sweet-Pea-Rudi19\willow_knowledge.db"
SOCIAL_DB    = r"C:\Users\Sean\Documents\GitHub\Willow\artifacts\Sweet-Pea-Rudi19\social\social_media.db"

DRY_RUN = "--dry-run" in sys.argv

# ─── REGEX PATTERNS ───────────────────────────────────────────────────────────

# Subreddit from post insights header: "r/SubredditName · 2d Title..."
RE_SUBREDDIT = re.compile(r'r/([A-Za-z0-9_]+)', re.IGNORECASE)

# Time-ago marker (separates subreddit from title)
RE_TIMEAGO = re.compile(r'r/([A-Za-z0-9_]+)\s*[·•�]\s*(\d+[hdmwy])\s+(.+?)(?:\s+Increase your|\s+Reach\s+Hourly|\s+Share or crosspost)', re.DOTALL)

# Achievement / rank lines (in order of specificity)
RE_RANK_ALLTIME_N = re.compile(r'(?:Amazing!|Nice!)\s+This is your #(\d+) post of all time', re.IGNORECASE)
RE_RANK_TOP_N     = re.compile(r'This is one of your top (\d+) posts of all time', re.IGNORECASE)
RE_RANK_TODAY_N   = re.compile(r'This is the #(\d+) post on r/([A-Za-z0-9_]+) today', re.IGNORECASE)

# Views — two layouts Reddit uses:
# Layout A: "Views {total} +{delta} First 48 hours {scale_hi} {scale_mid}"
RE_VIEWS_A = re.compile(r'Views\s+([\d,]+(?:\.\d+)?[kKmM]?)\s*\+?([\d,]+)\s+First 48 hours', re.IGNORECASE)
# Layout B: "Views First 48 hours {scale_hi} {scale_mid} {total} +{delta}"
RE_VIEWS_B = re.compile(r'Views First 48 hours\s+\d+\s+\d+\s+(?:\d+\s+)?([\d,]+(?:\.\d+)?[kKmM]?)\s*\+?([\d,]+)', re.IGNORECASE)
# Layout C: isolated large number before nav bar (fallback)
RE_VIEWS_STANDALONE = re.compile(r'(?:Views|Reach).*?([\d,]+(?:\.\d+)?[kKmM]?)\s*\+?([\d,]+)\s*(?:Home|Inbox|Create)', re.IGNORECASE | re.DOTALL)

# Engagement metrics
RE_UPVOTES   = re.compile(r'(\d+)\s+(?:upvotes?|Upvote Ratio\s*\d+%)', re.IGNORECASE)
RE_COMMENTS  = re.compile(r'(?:Comments|D Comments)\s*(\d+)', re.IGNORECASE)
RE_UPVOTE_RT = re.compile(r'(\d+)%', re.IGNORECASE)

# Geographic
RE_GEO_US = re.compile(r'United States\s+(\d+)%', re.IGNORECASE)

# Date from filename: Screenshot_YYYYMMDD_HHMMSS or OCR_Screenshot_YYYYMMDD
RE_DATE_FNAME = re.compile(r'(?:Screenshot|OCR_Screenshot)[_-](\d{4})(\d{2})(\d{2})')

# ─── HELPERS ──────────────────────────────────────────────────────────────────

def parse_views(text: str):
    """Extract view count as integer from OCR text."""
    def convert(s):
        s = s.replace(',', '').strip().lower()
        if s.endswith('k'):
            return int(float(s[:-1]) * 1000)
        if s.endswith('m'):
            return int(float(s[:-1]) * 1000000)
        try:
            return int(s)
        except:
            return None

    # Try Layout A first (more reliable)
    m = RE_VIEWS_A.search(text)
    if m:
        v = convert(m.group(1))
        if v and v > 0:
            return v, "layout_a"

    # Layout B
    m = RE_VIEWS_B.search(text)
    if m:
        v = convert(m.group(1))
        if v and v > 0:
            return v, "layout_b"

    # Standalone fallback
    m = RE_VIEWS_STANDALONE.search(text)
    if m:
        v = convert(m.group(1))
        if v and v > 0:
            return v, "fallback"

    return None, None


def parse_rank(text: str):
    """Extract rank/achievement text."""
    achievements = []

    m = RE_RANK_ALLTIME_N.search(text)
    if m:
        achievements.append(f"#{m.group(1)} post of all time")

    m = RE_RANK_TOP_N.search(text)
    if m:
        achievements.append(f"top {m.group(1)} posts of all time")

    m = RE_RANK_TODAY_N.search(text)
    if m:
        achievements.append(f"#{m.group(1)} post on r/{m.group(2)} today")

    return " | ".join(achievements) if achievements else None


def parse_post_title(text: str):
    """Extract subreddit and post title from post insights header."""
    m = RE_TIMEAGO.search(text)
    if m:
        subreddit = m.group(1)
        title_raw = m.group(3).strip()
        # Clean up title — remove ellipsis artifacts
        title = re.sub(r'\s+', ' ', title_raw).strip()
        # Remove trailing OCR artifacts
        title = re.sub(r'\s*[O0]\+\s*$', '', title)
        return subreddit, title
    return None, None


def date_from_filename(filename: str):
    """Extract ISO date from screenshot filename."""
    m = RE_DATE_FNAME.search(filename)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return None


def classify_item(snippet: str, title: str):
    """Classify OCR item type."""
    if not snippet:
        return "image_only"
    s = snippet.lower()
    fname = title.lower()

    if "post insights" in s:
        if re.search(r'r/[A-Za-z0-9_]+.*?\d+[hdm]\s+\w', s):
            return "post_insights_with_title"
        return "post_insights_metrics"
    if "top comments" in s or "view all" in s:
        return "comment_thread"
    if "u/beneficialbig" in s or "posts comments about" in s:
        return "profile_view"
    if "hinge" in fname or "feeld" in fname:
        return "dating_app"
    if "facebook" in fname or "linkedin" in fname:
        return "other_platform"
    return "other_reddit"


# ─── LOOKUP / UPSERT HELPERS ──────────────────────────────────────────────────

def get_or_create_community(conn, platform_id: int, name: str):
    """Get community ID, create if not exists."""
    row = conn.execute("SELECT id FROM communities WHERE name=?", (name,)).fetchone()
    if row:
        return row[0]
    conn.execute(
        "INSERT INTO communities(platform_id, name, display_name, owner, topic) VALUES (?,?,?,?,?)",
        (platform_id, name, f"r/{name}", "unknown", "unknown")
    )
    conn.commit()
    return conn.execute("SELECT id FROM communities WHERE name=?", (name,)).fetchone()[0]


def upsert_post(conn, account_id, community_id, title, posted_at, notes, source_file):
    """Insert post if not already present (match by title + community)."""
    row = conn.execute(
        "SELECT id FROM posts WHERE title=? AND community_id=?",
        (title, community_id)
    ).fetchone()
    if row:
        return row[0], False  # existing
    conn.execute(
        "INSERT INTO posts(account_id, community_id, title, posted_at, notes) VALUES (?,?,?,?,?)",
        (account_id, community_id, title, posted_at, notes)
    )
    conn.commit()
    return conn.execute(
        "SELECT id FROM posts WHERE title=? AND community_id=?",
        (title, community_id)
    ).fetchone()[0], True  # new


def insert_metrics(conn, post_id, snapshot_at, views_total, rank_today, geo_us_pct, source_file):
    """Insert metrics snapshot (deduplicated by post_id + snapshot_at)."""
    existing = conn.execute(
        "SELECT id FROM post_metrics WHERE post_id=? AND snapshot_at=?",
        (post_id, snapshot_at)
    ).fetchone()
    if existing:
        return False
    conn.execute("""
        INSERT INTO post_metrics(post_id, snapshot_at, views_total, rank_today, geo_us_pct, source_file)
        VALUES (?,?,?,?,?,?)
    """, (post_id, snapshot_at, views_total, rank_today, geo_us_pct, source_file))
    conn.commit()
    return True


def insert_milestone(conn, post_id, account_id, milestone_text, achieved_at, metric_value):
    """Insert milestone if not duplicate."""
    existing = conn.execute(
        "SELECT id FROM milestones WHERE post_id=? AND milestone=?",
        (post_id, milestone_text)
    ).fetchone()
    if existing:
        return False
    conn.execute("""
        INSERT INTO milestones(post_id, account_id, milestone, achieved_at, metric_value)
        VALUES (?,?,?,?,?)
    """, (post_id, account_id, milestone_text, achieved_at, metric_value))
    conn.commit()
    return True


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    knowledge = sqlite3.connect(KNOWLEDGE_DB)
    social = sqlite3.connect(SOCIAL_DB)

    # Load lookup IDs
    reddit_platform = social.execute("SELECT id FROM platforms WHERE name='Reddit'").fetchone()[0]
    reddit_acct = social.execute("SELECT id FROM accounts WHERE handle='BeneficialBig8372'").fetchone()[0]

    # Fetch all social items
    items = loam.execute("""
        SELECT id, title, content_snippet FROM knowledge
        WHERE category='social' ORDER BY id
    """).fetchall()

    print(f"Processing {len(items)} social items...")
    print(f"Mode: {'DRY RUN' if DRY_RUN else 'LIVE'}\n")

    stats = {
        "total": len(items),
        "post_insights_with_title": 0,
        "post_insights_metrics": 0,
        "comment_thread": 0,
        "profile_view": 0,
        "other": 0,
        "posts_found": 0,
        "posts_new": 0,
        "metrics_added": 0,
        "milestones_added": 0,
        "skipped_no_content": 0,
    }

    new_posts = []
    all_communities = set()

    for kid, title, snippet in items:
        if not snippet or snippet.strip() in ("", "Screenshot from Reddit (social media)"):
            stats["skipped_no_content"] += 1
            continue

        item_type = classify_item(snippet, title)
        stats[item_type if item_type in stats else "other"] += 1

        date_str = date_from_filename(title)

        if item_type == "post_insights_with_title":
            subreddit, post_title = parse_post_title(snippet)
            if not subreddit or not post_title:
                continue

            all_communities.add(subreddit)
            views, view_src = parse_views(snippet)
            rank = parse_rank(snippet)
            geo_us = None
            m = RE_GEO_US.search(snippet)
            if m:
                geo_us = float(m.group(1))

            stats["posts_found"] += 1

            if not DRY_RUN:
                community_id = get_or_create_community(social, reddit_platform, subreddit)
                post_id, is_new = upsert_post(
                    social, reddit_acct, community_id, post_title,
                    date_str, f"Source: {title}", title
                )
                if is_new:
                    stats["posts_new"] += 1
                    new_posts.append((subreddit, post_title, date_str, views, rank))

                if date_str:
                    if insert_metrics(social, post_id, date_str, views, rank, geo_us, title):
                        stats["metrics_added"] += 1

                if rank:
                    metric_val = f"{views:,} views" if views else None
                    if insert_milestone(social, post_id, reddit_acct, rank, date_str, metric_val):
                        stats["milestones_added"] += 1
            else:
                print(f"  [DRY] r/{subreddit} | {post_title[:60]} | views={views} | rank={rank}")
                if is_new := True:
                    stats["posts_new"] += 1
                    new_posts.append((subreddit, post_title, date_str, views, rank))

        elif item_type == "post_insights_metrics":
            # Metrics-only page — try to find views without a title
            views, view_src = parse_views(snippet)
            geo_us = None
            m = RE_GEO_US.search(snippet)
            if m:
                geo_us = float(m.group(1))
            # Can't associate to a post without title — skip for now
            pass

    # Report
    print(f"\n{'='*60}")
    print(f"EXTRACTION COMPLETE {'(DRY RUN)' if DRY_RUN else ''}")
    print(f"{'='*60}")
    print(f"  Total items: {stats['total']}")
    print(f"  Skipped (no content): {stats['skipped_no_content']}")
    print(f"  Post insights with title: {stats['post_insights_with_title']}")
    print(f"  Post insights (metrics only): {stats['post_insights_metrics']}")
    print(f"  Comment threads: {stats['comment_thread']}")
    print(f"  Profile views: {stats['profile_view']}")
    print(f"  Other: {stats['other']}")
    print(f"\n  Posts found: {stats['posts_found']}")
    print(f"  Posts NEW to DB: {stats['posts_new']}")
    print(f"  Metrics snapshots added: {stats['metrics_added']}")
    print(f"  Milestones added: {stats['milestones_added']}")

    print(f"\n  Communities seen: {sorted(all_communities)}")

    print(f"\n  New posts extracted:")
    for sub, t, d, v, r in new_posts:
        marker = f" [{r}]" if r else ""
        views_str = f" {v:,}v" if v else ""
        print(f"    r/{sub:<30} {d or '?'} {views_str:<12} {t[:55]}{marker}")

    loam.close()
    social.close()


if __name__ == "__main__":
    main()

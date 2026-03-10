#!/usr/bin/env python3
"""
Die-namic Ingestion Pass
========================
Ingests canonical die-namic creative_works and analytics docs into:
  - social_media.db: series, communities, dispatches, benchmarks, projects, series_files
  - willow_knowledge.db: all MD files as knowledge atoms

Run: python ingest_die_namic.py [--dry-run]
"""

import os
import re
import sys
import hashlib
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

_WILLOW_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_WILLOW_ROOT))
from core.db import get_connection

DIE_NAMIC = str(_WILLOW_ROOT.parent / 'die-namic-system')

CREATIVE_WORKS    = os.path.join(DIE_NAMIC, "docs", "creative_works")
REDDIT_ANALYTICS  = os.path.join(DIE_NAMIC, "docs", "ops", "reddit_analytics")
HOLLYWOOD_PITCHES = os.path.join(DIE_NAMIC, "docs", "hollywood-pitches")

DRY_RUN = "--dry-run" in sys.argv

stats = {
    "s1_series_updated":      0,
    "s2_communities_added":   0,
    "s3_dispatches_upserted": 0,
    "s3_post_files_added":    0,
    "s4_posts_upserted":      0,
    "s4_metrics_added":       0,
    "s4_milestones_added":    0,
    "s5_projects_added":      0,
    "s6_series_files_added":  0,
    "s7_knowledge_new":       0,
    "s7_knowledge_existing":  0,
}

# ── Helpers ────────────────────────────────────────────────────────────────────

def read_file(path):
    try:
        with open(path, encoding='utf-8', errors='replace') as f:
            return f.read()
    except Exception as e:
        print(f"  [WARN] Could not read {path}: {e}", file=sys.stderr)
        return ""


def infer_file_type(filename):
    name = os.path.basename(filename).upper()
    if 'CHARACTER_BIBLE' in name:    return 'character_bible'
    if 'WORLD_ARCHITECTURE' in name: return 'world_bible'
    if 'DISPATCH_LOG' in name:       return 'dispatch_log'
    if 'COSMOLOGY' in name:          return 'cosmology'
    if 'VOICE_GUIDE' in name:        return 'voice_guide'
    if 'LOCATIONS' in name:          return 'locations'
    if 'OPERATIONS' in name:         return 'operations'
    if 'HANDOFF' in name:            return 'handoff'
    if name == 'README.MD':          return 'readme'
    if name == 'INDEX.MD':           return 'index'
    if 'GUIDE' in name:              return 'guide'
    if 'BRIEFING' in name:           return 'briefing'
    if 'STYLE' in name:              return 'style_guide'
    return 'reference'


def get_series_id(conn, slug):
    row = conn.execute("SELECT id FROM series WHERE slug=?", (slug,)).fetchone()
    return row[0] if row else None


def get_community_id(conn, name):
    row = conn.execute("SELECT id FROM communities WHERE name=?", (name,)).fetchone()
    return row[0] if row else None


def get_or_create_community(conn, platform_id, name, display_name, owner, topic):
    row = conn.execute("SELECT id FROM communities WHERE name=?", (name,)).fetchone()
    if row:
        return row[0], False
    conn.execute(
        "INSERT INTO communities(platform_id, name, display_name, owner, topic) VALUES (?,?,?,?,?)",
        (platform_id, name, display_name, owner, topic)
    )
    conn.commit()
    return conn.execute("SELECT id FROM communities WHERE name=?", (name,)).fetchone()[0], True


def get_or_create_post(conn, title, community_id, series_id, account_id, status, notes):
    row = conn.execute(
        "SELECT id FROM posts WHERE title=? AND community_id=?",
        (title, community_id)
    ).fetchone()
    if row:
        return row[0], False
    conn.execute(
        "INSERT INTO posts(account_id, community_id, series_id, title, status, notes) VALUES (?,?,?,?,?,?)",
        (account_id, community_id, series_id, title, status, notes)
    )
    conn.commit()
    return conn.execute(
        "SELECT id FROM posts WHERE title=? AND community_id=?",
        (title, community_id)
    ).fetchone()[0], True


def add_post_file_deduped(conn, post_id, file_path, file_type, source_type, notes):
    exists = conn.execute(
        "SELECT id FROM post_files WHERE post_id=? AND file_path=?",
        (post_id, file_path)
    ).fetchone()
    if not exists:
        conn.execute(
            "INSERT INTO post_files(post_id, file_path, file_type, source, notes) VALUES (?,?,?,?,?)",
            (post_id, file_path, file_type, source_type, notes)
        )
        conn.commit()
        return True
    return False


def add_series_file_deduped(conn, series_id, file_path, file_type, notes=""):
    exists = conn.execute(
        "SELECT id FROM series_files WHERE series_id=? AND file_path=?",
        (series_id, file_path)
    ).fetchone()
    if not exists:
        conn.execute(
            "INSERT INTO series_files(series_id, file_path, file_type, notes) VALUES (?,?,?,?)",
            (series_id, file_path, file_type, notes)
        )
        conn.commit()
        return True
    return False


def upsert_knowledge(know_conn, title, content, category, summary=None):
    source_id = hashlib.md5(title.encode('utf-8')).hexdigest()
    exists = know_conn.execute(
        "SELECT id FROM knowledge WHERE source_type='die_namic' AND source_id=?",
        (source_id,)
    ).fetchone()
    if exists:
        return exists[0], False
    snip = content[:400].replace('\n', ' ').strip()
    _summary = summary or content[:150].replace('\n', ' ').strip()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    know_conn.execute(
        """INSERT INTO knowledge(source_type, source_id, title, summary, content_snippet, category, ring, created_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        ('die_namic', source_id, title, _summary, snip, category, 'bridge', now)
    )
    know_conn.commit()
    return know_conn.execute(
        "SELECT id FROM knowledge WHERE source_type='die_namic' AND source_id=?",
        (source_id,)
    ).fetchone()[0], True


# ── Section 1: Fix series metadata ────────────────────────────────────────────

def section1_fix_series(social):
    print("\n=== SECTION 1: Fix series metadata ===")
    bom_proj = social.execute("SELECT id FROM projects WHERE slug='books-of-mann'").fetchone()
    bom_proj_id = bom_proj[0] if bom_proj else None

    updates = [
        ({"title": "The Letter Under Blue Sky",
          "series_notes": "Book One of The Books of Mann. TRAPPIST-1b. Detective Robert Patrick Mann. Pen name: Lee S. Roberts."},
         "bom-book-one"),
        ({"project_id": bom_proj_id,
          "description": "Book Three of The Books of Mann. Narrator: L.E.E.-142 (robot, reader does not know). Raises Bob from age 3 to adulthood. ~47,900 words. Complete."},
         "what-i-carried"),
        ({"title": "Book Two: TBD",
          "series_notes": "Not started as of 2026-01-02. Draft chapter exists."},
         "bom-book-two"),
    ]

    for fields, slug in updates:
        row = social.execute("SELECT id FROM series WHERE slug=?", (slug,)).fetchone()
        if not row:
            print(f"  [SKIP] series slug '{slug}' not found")
            continue
        set_parts = ", ".join(f"{k}=?" for k in fields.keys())
        values = list(fields.values()) + [slug]
        if not DRY_RUN:
            social.execute(f"UPDATE series SET {set_parts} WHERE slug=?", values)
            social.commit()
        for k, v in fields.items():
            print(f"  [{slug}] {k} = {str(v)[:70]}")
        stats["s1_series_updated"] += 1

    print(f"  -> {stats['s1_series_updated']} series rows updated")


# ── Section 2: Add missing communities ────────────────────────────────────────

def section2_communities(social):
    print("\n=== SECTION 2: Add missing communities ===")
    reddit_id = social.execute("SELECT id FROM platforms WHERE name='Reddit'").fetchone()[0]

    communities_to_add = [
        ("LLMPhysics",          "r/LLMPhysics",          "mod_nemothorx", "AI/physics comedy"),
        ("StuffOnCats",         "r/StuffOnCats",          "unknown",       "cats"),
        ("sciencememes",        "r/sciencememes",         "unknown",       "science memes"),
        ("PharaohsScooterClub", "r/PharaohsScooterClub", "unknown",       "TBD"),
        ("DefinitelyNotGerald", "r/DefinitelyNotGerald", "unknown",       "Gerald sightings in natural phenomena"),
    ]

    for name, display_name, owner, topic in communities_to_add:
        exists = social.execute("SELECT id FROM communities WHERE name=?", (name,)).fetchone()
        if not exists:
            if not DRY_RUN:
                get_or_create_community(social, reddit_id, name, display_name, owner, topic)
            print(f"  [ADDED] {display_name}")
            stats["s2_communities_added"] += 1
        else:
            print(f"  [exists] {display_name}")

    print(f"  -> {stats['s2_communities_added']} communities added")


# ── Section 3: Parse DISPATCH_LOG.md ──────────────────────────────────────────

def section3_dispatches(social):
    print("\n=== SECTION 3: Parse DISPATCH_LOG.md ===")

    dispatch_log_path = os.path.join(DIE_NAMIC, "docs", "creative_works", "gerald", "DISPATCH_LOG.md")
    rel_path = "die-namic-system/docs/creative_works/gerald/DISPATCH_LOG.md"

    dfr_id      = get_community_id(social, "DispatchesFromReaIity")
    disp_ser    = get_series_id(social, "dispatches")
    reddit_acct = social.execute("SELECT id FROM accounts WHERE handle='BeneficialBig8372'").fetchone()[0]

    if not dfr_id or not disp_ser:
        print("  [WARN] Missing community/series -- skipping")
        return

    content = read_file(dispatch_log_path)
    if not content:
        print("  [WARN] DISPATCH_LOG.md not readable")
        return

    dispatch_rows = []
    for line in content.splitlines():
        line = line.strip()
        if not line.startswith('|'):
            continue
        if re.match(r'^\|\s*#\s*\|', line) or re.match(r'^\|[-| ]+\|$', line):
            continue
        # Match rows whose first cell is a number or fraction (9¾ = \u00be)
        m = re.match(
            r'^\|\s*([0-9\u00be\u00bc\u00bd]+)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|',
            line
        )
        if m:
            dispatch_rows.append({
                'num':      m.group(1).strip(),
                'title':    m.group(2).strip(),
                'core_bit': m.group(3).strip(),
                'status':   m.group(4).strip(),
                'notes':    m.group(5).strip(),
            })

    print(f"  Parsed {len(dispatch_rows)} dispatch rows")

    for d in dispatch_rows:
        num       = d['num']
        raw_title = d['title']
        core_bit  = d['core_bit']
        status    = d['status']
        notes_val = d['notes']

        if raw_title in ('', '\u2014', '-', '--'):
            if 'unknown' in status.lower():
                title      = f"DISPATCH #{num}: [Unknown]"
                post_notes = f"Gap in records -- {notes_val}" if notes_val else "Gap in records"
                if not DRY_RUN:
                    _, created = get_or_create_post(social, title, dfr_id, disp_ser, reddit_acct, 'unknown_gap', post_notes)
                    if created:
                        stats["s3_dispatches_upserted"] += 1
                print(f"  [GAP ] {title}")
            continue

        title = f"DISPATCH #{num}: {raw_title}"

        if 'posted' in status.lower():
            post_notes = core_bit if core_bit and core_bit not in ('', '\u2014', '-') else None
            if not DRY_RUN:
                post_id, created = get_or_create_post(social, title, dfr_id, disp_ser, reddit_acct, 'active', post_notes)
                if created:
                    stats["s3_dispatches_upserted"] += 1
                    print(f"  [NEW ] {title}")
                else:
                    print(f"  [SKIP] {title} (exists)")
                added = add_post_file_deduped(social, post_id, rel_path, 'dispatch_log', 'dispatch_log', f"Dispatch #{num} -- {core_bit}")
                if added:
                    stats["s3_post_files_added"] += 1
            else:
                print(f"  [DRY ] {title}")

        elif 'unknown' in status.lower():
            post_notes = f"Gap in records -- {notes_val}" if notes_val else "Gap in records"
            if not DRY_RUN:
                _, created = get_or_create_post(social, title, dfr_id, disp_ser, reddit_acct, 'unknown_gap', post_notes)
                if created:
                    stats["s3_dispatches_upserted"] += 1
            print(f"  [GAP ] {title}")

    # Dispatch #18
    d18 = "DISPATCH #18: Squeakdog Revelation"
    if not DRY_RUN:
        _, created = get_or_create_post(social, d18, dfr_id, disp_ser, reddit_acct, 'active',
                                        "From SQUEAKDOG_REVELATION_HANDOFF_v1.2.md")
        if created:
            stats["s3_dispatches_upserted"] += 1
            print(f"  [NEW ] {d18}")
        else:
            print(f"  [SKIP] {d18} (exists)")
    else:
        print(f"  [DRY ] {d18}")

    # Dispatch #19 — already in DB as "DISPATCH #19: The Squeakdog Lecture"
    d19 = "DISPATCH #19: The Squeakdog Lecture"
    exists = social.execute("SELECT id FROM posts WHERE title LIKE '%Squeakdog Lecture%'").fetchone()
    if not exists and not DRY_RUN:
        _, created = get_or_create_post(social, d19, dfr_id, disp_ser, reddit_acct, 'draft',
                                        "Draft. Not yet posted to Reddit.")
        if created:
            stats["s3_dispatches_upserted"] += 1
    print(f"  [{'SKIP' if exists else 'NEW '}] {d19}")

    print(f"  -> {stats['s3_dispatches_upserted']} dispatches upserted, {stats['s3_post_files_added']} post_files added")


# ── Section 4: Performance benchmark posts ────────────────────────────────────

def section4_benchmarks(social):
    print("\n=== SECTION 4: Performance benchmark posts ===")

    reddit_id   = social.execute("SELECT id FROM platforms WHERE name='Reddit'").fetchone()[0]
    reddit_acct = social.execute("SELECT id FROM accounts WHERE handle='BeneficialBig8372'").fetchone()[0]
    source_file = "die-namic-system/docs/ops/reddit_analytics/PERFORMANCE_BENCHMARKS.md"

    posts_to_add = [
        ("UTETY Framework Post",
         "LLMPhysics", 15000, 82, None,
         "#2 all-time. Framework post."),
        ("A ridiculous story that I thought Douglas Adams fans would enjoy, bring a towel",
         "douglasadams", 5000, 96, 156,
         "Gerald breakout. Rotisserie/stapler/mop. #3 all-time"),
        ("French Toast and the Fundamental Forces",
         "LLMPhysics", 4900, 97, 28,
         "Oakenscroll. #6 all-time on sub. #4 all-time overall"),
        ("Hotdog Physics",
         "LLMPhysics", 4200, 44, 10,
         "#5 all-time overall. Gerald"),
        ("Cat with a brain too big for its body",
         "StuffOnCats", 2900, 100, 2,
         "#1 all-time on r/StuffOnCats. 100% ratio. #6 all-time overall"),
        ("Grand Unification Theory",
         "sciencememes", 2100, 71, 0,
         "Removed then reinstated. #7 all-time overall"),
        ("Constitutional Debate",
         "DispatchesFromReaIity", 1400, 100, 5,
         "63% international. 100% ratio. #8 all-time overall"),
    ]

    for title, community_name, views, upvote_ratio, shares, notes in posts_to_add:
        community_id = get_community_id(social, community_name)
        if not community_id:
            if not DRY_RUN:
                community_id, _ = get_or_create_community(
                    social, reddit_id, community_name, f"r/{community_name}", "unknown", "unknown"
                )
            else:
                print(f"  [DRY ] {title[:60]} (community r/{community_name} not yet added)")
                stats["s4_posts_upserted"] += 1
                continue

        if not DRY_RUN:
            post_id, created = get_or_create_post(social, title, community_id, None, reddit_acct, 'active', notes)
            if created:
                stats["s4_posts_upserted"] += 1
                print(f"  [NEW ] {title[:70]}")
            else:
                print(f"  [SKIP] {title[:70]} (exists)")

            # Insert metrics — check for existing first
            existing_metric = social.execute(
                "SELECT id FROM post_metrics WHERE post_id=? AND snapshot_at=?",
                (post_id, '2026-01-02')
            ).fetchone()
            if not existing_metric:
                social.execute(
                    "INSERT INTO post_metrics(post_id, snapshot_at, views_total, upvote_ratio, shares, source_file) VALUES (?,?,?,?,?,?)",
                    (post_id, '2026-01-02', views, upvote_ratio, shares if shares else None, source_file)
                )
                social.commit()
                stats["s4_metrics_added"] += 1

            if shares and shares > 0:
                existing_ms = social.execute(
                    "SELECT id FROM milestones WHERE post_id=? AND milestone LIKE 'top performer%'",
                    (post_id,)
                ).fetchone()
                if not existing_ms:
                    social.execute(
                        "INSERT INTO milestones(post_id, account_id, milestone, achieved_at, metric_value) VALUES (?,?,?,?,?)",
                        (post_id, reddit_acct, f"top performer: {views:,} views, {shares} shares", '2026-01-02',
                         f"{views:,} views / {upvote_ratio}% ratio / {shares} shares")
                    )
                    social.commit()
                    stats["s4_milestones_added"] += 1

            if upvote_ratio == 100:
                existing_ms = social.execute(
                    "SELECT id FROM milestones WHERE post_id=? AND milestone='100% upvote ratio'",
                    (post_id,)
                ).fetchone()
                if not existing_ms:
                    social.execute(
                        "INSERT INTO milestones(post_id, account_id, milestone, achieved_at, metric_value) VALUES (?,?,?,?,?)",
                        (post_id, reddit_acct, "100% upvote ratio", '2026-01-02', f"{views:,} views at 100% ratio")
                    )
                    social.commit()
                    stats["s4_milestones_added"] += 1
        else:
            print(f"  [DRY ] {title[:70]} -- r/{community_name} {views:,}v {upvote_ratio}%")
            stats["s4_posts_upserted"] += 1

    print(f"  -> {stats['s4_posts_upserted']} posts, {stats['s4_metrics_added']} metrics, {stats['s4_milestones_added']} milestones")


# ── Section 5: Add new projects ───────────────────────────────────────────────

def section5_projects(social):
    print("\n=== SECTION 5: Add new projects ===")

    new_projects = [
        ('The Gate', 'the-gate',
         "DCI drum corps show. Mussorgsky/Ravel Pictures at an Exhibition. Transformation reveal at Finals. "
         "August 8, 2026, Lucas Oil Stadium. Full pitch package. Pitched to Blue Knights and The Academy.",
         'active'),
        ('The Seventeen Problem', 'seventeen',
         "Creative project. Seventeen Burns. Seventeen squeakdogs. Raw interviews. Handoff exists.",
         'in_development'),
        ('Hollywood Pitches', 'hollywood-pitches',
         "Franklin's Two-Headed Snake (documentary/docuseries, proof of concept). "
         "The Mighty Cat Brain Named Me Sweet Pea (documentary). "
         "Mann Family Patterns. The Gate (DCI).",
         'active'),
    ]

    for title, slug, description, status in new_projects:
        exists = social.execute("SELECT id FROM projects WHERE slug=?", (slug,)).fetchone()
        if not exists:
            if not DRY_RUN:
                social.execute(
                    "INSERT OR IGNORE INTO projects(title, slug, description, status) VALUES (?,?,?,?)",
                    (title, slug, description, status)
                )
                social.commit()
            print(f"  [ADDED] {title}")
            stats["s5_projects_added"] += 1
        else:
            print(f"  [exists] {title}")

    print(f"  -> {stats['s5_projects_added']} projects added")


# ── Section 6: Link creative_works docs to series_files ───────────────────────

def section6_series_files(social):
    print("\n=== SECTION 6: Link creative_works docs to series_files ===")

    bom_b1 = get_series_id(social, "bom-book-one")
    bom_b2 = get_series_id(social, "bom-book-two")
    bom_b4 = get_series_id(social, "bom-book-four")
    gerald = get_series_id(social, "gerald")
    wic    = get_series_id(social, "what-i-carried")

    def link(series_id, rel_path, file_type=None, notes=""):
        if series_id is None:
            return False
        ft = file_type or infer_file_type(rel_path)
        if not DRY_RUN:
            added = add_series_file_deduped(social, series_id, rel_path, ft, notes)
            if added:
                stats["s6_series_files_added"] += 1
            return added
        else:
            exists = social.execute(
                "SELECT id FROM series_files WHERE series_id=? AND file_path=?",
                (series_id, rel_path)
            ).fetchone()
            if not exists:
                stats["s6_series_files_added"] += 1
                return True
            return False

    # books_of_mann/ -> bom-book-one; world/character also -> bom-book-two, bom-book-four
    bom_dir = os.path.join(CREATIVE_WORKS, "books_of_mann")
    if os.path.isdir(bom_dir):
        for fname in sorted(os.listdir(bom_dir)):
            if not fname.endswith('.md'):
                continue
            rel = f"die-namic-system/docs/creative_works/books_of_mann/{fname}"
            added = link(bom_b1, rel)
            print(f"  {'[NEW]' if added else '[---]'} bom-book-one <- {fname}")
            if fname.upper() in ('WORLD_ARCHITECTURE.MD', 'CHARACTER_BIBLE.MD'):
                for sid, label in [(bom_b2, "bom-book-two"), (bom_b4, "bom-book-four")]:
                    link(sid, rel)
                    print(f"         also -> {label}")

    # gerald/ -> gerald
    gerald_dir = os.path.join(CREATIVE_WORKS, "gerald")
    if os.path.isdir(gerald_dir):
        for fname in sorted(os.listdir(gerald_dir)):
            if not fname.endswith('.md'):
                continue
            rel = f"die-namic-system/docs/creative_works/gerald/{fname}"
            added = link(gerald, rel)
            print(f"  {'[NEW]' if added else '[---]'} gerald <- {fname}")

    # naming-things-broken-dead/ -> what-i-carried
    ntbd_dir = os.path.join(CREATIVE_WORKS, "naming-things-broken-dead")
    if os.path.isdir(ntbd_dir):
        for fname in sorted(os.listdir(ntbd_dir)):
            if not fname.endswith('.md'):
                continue
            rel = f"die-namic-system/docs/creative_works/naming-things-broken-dead/{fname}"
            added = link(wic, rel)
            print(f"  {'[NEW]' if added else '[---]'} what-i-carried <- naming-things-broken-dead/{fname}")

    # poetry/ -> what-i-carried
    poetry_dir = os.path.join(CREATIVE_WORKS, "poetry")
    if os.path.isdir(poetry_dir):
        for fname in sorted(os.listdir(poetry_dir)):
            if not fname.endswith('.md'):
                continue
            rel = f"die-namic-system/docs/creative_works/poetry/{fname}"
            added = link(wic, rel)
            print(f"  {'[NEW]' if added else '[---]'} what-i-carried <- poetry/{fname}")

    # essays/ESSAY_COLLECTION.md -> what-i-carried
    essay_path = os.path.join(CREATIVE_WORKS, "essays", "ESSAY_COLLECTION.md")
    if os.path.exists(essay_path):
        added = link(wic, "die-namic-system/docs/creative_works/essays/ESSAY_COLLECTION.md")
        print(f"  {'[NEW]' if added else '[---]'} what-i-carried <- essays/ESSAY_COLLECTION.md")

    # LONDON_ISH_ABSURDISM_STYLE_GUIDE.md -> gerald
    style_path = os.path.join(CREATIVE_WORKS, "LONDON_ISH_ABSURDISM_STYLE_GUIDE.md")
    if os.path.exists(style_path):
        added = link(gerald, "die-namic-system/docs/creative_works/LONDON_ISH_ABSURDISM_STYLE_GUIDE.md")
        print(f"  {'[NEW]' if added else '[---]'} gerald <- LONDON_ISH_ABSURDISM_STYLE_GUIDE.md")

    print(f"  -> {stats['s6_series_files_added']} series_files entries added")


# ── Section 7: Ingest all MD content into willow_knowledge.db ─────────────────

def section7_knowledge(know):
    print("\n=== SECTION 7: Ingest MD content into willow_knowledge.db ===")

    walk_targets = [
        (CREATIVE_WORKS,    "narrative"),
        (REDDIT_ANALYTICS,  "analytics"),
        (HOLLYWOOD_PITCHES, "project"),
    ]

    for base_dir, category in walk_targets:
        if not os.path.isdir(base_dir):
            print(f"  [SKIP] {base_dir} not found")
            continue

        for dirpath, dirnames, filenames in os.walk(base_dir):
            dirnames.sort()
            for fname in sorted(filenames):
                if not fname.endswith('.md'):
                    continue
                full_path = os.path.join(dirpath, fname)
                content = read_file(full_path)
                if not content.strip():
                    continue

                try:
                    rel = Path(full_path).relative_to(Path(DIE_NAMIC).parent).as_posix()
                except ValueError:
                    rel = full_path.replace("\\", "/")

                title_base = Path(fname).stem.replace('_', ' ').replace('-', ' ')
                title = f"{rel} | {title_base}"
                summary = content[:150].replace('\n', ' ').strip()

                if not DRY_RUN:
                    _, is_new = upsert_knowledge(know, title, content, category, summary)
                    if is_new:
                        stats["s7_knowledge_new"] += 1
                        print(f"  [NEW ] [{category[:3]}] {rel}")
                    else:
                        stats["s7_knowledge_existing"] += 1
                else:
                    source_id = hashlib.md5(title.encode('utf-8')).hexdigest()
                    exists = know.execute(
                        "SELECT id FROM knowledge WHERE source_type='die_namic' AND source_id=?",
                        (source_id,)
                    ).fetchone()
                    marker = "exists" if exists else "would add"
                    print(f"  [{marker}] [{category[:3]}] {rel}")
                    if not exists:
                        stats["s7_knowledge_new"] += 1
                    else:
                        stats["s7_knowledge_existing"] += 1

    print(f"  -> {stats['s7_knowledge_new']} new, {stats['s7_knowledge_existing']} existing")


# ── Section 8: Report ─────────────────────────────────────────────────────────

def section8_report(social, know):
    print("\n" + "=" * 60)
    print(f"INGESTION {'(DRY RUN) ' if DRY_RUN else ''}COMPLETE  {datetime.now():%Y-%m-%d %H:%M:%S}")
    print("=" * 60)
    print(f"  S1  Series metadata updated:    {stats['s1_series_updated']}")
    print(f"  S2  Communities added:          {stats['s2_communities_added']}")
    print(f"  S3  Dispatches upserted:        {stats['s3_dispatches_upserted']}")
    print(f"  S3  Post-files entries added:   {stats['s3_post_files_added']}")
    print(f"  S4  Benchmark posts upserted:   {stats['s4_posts_upserted']}")
    print(f"  S4  Post metrics added:         {stats['s4_metrics_added']}")
    print(f"  S4  Milestones added:           {stats['s4_milestones_added']}")
    print(f"  S5  Projects added:             {stats['s5_projects_added']}")
    print(f"  S6  Series-files entries added: {stats['s6_series_files_added']}")
    print(f"  S7  Knowledge atoms new:        {stats['s7_knowledge_new']}")
    print(f"  S7  Knowledge atoms existing:   {stats['s7_knowledge_existing']}")

    if not DRY_RUN:
        print()
        print("  DB row counts after run:")
        for table in ["series", "communities", "posts", "post_metrics",
                      "milestones", "projects", "series_files", "post_files"]:
            try:
                n = social.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                print(f"    social.{table:<22} {n:>5}")
            except Exception:
                pass
        n_dm  = know.execute("SELECT COUNT(*) FROM knowledge WHERE source_type='die_namic'").fetchone()[0]
        n_all = know.execute("SELECT COUNT(*) FROM knowledge").fetchone()[0]
        print(f"    knowledge (die_namic)        {n_dm:>5}")
        print(f"    knowledge (all)              {n_all:>5}")
    print("=" * 60)


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print(f"ingest_die_namic.py  {'[DRY RUN]' if DRY_RUN else '[LIVE]'}")
    print(f"  social_media.db:     {SOCIAL_DB}")
    print(f"  willow_knowledge.db: {KNOWLEDGE_DB}")
    print(f"  die-namic root:      {DIE_NAMIC}")

    social = get_connection()

    know = get_connection()

    try:
        section1_fix_series(social)
        section2_communities(social)
        section3_dispatches(social)
        section4_benchmarks(social)
        section5_projects(social)
        section6_series_files(social)
        section7_knowledge(know)
        section8_report(social, know)
    finally:
        social.close()
        know.close()


if __name__ == "__main__":
    main()

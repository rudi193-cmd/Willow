#!/usr/bin/env python3
"""
NotebookLM Ingestion Pass
=========================
Reads HTML source files from Desktop/NotebookLM notebooks,
strips HTML, extracts chapter text, and populates:
  - social_media.db: chapter/post inventory with file links
  - willow_knowledge.db: narrative knowledge items for RAG

Run: python ingest_notebooklm.py [--dry-run]
"""

import os
import re
import sys
import hashlib
from html.parser import HTMLParser
from datetime import datetime
from pathlib import Path

_WILLOW_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_WILLOW_ROOT))
from core.db import get_connection

NOTEBOOKLM = str(Path.home().parent.parent / 'Users' / 'Sean' / 'Desktop' / 'NotebookLM')

DRY_RUN = "--dry-run" in sys.argv

# ── HTML stripping ─────────────────────────────────────────────────────────────

class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.chunks = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'head'):
            self._skip = True

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'head'):
            self._skip = False
        if tag in ('p', 'div', 'br', 'h1', 'h2', 'h3', 'li'):
            self.chunks.append('\n')

    def handle_data(self, data):
        if not self._skip:
            self.chunks.append(data)

    def get_text(self):
        text = ''.join(self.chunks)
        # Collapse runs of whitespace / blank lines
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()


def strip_html(path):
    """Return plain text from an HTML file."""
    try:
        with open(path, encoding='utf-8', errors='replace') as f:
            html = f.read()
        parser = TextExtractor()
        parser.feed(html)
        return parser.get_text()
    except Exception as e:
        return f"[READ ERROR: {e}]"


def snippet(text, n=400):
    return text[:n].replace('\n', ' ').strip()


# ── Chapter number parsing ─────────────────────────────────────────────────────

ORDINALS = {
    'ONE': 1, 'TWO': 2, 'THREE': 3, 'FOUR': 4, 'FIVE': 5,
    'SIX': 6, 'SEVEN': 7, 'EIGHT': 8, 'NINE': 9, 'TEN': 10,
    'ELEVEN': 11, 'TWELVE': 12, 'THIRTEEN': 13, 'FOURTEEN': 14,
    'FIFTEEN': 15, 'SIXTEEN': 16, 'SEVENTEEN': 17, 'EIGHTEEN': 18,
    'NINETEEN': 19, 'TWENTY': 20, 'TWENTY-ONE': 21, 'TWENTY-TWO': 22,
}

def chapter_num_from_filename(fname):
    """Extract integer chapter number from filenames like '# CHAPTER FOUR.html'."""
    fname = fname.upper().replace('.HTML', '').replace('(1)', '').strip()
    # Match ordinal words
    for word, num in sorted(ORDINALS.items(), key=lambda x: -len(x[0])):
        if word in fname:
            return num
    # Match digits
    m = re.search(r'\b(\d+)\b', fname)
    if m:
        return int(m.group(1))
    return None


def extract_chapter_title(text, chapter_num):
    """Try to pull a subtitle from the text, skipping browser/chapter artifacts."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    for line in lines:
        # Skip browser tab artifacts: "Tab 1", "Tab 2", etc.
        if re.match(r'^Tab\s+\d+$', line, re.IGNORECASE):
            continue
        # Skip bare chapter headings: "CHAPTER TWO", "CHAPTER 9", "TWO", etc.
        if re.match(r'^(chapter\s+)?(\d+|[A-Z][A-Z-]*)$', line, re.IGNORECASE):
            continue
        # Skip if just a bare digit
        if re.match(r'^\d+$', line):
            continue
        if line and len(line) < 120:
            return line
    return None


# ── Notebook definitions ───────────────────────────────────────────────────────

def find_notebook(base, prefix):
    """Find notebook folder by prefix match."""
    for d in os.listdir(base):
        if d.startswith(prefix[:35]):
            return os.path.join(base, d)
    return None


# ── social_media.db helpers ───────────────────────────────────────────────────

def get_or_create_post(conn, account_id, community_id, series_id, title, notes):
    row = conn.execute(
        "SELECT id FROM posts WHERE title=? AND community_id=?",
        (title, community_id)
    ).fetchone()
    if row:
        return row[0], False
    conn.execute(
        "INSERT INTO posts(account_id, community_id, series_id, title, notes, status) VALUES (?,?,?,?,?,?)",
        (account_id, community_id, series_id, title, notes, 'manuscript')
    )
    conn.commit()
    return conn.execute(
        "SELECT id FROM posts WHERE title=? AND community_id=?",
        (title, community_id)
    ).fetchone()[0], True


def add_post_file_deduped(conn, post_id, path, ftype, notes=""):
    exists = conn.execute(
        "SELECT id FROM post_files WHERE post_id=? AND file_path=?",
        (post_id, path)
    ).fetchone()
    if not exists:
        conn.execute(
            "INSERT INTO post_files(post_id, file_path, file_type, notes) VALUES (?,?,?,?)",
            (post_id, path, ftype, notes)
        )
        conn.commit()


# ── willow_knowledge.db helpers ───────────────────────────────────────────────

def upsert_knowledge(conn, title, content, category, summary):
    """Insert into knowledge table if not already present (by source_id)."""
    # Use MD5 of title as stable source_id
    source_id = hashlib.md5(title.encode('utf-8')).hexdigest()
    existing = conn.execute(
        "SELECT id FROM knowledge WHERE source_type='notebooklm' AND source_id=?",
        (source_id,)
    ).fetchone()
    if existing:
        return existing[0], False

    snip = snippet(content, 400)
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn.execute("""
        INSERT INTO knowledge(source_type, source_id, title, summary, content_snippet, category, ring, created_at)
        VALUES (?,?,?,?,?,?,?,?)
    """, ('notebooklm', source_id, title, summary, snip, category, 'bridge', now))
    conn.commit()
    return conn.execute(
        "SELECT id FROM knowledge WHERE source_type='notebooklm' AND source_id=?",
        (source_id,)
    ).fetchone()[0], True


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    social  = get_connection()
    know    = get_connection()

    # Lookup IDs
    acct    = social.execute("SELECT id FROM accounts WHERE handle='BeneficialBig8372'").fetchone()[0]
    dfr_com = social.execute("SELECT id FROM communities WHERE name='DispatchesFromReaIity'").fetchone()[0]
    rj_ser  = social.execute("SELECT id FROM series WHERE slug='regarding-jane'").fetchone()[0]
    wic_ser = social.execute("SELECT id FROM series WHERE slug='what-i-carried'").fetchone()[0]
    disp_ser= social.execute("SELECT id FROM series WHERE slug='dispatches'").fetchone()[0]
    ger_ser = social.execute("SELECT id FROM series WHERE slug='gerald'").fetchone()[0]
    bom_proj= social.execute("SELECT id FROM projects WHERE slug='books-of-mann'").fetchone()[0]

    # Get or create BOM Book One series
    bom_b1 = social.execute("SELECT id FROM series WHERE slug='bom-book-one'").fetchone()
    if not bom_b1:
        social.execute("""
            INSERT INTO series(title, slug, description, status, project_id)
            VALUES (?,?,?,?,?)
        """, ('Book One: The Detective', 'bom-book-one',
              'Book One of The Books of Mann. Robert Patrick Mann (The Detective) protagonist. Under the dome.',
              'active', bom_proj))
        social.commit()
    bom_b1_id = social.execute("SELECT id FROM series WHERE slug='bom-book-one'").fetchone()[0]

    bom_b4 = social.execute("SELECT id FROM series WHERE slug='bom-book-four'").fetchone()
    if not bom_b4:
        social.execute("""
            INSERT INTO series(title, slug, description, status, project_id)
            VALUES (?,?,?,?,?)
        """, ('Book Four: The Convergence', 'bom-book-four',
              'Book Four of The Books of Mann. Convergence event. Structure not yet fully formed.',
              'active', bom_proj))
        social.commit()
    bom_b4_id = social.execute("SELECT id FROM series WHERE slug='bom-book-four'").fetchone()[0]

    stats = {
        'chapters_found': 0,
        'posts_new': 0,
        'posts_existing': 0,
        'knowledge_new': 0,
        'knowledge_existing': 0,
    }

    print(f"{'DRY RUN — ' if DRY_RUN else ''}Ingesting NotebookLM sources...\n")

    # ── 1. Books of Mann — Book One chapters ──────────────────────────────────
    bom_nb = find_notebook(NOTEBOOKLM, 'The Books of Mann')
    if bom_nb:
        sources_dir = os.path.join(bom_nb, 'Sources')
        print("=== BOOKS OF MANN — Book One (# CHAPTER N.html) ===")

        seen_ch_nums = set()
        for fname in sorted(os.listdir(sources_dir)):
            if not fname.endswith('.html') or not fname.startswith('# CHAPTER'):
                continue
            # Skip THE LETTER UNDER BLUE SKY for now
            if 'LETTER' in fname.upper():
                continue

            ch_num = chapter_num_from_filename(fname)
            if ch_num is None:
                continue
            # Skip duplicate chapter files (e.g. # CHAPTER NINE(1).html)
            if ch_num in seen_ch_nums:
                print(f"  [SKIP dup] {fname}")
                continue
            seen_ch_nums.add(ch_num)

            path = os.path.join(sources_dir, fname)
            text = strip_html(path)
            subtitle = extract_chapter_title(text, ch_num)
            title = f"BOOK ONE — Chapter {ch_num}" + (f": {subtitle}" if subtitle and len(subtitle) < 80 else "")
            rel_path = f"Desktop/NotebookLM/The Books of Mann/Sources/{fname}"

            stats['chapters_found'] += 1
            print(f"  Ch.{ch_num:>2}  {title[:70]}")

            if not DRY_RUN:
                post_id, is_new = get_or_create_post(
                    social, acct, dfr_com, bom_b1_id, title,
                    f"Books of Mann Book One Chapter {ch_num}. Source: NotebookLM."
                )
                stats['posts_new' if is_new else 'posts_existing'] += 1
                add_post_file_deduped(social, post_id, rel_path, 'notebooklm_source',
                                      f"Chapter {ch_num} HTML source")

                kid, is_new_k = upsert_knowledge(
                    know, title, text, 'narrative',
                    f"Books of Mann Book One Chapter {ch_num}. {snippet(text, 150)}"
                )
                stats['knowledge_new' if is_new_k else 'knowledge_existing'] += 1

        # Book Two chapter 1 and structure docs
        print("\n=== BOOKS OF MANN — Book Two / Structure ===")
        bom_b2_files = [
            ('Book 2 chapter 1 draft.html', 'Book Two Chapter 1 — Draft', 'bom-book-two'),
            ('Locked in book 2 story arc.html', 'Book Two — Locked Story Arc', 'bom-book-two'),
            ('--LOCKED.html', 'Books of Mann — Locked Structure', 'bom-book-two'),
            ('Book 4 prologue.html', 'Book Four — Prologue', 'bom-book-four'),
        ]
        bom_b2_id = social.execute("SELECT id FROM series WHERE slug='bom-book-two'").fetchone()[0]

        for fname, label, series_slug in bom_b2_files:
            path = os.path.join(sources_dir, fname)
            if not os.path.exists(path):
                continue
            text = strip_html(path)
            rel_path = f"Desktop/NotebookLM/The Books of Mann/Sources/{fname}"
            ser_id = bom_b2_id if series_slug == 'bom-book-two' else bom_b4_id

            print(f"  {label[:70]}")
            stats['chapters_found'] += 1

            if not DRY_RUN:
                post_id, is_new = get_or_create_post(
                    social, acct, dfr_com, ser_id, label,
                    f"Source: NotebookLM. {snippet(text, 100)}"
                )
                stats['posts_new' if is_new else 'posts_existing'] += 1
                add_post_file_deduped(social, post_id, rel_path, 'notebooklm_source')

                kid, is_new_k = upsert_knowledge(know, label, text, 'narrative',
                    f"{label}. {snippet(text, 150)}")
                stats['knowledge_new' if is_new_k else 'knowledge_existing'] += 1

        # What I Carried Full Manuscript (in BOM notebook)
        wic_path = os.path.join(sources_dir, 'What I Carried - Full Manuscript.html')
        if os.path.exists(wic_path):
            text = strip_html(wic_path)
            rel_path = "Desktop/NotebookLM/The Books of Mann/Sources/What I Carried - Full Manuscript.html"
            print(f"\n  What I Carried — Full Manuscript ({len(text):,} chars)")
            if not DRY_RUN:
                kid, is_new_k = upsert_knowledge(
                    know, 'What I Carried — Full Manuscript (NotebookLM)',
                    text, 'narrative',
                    f"Complete manuscript. {len(text):,} chars. {snippet(text, 150)}"
                )
                stats['knowledge_new' if is_new_k else 'knowledge_existing'] += 1
                # Link to series_files
                wic_ser_row = social.execute("SELECT id FROM series WHERE slug='what-i-carried'").fetchone()[0]
                social.execute(
                    "INSERT OR IGNORE INTO series_files(series_id, file_path, file_type, notes) VALUES (?,?,?,?)",
                    (wic_ser_row, rel_path, 'manuscript_html', 'Full manuscript via NotebookLM BOM notebook')
                )
                social.commit()

    # ── 2. Regarding Jane (Alchemical Receipt of Jane Hughes) ─────────────────
    rj_nb = find_notebook(NOTEBOOKLM, 'The Alchemical Receipt of Jane Hughes')
    if rj_nb:
        sources_dir = os.path.join(rj_nb, 'Sources')
        print("\n=== REGARDING JANE (Alchemical Receipt of Jane Hughes) ===")

        text_files = sorted([f for f in os.listdir(sources_dir)
                             if f.endswith('.html') and f.startswith('Text')])

        for i, fname in enumerate(text_files):
            path = os.path.join(sources_dir, fname)
            text = strip_html(path)
            ch_label = f"Chapter {i + 1}" if fname == 'Text.html' else f"Section {i + 1}"
            subtitle = extract_chapter_title(text, i + 1)
            title = f"Regarding Jane — {ch_label}" + (f": {subtitle}" if subtitle and len(subtitle) < 80 else "")
            rel_path = f"Desktop/NotebookLM/The Alchemical Receipt of Jane Hughes/Sources/{fname}"

            stats['chapters_found'] += 1
            print(f"  [{fname}]  {len(text):>6,}c  {title[:60]}")

            if not DRY_RUN:
                post_id, is_new = get_or_create_post(
                    social, acct, dfr_com, rj_ser, title,
                    f"Regarding Jane source. NotebookLM: Alchemical Receipt. {snippet(text, 80)}"
                )
                stats['posts_new' if is_new else 'posts_existing'] += 1
                add_post_file_deduped(social, post_id, rel_path, 'notebooklm_source')

                kid, is_new_k = upsert_knowledge(know, title, text, 'narrative',
                    f"Regarding Jane. {snippet(text, 150)}")
                stats['knowledge_new' if is_new_k else 'knowledge_existing'] += 1

    # ── 3. Dispatches (key items) ─────────────────────────────────────────────
    disp_nb = find_notebook(NOTEBOOKLM, 'Dispatches from Reality_ Gerald, Jane, and Cosmolo')
    if disp_nb:
        sources_dir = os.path.join(disp_nb, 'Sources')
        print("\n=== DISPATCHES FROM REALITY ===")

        for fname in sorted(os.listdir(sources_dir)):
            if not fname.endswith('.html'):
                continue
            path = os.path.join(sources_dir, fname)
            text = strip_html(path)
            label = fname.replace('.html', '').replace('_', ' ').strip()
            rel_path = f"Desktop/NotebookLM/Dispatches from Reality/Sources/{fname}"

            # Detect dispatch number
            dm = re.search(r'DISPATCH\s*#?(\d+)', label, re.IGNORECASE)
            title = label if len(label) < 100 else label[:97] + '...'

            stats['chapters_found'] += 1
            print(f"  {title[:70]}")

            if not DRY_RUN:
                # Dispatches go as posts
                post_id, is_new = get_or_create_post(
                    social, acct, dfr_com, disp_ser if dm else ger_ser,
                    title,
                    f"NotebookLM source. {snippet(text, 80)}"
                )
                stats['posts_new' if is_new else 'posts_existing'] += 1
                add_post_file_deduped(social, post_id, rel_path, 'notebooklm_source')

                kid, is_new_k = upsert_knowledge(know, title, text, 'narrative',
                    f"Dispatch/Gerald content. {snippet(text, 150)}")
                stats['knowledge_new' if is_new_k else 'knowledge_existing'] += 1

    # ── 4. WC Case notebook ───────────────────────────────────────────────────
    wc_nb = find_notebook(NOTEBOOKLM, 'Sean Campbell_ Workers_ Compensation Case and Medi')
    if wc_nb:
        print("\n=== WORKERS COMP CASE (MT-0004) ===")
        # Just ingest the .md artifacts — structured analysis
        artifacts_dir = os.path.join(wc_nb, 'Artifacts')
        if os.path.exists(artifacts_dir):
            for fname in sorted(os.listdir(artifacts_dir)):
                if not fname.endswith('.md'):
                    continue
                path = os.path.join(artifacts_dir, fname)
                with open(path, encoding='utf-8', errors='replace') as f:
                    text = f.read()
                title = fname.replace('.md', '').strip()
                print(f"  {title[:70]}")

                if not DRY_RUN:
                    kid, is_new_k = upsert_knowledge(
                        know, f"WC-MT0004: {title}", text, 'legal',
                        f"Workers Comp MT-0004. {snippet(text, 150)}"
                    )
                    stats['knowledge_new' if is_new_k else 'knowledge_existing'] += 1

    # ── Report ─────────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"INGESTION {'(DRY RUN) ' if DRY_RUN else ''}COMPLETE")
    print(f"{'='*60}")
    print(f"  Source items found: {stats['chapters_found']}")
    print(f"  Posts new:          {stats['posts_new']}")
    print(f"  Posts existing:     {stats['posts_existing']}")
    print(f"  Knowledge new:      {stats['knowledge_new']}")
    print(f"  Knowledge existing: {stats['knowledge_existing']}")

    if not DRY_RUN:
        total_posts = social.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
        total_k = know.execute("SELECT COUNT(*) FROM knowledge WHERE category='narrative'").fetchone()[0]
        print(f"\n  Total posts in DB:        {total_posts}")
        print(f"  Total narrative knowledge: {total_k}")

        # Series breakdown
        print("\n  Series after ingestion:")
        for row in social.execute("""
            SELECT p.title as proj, s.title as ser, COUNT(po.id) as cnt
            FROM series s
            LEFT JOIN posts po ON po.series_id = s.id
            LEFT JOIN projects p ON s.project_id = p.id
            GROUP BY s.id ORDER BY p.title, s.title
        """).fetchall():
            print(f"    {(row[0] or 'no project')[:35]:<35} -> {row[1][:35]:<35} {row[2]} posts")

    social.close()
    know.close()


if __name__ == "__main__":
    main()

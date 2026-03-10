#!/usr/bin/env python3
"""
Add file-linking tables and seed known hard drive files into social_media.db.
"""
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from core.db import get_connection

conn = get_connection()

# Create tables
conn.execute("""
CREATE TABLE IF NOT EXISTS post_files (
    id          INTEGER PRIMARY KEY,
    post_id     INTEGER REFERENCES posts(id),
    file_path   TEXT NOT NULL,
    file_type   TEXT,
    source      TEXT,
    notes       TEXT
)
""")

conn.execute("""
CREATE TABLE IF NOT EXISTS series_files (
    id          INTEGER PRIMARY KEY,
    series_id   INTEGER REFERENCES series(id),
    file_path   TEXT NOT NULL,
    file_type   TEXT,
    notes       TEXT
)
""")
conn.commit()
print("Tables created.")

# Lookup helpers
def pid(title_fragment):
    r = conn.execute("SELECT id FROM posts WHERE title LIKE ?", (f"%{title_fragment}%",)).fetchone()
    return r[0] if r else None

def sid(slug):
    r = conn.execute("SELECT id FROM series WHERE slug=?", (slug,)).fetchone()
    return r[0] if r else None

def add_post_file(post_id, path, ftype, source, notes=""):
    if post_id is None:
        print(f"  [SKIP] no post found for file: {path}")
        return
    conn.execute(
        "INSERT INTO post_files(post_id, file_path, file_type, source, notes) VALUES (?,?,?,?,?)",
        (post_id, path, ftype, source, notes)
    )

def add_series_file(series_id, path, ftype, notes=""):
    if series_id is None:
        return
    conn.execute(
        "INSERT INTO series_files(series_id, file_path, file_type, notes) VALUES (?,?,?,?)",
        (series_id, path, ftype, notes)
    )


# ── Regarding Jane ────────────────────────────────────────────────────────────
rj = sid("regarding-jane")

add_post_file(pid("Chapter 1"), "artifacts/Sweet-Pea-Rudi19/narrative/Regarding Jane - Chapter 1- The Receipt.pdf",
              "published_pdf", "google_docs", "Chapter 1: The Receipt")
add_post_file(pid("Chapter Four"), "artifacts/Sweet-Pea-Rudi19/narrative/REGARDING JANE — Chapter Four- The Chicken Salad.pdf",
              "published_pdf", "google_docs", "Chapter 4: The Chicken Salad")
add_post_file(pid("Chapter Five"), "artifacts/Sweet-Pea-Rudi19/narrative/REGARDING JANE — Chapter Five.pdf",
              "published_pdf", "google_docs", "Chapter 5: The Seven Fools")

# Chapters on disk but NOT yet in social posts (9, 10, 11)
# Insert them as posts first, then link
dfr = conn.execute("SELECT id FROM communities WHERE name='DispatchesFromReaIity'").fetchone()[0]
acct = conn.execute("SELECT id FROM accounts WHERE handle='BeneficialBig8372'").fetchone()[0]

new_rj_chapters = [
    ("REGARDING JANE - Chapter Nine", None, "Chapter 9 — on disk, not yet posted or OCR captured"),
    ("REGARDING JANE - Chapter Ten: The In-Between", None, "Chapter 10: The In-Between — on disk"),
    ("REGARDING JANE - Chapter Eleven: The Same Car", None, "Chapter 11: The Same Car — on disk"),
]
for title, date, notes in new_rj_chapters:
    existing = conn.execute("SELECT id FROM posts WHERE title=?", (title,)).fetchone()
    if not existing:
        conn.execute(
            "INSERT INTO posts(account_id, community_id, series_id, title, posted_at, notes) VALUES (?,?,?,?,?,?)",
            (acct, dfr, rj, title, date, notes)
        )
conn.commit()

add_post_file(pid("Chapter Nine"), "artifacts/Sweet-Pea-Rudi19/narrative/REGARDING JANE CHAPTER NINE.pdf",
              "published_pdf", "google_docs")
add_post_file(pid("Chapter Ten"), "artifacts/Sweet-Pea-Rudi19/narrative/REGARDING JANE - CHAPTER TEN- The In-Between.pdf",
              "published_pdf", "google_docs")
add_post_file(pid("Chapter Eleven: The Same Car"), "artifacts/Sweet-Pea-Rudi19/narrative/REGARDING JANE - CHAPTER ELEVEN- The Same Car.pdf",
              "published_pdf", "google_docs")


# ── What I Carried ────────────────────────────────────────────────────────────
wic = sid("what-i-carried")
add_series_file(wic, "artifacts/Sweet-Pea-Rudi19/narrative/What I Carried - Full Manuscript.pdf",
                "manuscript", "Full compiled manuscript — all chapters")
add_series_file(wic, "artifacts/Sweet-Pea-Rudi19/narrative/What_I_Carried_Afterword.pdf",
                "afterword", "Afterword — status locked per context store")


# ── Dispatches ────────────────────────────────────────────────────────────────
disp = sid("dispatches")
add_post_file(pid("DISPATCH 6"), "artifacts/Sweet-Pea-Rudi19/narrative/⭐ Dispatch #6- Gerald Does Not Approve of My Weather Strategy (1).pdf",
              "published_pdf", "google_docs",
              "Reddit title 'Friday Night, Saturday Morning' may be different post — verify")

# Dispatch #19 exists as draft — not yet in social posts
existing = conn.execute("SELECT id FROM posts WHERE title LIKE '%Squeakdog%'").fetchone()
if not existing:
    conn.execute(
        "INSERT INTO posts(account_id, community_id, series_id, title, posted_at, status, notes) VALUES (?,?,?,?,?,?,?)",
        (acct, dfr, disp,
         "DISPATCH #19: The Squeakdog Lecture",
         None, "draft",
         "Draft in knowledge DB. Not yet posted to Reddit.")
    )
conn.commit()
add_post_file(pid("Squeakdog"), "artifacts/Sweet-Pea-Rudi19/_proposed/dispatches/dispatch_19_squeakdog_lecture_draft.md",
              "draft", "markdown", "Draft — corner shop hotdog rolls off rotisserie with intention")


# ── Itchy Things Collection ────────────────────────────────────────────────────
# These are posted but not tracked as a series yet
itchy = conn.execute("SELECT id FROM series WHERE slug='itchy-things'").fetchone()
if not itchy:
    conn.execute("""
        INSERT INTO series(title, slug, description, status)
        VALUES (?,?,?,?)
    """, ("The Itchy Things Collection", "itchy-things",
          "Short narrative pieces. Series Bible exists. Posted to Reddit/DFR. Sweater, Ungentle Blessing, What We Say.",
          "active"))
    conn.commit()

itchy_id = conn.execute("SELECT id FROM series WHERE slug='itchy-things'").fetchone()[0]
add_series_file(itchy_id,
    "artifacts/Sweet-Pea-Rudi19/narrative/SERIES_BIBLE.md",
    "bible", "The Itchy Things Collection series bible v1.0")

itchy_posts = [
    ("The Sweater Can Rest Now",  "SWEATER_CAN_REST_NOW.md",      "posted"),
    ("The Ungentle Blessing",     "THE_UNGENTLE_BLESSING.md",     "posted"),
    ("Why the Whole Sweater Itches in December", "WHY_SWEATER_ITCHES_DECEMBER.md", "posted"),
    ("What We Say When They Go",  "WHAT_WE_SAY_WHEN_THEY_GO.md", "posted"),
]
for title, fname, status in itchy_posts:
    existing = conn.execute("SELECT id FROM posts WHERE title=?", (title,)).fetchone()
    if not existing:
        conn.execute(
            "INSERT INTO posts(account_id, community_id, series_id, title, status, notes) VALUES (?,?,?,?,?,?)",
            (acct, dfr, itchy_id, title, status, f"Source: {fname}")
        )
conn.commit()
for title, fname, _ in itchy_posts:
    add_post_file(pid(title), f"artifacts/Sweet-Pea-Rudi19/narrative/{fname}",
                  "published_md", "markdown")


# ── Gerald Universe ────────────────────────────────────────────────────────────
ger = sid("gerald")
add_series_file(ger,
    "artifacts/Sweet-Pea-Rudi19/narrative/The Geraldverse Hero's Journey.pdf",
    "bible", "Gerald universe hero's journey structure — PDF")
add_series_file(ger,
    "artifacts/Sweet-Pea-Rudi19/narrative/Professor_Oakenscroll_Character_Bible-1.docx",
    "character_bible", "Oakenscroll character bible — DOCX")
add_series_file(ger,
    "artifacts/Sweet-Pea-Rudi19/narrative/NYE_TOAST_SQUEAKDOGS.md",
    "published", "NYE Toast by Oakenscroll to the Squeakdog Society of Kent")
add_post_file(pid("Squeakdog"),
    "artifacts/Sweet-Pea-Rudi19/narrative/NYE_TOAST_SQUEAKDOGS.md",
    "related", "markdown", "Oakenscroll NYE toast — Squeakdog Society of Kent")


# ── Douglas Adams crosspost ────────────────────────────────────────────────────
add_series_file(ger,
    "artifacts/Sweet-Pea-Rudi19/narrative/A ridiculous story that I thought Douglas Adams fans would enjoy, bring a towel.pdf",
    "published_pdf", "Likely the r/douglasadams crosspost of Gerald at the Laundromat")

conn.commit()

# ── Report ─────────────────────────────────────────────────────────────────────
print("\n=== SERIES FILES ===")
rows = conn.execute("""
    SELECT s.title, sf.file_path, sf.file_type
    FROM series_files sf JOIN series s ON sf.series_id = s.id
    ORDER BY s.title, sf.file_type
""").fetchall()
for r in rows:
    print(f"  [{r[2]}] {r[0]} → {r[2]}: {r[1].split('/')[-1]}")

print("\n=== POST → FILE LINKS ===")
rows = conn.execute("""
    SELECT p.title, pf.file_path, pf.file_type
    FROM post_files pf JOIN posts p ON pf.post_id = p.id
    ORDER BY p.title
""").fetchall()
for r in rows:
    print(f"  {r[2]:<20} {r[0][:45]:<45} → {r[1].split('/')[-1]}")

print("\n=== TOTAL POSTS NOW ===")
total = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
print(f"  {total} posts in social_media.db")

print("\n=== SERIES EPISODE COUNTS ===")
rows = conn.execute("""
    SELECT s.title, COUNT(p.id) as cnt
    FROM series s LEFT JOIN posts p ON p.series_id = s.id
    GROUP BY s.id ORDER BY cnt DESC
""").fetchall()
for r in rows:
    print(f"  {r[0]}: {r[1]} posts")

conn.close()
print("\nDone.")

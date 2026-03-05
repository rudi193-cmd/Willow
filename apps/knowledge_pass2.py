#\!/usr/bin/env python3
"""Knowledge Pass 2 -- Fleet-powered summary enrichment.
Uses llm_router.ask() to generate better summaries.
Run: python apps/knowledge_pass2.py [--limit N] [--source-type TYPE]
"""
import sys, os, sqlite3, time, argparse
sys.path.insert(0, "C:/Users/Sean/Documents/GitHub/Willow/core")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DB = "C:/Users/Sean/Documents/GitHub/Willow/artifacts/Sweet-Pea-Rudi19/willow_knowledge.db"

PRIORITY_SOURCES = [
    "notebooklm_transcript", "notebooklm_artifact", "notebooklm_source",
    "notebooklm", "ocr_image", "drop_doc", "drop_pdf", "die_namic"
]

def enrich_summary(title, content_snippet, category, source_type, router):
    prompt_parts = [
        "Summarize this knowledge entry in 2-3 sentences.",
        "Be specific about what it contains -- not just what type of document it is.",
        "",
        "Source type: " + str(source_type),
        "Category: " + str(category),
        "Title: " + str(title),
        "Content: " + (content_snippet or "")[:600],
        "",
        "Summary (2-3 sentences, specific):"
    ]
    prompt = chr(10).join(prompt_parts)
    resp = router.ask(prompt, preferred_tier="free")
    return resp.content.strip() if resp else None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--source-type", default=None)
    args = parser.parse_args()
    import llm_router
    llm_router.load_keys_from_json()
    conn = sqlite3.connect(DB)
    unavail = "%Content unavailable%"
    if args.source_type:
        rows = conn.execute(
            "SELECT id, title, content_snippet, category, source_type FROM knowledge "
            "WHERE pass_level=1 AND source_type=? AND content_snippet IS NOT NULL "
            "AND content_snippet NOT LIKE ? ORDER BY id LIMIT ?",
            (args.source_type, unavail, args.limit)
        ).fetchall()
    else:
        ph = ",".join(["?"] * len(PRIORITY_SOURCES))
        q = ("SELECT id, title, content_snippet, category, source_type FROM knowledge "
             "WHERE pass_level=1 AND source_type IN (" + ph + ") "
             "AND content_snippet IS NOT NULL "
             "AND content_snippet NOT LIKE ? ORDER BY id LIMIT ?")
        rows = conn.execute(q, (*PRIORITY_SOURCES, unavail, args.limit)).fetchall()
    print("[PASS2] " + str(len(rows)) + " entries to enrich")
    enriched = 0
    failed = 0
    for row_id, title, snippet, category, source_type in rows:
        new_summary = enrich_summary(title, snippet or "", category, source_type, llm_router)
        if new_summary:
            sql_u = "UPDATE knowledge SET summary=?, pass_level=2, updated_at=CURRENT_TIMESTAMP WHERE id=?"
            conn.execute(sql_u, (new_summary, row_id))
            conn.commit()
            enriched += 1
            print("  [OK] " + str(row_id) + " | " + (title or "")[:60])
        else:
            failed += 1
            print("  [FAIL] " + str(row_id) + " | " + (title or "")[:60])
        time.sleep(0.1)
    print("[PASS2 DONE] enriched=" + str(enriched) + " failed=" + str(failed))
    conn.close()

if __name__ == "__main__":
    main()

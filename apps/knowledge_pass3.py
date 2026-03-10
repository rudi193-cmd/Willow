#!/usr/bin/env python3
import sys, os, time, argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.db import get_connection
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
VALID = {'asserted','speculative','constructed','fictional','mixed','meta','unknown'}
UM = ['oakenscroll','gerald','utety','precausal','squeakdog','squeak dog','rotisserie','threefold sundering','numerical ethics','accidental cosmology','grandmother encoding','stone soup','french toast structural','ledger of non-contributions','cosmic chicken']
PL = ['Classify the epistemic status of this knowledge entry.','','Choose exactly ONE from:','- asserted: factual claim, documented event, verifiable fact','- speculative: theory, hypothesis, argument, opinion','- constructed: fictional wrapper encoding real concepts (UTETY, food-physics)','- fictional: purely creative narrative, no real-world claims','- mixed: combines multiple modes in one document','- meta: about an AI system, software, Willow/die-namic system','- unknown: insufficient content to determine','','CONTEXT','','Respond with ONLY: STATUS CONFIDENCE','Example: speculative 0.82']
def rule_classify(title, cat, st):
    t = (title or "").lower()
    if any(m in t for m in UM): return ("constructed", 0.88)
    if cat in ("governance", "specs") or st == "die_namic": return ("meta", 0.92)
    if cat in ("conversation_logs", "conversation_log", "logs") or "session" in t: return ("asserted", 0.75)
    if cat in ("screenshots", "photos") or st == "ocr_image": return ("asserted", 0.80)
    if cat == "code": return ("meta", 0.85)
    return None

def llm_classify(title, summary, cat, st, router):
    ctx = chr(10).join([
        "Source type: " + str(st or "unknown"),
        "Category: " + str(cat or "unknown"),
        "Title: " + str(title or ""),
        "Summary: " + (summary or "")[:400]
    ])
    parts = [p if p != "CONTEXT" else ctx for p in PL]
    resp = router.ask(chr(10).join(parts), preferred_tier="free")
    if not resp: return ("unknown", 0.0)
    raw = resp.content.strip().lower()
    tok = raw.split()
    if not tok: return ("unknown", 0.0)
    status = tok[0].strip(".,")
    if status not in VALID:
        for s in VALID:
            if s in raw: status = s; break
        else: status = "unknown"
    conf = 0.7
    if len(tok) > 1:
        try: conf = max(0.0, min(1.0, float(tok[1])))
        except Exception: pass
    return (status, conf)
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--min-pass-level", type=int, default=1)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--source-type", default=None)
    args = parser.parse_args()
    import llm_router
    llm_router.load_keys_from_json()
    conn = get_connection()
    if args.source_type:
        rows = conn.execute(
            "SELECT id, title, summary, content_snippet, category, source_type FROM knowledge "
            "WHERE pass_level >= ? AND epistemic_status = ? AND source_type = ? ORDER BY id LIMIT ?",
            (args.min_pass_level, "unknown", args.source_type, args.limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, title, summary, content_snippet, category, source_type FROM knowledge "
            "WHERE pass_level >= ? AND epistemic_status = ? ORDER BY id LIMIT ?",
            (args.min_pass_level, "unknown", args.limit)
        ).fetchall()
    print("[PASS3] " + str(len(rows)) + " entries to classify")
    stats = {s: 0 for s in VALID}
    stats["rule_based"] = 0; stats["llm_based"] = 0; stats["failed"] = 0
    for row_id, title, summary, snippet, cat, st in rows:
        result = rule_classify(title, cat, st)
        method = "rule"
        if result is None:
            eff = summary or snippet or ""
            if len(eff) < 20:
                result = ("unknown", 0.0)
                method = "skip"
            else:
                result = llm_classify(title, eff, cat, st, llm_router)
                method = "llm"
                stats["llm_based"] += 1
                time.sleep(0.1)
        else:
            stats["rule_based"] += 1
        status, conf = result
        stats[status] = stats.get(status, 0) + 1
        if not args.dry_run:
            upd = ("UPDATE knowledge SET epistemic_status=?, epistemic_confidence=?,"
                   " pass_level=MAX(pass_level,3), updated_at=CURRENT_TIMESTAMP WHERE id=?")
            conn.execute(upd, (status, conf, row_id))
            conn.commit()
        mk = "[DRY]" if args.dry_run else "[OK] "
        lbl = (title or "")[:55]
        print("  " + mk + str(row_id).rjust(6) + " | " + method.ljust(4)
              + " | " + status.ljust(12) + str(round(conf, 2)).ljust(5) + " | " + lbl)
    print("")
    print("[PASS3 DONE] stats=" + str(stats))
    if not args.dry_run:
        print("Epistemic status distribution:")
        for row in conn.execute(
            "SELECT epistemic_status, COUNT(*) FROM knowledge "
            "GROUP BY epistemic_status ORDER BY COUNT(*) DESC"
        ).fetchall():
            print("  " + str(row[1]).rjust(6) + "  " + str(row[0]))
    conn.close()

if __name__ == "__main__": main()

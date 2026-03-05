#!/usr/bin/env python3
"""
Direct bulk ingest of SESSION_HANDOFF files via loam.ingest_file_knowledge.
Bypasses the API to avoid the queue. Uses 4 threads for parallelism.
"""
import sys
import os
import hashlib
import sqlite3
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, r"C:\Users\Sean\Documents\GitHub\Willow")
sys.path.insert(0, r"C:\Users\Sean\Documents\GitHub\Willow\core")

import loam

USERNAME = "Sweet-Pea-Rudi19"
DB_PATH = r"C:\Users\Sean\Documents\GitHub\Willow\artifacts\Sweet-Pea-Rudi19\willow_knowledge.db"

PICKUP_DIR = Path(r"C:\Users\Sean\My Drive\Willow\Auth Users\Sweet-Pea-Rudi19\Pickup")
FILED_DIR  = Path(r"C:\Users\Sean\Willow\Filed")

lock = threading.Lock()
counts = {"ok": 0, "skipped": 0, "error": 0}

def get_existing_hashes():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT source_id FROM knowledge WHERE source_type='file'").fetchall()
    conn.close()
    return {r[0] for r in rows}

def file_hash(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()

def collect_handoffs():
    files = []
    for f in sorted(PICKUP_DIR.glob("SESSION_HANDOFF_*.md")):
        files.append(("pickup", f))
    for f in sorted(FILED_DIR.rglob("*")):
        if f.is_file() and ("handoff" in f.name.lower() or "SESSION_HANDOFF" in f.name):
            if f.suffix.lower() in (".md", ".txt"):
                files.append(("filed", f))
    return files

def process_file(idx, total, source, path, existing_hashes):
    fhash = file_hash(path)
    if fhash in existing_hashes:
        with lock:
            counts["skipped"] += 1
        return "skipped"

    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        with lock:
            counts["error"] += 1
            print(f"[{idx:>4}/{total}] ERROR read [{source}] {path.name}: {e}", flush=True)
        return "error"

    if len(content.strip()) < 50:
        with lock:
            counts["skipped"] += 1
        return "skipped"

    try:
        loam.ingest_file_knowledge(
            username=USERNAME,
            filename=path.name,
            file_hash=fhash,
            category="handoff",
            content_text=content[:4000],
            provider=f"ganesha-bulk-{source}",
        )
        existing_hashes.add(fhash)
        with lock:
            counts["ok"] += 1
            print(f"[{idx:>4}/{total}] OK    [{source}] {path.name}", flush=True)
        return "ok"
    except Exception as e:
        with lock:
            counts["error"] += 1
            print(f"[{idx:>4}/{total}] ERROR [{source}] {path.name}: {e}", flush=True)
        return "error"

def main():
    limit = None
    workers = 4
    for arg in sys.argv[1:]:
        if arg.startswith("--limit="):
            limit = int(arg.split("=")[1])
        if arg.startswith("--workers="):
            workers = int(arg.split("=")[1])

    print(f"Willow Handoff Direct Ingest | workers={workers}", flush=True)

    existing = get_existing_hashes()
    print(f"Existing file entries in DB: {len(existing)}", flush=True)

    files = collect_handoffs()
    print(f"Files to process: {len(files)}", flush=True)

    if limit:
        files = files[:limit]
        print(f"Limited to: {limit}", flush=True)

    print(flush=True)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(process_file, i+1, len(files), src, path, existing): (src, path)
            for i, (src, path) in enumerate(files)
        }
        done = 0
        for future in as_completed(futures):
            done += 1
            future.result()
            if done % 50 == 0:
                with lock:
                    print(f"--- {done}/{len(files)} | ok={counts['ok']} skipped={counts['skipped']} error={counts['error']}", flush=True)

    print(flush=True)
    print(f"Done. ok={counts['ok']}  skipped={counts['skipped']}  error={counts['error']}", flush=True)

    # Final DB count
    conn = sqlite3.connect(DB_PATH)
    total = conn.execute("SELECT COUNT(*) FROM knowledge").fetchone()[0]
    handoffs = conn.execute("SELECT COUNT(*) FROM knowledge WHERE category='handoff'").fetchone()[0]
    conn.close()
    print(f"DB total: {total} | handoff category: {handoffs}", flush=True)

if __name__ == "__main__":
    main()

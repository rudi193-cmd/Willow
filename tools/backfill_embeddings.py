#!/usr/bin/env python3
"""
Embedding Backfill — tools/backfill_embeddings.py

Fills NULL embeddings in sweet_pea_rudi19.knowledge using all-MiniLM-L6-v2.
Text source: summary + content_snippet (title as fallback).
Batch size: 64 rows. Progress reported every batch.

Run: python3 tools/backfill_embeddings.py [--dry-run] [--limit N]

CHECKSUM: ΔΣ=42
"""

import os
import sys
import struct
import argparse
import psycopg2

WILLOW_DB_URL = os.environ.get("WILLOW_DB_URL", "postgresql://willow:willow@172.26.176.1:5437/willow")
SCHEMA = "sweet_pea_rudi19"
BATCH = 64


def get_text(row) -> str:
    """Build embeddable text from a knowledge row."""
    title = (row[1] or "").strip()
    summary = (row[2] or "").strip()
    snippet = (row[3] or "").strip()
    parts = []
    if summary:
        parts.append(summary[:600])
    if snippet and snippet != summary:
        parts.append(snippet[:200])
    if not parts and title:
        parts.append(title)
    return " ".join(parts)[:800]


def pack_vector(vec) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def main():
    parser = argparse.ArgumentParser(description="Backfill NULL embeddings in knowledge table")
    parser.add_argument("--dry-run", action="store_true", help="Count rows, don't update")
    parser.add_argument("--limit", type=int, default=0, help="Stop after N rows (0=all)")
    args = parser.parse_args()

    # Load model
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer("all-MiniLM-L6-v2")
        print(f"Model loaded: all-MiniLM-L6-v2 (384-dim)")
    except ImportError:
        print("ERROR: sentence-transformers not installed.")
        print("Run: pip3 install sentence-transformers --break-system-packages")
        sys.exit(1)

    conn = psycopg2.connect(WILLOW_DB_URL)
    cur = conn.cursor()

    # Count
    cur.execute(f"SELECT COUNT(*) FROM {SCHEMA}.knowledge WHERE embedding IS NULL")
    total_null = cur.fetchone()[0]
    print(f"NULL embeddings: {total_null}")

    if args.dry_run:
        conn.close()
        return

    limit_clause = f"LIMIT {args.limit}" if args.limit else ""
    cur.execute(
        f"SELECT id, title, summary, content_snippet FROM {SCHEMA}.knowledge "
        f"WHERE embedding IS NULL ORDER BY id {limit_clause}"
    )
    rows = cur.fetchall()
    print(f"Fetched {len(rows)} rows to embed")

    updated = 0
    skipped = 0

    for i in range(0, len(rows), BATCH):
        batch = rows[i : i + BATCH]
        texts = []
        ids = []
        for row in batch:
            t = get_text(row)
            if t:
                texts.append(t)
                ids.append(row[0])
            else:
                skipped += 1

        if not texts:
            continue

        vecs = model.encode(texts, show_progress_bar=False, batch_size=BATCH)

        update_cur = conn.cursor()
        for row_id, vec in zip(ids, vecs):
            emb_bytes = pack_vector(vec)
            update_cur.execute(
                f"UPDATE {SCHEMA}.knowledge SET embedding = %s WHERE id = %s",
                (psycopg2.Binary(emb_bytes), row_id),
            )
        conn.commit()
        updated += len(ids)

        pct = (i + len(batch)) / len(rows) * 100
        print(f"  [{pct:5.1f}%] {updated} embedded, {skipped} skipped (no text)")

    conn.close()
    print(f"\nDone. Updated: {updated}, Skipped: {skipped}")


if __name__ == "__main__":
    main()

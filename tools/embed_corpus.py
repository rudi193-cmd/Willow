#!/usr/bin/env python3
"""
Corpus Embedding Job — Local Semantic Search for Willow
========================================================
Embeds all knowledge atoms using sentence-transformers (all-MiniLM-L6-v2).
Runs 100% local. Zero cloud tokens. Model already cached on this machine.

Usage:
    python tools/embed_corpus.py                    # embed all unembedded atoms
    python tools/embed_corpus.py --all              # re-embed everything
    python tools/embed_corpus.py --search "query"   # semantic search test
    python tools/embed_corpus.py --backfill ATOM_ID # find similar to a specific atom

Embedding stored as bytea in knowledge.embedding column (384-dim float32).

Authority: Sean Campbell
System: Willow
ΔΣ=42
"""

import argparse
import logging
import struct
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "core"))

import numpy as np
from db import get_connection

log = logging.getLogger("willow.embed")

BATCH_SIZE = 64
MODEL_NAME = "all-MiniLM-L6-v2"
DIM = 384

_model = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def _vec_to_bytes(vec) -> bytes:
    return np.array(vec, dtype=np.float32).tobytes()


def _bytes_to_vec(b: bytes):
    return np.frombuffer(b, dtype=np.float32)


def _text_for_atom(row) -> str:
    """Build the text to embed: title + summary + snippet (truncated)."""
    parts = []
    if row[1]:
        parts.append(row[1])  # title
    if row[2]:
        parts.append(row[2][:200])  # summary
    if row[3]:
        parts.append(row[3][:800])  # content_snippet
    return " ".join(parts).strip()


def embed_corpus(reembed_all: bool = False) -> dict:
    """Embed all knowledge atoms. Returns stats."""
    conn = get_connection()
    model = _get_model()

    if reembed_all:
        rows = conn.execute(
            "SELECT id, title, summary, content_snippet FROM knowledge ORDER BY id"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, title, summary, content_snippet FROM knowledge "
            "WHERE embedding IS NULL ORDER BY id"
        ).fetchall()

    total = len(rows)
    log.info(f"Atoms to embed: {total}")

    embedded = 0
    skipped = 0
    t0 = time.time()

    for i in range(0, total, BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        texts = []
        ids = []
        for row in batch:
            text = _text_for_atom(row)
            if not text or len(text) < 10:
                skipped += 1
                continue
            texts.append(text)
            ids.append(row[0])

        if not texts:
            continue

        vecs = model.encode(texts, show_progress_bar=False)

        for kid, vec in zip(ids, vecs):
            conn.execute(
                "UPDATE knowledge SET embedding = %s WHERE id = %s",
                (_vec_to_bytes(vec), kid)
            )
        conn.commit()
        embedded += len(ids)

        if (i + BATCH_SIZE) % (BATCH_SIZE * 10) == 0 or i + BATCH_SIZE >= total:
            elapsed = time.time() - t0
            rate = embedded / max(elapsed, 0.1)
            log.info(f"  {embedded}/{total} embedded ({rate:.0f}/sec)")

    elapsed = time.time() - t0
    log.info(f"Done: {embedded} embedded, {skipped} skipped, {elapsed:.1f}s")
    conn.close()

    return {"embedded": embedded, "skipped": skipped, "total": total, "seconds": round(elapsed, 1)}


def search(query: str, limit: int = 20, min_score: float = 0.3) -> list:
    """Semantic search against embedded corpus. Returns [(id, title, score), ...]."""
    conn = get_connection()
    model = _get_model()

    q_vec = model.encode(query)

    rows = conn.execute(
        "SELECT id, title, category, embedding FROM knowledge WHERE embedding IS NOT NULL"
    ).fetchall()

    results = []
    for row in rows:
        kid, title, cat, emb_bytes = row[0], row[1], row[2], row[3]
        if not emb_bytes:
            continue
        # Handle memoryview from psycopg2
        if isinstance(emb_bytes, memoryview):
            emb_bytes = bytes(emb_bytes)
        doc_vec = _bytes_to_vec(emb_bytes)
        score = float(np.dot(q_vec, doc_vec) / (np.linalg.norm(q_vec) * np.linalg.norm(doc_vec) + 1e-8))
        if score >= min_score:
            results.append((kid, title, cat, score))

    results.sort(key=lambda x: -x[3])
    conn.close()
    return results[:limit]


def backfill_similar(atom_id: int, edge_type: str = "supports", target_id: int = None,
                     min_score: float = 0.5, limit: int = 100, dry_run: bool = True) -> list:
    """Find atoms semantically similar to a given atom. Optionally create edges."""
    conn = get_connection()
    model = _get_model()

    source = conn.execute(
        "SELECT id, title, summary, content_snippet, embedding FROM knowledge WHERE id = %s",
        (atom_id,)
    ).fetchone()

    if not source:
        log.error(f"Atom {atom_id} not found")
        conn.close()
        return []

    if source[4]:
        emb = bytes(source[4]) if isinstance(source[4], memoryview) else source[4]
        q_vec = _bytes_to_vec(emb)
    else:
        text = _text_for_atom(source)
        q_vec = model.encode(text)

    rows = conn.execute(
        "SELECT id, title, category, embedding FROM knowledge "
        "WHERE embedding IS NOT NULL AND id != %s",
        (atom_id,)
    ).fetchall()

    results = []
    for row in rows:
        kid, title, cat, emb_bytes = row[0], row[1], row[2], row[3]
        if not emb_bytes:
            continue
        if isinstance(emb_bytes, memoryview):
            emb_bytes = bytes(emb_bytes)
        doc_vec = _bytes_to_vec(emb_bytes)
        score = float(np.dot(q_vec, doc_vec) / (np.linalg.norm(q_vec) * np.linalg.norm(doc_vec) + 1e-8))
        if score >= min_score:
            results.append((kid, title, cat, score))

    results.sort(key=lambda x: -x[3])
    results = results[:limit]

    if not dry_run and target_id:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        created = 0
        for kid, title, cat, score in results:
            existing = conn.execute(
                "SELECT id FROM knowledge_edges WHERE source_id = %s AND target_id = %s AND edge_type = %s",
                (kid, target_id, edge_type)
            ).fetchone()
            if not existing:
                conn.execute(
                    "INSERT INTO knowledge_edges (source_id, target_id, edge_type, weight, canonical, created_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    (kid, target_id, edge_type, round(score, 3), 1, now)
                )
                created += 1
        conn.commit()
        log.info(f"Created {created} new '{edge_type}' edges to #{target_id}")

    conn.close()
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(description="Embed Willow knowledge corpus locally")
    parser.add_argument("--all", action="store_true", help="Re-embed all atoms (not just unembedded)")
    parser.add_argument("--search", type=str, help="Semantic search query")
    parser.add_argument("--backfill", type=int, help="Find atoms similar to this atom ID")
    parser.add_argument("--target", type=int, help="Target atom ID for edge creation (with --backfill)")
    parser.add_argument("--min-score", type=float, default=0.5, help="Minimum similarity score")
    parser.add_argument("--apply", action="store_true", help="Actually create edges (default is dry-run)")
    parser.add_argument("--limit", type=int, default=20, help="Max results")
    args = parser.parse_args()

    if args.search:
        results = search(args.search, limit=args.limit, min_score=args.min_score)
        for kid, title, cat, score in results:
            print(f"  {score:.3f} | #{kid} [{cat}] {title[:60]}")

    elif args.backfill:
        results = backfill_similar(
            args.backfill,
            target_id=args.target or args.backfill,
            min_score=args.min_score,
            limit=args.limit,
            dry_run=not args.apply,
        )
        mode = "APPLY" if args.apply else "DRY-RUN"
        print(f"\n[{mode}] Similar to #{args.backfill} (min_score={args.min_score}):")
        for kid, title, cat, score in results:
            print(f"  {score:.3f} | #{kid} [{cat}] {title[:60]}")
        print(f"\nTotal: {len(results)}")

    else:
        result = embed_corpus(reembed_all=args.all)
        print(f"\nEmbedded: {result['embedded']}")
        print(f"Skipped: {result['skipped']}")
        print(f"Time: {result['seconds']}s")

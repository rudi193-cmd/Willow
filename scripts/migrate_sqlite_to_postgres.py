#!/usr/bin/env python3
"""
Backfill ALL remaining SQLite data into Postgres sweet_pea_rudi19 schema.
Read-only on SQLite. Insert with ON CONFLICT DO NOTHING on Postgres.
Uses raw psycopg2 (bypasses db.py wrapper whose lastval() call aborts txns).
"""

import sys
import os
import sqlite3

sys.path.insert(0, "/mnt/c/Users/Sean/Documents/GitHub/Willow")

import psycopg2
import psycopg2.extras

WILLOW_ROOT = "/mnt/c/Users/Sean/Documents/GitHub/Willow"
DB_URL = os.environ["WILLOW_DB_URL"]
SCHEMA = "sweet_pea_rudi19"

def sqlite_ro(path):
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)

def pg_connect():
    conn = psycopg2.connect(DB_URL)
    conn.autocommit = False
    cur = conn.cursor()
    cur.execute(f"SET search_path = {SCHEMA}, public")
    return conn, cur

def pg_count(cur, table):
    cur.execute(f"SELECT COUNT(*) FROM {SCHEMA}.{table}")
    return cur.fetchone()[0]

def safe_insert(cur, conn, sql, row):
    try:
        cur.execute("SAVEPOINT sp")
        cur.execute(sql, row)
        cur.execute("RELEASE SAVEPOINT sp")
        return True
    except Exception:
        cur.execute("ROLLBACK TO SAVEPOINT sp")
        return False

def report(table, before, after):
    inserted = after - before
    print(f"  {table}: {before} -> {after} (+{inserted})")
    return (table, before, after, inserted)

results = []
pg, pgc = pg_connect()

# ── 1. health_checks ──
print("\n[1/11] health_checks")
before = pg_count(pgc, "health_checks")
sl = sqlite_ro(f"{WILLOW_ROOT}/artifacts/Sweet-Pea-Rudi19/health.db")
rows = sl.execute("SELECT id, timestamp, check_type, target, status, details, latency_ms FROM health_checks").fetchall()
sl.close()
ok = skip = 0
for r in rows:
    if safe_insert(pgc, pg,
        f"INSERT INTO {SCHEMA}.health_checks (id, timestamp, check_type, target, status, details, latency_ms) VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING", r):
        ok += 1
    else:
        skip += 1
pg.commit()
results.append(report("health_checks", before, pg_count(pgc, "health_checks")))
print(f"  (ok={ok}, skip={skip})")

# ── 2. health_issues ──
print("\n[2/11] health_issues")
before = pg_count(pgc, "health_issues")
sl = sqlite_ro(f"{WILLOW_ROOT}/artifacts/Sweet-Pea-Rudi19/health.db")
rows = sl.execute("SELECT id, detected_at, issue_type, target, description, severity, resolved, resolved_at, resolution FROM health_issues").fetchall()
sl.close()
ok = skip = 0
for r in rows:
    # Cast 'resolved' (index 6) from int to bool
    r_list = list(r)
    r_list[6] = bool(r_list[6]) if r_list[6] is not None else None
    if safe_insert(pgc, pg,
        f"INSERT INTO {SCHEMA}.health_issues (id, detected_at, issue_type, target, description, severity, resolved, resolved_at, resolution) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING", tuple(r_list)):
        ok += 1
    else:
        skip += 1
pg.commit()
results.append(report("health_issues", before, pg_count(pgc, "health_issues")))
print(f"  (ok={ok}, skip={skip})")

# ── 3. entities ──
print("\n[3/11] entities")
before = pg_count(pgc, "entities")
sl = sqlite_ro(f"{WILLOW_ROOT}/artifacts/Sweet-Pea-Rudi19/willow_knowledge.db")
rows = sl.execute("""SELECT id, name, entity_type, description, mention_count, layer,
    reference_string, first_seen, last_mentioned, mention_contexts, emotional_valence,
    promotion_status, never_promote, username, promoted_from, domain, verified, confidence,
    source_type, sources, corrections, verified_at, verified_by FROM entities""").fetchall()
sl.close()
ok = skip = 0
for r in rows:
    r_list = list(r)
    # 'verified' is col index 16, cast int->bool
    r_list[16] = bool(r_list[16]) if r_list[16] is not None else None
    if safe_insert(pgc, pg,
        f"""INSERT INTO {SCHEMA}.entities (id, name, entity_type, description, mention_count, layer,
            reference_string, first_seen, last_mentioned, mention_contexts, emotional_valence,
            promotion_status, never_promote, username, promoted_from, domain, verified, confidence,
            source_type, sources, corrections, verified_at, verified_by)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (id) DO NOTHING""", tuple(r_list)):
        ok += 1
    else:
        skip += 1
pg.commit()
results.append(report("entities", before, pg_count(pgc, "entities")))
print(f"  (ok={ok}, skip={skip})")

# ── 4. entity_connections ──
print("\n[4/11] entity_connections")
before = pg_count(pgc, "entity_connections")
sl = sqlite_ro(f"{WILLOW_ROOT}/artifacts/Sweet-Pea-Rudi19/willow_knowledge.db")
rows = sl.execute("""SELECT id, entity_a_id, entity_b_id, connection_type, weight, source,
    created_at, confirmed, confidence, source_type FROM entity_connections""").fetchall()
sl.close()
ok = skip = 0
for r in rows:
    if safe_insert(pgc, pg,
        f"""INSERT INTO {SCHEMA}.entity_connections (id, entity_a_id, entity_b_id, connection_type,
            weight, source, created_at, confirmed, confidence, source_type)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING""", r):
        ok += 1
    else:
        skip += 1
pg.commit()
results.append(report("entity_connections", before, pg_count(pgc, "entity_connections")))
print(f"  (ok={ok}, skip={skip})")

# ── 5. knowledge_entities ──
print("\n[5/11] knowledge_entities")
before = pg_count(pgc, "knowledge_entities")
sl = sqlite_ro(f"{WILLOW_ROOT}/artifacts/Sweet-Pea-Rudi19/willow_knowledge.db")
rows = sl.execute("SELECT knowledge_id, entity_id FROM knowledge_entities").fetchall()
sl.close()

# Pre-check valid FK IDs
pgc.execute(f"SELECT id FROM {SCHEMA}.knowledge")
valid_k = set(r[0] for r in pgc.fetchall())
pgc.execute(f"SELECT id FROM {SCHEMA}.entities")
valid_e = set(r[0] for r in pgc.fetchall())

ok = skip = skip_fk = 0
for r in rows:
    if r[0] not in valid_k or r[1] not in valid_e:
        skip_fk += 1
        continue
    if safe_insert(pgc, pg,
        f"INSERT INTO {SCHEMA}.knowledge_entities (knowledge_id, entity_id) VALUES (%s,%s) ON CONFLICT (knowledge_id, entity_id) DO NOTHING", r):
        ok += 1
    else:
        skip += 1
pg.commit()
results.append(report("knowledge_entities", before, pg_count(pgc, "knowledge_entities")))
print(f"  (ok={ok}, skip={skip}, skip_fk={skip_fk})")

# ── 6. knowledge_edges (batched) ──
print("\n[6/11] knowledge_edges (973K rows, batched)")
before = pg_count(pgc, "knowledge_edges")

pgc.execute(f"SELECT id FROM {SCHEMA}.knowledge_edges")
existing_edge_ids = set(r[0] for r in pgc.fetchall())
print(f"  {len(existing_edge_ids)} already in Postgres")

pgc.execute(f"SELECT id FROM {SCHEMA}.knowledge")
valid_knowledge_ids = set(r[0] for r in pgc.fetchall())
print(f"  {len(valid_knowledge_ids)} valid knowledge IDs")

sl = sqlite_ro(f"{WILLOW_ROOT}/artifacts/Sweet-Pea-Rudi19/willow_knowledge.db")
cur_sl = sl.cursor()
cur_sl.execute("SELECT id, source_id, target_id, edge_type, weight, canonical, created_at FROM knowledge_edges ORDER BY id")

BATCH = 5000
inserted_total = 0
skipped_fk = 0
skipped_exist = 0
batch = []
row_num = 0

def flush_batch(batch, pgc, pg):
    if not batch:
        return 0, 0
    ok = fail = 0
    try:
        psycopg2.extras.execute_values(pgc,
            f"""INSERT INTO {SCHEMA}.knowledge_edges (id, source_id, target_id, edge_type, weight, canonical, created_at)
               VALUES %s ON CONFLICT (id) DO NOTHING""",
            batch, page_size=5000)
        pg.commit()
        ok = len(batch)
    except Exception:
        pg.rollback()
        for b in batch:
            if safe_insert(pgc, pg,
                f"""INSERT INTO {SCHEMA}.knowledge_edges (id, source_id, target_id, edge_type, weight, canonical, created_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING""", b):
                ok += 1
            else:
                fail += 1
        pg.commit()
    return ok, fail

while True:
    row = cur_sl.fetchone()
    if row is None:
        ok, fail = flush_batch(batch, pgc, pg)
        inserted_total += ok
        break

    row_num += 1
    if row[0] in existing_edge_ids:
        skipped_exist += 1
        continue
    if row[1] not in valid_knowledge_ids or row[2] not in valid_knowledge_ids:
        skipped_fk += 1
        continue

    batch.append(row)
    if len(batch) >= BATCH:
        ok, fail = flush_batch(batch, pgc, pg)
        inserted_total += ok
        batch = []
        if row_num % 100000 < BATCH:
            print(f"  ... processed {row_num} rows, inserted {inserted_total}")

sl.close()
after = pg_count(pgc, "knowledge_edges")
print(f"  knowledge_edges: {before} -> {after} (+{after - before})")
print(f"  (skipped_existing={skipped_exist}, skipped_fk={skipped_fk})")
results.append(("knowledge_edges", before, after, after - before))

# ── 7+8. deltas ──
print("\n[7-8/11] deltas (kart + Sweet-Pea)")
before = pg_count(pgc, "deltas")
for label, path in [("kart", "artifacts/kart/deltas.db"), ("Sweet-Pea", "artifacts/Sweet-Pea-Rudi19/deltas.db")]:
    sl = sqlite_ro(f"{WILLOW_ROOT}/{path}")
    rows = sl.execute("SELECT delta_id, thread_from, thread_to, timestamp, state_before, state_after, changes, entropy_delta, coherence_score FROM deltas").fetchall()
    sl.close()
    ok = skip = 0
    for r in rows:
        if safe_insert(pgc, pg,
            f"""INSERT INTO {SCHEMA}.deltas (delta_id, thread_from, thread_to, timestamp, state_before, state_after, changes, entropy_delta, coherence_score)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (delta_id) DO NOTHING""", r):
            ok += 1
        else:
            skip += 1
    pg.commit()
    print(f"  deltas ({label}): ok={ok}, skip={skip}")
after = pg_count(pgc, "deltas")
results.append(report("deltas", before, after))

# ── 9. graft tasks + task_log ──
print("\n[9/11] graft tasks")
before_tasks = pg_count(pgc, "tasks")
sl = sqlite_ro(f"{WILLOW_ROOT}/artifacts/Sweet-Pea-Rudi19/graft.db")
rows = sl.execute("SELECT id, task_id, subject, description, status, agent, created_at, updated_at, completed_at, metadata FROM tasks").fetchall()
sl.close()
ok = skip = 0
for r in rows:
    vals = (r[0], 'Sweet-Pea-Rudi19', r[1], r[2], r[3], r[4] or 'pending', r[5] or 'graft', r[6], r[7], r[8], r[9])
    if safe_insert(pgc, pg,
        f"""INSERT INTO {SCHEMA}.tasks (id, username, task_id, subject, description, status, agent, created_at, updated_at, completed_at, metadata)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING""", vals):
        ok += 1
    else:
        skip += 1
pg.commit()
results.append(report("tasks (graft)", before_tasks, pg_count(pgc, "tasks")))
print(f"  (ok={ok}, skip={skip})")

print("\n[9b/11] graft task_log")
before_tl = pg_count(pgc, "task_log")
sl = sqlite_ro(f"{WILLOW_ROOT}/artifacts/Sweet-Pea-Rudi19/graft.db")
rows = sl.execute("SELECT id, task_id, timestamp, action, agent, details FROM task_log").fetchall()
sl.close()
ok = skip = 0
for r in rows:
    vals = (r[0], 'Sweet-Pea-Rudi19', r[1], r[2], r[3], r[4] or 'graft', r[5])
    if safe_insert(pgc, pg,
        f"""INSERT INTO {SCHEMA}.task_log (id, username, task_id, timestamp, action, agent, details)
           VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING""", vals):
        ok += 1
    else:
        skip += 1
pg.commit()
results.append(report("task_log (graft)", before_tl, pg_count(pgc, "task_log")))
print(f"  (ok={ok}, skip={skip})")

# ── 10. loam tables ──
print("\n[10/11] loam")
pgc.execute(f"""CREATE TABLE IF NOT EXISTS {SCHEMA}.loam_atoms (
    id BIGINT PRIMARY KEY, content TEXT, source_session TEXT, domain TEXT, depth INTEGER, created TEXT)""")
pgc.execute(f"""CREATE TABLE IF NOT EXISTS {SCHEMA}.loam_entities (
    id BIGINT PRIMARY KEY, name TEXT, type TEXT, mention_count INTEGER, first_seen TEXT, last_seen TEXT)""")
pgc.execute(f"""CREATE TABLE IF NOT EXISTS {SCHEMA}.loam_gaps (
    id BIGINT PRIMARY KEY, question TEXT, context TEXT, created TEXT, resolved INTEGER)""")
pgc.execute(f"""CREATE TABLE IF NOT EXISTS {SCHEMA}.loam_patterns (
    id BIGINT PRIMARY KEY, description TEXT, domain TEXT, frequency INTEGER, first_detected TEXT, last_detected TEXT)""")
pg.commit()

sl = sqlite_ro(f"{WILLOW_ROOT}/artifacts/Sweet-Pea-Rudi19/loam.db")
for tbl, pg_tbl, cols in [
    ("atoms", "loam_atoms", "id, content, source_session, domain, depth, created"),
    ("entities", "loam_entities", "id, name, type, mention_count, first_seen, last_seen"),
    ("gaps", "loam_gaps", "id, question, context, created, resolved"),
    ("patterns", "loam_patterns", "id, description, domain, frequency, first_detected, last_detected"),
]:
    rows = sl.execute(f"SELECT {cols} FROM {tbl}").fetchall()
    col_list = cols.split(", ")
    placeholders = ", ".join(["%s"] * len(col_list))
    before = pg_count(pgc, pg_tbl)
    ok = skip = 0
    for r in rows:
        if safe_insert(pgc, pg,
            f"INSERT INTO {SCHEMA}.{pg_tbl} ({cols}) VALUES ({placeholders}) ON CONFLICT (id) DO NOTHING", r):
            ok += 1
        else:
            skip += 1
    pg.commit()
    after = pg_count(pgc, pg_tbl)
    results.append(report(pg_tbl, before, after))
sl.close()

# ── 11. shiva nodes ──
print("\n[11/11] shiva_nodes (Sweet-Pea-Rudi19.db)")
before = pg_count(pgc, "shiva_nodes")
sl = sqlite_ro(f"{WILLOW_ROOT}/shiva_memory/Sweet-Pea-Rudi19.db")
rows = sl.execute("SELECT id, username, domain, depth, temporal, content, source, created_at, updated_at, is_deleted, is_sensitive FROM nodes").fetchall()
sl.close()

pgc.execute(f"SELECT id FROM {SCHEMA}.shiva_nodes")
existing = set(r[0] for r in pgc.fetchall())

ok = skip = 0
for r in rows:
    if r[0] in existing:
        skip += 1
        continue
    if safe_insert(pgc, pg,
        f"""INSERT INTO {SCHEMA}.shiva_nodes (id, username, domain, depth, temporal, content, source, created_at, updated_at, is_deleted, is_sensitive, pigeon_synced, session_id)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,0,NULL) ON CONFLICT (id) DO NOTHING""", r):
        ok += 1
    else:
        skip += 1
pg.commit()
results.append(report("shiva_nodes", before, pg_count(pgc, "shiva_nodes")))
print(f"  (ok={ok}, skip={skip})")

# ── Summary ──
print("\n" + "=" * 60)
print("MIGRATION SUMMARY")
print("=" * 60)
print(f"{'Table':<25} {'Before':>8} {'After':>8} {'Inserted':>10}")
print("-" * 60)
total_inserted = 0
for table, before, after, inserted in results:
    print(f"{table:<25} {before:>8} {after:>8} {inserted:>10}")
    total_inserted += inserted
print("-" * 60)
print(f"{'TOTAL INSERTED':<25} {'':>8} {'':>8} {total_inserted:>10}")
print("=" * 60)

pgc.close()
pg.close()
print("\nDone. All SQLite sources read-only. Postgres updated.")

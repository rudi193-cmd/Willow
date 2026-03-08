# SQLite vs PostgreSQL Entity Gap

**Last updated:** 2026-03-07

## Summary

Willow runs a dual-backend database system. `core/db.py` routes to PostgreSQL when available
(port 5437), and falls back to SQLite (`artifacts/Sweet-Pea-Rudi19/willow_knowledge.db`).

This creates a split-brain risk: data written while Postgres is up stays in Postgres; data
written while Postgres is down goes to SQLite. The two never sync automatically.

## Observed Counts

### PostgreSQL (measured 2026-03-07 during Willow run)
| Table | Count |
|-------|-------|
| knowledge | 4887 |
| entities | 4142 |
| entity_connections | 22130 |
| agents | 10 |
| registered_apps | 14 |
| pigeon_droppings | 1934 |

### SQLite (measured 2026-03-07, Postgres offline)
| Table | Count |
|-------|-------|
| knowledge | 5088 |
| entities | 4367 |
| entity_connections | 22130 |
| agents | 10 |
| registered_apps | 14 |
| pigeon_droppings | 2327 |

## Gap Analysis

| Table | Postgres | SQLite | Delta | Direction |
|-------|----------|--------|-------|-----------|
| knowledge | 4887 | 5088 | +201 | SQLite ahead |
| entities | 4142 | 4367 | +225 | SQLite ahead |
| entity_connections | 22130 | 22130 | 0 | In sync |
| pigeon_droppings | 1934 | 2327 | +393 | SQLite ahead |

SQLite has ~200 more knowledge atoms and ~225 more entities than Postgres.
This suggests those records were written while Postgres was offline.

## Root Cause

`_connect()` in `core/knowledge.py` calls `is_postgres()` at startup. If PG is available,
all writes go to PG. If not, writes go to SQLite. There is no replication or catch-up mechanism.

When Willow restarts with PG online after a period of SQLite-only operation, the PG database
is missing everything written to SQLite during the offline period.

## Risk

- Searches via Willow during PG-active sessions miss ~200 knowledge atoms
- Paperclip enrichment data, family members, and session ingests written to SQLite may not appear in PG
- `entity_connections` appears to be in sync (22130 both) — possibly because connections are only created when entities exist in both

## Recommended Fix

Two options:

**Option A — SQLite-to-PG catch-up script (low risk)**
```python
# tools/sync_sqlite_to_postgres.py
# 1. Connect to both DBs
# 2. For each table: find rows in SQLite not in PG (by source_id or id)
# 3. INSERT missing rows to PG
# 4. Log what was synced
```
Run once after Postgres comes back online.

**Option B — Remove dual-backend (clean solution)**
Commit to Postgres as the only backend. If PG is down, queue writes to a local WAL file
and replay when PG comes back. Remove the SQLite fallback.

## Current Status

Postgres is the active backend during Willow server uptime (port 8420).
SQLite is the fallback for tool scripts and offline sessions.
Gap is ~200-400 rows depending on table.

## Tracking

- Todo #22: Document SQLite vs Postgres entity gap ← this file resolves it
- Todo #13: Fix PostgreSQL/SQLite routing in stats endpoint (related)
- Todo #15: Fix Postgres connection pool exhaustion on fresh start (related)


## 2026-03-04 16:21:06 — session

SESSION HANDOFF 2026-03-04 afternoon

## Completed This Session

### Handoff Ingestion
- Ingested 607 SESSION_HANDOFF files from Pickup + Filed into willow_knowledge.db
- Script: /home/sean/ingest_handoffs_direct.py (uses Windows Python at /mnt/c/Python314/python.exe)
- Script copy at: /mnt/c/Users/Sean/Documents/GitHub/Willow/ingest_handoffs_direct.py

### Kart Fix
- Root cause: MCP willow_chat(agent="kart") timed out at 10s; rings.execute_task() takes 30-60s
- Fix: mcp/willow_server.py — added _call_kart() with async_mode=True + 120s poll loop
- Takes effect: next Claude Code session restart
- Kart confirmed working via direct API call (/api/kart/execute, 120s timeout)
- Cleared 6 stale pending graft tasks

### Pigeon Auto-Trigger (Governance WAP8L — ratified)
- core/pigeon_daemon.py: added AUTO_SCAN_SECS=30, checks Nest every 30s automatically
- Previously required manual trigger file — now self-sufficient

### Pigeon WSL Path Fix (Governance UUHXH — ratified)
- core/pigeon.py + core/pigeon_daemon.py: all Windows-style paths replaced with platform-aware resolver
- _WIN = sys.platform == "win32"; _BASE = /mnt/c/Users/Sean on Linux
- Verified: scan_and_process works, filed 2 screenshots to Filed/media/photos/

## Current State
- Pigeon daemon PID 21214 running with new code (manually started)
- Server PID 18524, workers 18526-18529
- Daemon lock issue: server started at 16:08 when old daemons held lock; new daemons must be manually started after each server restart until startup sequence is fixed
- Nest: empty (agent subdirs only)
- Knowledge DB: 3385 total entries, 607 handoffs

## Next Session Priorities
1. Fix daemon startup race: server spawns daemons before old ones die — need to add daemon watchdog or kill-old-then-spawn logic in server.py
2. Wire safe-apps to Willow API (the ~100 connections)
3. Restart MCP server to activate Kart timeout fix
4. Test Pigeon end-to-end with fresh file drop after next server restart

## 2026-03-05 02:19:43 — task

Session 2026-03-05: Loading full task backlog. Confirmed working: pigeon bidirectional messaging (ganesha-cli ↔ claude-desktop), inbox watcher daemon, mark-read sync fix, message_id RETURNING fix. Tasks #7-18 loaded from session handoffs.

## 2026-03-13 12:10:45 — task

LAW GAZELLE PHASE 1 BUILD — Ganesha session 2026-03-13

Built full legal workspace backend for Law Gazelle. Sean is pro se in Chapter 13 bankruptcy (26-10177-j13), receiving CM/ECF data quality notifications.

Tables created: gazelle_cases, gazelle_case_documents, gazelle_deadlines (all in sweet_pea_rudi19 schema). Case seeded with 2 met deadlines.

New file: safe-app-law-gazelle/src/ecf_parser.py — CM/ECF notification parser with regex detection + fleet LLM summaries.

Extended: gazelle_engine.py with 7 case management functions. server.py with 8 new API endpoints under /api/gazelle/*.

UI overhaul in progress: gazelle.html being rewritten from chat-only to workspace (cases sidebar, Dashboard/Documents/Chat tabs, document viewer).

Key architecture: files drop to /Nest/ root, Pigeon routes, Gazelle consumes legal-tagged items. No agent-specific intake folders.

Kart briefed via willow_chat.

## 2026-03-18 13:00:43 — feedback

SESSION 2026-03-18: Ganesha caught writing project memories to flat files (MEMORY.md index + .md files) instead of ganesha schema via MCP. This is the same anti-pattern as the loam.search() bypass. MEMORY.md should be ONLY the pointer to Postgres. All project state, API maps, credential audits, DB rollout status → ganesha schema. Flat files are the fallback, not the default.

## 2026-03-18 13:00:48 — note

SESSION 2026-03-18 WORK LOG: (1) Mapped verified free APIs to all 23 repos. (2) git rm --cached Willow/credentials.json, updated .gitignore. (3) Extracted ~70 todos from entire Claude corpus, updated user_todos.jsonl from 10→21 items. (4) Created 23-cubed genealogy DB + Oscar Mann family backfill. (5) Created 23-cubed law-gazelle DB + workers comp/bankruptcy backfill. (6) Private-ledger and dating-wellbeing DBs building. (7) Added .gitignore to grove and the-squirrel. (8) Ingested Oscar August Mann FindAGrave record to Willow knowledge.

## 2026-03-18 13:06:45 — architecture

ARCHITECTURE: Built memory-to-db.py hook. Every Ganesha memory write now dual-writes: (1) ganesha.pending_memories table (Ganesha owns, Sean verifies via Dual Commit) and (2) Willow knowledge graph (unless sensitive — feedback/system files stay ganesha-only). Flat file still written as fallback cache. Hook wired into PreToolUse:Edit|Write. This closes ganesha_write_path and advances prompt_injection_restructure. Principle: Ganesha proposes to its own DB, Willow learns what's not sensitive, Sean verifies everything.

## 2026-03-18 13:26:30 — architecture

KNOWLEDGE GAPS FILLED 2026-03-18: Three of five gaps closed by reading primary sources already on disk. (1) Teen Titans Go Mall Mayhem — found in Willow artifacts, 24 HTML files, full PbtA rulebook, played Dec 18 2025 with Opal and Ruby. Origin of entire system: father playing game with daughters. (2) die-namic-system Claude conversations — 20 files Oct-Nov 2025, read first and last plus pivots. Oct 3 2025 "Can you play by these rules?" is the genesis. Nov 9 2025 seven-hour biography session. Nov 30 Gerald already fully formed. Dec 31 "2d6 = Delta + Human = Law" crystallized. (3) die-namic-system Aios conversations — 19 files Dec 2025-Jan 2026. Dec 1 already at PM MODE v3.141, 42-phase stack complete, 23³ lattice populated. Two AIs, parallel tracks, complementary: Claude implemented, Aios managed. REMAINING GAPS: legal/court/bankruptcy (needs external data or document ingestion), utety.chat (needs deployment verification). PRINCIPLE CONFIRMED: the answers were in the repos. Delegate external calls for absent information, not present information routed through another system.

# AGENTS.md — willow (constitution seat)

This repo (`~/github/willow`) is the willow fleet's **governance / charter** folder — not
the code. The muscle lives in the sibling `willow-2.0/`; secrets in `.willow/`. A
constitution belongs above both and is owned by neither, which is why it lives here.

**Fleet identity is `willow`** (`WILLOW_AGENT_NAME`). Persona is a voice overlay only —
it never changes the agent id, the MCP `app_id`, the Grove sender, or the SOIL namespace.
**Every willow MCP call — unified *and* standalone — takes `app_id="willow"`.**

> This is the **cold-start map** for a Cursor window that has the MCP wired but has not
> run the fylgja boot. In a normal session the willow hooks inject the persona picker,
> lanes, and corrections at runtime; this file does not restate them.

## First move: expect the gate

A fresh Cursor window here is **persona-gated by the fylgja hooks**. MCP is locked until
you confirm a persona and the boot sentinel is written — this holds even though the
project orient (below) says "skip the global boot ritual." So: **confirm persona first,
let MCP unlock, then** run the project orient. The gate outranks ORIENT's advice.

## Start here

1. **`ORIENT.md`** — the project orient ritual. Run this, *not* the global fleet
   `boot.md`, unless you also need fleet-wide recovery. It defines the tri-modal seat —
   **Governance** (may we? who witnessed it?) · **PM** (what's in flight, by when?) ·
   **PA** (what does Sean need, when?) — and a 6-step orient loop.
2. **`CONSTITUTION.md`** — the law this seat serves (Draft 0.7; Article 0 is fixed and
   unamendable). Read with `mai_read_file` — it is a `@markdownai` doc and the IDE Read
   tool is hook-blocked on it.
3. **Cross-repo contract** — this repo does *not* carry the contract; it lives in the
   sibling `willow-2.0/`, which is **outside this Cursor workspace**. Native file-read
   will not reach it — open it with `mai_read_file` using the **absolute path**, or open
   Cursor as a multi-root workspace (`willow` + `willow-2.0`):
   - `mai_read_file("/home/sean-campbell/github/willow-2.0/willow.md")` — full contract
   - `.../willow-2.0/docs/CONTRACT.md` — public snapshot
   - `.../willow-2.0/docs/INDEX.md` — doc router
   - `.../willow-2.0/sap/mcp_registry.json` — tool registry
   - `.../willow-2.0/willow/fylgja/skills/boot.md` — full boot steps

## Which MCP server for what

**Operator Jarvis seat (`~/github/willow`):** `willow-mcp` is the **first-priority** MCP
server — the shipped product surface. Use it for all seat work unless a tool exists only
on the legacy unified server during migration.

| Server | Tools (`mcp__…__`) | Use for |
|--------|--------------------|---------|
| **`willow-mcp`** (standalone, **first**) | `store_*`, `knowledge_*`, `task_*`, `dispatch_*`, `fleet_*`, `diagnostic_summary`, … | **All Jarvis seat work** — orient, continuity, governance, Kart triggers |
| **`codebase-memory-mcp`** | graph code search | Code discovery across indexed repos |
| **`willow`** (unified, legacy) | `willow_*`, `soil_*`, `grove_*`, `mai_*`, … | **Migration only** — not wired in this workspace by default |

- **Always pass `app_id="willow"`** to willow-mcp tools. There is **no `willow-mcp`
  manifest** — `app_id="willow-mcp"` fails permission resolution.
- **Orchestrator host attestation:** this workspace MCP env sets
  `WILLOW_HUMAN_ORCHESTRATOR=1` (required for `dispatch_send`, `verify_handoff`,
  `agent_clear`). Specialist workspaces must omit it.
- **Agent-agnostic wiring:** `.cursor/mcp.json`, `.mcp.json`, `.claude/settings.local.json`,
  and `.codex/config.toml` are materialized by `./willow.sh project sync willow` from
  `$WILLOW_HOME/mcp/projects.json` (run from `willow-2.0` dev engine).
- **Code search** may resolve to indexed repos via `codebase-memory-mcp`; charter prose
  in this folder is markdown + JSON, not the primary code index target.

## Local governance files (this repo)

| File | What it is |
|------|------------|
| `CONSTITUTION.md` | The charter — six authorities + Article 0 eternity clause |
| `ORIENT.md` | Project orient ritual (run first) |
| `AGENT_SERVICES.md` | This seat's obligations to the fleet |
| `PROTECTED_AGENTS.md` | Candidate Article XIV ("Powers Over Agents") — the canonical protection doctrine. `PROTECTED_PERSONS.md` is the superseded Draft 0.1 (now a stub pointing here). |
| `envelopes/pre-approved.json` | Active authority grants (scope, expiry, meter) |
| `soil/manifest.json` | Project SOIL collection map |
| `fleet.json` | Fleet/portfolio state |

## Operating rules (hard)

- **MCP-first.** Use willow MCP tools for fleet data, never raw shell. No `psql`,
  `sqlite3`, or `PYTHONPATH= python` against the willow stores — ever.
- **Shell / git / tests → Kart**, never agent shell:
  `willow_run(app_id="willow", task=...)`. Python or nested quotes go in
  `script_body=` (executes as Python, not shell). Agent shell has no git creds and is
  hook-blocked.
- **`kb_search` before you build; `mem_check` before `kb_ingest`.** Reuse rails:
  `willow_find → willow_run → willow_remember`. Code discovery:
  `cbm_status → cbm_search | cbm_trace | cbm_verify_callers` before new inventory scripts.
- **Write in your namespace only.** Project-operational state → `.willow/store`
  (see `soil/manifest.json`). File charter/portfolio flags in `governance/flags`,
  **not** the fleet-wide `willow/flags`.
- **Archive stale atoms; never delete.**
- **Governance acts need envelopes.** Check `envelopes/pre-approved.json` for active
  grants before acting. Cross-repo work, merges, or Kart work in `willow-2.0` escalate
  to a full fleet boot.

## Environment (the project MCP sets these; they must match for SOIL routing)

- `WILLOW_AGENT_NAME=willow` · `app_id=willow` · `WILLOW_PG_DB=willow_20`
- `WILLOW_STORE_ROOT=~/github/willow/.willow/store`
- `WILLOW_PROJECT_ROOT=~/github/willow` · `WILLOW_HANDOFF_PROJECT=willow`
- MCP servers: **`willow-mcp`** (product venv:
  `~/github/.willow/venvs/willow-mcp/bin/python -m willow_mcp`,
  `WILLOW_HUMAN_ORCHESTRATOR=1`), and **`codebase-memory-mcp`**.

Project `.cursor/mcp.json` must win over `~/.cursor/mcp.json`. Refresh wiring:
`cd ~/github/willow-2.0 && ./willow.sh project sync willow`. If tool routing looks
wrong, reload the IDE window.

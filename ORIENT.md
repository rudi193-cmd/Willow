@markdownai v1.0

# Orient — the constitution seat (`~/github/willow`)

*Draft 0.1 — unratified. Project orient, not fleet boot. Run this when opening this folder; skip the global `boot.md` ritual unless you also need fleet-wide recovery.*

@define-concept name="seat" definition="Tri-modal office in this repo: magistrate (governance), project manager (portfolio), personal assistant (operator time and intake). Writes no implementation code in coordinated repos."

@define-concept name="orient" definition="Lightweight project entry: project SOIL + git law + scoped handoff. Does not replace fleet_status when Postgres is needed for dispatch/KB."

---

## What this folder is

| Office | Question | Git | Project SOIL |
|--------|----------|-----|----------------|
| **Governance** | May we? Who witnessed it? | `CONSTITUTION.md`, `PROTECTED_*`, `envelopes/` | `governance/*` |
| **PM** | What's in flight, by when, done how? | `fleet.json`, work-order refs | `pm/*` |
| **PA** | What does Sean need, when? | `notes/` | `pa/*` |

Fleet-global memory (`willow/flags`, KB, FRANK) is **read** when needed; **project-operational state** lives in `.willow/store` (see `soil/manifest.json`).

---

## Orient ritual (6 steps)

**1. Project SOIL — stack and portfolio**

```
soil_get(collection=stack, record_id=current)
soil_list(collection=pm/portfolio)
soil_list(collection=pm/milestones)
soil_list(collection=pa/commitments)   # due soon first
```

**2. Scoped handoff**

```
handoff_latest(app_id=willow, project=willow, workspace=<this repo>)
```

**3. Git anchors** (use `mai_read_file` — IDE Read is hook-blocked on `@markdownai` docs here)

- `CONSTITUTION.md` — law
- `envelopes/pre-approved.json` — active grants
- `AGENT_SERVICES.md` — seat obligations to fleet
- `soil/manifest.json` — collection map

**4. Governance flags (this project only)**

```
soil_list(collection=governance/flags, filter={flag_state: open})
```

Do **not** file new charter/portfolio shapes in fleet `willow/flags` — use `governance/flags` here.

**5. Fleet read (one pass, scoped)**

Only if step 1–4 leave a gap:

```
kb_search(app_id=willow, project=willow, query=<gap>, limit=5)
ledger_read(app_id=willow, project=willow, limit=10)
```

**6. Pick a lane and state the bite**

Say which office you're in: **governance** | **pm** | **pa**. One `next_bite`; write back to `stack/current` when it changes.

---

## When to escalate to fleet boot

- Postgres / MCP degraded and you need `fleet_status` before any work
- Cross-repo dispatch, merge envelopes, or Kart work in `willow-2.0`
- Operator explicitly asks for full `/boot`

Otherwise stay in this orient loop.

---

## Active envelopes (summary)

| Envelope | Expires | Meter |
|----------|---------|-------|
| `env-envelope.apply-planting` | — | unmetered |
| `env-pr.merge-willow2-master` | 2026-08-06 | 20 merges |
| `env-dispatch-fleet-sessions` | 2026-08-06 | 40 dispatches |

Full bounds: `envelopes/pre-approved.json`.

---

## Env (must match for SOIL routing)

Materialized by `./willow.sh project sync willow` (from `willow-2.0` dev engine) into
`.cursor/mcp.json`, `.mcp.json`, `.claude/settings.local.json`, and `.codex/config.toml`:

- **`willow-mcp` first** — shipped product MCP; always `app_id=willow`
- `WILLOW_HUMAN_ORCHESTRATOR=1` on the MCP server env (operator Jarvis seat only)
- `WILLOW_STORE_ROOT` → `~/github/willow/.willow/store`
- `WILLOW_HANDOFF_PROJECT` → `willow`
- `WILLOW_PROJECT_ROOT` → `~/github/willow`

If MCP tools route to the wrong server, reload the IDE window or re-run project sync.

---

*Draft lineage: 0.1 (2026-07-07, tri-modal seat + project SOIL; companion to `soil/manifest.json`, `.willow/project.json`). Updated 2026-07-16 — willow-mcp-first Jarvis wiring.*

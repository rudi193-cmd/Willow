# Willow-2.0 Decommission Plan

Status: **RATIFIED FOR IMPLEMENTATION** · updated 2026-07-17 · seat: willow

Operator authorization: in-session directive 2026-07-16 19:20 MDT, recorded before work in
FRANK `045ce21e-21e7-4aa3-9e3f-db701aea0d09`. The authorization covers staged implementation
and independent verification; it does **not** waive any phase gate or authorize premature
service disablement.

Governs the retirement of the **willow-2.0 code apparatus**. Verify-don't-assert,
archive-don't-delete (per canon/02-the-discipline). Each phase has a verify gate that must pass
before the next begins. Disabling or unwiring the legacy runtime remains a separate gated act
after the standalone acceptance battery passes.

---

## 1. Scope (operator-ratified 2026-07-10)

**In scope:** retire the willow-2.0 **code + process fleet + hooks**.
**Cutover:** **staged + reversible** — disable → stop → observe → uninstall → archive. Never delete.

**Explicitly NOT in scope (survives):**
- Postgres `willow_20` + store root (`.willow/store`) — the shared substrate. No data migration.
- The **FRANK ledger** (745 entries), KB (20.6k), jeles memory — stay in place; willow-mcp keeps reading them.
- The **charter repo** (`github/willow` — CONSTITUTION, envelopes, fleet.json, soil, PROTECTED_*).
- `willow-mcp`, `willow-seed`, `willow-gate`.

## 2. Topology

| Path | Role | Fate |
|---|---|---|
| `github/willow-2.0` | The code apparatus (200-tool `mcp__willow__*` server, Kart, fleet logic) | **RETIRE** |
| `github/willow` (charter) | Constitution, envelopes, soil, PROTECTED_* | KEEP |
| `github/willow-mcp` | Successor: `src/willow_mcp`, ~50-tool platform, own `hooks/`, `deploy/` | KEEP (destination) |
| Postgres `willow_20` + `.willow/store` | Shared substrate | KEEP (no move) |
| `willow-seed` / `willow-gate` | Escape + membrane | KEEP |

MCP registrations:
- `~/.cursor/mcp.json:7` → `willow-2.0/sap/unified_mcp.sh` (WILLOW_ROOT=willow-2.0) = **the 200-tool server → DE-REGISTER**
- `github/willow/.cursor/mcp.json` + `.mcp.json` → `python -m willow_mcp` (app_id willow / willow-mcp) = **KEEP**

## 3. Current dependency knot (verified 2026-07-17)

The original 2026-07-10 assessment is partly obsolete. The executor extraction and Postgres
queue binding are built; the production cutover is not.

**Completed engineering:**
- Kartikeya `0.0.1` is a standalone package and a hard `willow-mcp` dependency.
- `WillowMcpTaskQueue` binds Kartikeya to the adopted Postgres task table; SQLite fallback,
  `willow-mcp worker`, heartbeat publication, and stranded-queue diagnostics exist.
- `session_enter` supplies human-orchestrator/specialist/dispatch entry and persona context.

**Cutover blockers:**
- **Executor authority:** Kartikeya still treats stored `# allow_net` as authority. The operator
  selected signed per-task authorization before cutover. The signature must bind submitter,
  exact task hash, expiry, nonce, and scope; no MCP tool or worker may mint it.
- **Worker productionization:** no installer-managed worker service exists; Postgres lane
  filtering, claim ownership/time, and stale recovery are incomplete. The running executor is
  still the willow-2.0 worker.
- **Project orientation:** `ORIENT.md` uses logical slash-delimited collections, while
  willow-mcp rejects `/` and the Willow manifest scopes only `willow_*`/`projects_*`.
  Standalone project SOIL orientation therefore fails.
- **Native startup:** the standalone hook enforces MCP/store/egress rules but does not perform
  SessionStart. Fylgja still supplies the persona picker and boot gate.
- **Consent writer:** willow-mcp is deliberately read-only; the writer remains
  `willow-2.0/willow/fylgja/global_settings.py`.
- **Governance continuity:** standalone session entry does not yet surface project-scoped
  handoff/FRANK state, envelope citations/meters are not mechanically enforced, and
  `fleet_status` is not aligned with the charter roster.

**Resolved (probe 2026-07-10):** Grove is **NOT** a willow-mcp dependency — `dispatch_*` is file-backed
(`paths.dispatch_root()`), no `grove_serve`/`:7777` calls. `the_grove.py`/`GroveOAuthProvider` are unrelated
local concepts. So `grove-serve`/`grove-mcp`/`grove-ngrok`/`willow-grove-listen` → **retire** (caveat: external
Discord/Grove reach is a product feature decision, not a dependency). `vault.py`/`pgp.py` already ported standalone.

Until every blocker above is resolved and the clean-environment gate passes, disabling
willow-2.0 breaks either execution, orientation, consent, or governance. **This is Phase 1.**

## 4. Unit classification (`systemctl --user`)

**Retire — willow-2.0-only, no survivor depends:**
`nest-watcher` · `orin-worker` · `willow-discord-responder` · `willow-w8-census.timer` · `willow-wce.timer`
· `willow-metabolic.{service,socket,timer}` · `willow-bridge-cross-runtime` (already disabled)
· `grove-serve` · `grove-mcp` · `grove-ngrok` · `willow-grove-listen` (Grove not a willow-mcp dep — probe
  2026-07-10; retire unless external Discord/Grove reach is wanted as a product feature)

**Re-home or keep — survivor depends (resolve in Phase 1):**
`kart-worker` · `kart-worker-batch` (Kart executor — willow-mcp's only execution backend)

**Separate ownership — out of this scope (decide individually):**
`willow-bot` (own repo, uvicorn) · `sentinel-watchdog` (`~/.willow/fleet-dispatch/`)

**Survivor — ENABLE:** `willow-mcp-serve.service` (willow-mcp, port 8766, currently disabled)

**Hooks:** fylgja (persona picker, boot injection, MCP-first blocks, pgp gate) → replace with willow-mcp
native `hooks/` (`pre_tool_use` exists). The persona-picker removal your constraint names lives here.

## 5. Phases (each gated on verify)

**Phase 0 — Inventory & classification.** [complete]
Units, registrations, successor repositories, and hook ownership are classified. `dispatch_*`
is file-backed and does not need Grove. Project-local MCP wiring already prefers willow-mcp;
the global `~/.cursor/mcp.json` still registers the legacy unified server.

**Phase 1 — Re-home the backends + strip willow deps (THE work).** [in progress]
- **1a — Secure executor:** signed per-task network envelope verified at execution; release and
  pin the first Kartikeya version carrying fail-closed authorization.
- **1b — Production worker:** real lane claims, claim timestamps/ownership, stale recovery,
  terminal timestamps, worker service templates, and install/status/uninstall support.
- **1c — Native project orientation:** explicit logical-to-physical collection aliases,
  archive-first record migration, project-aware `session_enter`, project-scoped v3 handoffs,
  and explicit FRANK status.
- **1d — Native startup:** invoke `session_enter` through supported-client SessionStart wiring;
  remove the picker/sentinel protocol rather than porting it.
- **1e — Operator settings:** operator-only willow-mcp consent CLI with atomic fail-closed writes;
  never expose consent enablement as an MCP tool.
- **1f — Governance continuity:** minimum FRANK append/read, envelope citation/meter enforcement,
  and charter-roster compilation.
- **1g — Grove:** resolved as not a dependency; retire unless retained as a separately authorized
  product feature.
- **Gate:** a session with ONLY willow-mcp (no `mcp__willow__` server, no fylgja) boots, orients, submits AND
  runs isolated and signed-network Kart jobs, writes a consent setting through the operator CLI,
  reads/writes a project handoff, appends/verifies FRANK, and reports the charter roster — with
  zero reach into `willow-2.0/`. Every acceptance claim requires an independent verifier.

**Phase 2 — Disable (reversible).**
`systemctl --user disable --now` the retire-list units; de-register `~/.cursor/mcp.json:7`; unwire fylgja.
Keep backups of every unit file + config. Enable `willow-mcp-serve`.

**Phase 3 — Observation window (seven clean working days, willow-mcp only).**
Run day-to-day. Watch for broken tool calls, missing boot context, silent governance gaps (who writes the
FRANK ledger now?), Kart/Grove regressions. Success = clean working days with no willow-2.0 reach-back.

**Phase 4 — Uninstall & archive.**
Remove unit files (after stop+disable); tag a final willow-2.0 commit and **push to remote** (durability, like
seed/gate); mark the repo read-only / move aside. **Do not delete.** Final config cleanup.

## 6. Risks / open questions
- **Governance continuity:** FRANK append/read and envelope citation/meter enforcement must be
  re-homed before Phase 2; retaining the Postgres chain is intentional, but retaining willow-2.0
  code to access it is not.
- **Membrane gap:** fylgja currently provides the write-protection/MCP-first membrane. willow-gate is meant to
  replace it, but operator constraint = no agent in the gate yet. There may be a window with neither. Flag before unwiring.
- **Do hook/MCP changes mid-session:** tearing out fylgja changes the live environment. Do unwiring **between** sessions.
- **Task authority:** `submitted_by` alone is a database assertion. The signed task envelope is
  required so a shared-table writer cannot forge another app's network authority.
- **Project state:** do not manufacture missing records. Inventory the legacy/project stores,
  migrate with provenance, and archive source records after verification.

## 7. Constraint chain (operator, standing)
No agent installed in willow-gate until: (1) persona picker removed, (2) willow-mcp boots standalone with zero
willow deps. This plan's Phase 1 gate **is** condition (2); Phase 1c **is** condition (1).

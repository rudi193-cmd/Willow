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

### 3a. First observed reach-back (willow, 2026-07-30, logged at operator direction)

Both `willow-mcp-worker-{fast,batch}.service` units were installed but never enabled, so **no
Kart worker was alive on either lane**; `fleet_health` reported the batch lane stranded. Starting
them restored execution (fast lane verified end-to-end: task `G2F70UC2`, bwrap, rc 0). Enabling
the units is still outstanding — this recurs on every reboot until it is done.

Draining the batch lane surfaced a standing **willow-2.0 reach-back**, task `D0AE504A`:

```
"${WILLOW_PYTHON:-python3}" /home/sean-campbell/github/willow-2.0/scripts/willow_embed_backfill.py
```

Queued by `sap_startup` (willow-2.0 `sap/sap_mcp.py`) at every boot. It failed `rc 2` on all three
attempts with ENOENT. **The script is not missing** — it exists on disk. bwrap reports an unmounted
path as ENOENT, and the sandbox manifest said so explicitly: `path not mounted in sandbox`.

Mechanism, confirmed against the artifacts — two independent Phase 1 changes each severed the path:

1. `kartikeya/src/kartikeya/sandbox.py:114` `willow_repo_root()` resolves, when `$WILLOW_ROOT` is
   unset, in the order `$WILLOW_MCP_REPO` → installed `willow_mcp` tree → `~/github/willow-mcp` →
   legacy `~/github/willow-2.0` (**last**). The new worker units set no `WILLOW_ROOT` — by design,
   so workers "do not inherit hidden willow-2.0 paths" — so `{{WILLOW_ROOT}}` in
   `kart-sandbox.json#bind_read_write` now renders to **willow-mcp**. willow-2.0 gets no mount.
2. The fleet `kart-sandbox.json#bind_try` enumerates ~30 repos and does **not** include willow-2.0.
   The vendored default's `{{HOME}}/github` blanket was replaced by enumeration in the 2026-07-22
   vault unbind (`BCFF95C8` → `B05ECA31` → `0AEAFA7A`). Before that, willow-2.0 was reachable
   through the blanket.

**Reading:** this is Phase 1 working, not a Kart defect. Do **not** re-add willow-2.0 to `bind_try`
— that reverts two deliberate decommission moves to keep a legacy startup job alive. The gate's
"zero reach into `willow-2.0/`" condition is now partly enforced *by the sandbox itself*, and this
job is the first thing it caught.

**Carried into Phase 1 / Phase 3:**
- Stop `sap_startup` queuing the job (it lives in willow-2.0, itself retire-scope).
- Port embed-backfill into willow-mcp before Phase 2. Not a path edit: the script imports
  `core.agent_identity`, `core.embedder`, `core.pg_bridge`, `core.willow_store` — four willow-2.0
  core modules. Losing it degrades semantic search over `knowledge` / `opus_atoms` / `jeles_atoms`.
- **Unestablished, needs a probe:** how long this has been failing (pattern says since 2026-07-22;
  dating the 171 failed task rows needs DB access the seat lacks), and how far behind the
  embeddings actually are — that decides whether the port is urgent or merely tidy.

**Monitoring finding (§6 candidate):** a startup job failed on every boot for roughly a week and
nothing surfaced it. It came to light only because the operator asked for a lane restart. Phase 3's
observation window assumes reach-back is *noticed*; on this evidence it is not. A reach-back
detector — diff task paths against the sandbox mount policy — should precede Phase 3, not follow it.

### 3b. Crossing census (willow seat, 2026-08-05, gate open for the first time)

Signing the nine manifests opened every gated verb and made the seat's own state readable.
Nine faults surfaced in one session; classified by origin, **five are 2.0 crossover and four
are not** — which is the number that decides whether unwiring is the fix.

**2.0 crossover — recurring, felt every session:**

| Crossing | Where it lives | Disposition |
|---|---|---|
| Hook redirects name `willow_run` / `willow_find` / `soil_list` / `kb_search` — none wired here | fylgja `PreToolUse` | Phase 1h |
| `[WILLOW-LANES]` banner advertises the same dead verbs | fylgja `UserPromptSubmit` | Phase 1h |
| Persona picker + boot sentinel gate (cost the first four turns) | fylgja | Phase 1d |
| `.claude/settings.local.json` exports `WILLOW_ROOT` / `WILLOW_PYTHON` / `PYTHONPATH` into 2.0 | project config | Phase 2 |
| `willow-metabolic.timer` → `willow.sh metabolic` → nightly `norn_pass` | 2.0 unit | **disabled 2026-08-05** |
| 5 user crontab lines against `~/willow-2.0` (a second copy outside `github/`) | crontab | Phase 2 |

**Not 2.0 — one-time willow-mcp/host config, three closed the same night:** unsigned manifests
under PGP enforcement (root cause of the "no_manifest" incident; nine signed, code fix in
willow-mcp **PR #294**); `mcp_apps` owned by `willow-operator` via `harden-trust-root`, so the
operator cannot sign into it without `sudo install`; worker units installed-but-never-`enable`d;
and the `knowledge` schema mapping unconfirmed, which leaves this seat able to read 21,907 atoms
and write none.

**Why cloud agents do not hit these.** Not a code difference — a fresh home with enforcement
off, no `harden-trust-root` chown, and no fylgja layer. The local seat is not running worse
software; it is running the same software through a 2.0 harness.

**The 488-failure backlog, now readable.** 488 failed / 282 completed (63%), not a retry loop —
attempts terminate correctly at 3. Two causes, both 2.0: `kart-sandbox.json` binds
`willow-2.0/.venv-dev` read-only but never the repo body, so any task whose *script* lives there
dies "No such file or directory" while Kart itself names the reason in
`result.sandbox_manifest.notes`; and the nightly `auto_dream.py … # allow_localhost` is denied
`network_authorization_denied: signed envelope missing` twice a night, correctly — an unattended
cron cannot hold an operator-signed envelope by construction. **Deliberately not fixing the
sandbox bind:** it would spend authority on a retiring tree, and with the timer disabled nothing
enqueues from there.

### 3c. Boot-surface census (willow seat, 2026-08-05, read via codebase-memory)

Read at willow-mcp `35d7285` (PR #294 head) and willow-2.0 `dd780da`. **Source only — not the
live wiring**; `.claude/settings.json` on this host may differ from what either repo ships.

willow-mcp registers **two** hook events (`SessionStart`; `PreToolUse` × 4 matchers,
`.claude-plugin/plugin.json`). 2.0 ships **seven** event modules with a `main()`:
`session_start` · `prompt_submit` · `pre_tool` · `post_tool` · `stop` · `session_stop` · `shutdown`.

The line counts overstate the gap. `session_start_hook.handle()` is 19 lines against 2.0's
284-line `main()`, but willow-mcp moved the orientation **into the verb**: `server.session_enter`
(`server.py:2931-2988`) returns project info, ORIENT presence, five store collections (stack,
portfolio, milestones, commitments, governance flags), `latest_handoff`, collection aliases and
FRANK status; `dispatch.session_enter` adds `persona_context` + `seed_context` with the exposure
slice. Most of the *content* has already crossed.

**What has not crossed is the capture side and the continuation side.**

| # | Gap | 2.0 owner | Bites? |
|---|---|---|---|
| 1 | **No Stop/SessionEnd hook.** 2.0's `stop.py` writes the stack snapshot the *next* boot renders as `[STACK]`. willow-mcp's closeout is an agent-invoked verb (`session_handoff_write` / `handoff_write_v4`) — agent forgets or session dies, nothing is written. | `events/stop.py` | **yes — producer gap** |
| 2 | **Corrections lane has no producer.** `_seed_corpus_corrections` (`session_start.py:690`) globs `~/.claude/**/memory/feedback_*.md` → SOIL `corpus/corrections`, idempotent by key; boot reads it back with counts, caps and human-over-automated precedence. willow-mcp's `seed_loader` has the agent seed + exposure slice and **no** corrections/preferences/confirmations lanes. | `events/session_start.py` | **yes — live** |
| 3 | **SessionStart is continuation-blind.** `handle()` never reads `source`. 2.0 branches on `startup\|resume\|clear\|compact`: lite injection, dedup fingerprint, ledger resume context. (Boot-sentinel inheritance in the same branch dies with §1d — fine. Dedup and lite-inject do not.) | `events/session_start.py` | **yes — token cost per compact** |
| 4 | No `UserPromptSubmit` hook. Persona picker (cosmetic — voice only), lane banner (dead verbs, good riddance), **`[CLOCK]` UTC-vs-local stamp (load-bearing, no successor)**. | `events/prompt_submit.py` | partly |
| 5 | No `PostToolUse` hook — feeds `recent_traces` and the `learned denials — automated` lane. willow-mcp has `friction_scan` / `friction_flags_list` as verbs, nothing auto-recording. | `events/post_tool.py` | no |
| 6 | No boot liveness assembly and **no degraded verdict**. 2.0: `postgres == "unknown" → BOOT DEGRADED — invoke /startup before responding to anything.` willow-mcp owns every input (`fleet_health`, `env_check`, `diagnostic_summary`, `heartbeat.py`, `soil_heartbeat.py`) — nothing assembles them, nothing refuses to proceed. | `events/session_start.py` | safety property |

**The asymmetry, named:** willow-mcp inherited the *read* side of boot and left the *write* side
in 2.0. Everything that surfaces at session open is a verb you can call; everything that fills
those surfaces **between** sessions is still a fylgja hook. This is also why cloud agents do not
notice — they enter, read, leave, and never depend on what the last session deposited.

**Consequence for Phase 1h:** the `PreToolUse` half is a true peer swap and stays as written.
The `SessionStart` half is **not** — repointing it today loses gaps 3 and 6 and, via gap 2,
silently stops feeding SOIL from the operator's own feedback files. That half is a build
(Phases 1i / 1j), not a repoint.

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
  *[built + installed; verified running 2026-07-30 — see §3a. **Both lanes started and
  `enable`d 2026-08-05**; queue drained 13 → 0. Item closed.]*
- **1c — Native project orientation:** explicit logical-to-physical collection aliases,
  archive-first record migration, project-aware `session_enter`, project-scoped v3 handoffs,
  and explicit FRANK status.
- **1d — Native startup:** invoke `session_enter` through supported-client SessionStart wiring;
  remove the picker/sentinel protocol rather than porting it. *[**Gated on 1i + 1j** as of
  2026-08-05 — §3c found willow-mcp's SessionStart hook is a 19-line stub and the boot
  capture path is still 2.0's. Repointing before those land loses state silently.]*
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

**Phase 1h — Hook membrane handover (`PreToolUse` only).** [ready to build; unblocks Phase 2]
*Scope narrowed 2026-08-05 by §3c: this phase covers the `PreToolUse` swap and the
`UserPromptSubmit` banner removal. The `SessionStart` repoint moved to §1d and is gated on
1i + 1j, because willow-mcp's SessionStart hook is a stub, not a peer.*
*Mechanism verified 2026-08-05 — see §3b. Written from the mechanism, not the symptom:
the first draft of this order said "fix fylgja's redirect text," which would have kept the
2.0 hook alive forever.*
- The successor already exists in-repo: `willow_mcp/pre_tool_hook.py` → `willow_mcp/bundle/
  hooks/pre_tool_use.py`, seven guards including the sudo invariant (FRANK `90e52ab7`),
  raw-store access, Write/Edit against owned SQLite, self-granted egress, and the
  IDE-native web tools. Its redirect hints name `task_submit`, `store_search`,
  `knowledge_search`, `code_graph_search`, and the IDE `Read` tool — **all live verbs.**
- So this is not a port and not an edit. It is: stop loading the fylgja hook, load
  willow-mcp's. Fylgja's hook source is deliberately unreadable to agents
  (`WILLOW_HOOK_MAINTENANCE=1` for maintainers), so the swap is operator-run.
- Steps: (1) back up `~/.claude/settings.json` and `.cursor/hooks.json`; (2) repoint the
  `PreToolUse` matcher at `willow_mcp.pre_tool_hook:main`; (3) drop the fylgja
  `UserPromptSubmit` banner that advertises the dead verbs; (4) confirm a blocked `ls`
  now names a verb the seat actually holds; (5) then §1d removes the picker/sentinel.
- **Do it between sessions** (§6), and keep the boot gate for last — it is the one whose
  failure locks the seat out rather than merely annoying it.

**Phase 1i — Session capture path (willow-mcp build).** [prerequisite for §1d]
*Closes §3c gap 1. The one item here that is not convenience: without it, unwiring 2.0 means
no session deposits anything for the next session to find, and the loss is silent.*
- Add a `SessionEnd`/`Stop` hook to willow-mcp (`plugin.json` + `src/willow_mcp/`) that writes
  the stack snapshot — open tasks, open threads, pending decisions — on session close.
- It must be a **hook, not a verb.** `session_handoff_write` already exists and is the
  agent-invoked path; the whole defect is that an agent that forgets, or a session that dies,
  writes nothing. Capture cannot depend on the agent remembering.
- Consumer side: `session_enter` already returns `latest_handoff`; extend `orientation` with
  the snapshot so the read side lands the moment the write side exists.
- Verify: kill a session without a closeout, open a new one, confirm the snapshot is present.

**Phase 1j — Corrections pump + continuation awareness (willow-mcp build).** [prerequisite for §1d]
*Closes §3c gaps 2, 3 and 6.*
- **Corrections pump (gap 2):** port `_seed_corpus_corrections` into `seed_loader` — glob the
  operator's memory `feedback_*.md`, idempotent put into `corpus/corrections`, and surface
  corrections / preferences / confirmations as distinct lanes with counts, caps, and the
  human-over-automated precedence rule 2.0 already encodes. **Check the path grant first:**
  the pump reads the operator's memory directory, which is not this seat's namespace.
- **Continuation awareness (gap 3):** teach `session_start_hook.handle()` to read `source`;
  lite injection on `compact|resume|clear`, dedup fingerprint to suppress an identical
  re-injection. Do **not** port the boot-sentinel inheritance — that dies with §1d.
- **Degraded verdict (gap 6):** assemble the liveness inputs willow-mcp already owns
  (`fleet_health`, `env_check`, `diagnostic_summary`, `soil_heartbeat`) and emit an explicit
  *boot is degraded, do not act* line. This is a safety property, not a banner — willow-mcp
  currently has no way to say it.
- Out of scope, dying with the tree: `PostToolUse` traces / learned-denials (§3c gap 5), the
  persona picker and lane banner (gap 4). **Keep the `[CLOCK]` UTC-vs-local stamp** — it has
  no successor and the one-day artifact gap is a real reading hazard.

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
- ~~**Membrane gap:**~~ **RESOLVED 2026-08-05.** The window with neither does not exist:
  willow-mcp already ships the membrane (`bundle/hooks/pre_tool_use.py`, seven guards).
  willow-gate is not on the critical path for unwiring fylgja, and the operator constraint
  on installing an agent in the gate does not block Phase 1h. See §3b and Phase 1h.
- **The redirect targets are the live wound.** Fylgja routes every blocked `ls`/`grep`/`cat`/
  python to `willow_run` / `willow_find` / `soil_list` / `kb_search` — verbs from the legacy
  unified server that this project's `.mcp.json` does not wire. There is no legal successor
  for those commands today; the seat reads files one at a time. This is the single largest
  source of per-session friction and Phase 1h closes it.
- **The capture path fails silently.** §3c: willow-mcp holds the read side of boot, 2.0 still holds
  the write side. Unwire `SessionStart` before 1i/1j land and sessions stop depositing state — with
  no error, because every *read* surface still answers. Nothing looks broken until the day a
  session needs what the last one should have left. This risk is what gates §1d.
- **Do hook/MCP changes mid-session:** tearing out fylgja changes the live environment. Do unwiring **between** sessions.
- **Task authority:** `submitted_by` alone is a database assertion. The signed task envelope is
  required so a shared-table writer cannot forge another app's network authority.
- **Project state:** do not manufacture missing records. Inventory the legacy/project stores,
  migrate with provenance, and archive source records after verification.

## 7. Constraint chain (operator, standing)
No agent installed in willow-gate until: (1) persona picker removed, (2) willow-mcp boots standalone with zero
willow deps. This plan's Phase 1 gate **is** condition (2); Phase 1c **is** condition (1).

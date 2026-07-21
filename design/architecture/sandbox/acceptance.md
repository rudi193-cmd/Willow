# New-user sandbox — acceptance checklist

Spec: [willow-new-user-draft.drawio](../willow-new-user-draft.drawio) (WORKING DRAFT 2026-07-20).

**Run on:** Cursor cloud agent or future persistent VM only. Do not run `sandbox-smoke.sh` on the operator T500 when memory is tight — review results in `LAST-RUN.md` instead.

Drive notes: [SANDBOX-FINDINGS.md](SANDBOX-FINDINGS.md)

## Core flow (You → Willow → hub)

| ID | Draft element | Check | Pass criteria |
|----|---------------|-------|---------------|
| A1 | You | Keys & approval | Smoke sets isolated `WILLOW_HOME`; egress keypair exists after `setup-egress` |
| A2 | Your tools | (manual) | Cursor / CLI can point MCP at sandbox env printed by smoke |
| A3 | Willow bench | Hub reachable | `diagnostic_summary` verdict is `ok` or `degraded` (not `broken`) |
| A4 | willow-mcp hub | Home layout | `willow-mcp-init` creates `$WILLOW_HOME` with `mcp_apps/`, `store/`, config |
| A5 | Hub → vault | Your data | `store_stats` succeeds (smoke seat has `store_read` only); Postgres schema applied when PG available |
| A6 | Vault → computer | Hosted locally | `WILLOW_HOME` path is under sandbox `.sandbox/` (gitignored) |

## Gate (SSH · PGP · egress)

| ID | Draft element | Check | Pass criteria |
|----|---------------|-------|---------------|
| G1 | SSH | (deferred) | Phase 0 does not provision SSH; documented for Phase 1 VM |
| G2 | PGP / signed apps | Egress keys | `~/.config/willow-mcp/egress/public.pem` exists (or sandbox override path) |
| G3 | Egress consent | Standing consent | `settings.global.json` has `consent.internet` (sandbox writes via helper — not TTY `consent set`) |
| G4 | Hub → Gate | Egress gate | `willow-mcp gates --json` shows internet consent; `task_submit` with `allow_net=true` denied without lease |
| G5 | Gate → world | (partial) | Net task path not required in Phase 0 if `--skip-kart`; lease + signed envelope documented in AGENT-RUN.md |

## Kart (bundled)

| ID | Draft element | Check | Pass criteria |
|----|---------------|-------|---------------|
| K1 | Hub → Kart | Task queue | `task_submit` returns `pending` + `task_id` (requires Postgres + `schema_confirm_mapping` for `tasks`) |
| K2 | Kart worker | Execution | `willow-mcp worker --lane fast --once` completes task; result contains `sandbox-smoke-ok` |
| K3 | bwrap | (best-effort) | If bwrap missing, smoke records skip reason (not a hard fail for Phase 0) |

## SAFE store → optional apps

| ID | Draft element | Check | Pass criteria |
|----|---------------|-------|---------------|
| S1 | SAFE catalog | Compile | `willow-mcp-compile --force` after init |
| S2 | Pick at onboarding | (manual) | Operator/agent selects Jeles / UTETY toggles — smoke uses flags |
| J1 | Jeles optional | Repo | `~/github/Jeles` exists with `docs/architecture.md` (or `--skip-jeles`) |
| U1 | UTETY optional | Repo | `~/github/UTETY` exists with `utety/core/` (or `--skip-utety`) |

## Phase 0 exit

All of: **A3**, **A4**, **G2**, **G3**, and either **K1+K2** (Postgres path) or documented skip with reason.

---

## Phase 1 (deferred) — persistent cloud VM

Start only after Phase 0 is green in a cloud agent run.

| Prerequisite | Notes |
|--------------|-------|
| Fly.io or VPS | One VM = “your computer + `{user}-data-vault`” |
| Postgres volume | Persistent data; not ephemeral container |
| systemd units | [willow-mcp/deploy/willow-mcp-serve.service.template](https://github.com/rudi193-cmd/willow-mcp/blob/master/deploy/willow-mcp-serve.service.template) + worker template |
| SSH + onboard | Operator SSH in; run same `sandbox-smoke.sh` against persistent `WILLOW_HOME` |
| Jeles remote | `WILLOW_JELES_BASE_URL` → [jeles-remote](https://github.com/rudi193-cmd/jeles-remote) on Fly |
| Multi-tenant | Out of scope until single-tenant VM is stable |

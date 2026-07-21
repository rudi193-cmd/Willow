# Sandbox drive — findings (2026-07-21)

Driven via `sandbox-smoke.sh` on this host. Exit 0; Kart worker did not complete a shell task.

## What passes

| Box | Result | Notes |
|-----|--------|-------|
| Bootstrap | ok | Docker PG on `127.0.0.1:55432`, schema applied |
| Doctor | ok | `diagnostic_summary` verdict ok (net_lease warn expected) |
| Hub / vault layout | ok | Isolated `$WILLOW_HOME` under `.sandbox/` |
| Store | ok | `store_stats` via `sandbox-admin` |
| Schema confirm | ok | `tasks` mapping confirmed (per-app) |
| Task queue | ok | `task_submit` → `pending` + `task_id` |
| Gate deny | ok | `allow_net=true` refused without `task_net` permission |
| Jeles / UTETY | ok | Repo presence checks |

## What breaks (or degrades)

### 1. Kart worker — bwrap namespace failure (hard on this host)

```
bwrap: Creating new namespace failed: Resource temporarily unavailable
```

- `task_submit` succeeds; `willow-mcp worker --once` claims the task then fails at sandbox setup.
- Plain `bwrap` works in a normal shell — failure is context-specific (nested agent sandbox, mount pressure, or user-namespace quota under Cursor).
- Task stays `pending` with `result.error: sandbox_setup_failed`; retries scheduled.
- **Phase 0:** documented skip in `LAST-RUN.md` (acceptance K3).
- **Route better:** smoke could treat `task_submit` alone as K1 pass and gate K2 on `status=completed`; cloud agents without nested bwrap limits should get green K2.

### 2. Kart mount policy routes to operator fleet (routing bug for new-user)

Even with isolated `WILLOW_HOME`, Kart resolves `willow_repo_root()` → `~/github/willow-2.0` because kartikeya probes for `core/kart_sandbox.py` / `core/pg_bridge.py` and falls back to the fleet checkout.

Observed mounts in failed task:

- `bound_ro`: entire `~/github`, `willow-2.0/.venv`, operator `~/.willow/mcp_apps`
- `bound_rw`: `willow-2.0`, `~/.willow`, operator caches

**Not** the new-user draft model (`willow-mcp` hub + `{user}-data-vault` only).

**Route better (smoke harness — applied):**

- Ship `kart-sandbox.json` template; smoke renders real paths into `$WILLOW_HOME/kart-sandbox.json` and sets `KART_SANDBOX_CONFIG` to the rendered file
- `unset WILLOW_ROOT` in smoke script
- Kart `bound_rw` now targets `willow`, `willow-mcp`, and sandbox `WILLOW_HOME` (not `willow-2.0`)
- kartikeya still auto-binds `willow-2.0` venv paths via `willow_repo_root()` fallback — product fix still needed

### 3. Consent file path — smoke wrote the wrong file (fixed)

Smoke was writing `$WILLOW_HOME/settings.global.json` (legacy). `willow-mcp-init` creates **canonical** `$WILLOW_HOME/config/settings.global.json`, which `consent.py` reads first. The smoke write was ignored.

Gate deny still passed because init already had `internet: false` in canonical — lucky, not correct.

**Fix:** smoke now writes `config/settings.global.json`.

### 4. Egress keys are operator-global, not sandbox-local

`setup-egress` → `~/.config/willow-mcp/egress/` (by design: keys live outside `WILLOW_HOME`). Correct for production; means smoke does **not** prove a greenfield user can bootstrap egress in isolation without touching operator config.

**Route better:** document in acceptance; Phase 1 VM gets its own `XDG_CONFIG_HOME`.

### 5. Schema mappings are per-app (friction)

`schema_confirm_mapping` for `sandbox-admin` does not unlock `hanuman` or `willow`. Smoke needs a dedicated `sandbox-admin` seat with `schema_admin` + `task_queue` + `store_read`.

**Route better:** product could offer fleet-wide schema confirmation for a DB fingerprint, or `sandbox-bootstrap.sh` could confirm `tasks` once for a bootstrap app.

### 6. Schema map churn per ephemeral DB

Each Docker PG instance gets a new DB fingerprint → new files under `mcp_apps/sandbox-admin/schema_maps/`. Harmless for smoke; noisy under `.sandbox/`.

**Route better:** reuse a fixed `WILLOW_PG_DB=willow_sandbox` when port 55432 is dedicated to smoke.

### 7. Doctor noise

Every `doctor` / `diagnostic_summary` logs INFO `gate: denied tool 'task_net'` — expected, but clutters agent paste.

**Route better:** downgrade to DEBUG when denial is the designed gate path.

## Gate routing — works as designed

Three-key egress model layers correctly in smoke:

1. **Manifest** — `task_net` not in `sandbox-admin` → `net_denied` before lease/consent
2. **Consent** — `internet: false` in canonical settings
3. **Lease** — none (`net_lease: warn` in doctor)

Smoke's `allow_net=true` curl task fails at step 1 with a clear manifest error. Good.

## Recommended next routes

| Priority | Change | Where |
|----------|--------|-------|
| P0 | Canonical consent path in smoke | `sandbox-smoke.sh` (done) |
| P0 | Minimal `kart-sandbox.json` for new-user | `sandbox/` + smoke install step (done) |
| P1 | Kart `willow_repo_root` fallback off willow-2.0 | kartikeya 0.0.3 (done) |
| P1 | `sandbox-bootstrap.sh` confirms `tasks` schema | willow-mcp |
| P2 | Smoke reuses fixed PG db name | `sandbox-smoke.sh` (done: `willow_sandbox` + named container) |
| P2 | `SANDBOX-FINDINGS.md` → acceptance cross-links | docs (done) |

## Re-run

```bash
cd ~/github/willow/design/architecture/sandbox
GITHUB_ROOT=~/github ./sandbox-smoke.sh
cat LAST-RUN.md
```

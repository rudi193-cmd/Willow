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

### 1. Kart worker — bwrap + rlimit preexec (fixed in smoke)

```
bwrap: Creating new namespace failed: Resource temporarily unavailable
```

- Root cause on this host: kartikeya's POSIX `RLIMIT_AS` / `RLIMIT_NPROC` preexec runs in the bwrap child **before** namespace setup; without `KART_CGROUP_PARENT`, rlimit mode breaks bwrap.
- **Workaround:** `WILLOW_KART_NO_RLIMIT=1` (smoke sets this in `sandbox_env()`).
- Plain `bwrap` and `build_bwrap_argv` subprocess tests pass; only `run_shell` with resource caps fails.
- **Product follow-up:** apply limits via cgroup leaf when parent is delegated, or set rlimits inside the sandbox after bwrap exec — not in the preexec that precedes namespace creation.

### 2. Kart mount policy — willow-mcp-first (fixed in kartikeya 0.0.4+)

kartikeya now prefers `WILLOW_MCP_REPO` / installed `willow_mcp` before `willow-2.0`. With editable kartikeya + smoke `kart-sandbox.json`:

- `bound_rw`: `willow`, `willow-mcp`, sandbox `WILLOW_HOME` (no `willow-2.0` rw)
- `bound_ro`: may still include `willow-2.0/.venv-dev` via global venv fallback / `KART_EXTRA_VENVS`
- `path_dirs` may still list `~/.willow/venv/bin` when operator fleet venv exists

**Remaining route:** optional `KART_EXTRA_VENVS` unset in smoke; kartikeya could skip fleet venv candidates when `WILLOW_HOME` is explicit.

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

## Data-vault layout (`--vault` / `sandbox-vault-smoke.sh`)

Drive notes (2026-07-21):

| Item | Status | Notes |
|------|--------|-------|
| Full smoke (fresh + reuse) | ok | Exit 0; Kart completes |
| Secrets + SOIL in box | ok | `WILLOW_HOME == WILLOW_STORE_ROOT` at box root |
| Postgres PGDATA in box | ok | `postgres/data/` via Docker volume; check via `docker exec` |
| KB ingest + search | ok | After `schema_confirm_mapping(knowledge)` + manifest perms |
| Empty `store/` subdir | friction | `willow-mcp-init` creates `store/` even when store root is the box — harmless |
| `kart.db` at box root | friction | Pre-provisioned by blueprint; Postgres queue is authoritative when PG up |
| Egress keys | unchanged | Still operator-global `~/.config/willow-mcp/egress/` |

```bash
GITHUB_ROOT=~/github ./sandbox-vault-smoke.sh --fresh
cat LAST-RUN-VAULT.md
```

# Run new-user sandbox smoke (Cursor cloud agent)

Use this in a **Cursor cloud agent** session. Do not run on the operator T500 when memory is tight.

## Repos needed

Clone or mount alongside each other:

| Repo | Path |
|------|------|
| willow (charter + this harness) | `~/github/willow` |
| willow-mcp | `~/github/willow-mcp` |
| willow-data-vault (vault layout) | `~/github/willow-data-vault` |
| Jeles (optional check) | `~/github/Jeles` |
| UTETY (optional check) | `~/github/UTETY` |

## Copy-paste agent prompt

```text
Run the new-user sandbox smoke harness. Do NOT use operator Postgres or ~/.willow.

cd ~/github/willow/design/architecture/sandbox
chmod +x sandbox-smoke.sh
GITHUB_ROOT=~/github ./sandbox-smoke.sh

If Postgres via Docker fails, retry with: ./sandbox-smoke.sh --skip-kart
Paste the full contents of LAST-RUN.md when done.
```

## Data-vault layout (Postgres + SOIL + secrets in the box)

Uses `willow-data-vault/bootstrap/provision.sh` per the blueprint README — `WILLOW_HOME == WILLOW_STORE_ROOT` at `.sandbox-vault/data-vault/`, Postgres PGDATA at `postgres/data/` inside the box.

```bash
cd ~/github/willow/design/architecture/sandbox
GITHUB_ROOT=~/github ./sandbox-vault-smoke.sh --fresh
# or: ./sandbox-smoke.sh --vault --fresh
```

Report: `LAST-RUN-VAULT.md`

## Environment (agent sets automatically)

| Variable | Default | Purpose |
|----------|---------|---------|
| `GITHUB_ROOT` | parent of `willow/` | Finds Jeles, UTETY, willow-mcp |
| `WILLOW_MCP_REPO` | `$GITHUB_ROOT/willow-mcp` | Bootstrap source |
| `SANDBOX_ROOT` | `./.sandbox` | Isolated state (gitignored) |
| `WILLOW_HOME` | `$SANDBOX_ROOT/willow-home` | Vault + hub data |
| `WILLOW_APP_ID` | `sandbox-admin` | Smoke seat (`schema_admin` + `task_queue` + `store_read`) |
| `KARTIKEYA_REPO` | `$GITHUB_ROOT/kartikeya` | Editable install when present (0.0.3+ for willow-mcp-only routing) |
| `WILLOW_PG_DB` | `willow_sandbox` | Stable Docker PG db (reuses container `willow-sandbox-pg`) |
| `PG_CONTAINER` | `willow-sandbox-pg` | Named Postgres container |

## Non-TTY notes

- `willow-mcp onboard --enable-internet` requires a TTY. Smoke uses:
  - `willow-mcp setup-egress` (no TTY)
  - Direct write to `$WILLOW_HOME/config/settings.global.json` for consent baseline
- `willow-mcp consent set` also requires TTY — use settings file in sandbox only.
- Full egress task path: operator runs `willow-mcp grant-net sandbox-admin --ttl 30m` + `sign-net-task` on a real terminal (Phase 1).

## Flags

```bash
./sandbox-smoke.sh --fresh          # wipe .sandbox/willow-home and re-bootstrap
./sandbox-smoke.sh --skip-kart      # SOIL-only / no Postgres
./sandbox-smoke.sh --skip-jeles
./sandbox-smoke.sh --skip-utety
./sandbox-smoke.sh --skip-pg        # passes WILLOW_SKIP_PG to bootstrap
```

## Success

See [acceptance.md](acceptance.md) and [SANDBOX-FINDINGS.md](SANDBOX-FINDINGS.md). After run, commit or paste [LAST-RUN.md](LAST-RUN.md) (generated, gitignored).

## MCP client (optional follow-up)

After smoke, point Cursor MCP at the sandbox using values printed by `willow-mcp/scripts/sandbox-bootstrap.sh`:

```json
{
  "willow-mcp": {
    "command": "/path/to/willow-mcp/.venv/bin/python3",
    "args": ["-m", "willow_mcp"],
    "env": {
      "WILLOW_HOME": "/path/to/sandbox/.sandbox/willow-home",
      "WILLOW_STORE_ROOT": "/path/to/sandbox/.sandbox/willow-home/store",
      "WILLOW_APP_ID": "sandbox-admin"
    }
  }
}
```

Do **not** set `WILLOW_ROOT=willow-2.0`. This harness is willow-mcp only.

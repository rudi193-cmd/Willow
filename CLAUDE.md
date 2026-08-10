# Agent instructions — willow (constitution seat)

You are in the **willow** fleet's governance / charter repo
(`~/github/willow-memory/willow`). This folder holds the law, envelopes, and portfolio
state; the code lives in the sibling `willow-mcp/` under the same org folder.

> **Layout moved 2026-08-10.** `~/github/` is now one directory per GitHub org — see
> [`governance/LOCAL_GITHUB_LAYOUT.md`](governance/LOCAL_GITHUB_LAYOUT.md). The old flat
> `~/github/willow` and `~/github/.willow` paths are gone; `~/.willow` is a symlink to
> `~/github/willow-memory/.willow`. **`willow-2.0` is tier F — archived, not cloned.**
> Anything still telling you to run `./willow.sh` from it is stale.

**Read first:** [`AGENTS.md`](AGENTS.md) (cold-start map) · [`ORIENT.md`](ORIENT.md) (project
orient ritual — run this, not the global fleet boot, unless fleet-wide recovery is needed).

## Identity

- **Fleet identity is `willow`.** Always pass `app_id="willow"` to willow-mcp tools — there
  is no `willow-mcp` manifest (`app_id="willow-mcp"` fails). Persona is voice only; it
  never changes the agent id, `app_id`, Grove sender, or SOIL namespace.
- **Expect the persona/boot gate.** Fylgja hooks lock MCP until you confirm a persona and
  the boot sentinel is written. Confirm persona first, then orient — the gate outranks
  ORIENT's "skip boot."

## MCP

- **`willow-mcp` is first priority** (plus `codebase-memory-mcp`). The legacy unified
  `willow` server is migration-only and not wired here by default.
- **MCP-first, always.** No `psql`, `sqlite3`, or raw Python against willow stores.
  Shell, git, and tests → `task_submit` / Kart via willow-mcp — agent shell is
  hook-blocked and has no git creds.
- **`@markdownai` docs** (`CONSTITUTION.md`, `ORIENT.md`) must be read with `mai_read_file`,
  not the native Read tool.
- **Cross-repo contract:** the `willow-2.0/willow.md` contract is **not on disk** — that
  repo is archived. Current product docs are in the sibling `willow-mcp/`:
  `README.md`, `DEVELOPER.md`, `docs/`.

## Operating rules (hard)

- **Write in-namespace only:** project state → `.willow/store`; charter flags →
  `governance/flags`, not fleet-wide `willow/flags`.
- **`knowledge_search` before you build;** archive stale atoms, never delete.
- **Governance acts need envelopes** — check `envelopes/pre-approved.json` before acting.
- Cross-repo work, merges, or Kart work in `willow-mcp` / `kartikeya` escalate to a full
  fleet boot.

## Wiring

IDE configs (`.mcp.json`, `.claude/settings.local.json`, `.cursor/mcp.json`,
`.codex/config.toml`) are materialized from `$WILLOW_HOME/mcp/projects.json` by the
**`willow-mcp` CLI**. `./willow.sh` is gone with `willow-2.0`:

```bash
export WILLOW_HOME=~/github/willow-memory/.willow
W=$WILLOW_HOME/venvs/willow-mcp/bin
$W/willow-mcp project sync willow      # materialize IDE wiring
$W/willow-mcp doctor                   # health check, with copy/paste fixes
```

Reload the IDE after sync if tool routing looks wrong.

**Rebuilding the venv from scratch** (it is gitignored runtime, not checked in):

```bash
python3 -m venv $WILLOW_HOME/venvs/willow-mcp
$WILLOW_HOME/venvs/willow-mcp/bin/pip install -e ~/github/willow-memory/willow-mcp
$W/willow-mcp-init                                          # scaffold $WILLOW_HOME
$W/willow-mcp onboard --project-root ~/github/willow-memory/willow
```

**The `willow` and `github` entries in `projects.json` are not editable in place.**
`load_registry()` overlays them from `willow-mcp/src/willow_mcp/deploy/mcp_projects.seed.json`
on every load and persists the result, so a local edit silently reverts. Fix the seed.

**Charter test/lint loop** (stdlib-only; mirrors `.github/workflows/`):

```bash
python3 -m venv .venv && .venv/bin/pip install 'ruff==0.15.0' bandit coverage
.venv/bin/ruff check mem_ratify && .venv/bin/bandit -r mem_ratify -ll -q
python3 -m unittest discover -s mem_ratify/tests -t . -p "test_*.py"
python3 -m unittest discover -s tools/tests -t . -p "test_*.py"
python3 tools/doc_gate.py
```

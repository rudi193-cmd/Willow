# Agent instructions — willow (constitution seat)

You are in the **willow** fleet's governance / charter repo (`~/github/willow`). The code
lives in the sibling `willow-2.0/`; this folder holds the law, envelopes, and portfolio
state.

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
  not the native Read tool. Cross-repo contract lives in `willow-2.0/` (outside this
  workspace) — use `mai_read_file` with an absolute path, e.g.
  `/home/sean-campbell/github/willow-2.0/willow.md`.

## Operating rules (hard)

- **Write in-namespace only:** project state → `.willow/store`; charter flags →
  `governance/flags`, not fleet-wide `willow/flags`.
- **`knowledge_search` before you build;** archive stale atoms, never delete.
- **Governance acts need envelopes** — check `envelopes/pre-approved.json` before acting.
- Cross-repo work, merges, or Kart work in `willow-2.0` escalate to a full fleet boot.

## Wiring

IDE configs (`.mcp.json`, `.claude/settings.local.json`, `.cursor/mcp.json`,
`.codex/config.toml`) are materialized from `$WILLOW_HOME/mcp/projects.json`:

```bash
cd ~/github/willow-2.0 && ./willow.sh project sync willow
```

Reload the IDE after sync if tool routing looks wrong.

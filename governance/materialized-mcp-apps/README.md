# Materialized MCP manifests (2026-08-06)

Compiled from **willow-mcp bundle** `specialists.json` (not the stale `$WILLOW_HOME/config` overlay).

Install into the fleet home:

```bash
cd ~/github/willow
WILLOW_HOME=~/github/.willow ./governance/scripts/install-materialized-mcp-apps.sh
```

If `compile-agents --force` fails with **Permission denied** on `mcp_apps/*/manifest.json`, the tree is owned by `willow-operator`. Either:

```bash
sudo chown -R "$USER":willow-operator ~/github/.willow/mcp_apps
```

then compile, **or** use the install script above (pre-built manifests). After adding `willow-operator`, try **`newgrp willow-operator`** or a **fresh login** before group write works without chown.

To compile from bundle (once writable):

```bash
WILLOW_HOME=~/github/.willow ~/github/.willow/venvs/willow-mcp/bin/willow-mcp compile-agents --force \
  --registry ~/github/willow-mcp/src/willow_mcp/bundle/config/specialists.json
```

Then **reload Cursor MCP** (or restart the IDE). Jarvis seat `.cursor/mcp.json` already sets `WILLOW_HOME` to `~/github/.willow`.

**Willow manifest** here adds `schema_admin` + `task_queue` for G3 schema confirm + Kart witness (operator seat).

**Loki** includes `frank_read` and **no** charter `collection_aliases` (G1/G6).

After install, optional G3 probes (orchestrator seat, new MCP process):

- `schema_confirm_mapping(app_id="willow", table="tasks", preview=True)` then confirm
- `task_submit` a trivial Kart task on `tasks` and poll to terminal

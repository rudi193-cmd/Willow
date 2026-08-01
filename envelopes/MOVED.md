# This directory's default-path role has moved to willow-mcp

**Status:** superseded as the *default* home. `pre-approved.json` and
`syscall-table.json` in this directory are kept as historical/reference
record (archive, don't delete) — they are this operator's real, already-
issued grants and verb table as of 2026-07-22 / 2026-07-06. They are **no
longer read by default** by any current willow-mcp checkout.

**Successor:** `willow-mcp`'s `envelopes.py` (`registry_path()` /
`syscall_path()`) now defaults to `$WILLOW_HOME/constitutional/pre-approved.json`
and `$WILLOW_HOME/constitutional/syscall-table.json` — see
`src/willow_mcp/paths.py`'s `envelope_registry_path()` / `syscall_table_path()`.
`willow-mcp-init` seeds that location with an **empty-shape** starter registry
(`src/willow_mcp/bundle/constitutional/pre-approved.json`) and a real copy of
the syscall table (same directory) — the registry starts empty on purpose,
because a live registry is this operator's own ratified grants, not shippable
package content; the syscall table ships real because it's generic verb
mechanism, not a secret.

**Reason.** Two separate problems used to be solved by one fact — this
directory living in a git repo willow-mcp reached across to by default:
1. willow-mcp had a hard dependency on a sibling `willow` charter repo
   existing at all, just to resolve its own fail-closed governance gate.
2. This operator's live grants (real paths, real dates, real kart-sandbox
   bind config) were committed to git here — the same "repo is blueprint, not
   data" problem `docs/design/safe-app-installer.md` D7 already names for the
   vault, just not yet applied to this file.

Both are fixed the same way: the *mechanism* ships with willow-mcp; the *live
data* moves to `$WILLOW_HOME`, which is local, operator-owned, and never
committed to any repo — same treatment as the vault.

**What actually migrates, and what doesn't (yet).** `federation-wire-format.md`
moved verbatim to `willow-mcp/docs/design/federation-wire-format.md` — it's a
generic draft protocol spec, not operator data, so there was nothing to leave
behind; this directory no longer carries a copy. `pre-approved.json` and
`syscall-table.json` are **not** auto-migrated: this operator's real 15 active
envelopes, 3 `pre_approved` entries, and 2 proposals stay exactly as they are
in this file until manually copied into `$WILLOW_HOME/constitutional/
pre-approved.json` on the real machine. Until that copy happens,
`WILLOW_ENVELOPE_REGISTRY` can still point straight at this file — the
override was never removed, only the *default* changed — so nothing breaks
before the migration; it just isn't automatic.

**Why the stub (this file) exists rather than a silent directory removal:**
so the next person to `ls envelopes/` finds the reason and the successor
paths in the same place they'd have looked for the registry itself.

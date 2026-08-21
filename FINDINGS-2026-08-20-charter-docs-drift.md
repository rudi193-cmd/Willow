# Findings — 2026-08-20 — charter documentation, checked against the tree

Method borrowed from Nestor's own doc audits
(`FINDINGS-2026-08-05-docs-standup.md`, `FINDINGS-2026-08-10-docs-refresh.md`):
**drift reconciliation** — every checkable claim verified against the artifact it
describes, never against memory. Nestor's rule that a seal means *a person checked
this*, never *the tests passed*, is the frame: a documentation claim is a claim,
and an unverified claim is not a true one.

That frame was chosen because every failure this session was the same shape — an
unverified claim treated as verified. Three of them were mine.

Scope: the 2026-08-10 org-directory move and the 2026-08-20 repo transfers, against
every `.md` in this repo. Mechanical drift corrected; doctrinal disagreement flagged,
not amended.

---

## What was checked, and how

| Check | Result |
|-------|--------|
| Internal markdown links resolve | 2 broken of ~200 |
| Filesystem paths (`~`, `$HOME`, `{{HOME}}`) exist | **42 dead** |
| Pre-move flat paths vs. org layout | 12 files, 38 references |
| Old paths named *deliberately* (as gone) | 3 — correctly left alone |

The 42 dead paths are not one defect. They separate into four classes, and
treating them as one would have made three of the four worse.

---

## Corrected (mechanical)

**`governance/FLEET_PLACEMENT_DRAFT.md`** — 18 "Local today" cells asserted
pre-move disk locations: `~/github/nestor`, `~/github/willow-mcp`, `~/github/Jeles`,
`~/github/UTETY`, `~/github/terpsi-music`, and all 12 almanac verticals. Every one
repointed into its org directory. The file now has **zero** dead paths.

**`governance/materialized-mcp-apps/README.md`** — a live install runbook in which
*every* path was pre-move. Copy-pasting it today fails at `cd`. Repointed: the repo,
`$WILLOW_HOME`, the venv binary, and the `specialists.json` registry.

**Charter location claims.** Three sites said the constitution repo's path was
"unsettled" or named `~/github/willow`. It has been at `~/github/willow-memory/willow`
since 2026-08-10. Corrected, and — the distinction that was actually being lost —
separated from the **GitHub transfer** of `rudi193-cmd/Willow`, which genuinely is
still open. Local path and remote owner are two questions; only the second is unsettled.

**`fleet.json`** — described the roster as needing alignment with
`willow-2.0/core/safe_agents.py`, a standing obligation against a file archived on
2026-08-10. Rewritten to record the alignment as unresolved and point at the
roster gap and the FRANK `7d071410` hold, rather than inventing a new target.

**`ORIENT.md`** — told the reader to run `./willow.sh project sync willow` "from the
`willow-2.0` dev engine"; escalation trigger named Kart work "in `willow-2.0`". Both
corrected. Its envelope table also drifted from the registry (expiry `2026-08-06`
against the registry's `2026-09-06`) and is now marked as non-authoritative.

**`CLAUDE.md`** — instructed agents that `load_registry()` re-overlays the `willow`
and `github` entries from the seed, so local edits revert and you must "fix the seed."
**That behaviour no longer exists**; the overlay was removed upstream. The instruction
sent a reader to edit a file that changes nothing. Corrected, with the real defect
recorded in its place (see below).

---

## Left alone, deliberately

**Old paths named as gone.** `CLAUDE.md:9`, `AGENTS.md:9`, `LOCAL_GITHUB_LAYOUT.md:20`
name `~/github/willow` and `~/github/.willow` in order to say they no longer exist.
Rewriting these would delete the warning. A path-existence check flags them; a reader
does not.

**Historical records.** `governance/SERVICE_MIGRATION.md` (a dated decision record),
`design/willow-2.0-decommission-plan.md`, and the `design/architecture/sandbox/*`
run records reference archived paths *as history*. The rule applied throughout:
**fix anything that tells you to use a dead path; keep anything that says one existed.**

**Two broken links** — `design/architecture/sandbox/AGENT-RUN.md → LAST-RUN.md` and
`seed/canon/README.md → ../MAINTAINER.md`. Both point at files that were never
committed. Left for the author; creating a stub to satisfy a link checker would be
the worst of both outcomes.

---

## Flagged, not amended (doctrinal)

**`Homestead · Sovereign` vs `Homestead · Affairs`** — two ratified naming decisions
in conflict (2026-08-03 and 2026-08-10). Root ratified **Affairs** in session on
2026-08-20 on the evidence of `homestead-law/README.md`; scribed to FRANK `25f83bce`
and applied across 10 sites. *Sovereign* is retained as the leg's **content** — the
five-point test, exit, anti-capture — not its name.

**`project sync` is not deterministic** — `_willow_mcp_server_block()` seeds
`WILLOW_STORE_ROOT` from `store_root()`, which reads the **ambient process
environment**, before any registry override is considered. A shell exporting that
variable bakes it into every `.mcp.json` it writes. The `_skip_store_override()`
guard does not catch it: the guard inspects the registry entry, while the value
that lands comes from the environment. Fix is in `willow-mcp`, cross-repo, not taken.
FRANK `58b6912c` (first diagnosis — **wrong mechanism**) → `7d9d1faf` (corrected).

**Five envelopes in `active[]` grant unexpired authority over `rudi193-cmd/willow-2.0`**,
a repo that no longer exists, and all three `pre_approved[]` filesystem grants carry
`enforced_by` pointing into the archived sandbox config. The real enforcer is
`$WILLOW_HOME/kart-sandbox.json`, verified from a Kart task's own
`sandbox_manifest.config_source`. Retiring dead grants and repointing `enforced_by`
are verb 12 — root's acts.

---

## The pattern underneath

Four of tonight's defects, and the two I got wrong myself, are one class: **a tool or
a document resolving an artifact it never confirmed.** The seed guidance described a
code path that had been deleted. `search_code` returned `0 matches` for a tree that
did not exist. `frank-anchor` reported an empty ledger as unanchored. `project sync`
reads a store root from whichever shell invoked it. Each fails *open* and *quietly* —
answering confidently about something it never found.

Gap `006e0144da95` asked whether there was a third instance. There are at least five,
and the newest is this document's own former guidance.

*Checked by running. Nothing above is read-only speculation.*

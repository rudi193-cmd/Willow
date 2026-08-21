# Ratification bundle — repoint every filesystem path in the envelope registry

**Status:** proposal · drafted by willow 2026-08-21 · **root's act (verb 12)**
**Registry:** [`envelopes/pre-approved.json`](../../envelopes/pre-approved.json)
**Scope:** every `paths[]` and `enforced_by` in `pre_approved[]` and `active[]`

---

## The finding

The 2026-08-10 org-directory move invalidated **every filesystem grant in the
constitution**, and nothing reported it.

Measured 2026-08-21 across all 15 active envelopes and all 3 pre-approved
grants: **9 of 9 filesystem paths do not exist on this box.** Not only the
tier-F ones — `willow-mcp` and `kartikeya` are cloned here, and their grants
point at pre-move flat paths too.

| envelope | paths | on disk |
|---|---|---|
| `env-fs.write-willow-mcp` | 1 | **0** |
| `env-fs.write-kartikeya-migration` | 1 | **0** |
| `env-fs.write-kart-fast-timeout` | 5 | **0** |
| `env-fs.write-kart-sandbox-vault-unbind` | 2 | **0** |
| `pre_approved[]` (3 grants) | 4 | 1 (`~/.willow`, via symlink) |

Meanwhile **every remote target is live**: `willow-2.0` (pushed 2026-08-19),
`willow-mcp` (2026-08-19), `kartikeya` (2026-08-05), none archived.

**So the registry is internally inconsistent.** A grantee holds `git.commit` and
`pr.open` against a repository they cannot `fs.write` a file in. The verbs that
reach GitHub work; the verb that touches the disk does not. Nobody hit a
refusal, because a bind that fails open is indistinguishable from one nobody
wanted — the same shape as the 31 dead `bind_try` entries in
`$WILLOW_HOME/kart-sandbox.json`, one layer up in the law.

### A correction this proposal is built on

An earlier note in `ORIENT.md` (commit `ba332ae`) called `rudi193-cmd/willow-2.0`
*"a repo that no longer exists"* and marked its merge envelope **DEAD TARGET**.
**That was false**, and it was written into the charter. willow-2.0 is live and
merging; **tier F means not cloned on this box**, which
`FLEET_PLACEMENT_DRAFT.md` §8 states exactly. Corrected in place 2026-08-21.
This proposal therefore does **not** retire anything for being "dead."

---

## Proposed changes

### 1. Repoint paths that moved (mechanical)

| from | to |
|---|---|
| `{{HOME}}/github/willow` | `{{HOME}}/github/willow-memory/willow` |
| `{{HOME}}/github/willow-mcp` | `{{HOME}}/github/willow-memory/willow-mcp` |
| `{{HOME}}/github/kartikeya` | `{{HOME}}/github/willow-memory/kartikeya` |
| `{{HOME}}/github/.willow` | `{{HOME}}/github/willow-memory/.willow` |

`{{HOME}}/.willow` is left alone — it is a symlink into the new location and
still resolves. Named here so a later reader does not "fix" it.

### 2. Decide what a tier-F path means (**not** mechanical)

Seven `active[]` paths name files inside `{{HOME}}/github/willow-2.0`, which is
**deliberately not cloned** (§8). The files all still exist upstream — verified
against GitHub — so the grants are not stale, but they cannot be exercised here.

Three options, and this is the one that needs a decision rather than a rewrite:

- **(a) Leave them.** Honest: the grant describes a box where willow-2.0 *is*
  cloned. Cost: `fs.write` stays unusable on this box, and the registry keeps
  reporting paths that fail an existence check.
- **(b) Make the path conditional** — e.g. `{{WILLOW_2_ROOT}}`, unset here. The
  grant becomes explicitly environment-scoped instead of silently broken.
- **(c) Retire the `fs.write` halves** and keep `git.commit`/`pr.open`, on the
  reasoning that work on a repo this box does not clone happens elsewhere.

### 3. Repoint `enforced_by` (3 grants)

All three `pre_approved[]` entries carry
`enforced_by = willow-2.0/willow/fylgja/config/kart-sandbox.json`, which is not
on disk. The **actual** enforcer is `$WILLOW_HOME/kart-sandbox.json` — verified
2026-08-20 from a Kart task's own `sandbox_manifest.config_source`
(`config_is_vendored_default: false`). Every `enforced_by` in the law is
currently a dangling reference.

### 4. Fix the planting envelope's registry path

`env-envelope.apply-planting` — the envelope licensing this seat to exist —
carries `registry_path: "envelopes/pre-approved.json"`, resolved by the enforcer
under `$WILLOW_HOME/constitutional/`, where a **starter stub** sits instead of
the real 466-line registry. **Verb 13 is unenforceable today** (gap
`a089df0ae05f`, FRANK `20c2bd75`). Either the path is absolutised or the real
registry is restored to the enforced location. Root's act either way, and the
seat has been citing this authority all session while it does not resolve.

---

## Two findings the sweep produced that are not path defects

**`env-fs.write-willow-mcp`, `env-git.commit-willow-mcp`, `env-pr.open-willow-mcp`
have no expiry.** Standing, unmetered-by-time write and PR authority over the
shipped product. Every other action envelope in the registry expires. Worth an
explicit decision rather than an inherited one.

**`env-fs.write-willow-mcp` is granted to two grantees** — `hanuman` and `kart` —
the only envelope in the registry with a list rather than a name. Intentional or
not, it is unique and should be stated as one or the other.

---

## What is NOT proposed

- No envelope is retired for being "dead." Nothing here is dead.
- `env-pr.merge-willow2-master` is untouched: merge authority into a repo that is
  actively merging. Whether that is still wanted is a separate question.
- The **completed** `kart-sandbox-vault-unbind` work (verified: `sean-data-vault`
  appears 0 times in upstream's sandbox config) is noted but not retired here —
  retiring spent grants is worth doing and deserves its own decision, not a
  rider on a path fix.
- The **unlanded** `kart-fast-timeout` work (`KART_FAST_TIMEOUT` appears 0 times
  in upstream `core/kart_execute.py` and `core/kart_worker.py`) expires in 27
  days with the fix still outstanding. Flagged, not decided.

---

## Ratification

Verb 12 (registry edit) is root-only and non-grantable. This document is the
proposal; willow scribes the result under `env-envelope.apply-planting` (verb
13) **if and when** §4 makes that envelope enforceable again — which is
currently the open question underneath all of this.

*Drafted from measurement, not recall: every path checked against the filesystem,
every repo against the GitHub API, every "did the work land" against upstream
file contents.*

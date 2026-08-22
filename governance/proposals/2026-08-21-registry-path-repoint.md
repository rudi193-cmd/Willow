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

> **[REV 2 — this claim is now false. See “Revision 2” at the end.]**

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
**deliberately not cloned** (§8) **and, since 2026-08-22, archived — see Revision 2 §B.**
The files all still exist upstream — verified
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

### 4. ~~Fix the planting envelope's registry path~~ — **WITHDRAWN, and it was wrong**

**Corrected 2026-08-21 by executing it instead of reading about it.**

This section claimed the enforced registry held *"a starter stub"* and that
**"verb 13 is unenforceable today."** Both false, and the claim was repeated
several times in session before it was checked.

What is actually true, established by calling `envelope_apply`:

1. The enforced registry holds **exactly one entry** — `env-envelope.apply-planting`
   itself. Not a stub: tranche 0, deliberately.
2. **Root already fixed this on 2026-08-11**, and the entry records it in a
   `restored[]` block: *"Enforced registry found empty 2026-08-11; empty since
   the 2026-08-10 layout move. Re-issued alone as tranche 0 so verb 13 returns
   and every later entry can be scribed under citation."* `registry_path` was
   changed **relative → absolute**; no other field altered. Filed as
   `willow-mcp #332(a)`. Root did it by hand and said why: *"the seat held no
   verb 13 to scribe with, because this entry is what grants it."*
3. Tonight's only real blocker was a **directory permission**.
   `$WILLOW_HOME/constitutional` was `0o775` — group-writable — and
   `paths.py:33` refuses on `st_uid != euid or S_IMODE & 0o022`. `chmod 755` on
   the directory and `644` on its files, and verb 13 returns `ok: true`.

Two `EAMBIG` refusals were hit on the way, both correct and both naming the
fault precisely: `untrusted ownership or permissions on source path`, then
`bounds mismatch [registry_path]` when the call passed the relative form the
**charter copy** still carries.

**Which surfaces the one real finding in this section.** The charter's
`envelopes/pre-approved.json` still has the **relative** `registry_path` and no
`restored[]` block. The enforced copy has both. **The registry in this repo is
behind the one that governs** — the opposite of what this document assumed, and
the reason to read the enforced copy first.

Proposed instead: **sync the charter registry to the enforced copy** for this
entry (absolute path + the `restored[]` provenance), so the committed law and
the enforced law agree.

**What is NOT fixed, per the envelope's own words:** *"Pinning the path here
fixes this entry; it does not fix the class, and the syscall table's verb 13
bounds signature still describes a relative path."* Gap `006e0144da95` stands.
Every envelope minted against that signature inherits the defect —
`constitutional/syscall-table.json`, verb 12.

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
  actively merging **— no longer true; the repo is archived. See Revision 2 §B.**
  Whether that is still wanted is a separate question.
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
proposal; willow scribes the result under `env-envelope.apply-planting`
(verb 13), **which is live** — verified 2026-08-21, `ok: true`, citation
`367deea1`. §4 originally made this conditional on repairing that envelope; it
needed no repair, only `chmod 755` on the trust directory.

*Drafted from measurement, not recall: every path checked against the filesystem,
every repo against the GitHub API, every "did the work land" against upstream
file contents.*

---

# Revision 2 — 2026-08-22

**Companion:** [`2026-08-22-governed-path-write-gate.md`](2026-08-22-governed-path-write-gate.md) — this proposal fixes what the registry *says*; that one fixes whether anything stops an agent rewriting it. Its authorizing envelope is one this document repoints, so this one lands first.

**Re-measured against the tree and the GitHub API, not against Revision 1.**
Revision 1 was drafted early on 2026-08-21. Later the *same* session archived
`willow-2.0` and transferred six repositories to the `willow-memory` org. Two of
Revision 1's load-bearing claims did not survive its own session.

## A. What Revision 1 got wrong

1. **"Every remote target is live."** False as of 2026-08-22.
   `rudi193-cmd/willow-2.0` is `archived: true` (verified via `gh api`). Seven
   `active[]` envelopes bind to it.
2. **"`env-pr.merge-willow2-master` … a repo that is actively merging."** False.
   GitHub refuses writes — merges included — on an archived repository. That
   envelope is not merely unexercisable *on this box*; it is unexercisable
   anywhere until the repo is unarchived.

Neither error was in the measurement. Both were facts that changed under the
document after it was written, and nothing re-checked them.

## B. §2 has collapsed — the tier-F question no longer has three answers

Revision 1 §2 offered (a) leave / (b) conditional path / (c) retire the
`fs.write` halves, on the reasoning that the willow-2.0 files "all still exist
upstream, so the grants are not stale." That reasoning is spent. With the repo
archived, the seven willow-2.0 envelopes —

| envelope | verb |
|---|---|
| `env-pr.merge-willow2-master` | pr.merge |
| `env-fs.write-kart-fast-timeout` | fs.write |
| `env-git.commit-kart-fast-timeout` | git.commit |
| `env-pr.open-kart-fast-timeout` | pr.open |
| `env-fs.write-kart-sandbox-vault-unbind` | fs.write |
| `env-git.commit-kart-sandbox-vault-unbind` | git.commit |
| `env-pr.open-kart-sandbox-vault-unbind` | pr.open |

— cannot be exercised by any grantee on any box. Option (b) is now
ceremony over a target nothing can write to. **The live question is only whether
root retires them now or lets them expire** (`2026-09-17` and `2026-09-22`;
the merge envelope `2026-09-06`). Retiring is still verb 12 and still root's.

Note what this does *not* settle: `kart-fast-timeout` was flagged in Revision 1
as **unlanded** work — `KART_FAST_TIMEOUT` appears 0 times in upstream
`core/kart_execute.py` and `core/kart_worker.py`. Archiving the repo does not
land it. If that fix is still wanted, it needs a target that accepts writes, and
that is a new envelope against a new repo, not a repoint of this one.

## C. New finding — the remote bounds are stale in the opposite direction

Revision 1 scoped itself to `paths[]` and `enforced_by`. That scope is too
narrow. **Four envelopes name an owner that no longer owns the repository:**

| envelope | `bounds.repo` says | GitHub says |
|---|---|---|
| `env-git.commit-willow-mcp` | `rudi193-cmd/willow-mcp` | `willow-memory/willow-mcp` |
| `env-pr.open-willow-mcp` | `rudi193-cmd/willow-mcp` | `willow-memory/willow-mcp` |
| `env-git.commit-kartikeya-migration` | `rudi193-cmd/kartikeya` | `willow-memory/kartikeya` |
| `env-pr.open-kartikeya-migration` | `rudi193-cmd/kartikeya` | `willow-memory/kartikeya` |

This is not cosmetic. Scalar bounds are compared by **exact string equality** —
`willow_mcp/envelopes.py:105`, `return actual == grant`; the `fnmatch` branch
applies only to list-valued grants, and these are scalars. So:

- A grantee who passes the repository's **true** name, `willow-memory/willow-mcp`,
  is **refused** with `EAMBIG / bounds mismatch` — the same refusal shape that
  the relative `registry_path` produced on 2026-08-21.
- A grantee who passes the **old** name is admitted, and GitHub's transfer
  redirect quietly delivers the act to the new repo. The law authorizes a name
  that no longer identifies its target, and the act lands anyway.

The second case is the more serious one, and it is this proposal's own thesis
recurring one layer up: **an authorization resolving through a redirect it never
confirmed, failing open and quiet.**

**Proposed:** repoint all four to `willow-memory/…`. `willow-2.0` is *not*
repointed — it stayed at `rudi193-cmd` and was archived there, so its bounds are
still truthful; §B governs its envelopes, not this section.

## D. New finding — `{{HOME}}/github/.willow` is no longer missing. It is a decoy.

Revision 1 listed `{{HOME}}/github/.willow` (in `reach-willow-home-rw`, grantee
`kart`, mode `rw`) among the paths that do not exist. **It exists again** —
recreated 2026-08-20, mode `0775`, containing exactly one file:

```
/home/sean-campbell/github/.willow/active-agent   →   "willow"
```

The fleet home is `~/github/willow-memory/.willow`. So a standing read-write
grant that Revision 1 could report as *safely broken* now **resolves, to the
wrong directory**. A missing path fails closed and gets noticed. A path that
resolves to a near-empty stub does not.

**Proposed:** repoint to `{{HOME}}/github/willow-memory/.willow`, and delete the
stray `~/github/.willow` — deleting it is not a governance act and needs no
envelope, but it should happen in the same breath, or the next sweep re-finds it
and reads it as legitimate.

## E. Correction to Revision 1 §3 — `enforced_by` is documentation, not enforcement

Revision 1 called all three `enforced_by` values "dangling references," which is
true, and implied repointing them restores enforcement, which is not.
**`enforced_by` is read by no code**: `grep -rn "enforced_by" willow-mcp/src
--include=*.py` returns nothing. It is a prose claim about where enforcement
lives. Repointing it makes the law *honest*; it changes no behaviour.

Worth stating plainly because the file it should point at,
`$WILLOW_HOME/kart-sandbox.json`, is mode **`0664` — group-writable**. That is
the exact condition `paths.py:33` (`S_IMODE & 0o022`) refuses on, and it is what
blocked verb 13 on 2026-08-21 until `chmod 755`. Nothing checks this file's
permissions today because nothing reads it from the registry at all. If
`enforced_by` ever becomes load-bearing, it will refuse on day one.

## F. The change set, in full

Root's act, verb 12. Mechanical parts first.

**F1 — filesystem repoints (unchanged from Revision 1 §1, still correct):**

| from | to |
|---|---|
| `{{HOME}}/github/willow` | `{{HOME}}/github/willow-memory/willow` |
| `{{HOME}}/github/willow-mcp` | `{{HOME}}/github/willow-memory/willow-mcp` |
| `{{HOME}}/github/kartikeya` | `{{HOME}}/github/willow-memory/kartikeya` |
| `{{HOME}}/github/.willow` | `{{HOME}}/github/willow-memory/.willow` (§D) |

`{{HOME}}/.willow` is left alone — a symlink into the new location, still
resolving. `{{HOME}}/github/willow-2.0/**` is left alone — see §B.

**F2 — remote repoints (new, §C):** four envelopes, `rudi193-cmd/willow-mcp` →
`willow-memory/willow-mcp` and `rudi193-cmd/kartikeya` → `willow-memory/kartikeya`.

**F3 — `enforced_by` repoints (three `pre_approved[]` entries, §E):**
`willow-2.0/willow/fylgja/config/kart-sandbox.json` →
`$WILLOW_HOME/kart-sandbox.json`, fragments (`#bind_read_write`, `#bind_try`)
preserved. Honesty fix only.

**F4 — decisions, not rewrites:**

1. **The seven willow-2.0 envelopes** (§B): retire now, or let them lapse
   2026-09-06 / -17 / -22.
2. **The three no-expiry `willow-mcp` grants** — `env-fs.write-willow-mcp`,
   `env-git.commit-willow-mcp`, `env-pr.open-willow-mcp` all carry
   `expires_at: null`. Verified 2026-08-22: they are the **only** action
   envelopes in the registry without an expiry. Standing, time-unmetered write
   and PR authority over the shipped product.
3. **`env-fs.write-willow-mcp`'s two grantees** — `["hanuman", "kart"]`, the
   registry's only list-valued grantee. Note this interacts with §C: because the
   grantee field is a list it takes the `fnmatch` branch, while `bounds.repo`
   stays an exact-match scalar. Intentional or inherited — root should say which.

**F5 — out of scope, still open:** gap `006e0144da95`. The verb 13 bounds
signature in `constitutional/syscall-table.json` still describes a **relative**
`registry_path`, so every envelope minted against it inherits the 2026-08-10
failure. That is the class; everything above is instances.

## G. Provenance

Every claim in this revision was produced 2026-08-22 by execution, not recall:
paths by `test -e` against the live tree, repository owner and archived state by
`gh api repos/…`, the exact-match comparison by reading
`willow_mcp/envelopes.py:95-105` and `:216-221`, the `enforced_by` dead end by
grep over `willow-mcp/src`, expiries and grantees by `jq` over the charter
registry.

**Read order for whoever acts on this:** the **enforced** registry at
`$WILLOW_HOME/constitutional/pre-approved.json` governs; the charter copy in this
repo is the committed record. As of 2026-08-22 the enforced copy holds one entry
(`env-envelope.apply-planting`, tranche 0) and the charter copy holds fifteen.
They are not two views of one registry, and neither is a substitute for the other.

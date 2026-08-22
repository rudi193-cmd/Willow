# Proposal — block writes to the registry at the tool boundary, in shell and out

**Status:** proposal · drafted by willow 2026-08-22 · **willow-mcp code change**
**Companion:** [`2026-08-21-registry-path-repoint.md`](2026-08-21-registry-path-repoint.md) — that one fixes what the registry *says*; this one fixes whether anything stops you rewriting it.
**Target:** `willow-mcp/src/willow_mcp/bundle/hooks/pre_tool_use.py`
**Envelope required:** `env-fs.write-willow-mcp` — grantees `hanuman`, `kart`. **Not this seat.**

---

## The finding

**The PreToolUse guard has no notion of the law it protects.** Measured
2026-08-22 by feeding the hook the actual commands this session ran:

| command, targeting `envelopes/pre-approved.json` | hook returns |
|---|---|
| `sed -i s/a/b/ …` | **nothing** |
| `echo hi >> …` | **nothing** |
| `rm …` | `warn` |
| `Edit` tool, same file | **nothing** |

`grep -n "envelopes\|constitutional\|governance" pre_tool_use.py` returns two
comment lines and no rule. To the guard, the envelope registry is an ordinary
file. This proposal was itself drafted by rewriting a governance document with
`sed -i` and appending two hundred lines with `cat >>`; nothing objected.

### Two mechanisms, and the gap is between them

The guard is **not** thin — 813 lines, ~30 rules — and it is **not** blind to
shell. It has two separate write-detection vocabularies, and they disagree:

- **`_WRITE_VERB_RE` (line 596)** — `>`, `>>`, `tee`, `cp`, `mv`, `install`,
  `touch`, `dd`, `truncate`, `sed -i`. Effect-based and correct. Used by
  **`check_bash_self_grant` only**, which is why leases, the `gate/` keystore,
  and `task_net` manifest edits are properly defended *in shell as well as in
  the Write/Edit tools*. Verified: a probe command naming a lease path was
  refused before it ran.
- **`_ROUTE_FS_MUTATE_RE` (line 172)** — `mkdir|rm|mv|cp|chmod|chown|tar`.
  Name-based, `warn` tier, omits `sed -i` and redirection entirely. This is the
  only rule a write to the registry can reach, and it does not reach it.

So the escalation-critical surfaces got the good mechanism and the
constitutional surfaces got the weak one. **The vocabulary this proposal needs
already exists in the file.**

### Why `warn` is not a control

Every `cat`, `grep`, and `find` run this session emitted
`{"decision": "warn", …}`. **None of them reached the model.** The only decision
that arrived all session was the `block` on a Python heredoc. Warn is emitted
into a room the agent is not in.

This matters more than it looks, because the pressure runs the other way. The
harness instruction active in this session opens: *"Do your work through the
Bash tool wherever it can accomplish the job … rather than using the dedicated
Read, Edit, or Write tools."* That is in the model's context, every turn. The
seat's counter-instruction is a `warn` the model cannot see. **When harness
policy and seat policy collide, only `block` survives the collision.** Any
routing the fleet actually depends on — Kart included — has to be stated at
block tier or it is decoration.

---

## Proposed change

Three edits, reusing both existing mechanisms rather than inventing a third.

### 1. Name the governed paths

```python
# The law itself: the envelope registries and the syscall table. A write here
# is verb 12 (registry edit, root-only, non-grantable) or verb 13 (scribe under
# citation, via envelope_apply). Neither is a file edit, in any tool.
_GOVERNED_LAW_RE = re.compile(
    r"(?:^|/)(?:envelopes/pre-approved\.json"
    r"|constitutional/(?:pre-approved|syscall-table)\.json)$|"
    r"constitutional/(?:pre-approved|syscall-table)\.json\b"
)
```

Deliberately narrow. It names the **registries and the table**, not directories.

### 2. Gate it in shell — beside the self-grant check, using the verb set that already works

In `check_bash_self_grant` (or a sibling `check_bash_governed_write`, called
from the same position in `main`, before routing):

```python
if _WRITE_VERB_RE.search(command) and _GOVERNED_LAW_RE.search(command):
    return _GOVERNED_LAW_REASON
```

### 3. Gate it in the Write/Edit branch — where `check_trust_root_write` already stands

```python
if _GOVERNED_LAW_RE.search(path):
    return _GOVERNED_LAW_REASON
```

Both return `block`, both by the existing dispatch in `main` (lines 780-800) —
no new decision tier, no change to how decisions are emitted.

**Reason string** (the hint has to name the legitimate path, or the block is
just an obstacle):

> This file is the envelope registry / syscall table. Editing it is **verb 12**
> — root-only and non-grantable — and recording an act against it is **verb 13**,
> `envelope_apply`, which scribes under citation. Neither is a file write. Draft
> the change as a proposal under `governance/proposals/` and put it to root.

### What this must NOT block

- **Reading.** `cat`, `jq`, `Read` on any of these files — reading the law is the
  job. Only `_WRITE_VERB_RE` matches trip it, exactly as with the keystore rule.
- **`governance/proposals/`.** Drafts are not law. Blocking writes there would
  block the only sanctioned way to *propose* a change — including this document.
- **Ordinary repo files.** The regex names two filenames, not a tree.

### It must NOT be lifted for the orchestrator seat

`check_bash_routing` exempts the willow seat from exactly the git/gh steers
(`_GIT_GH_ROUTING`, line 209), on the sound reasoning that repo maintenance *is*
that seat's job. **This gate is the opposite case.** The seat's relationship to
the registry is to scribe under citation — verb 13, `envelope_apply`, which is
the one envelope the seat actually holds — and to draft proposals for root.
Hand-editing the registry is not a faster version of that; it is the thing verb
12 exists to prevent. The exemption list must not grow to include it, and the
comment at line 124 should say so, since that comment is the note the next
person will read before widening the lift.

---

## Verification

`willow-mcp/tests/test_pre_tool_use_hook.py`. Four cases, all currently failing:

1. `sed -i` on `envelopes/pre-approved.json` → `block`
2. `>>` redirection onto `$WILLOW_HOME/constitutional/pre-approved.json` → `block`
3. `Edit` tool on either → `block`
4. `cat` / `jq` on either → **not** blocked

Plus one regression case: a Write to `governance/proposals/anything.md` → not
blocked.

---

## Dependency on the companion proposal

The envelope that authorizes this change, `env-fs.write-willow-mcp`, is one of
the three the companion flags in its §F4:

- its `paths[]` is `{{HOME}}/github/willow-mcp`, which **does not exist**
  post-move (companion §F1);
- its `bounds.repo` siblings name `rudi193-cmd/willow-mcp`, and GitHub now
  reports `willow-memory/willow-mcp`, compared by exact string equality
  (companion §C);
- it carries `expires_at: null` and two grantees, `["hanuman", "kart"]`
  (companion §F4.2, §F4.3).

**So the fix for "the law is unenforced" routes through an envelope that is
itself mis-pointed.** The companion should land first, or this change gets made
under a grant whose filesystem path resolves nowhere and whose repo name reaches
its target only by redirect.

---

## What this does not fix

It does not make agents prefer Kart. It removes one specific bypass — the
registry — and states at block tier that the way to change the law is to propose
it. Everything else in `_BASH_ROUTING` that matters is still at `warn`, and warn
is still invisible; whether the rest of that table should be promoted is a
larger question and not decided here. Gap `c2fffe6af8f2`.

*Measured, not recalled: every verdict above produced by piping the actual
command to `willow_mcp.pre_tool_hook` and reading what it printed.*

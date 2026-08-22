# Proposal — verb 13's bounds value is a specimen where every other verb's is a type

**Status:** proposal · drafted by willow 2026-08-22 · **root's act (verb 12)**
**Closes (with a corrected premise):** gap `006e0144da95`
**Target:** `constitutional/syscall-table.json` — both copies
**Companions:** [`2026-08-21-registry-path-repoint.md`](2026-08-21-registry-path-repoint.md) · [`2026-08-22-governed-path-write-gate.md`](2026-08-22-governed-path-write-gate.md)

---

## The gap as recorded, and what is actually true

Gap `006e0144da95` says the verb 13 bounds signature still describes a relative
`registry_path`, and that **"every envelope minted against that signature
inherits the defect."** The planting envelope says the same about itself:
*"Pinning the path here fixes this entry; it does not fix the class."*

The first clause is true. **The second is not, and the difference decides the
fix.**

**Envelopes do not inherit values from the table.** `envelopes.py:210` reads the
verb spec's bounds for its **keys only**:

```python
signature = set((spec.get("bounds") or {}).keys())
signature -= {"max_count", "expires_at"}
if set(bounds) != signature:
    return {"ok": False, "errno": "EAMBIG", "reason": "bounds signature mismatch"}
```

Every subsequent comparison is against the **envelope's own** bounds values, not
the table's. `spec["bounds"]` appears exactly once in the file, at that line.
So the string `envelopes/pre-approved.json` sitting in the table is **inert** —
no envelope, minted or existing, is checked against it or given it as a default.

The inheritance is real but **human**: an operator minting a verb 13 envelope
reads the table as the specification and copies what is written there. That is
what happened before 2026-08-10 and what root fixed by hand on 2026-08-11
(willow-mcp #332a, relative → absolute, `restored[]` provenance on the entry).

So this is a **documentation defect in a document that governs by being read**.
It is worth fixing, it is one line, and it should not be described as an
enforcement bug — the enforcement is fine.

## What makes verb 13 the odd one out

Every path-shaped bounds value in the table is a **type descriptor**. Verb 13's
alone is a **concrete specimen**:

| verb | bounds field | value |
|---|---|---|
| 1 `fs.write` | `paths` | `list[path] — {{HOME}}-relative templates allowed` |
| 2 `git.commit` | `repo` | `path or org/name` |
| 3 `git.push` | `repo` | `path or org/name` |
| 4 `pr.open` | `repo` | `org/name` |
| 5 `pr.merge` | `repo` | `org/name` |
| 9 `msg.external` | `recipients` | `list[address/handle/repo]` |
| 11 `dispatch` | `to_agents` | `list[agent-id] — from fleet.json` |
| 14 `agent.lifecycle` | `agent_id` | `id (roster entry for retire/tier_change; new id for create)` |
| **13 `envelope.apply`** | **`registry_path`** | **`envelopes/pre-approved.json`** |

Nine describe a shape. One names a file. A reader following the table's own
convention would never write a literal path there — and a reader copying verb 13
gets a relative one, which is precisely the failure.

## The enforced copy contradicts itself

The two copies of the table differ in exactly one field, and the difference is
correct:

| | `companion.registry` |
|---|---|
| charter, `willow/envelopes/syscall-table.json` | `envelopes/pre-approved.json` |
| enforced, `$WILLOW_HOME/constitutional/syscall-table.json` | `pre-approved.json` |

Each is right **relative to its own directory** — someone localized that field
deliberately when the enforced copy was installed. **They did not localize verb
13's `bounds.registry_path`, which is `envelopes/pre-approved.json` in both.**

So inside the enforced table, four lines apart, the same file is named two
different ways, and only one of them resolves from that directory. That is the
clearest statement of the defect available, and it is visible without reading any
code.

## Proposed change

**One field, both copies**, bringing verb 13 into the convention the other nine
already follow:

```json
"bounds": {
  "registry_path": "path to the enforced registry — ABSOLUTE; a relative path resolves against the caller's cwd and is refused (EAMBIG bounds mismatch)"
}
```

The parenthetical is the part that earns its place: it tells the next minter what
goes wrong, not merely what to write. The 2026-08-10 failure was silent, and the
2026-08-11 repair was manual.

**Leave `companion.registry` alone in both copies.** Each is correct for its own
location. Worth a note in the table itself saying so, because the next person to
diff the two copies will see a mismatch and be tempted to "fix" it into
agreement — which would break whichever copy lost.

## What this does not fix

Nothing mechanical, because nothing mechanical is broken. No behaviour changes,
no test changes, no code changes. This closes gap `006e0144da95` by **correcting
its premise and fixing the real thing**: a specification document that, read
literally and in good faith, yields a broken envelope.

It also does not address the deeper asymmetry the sweep surfaced: in this table,
**bounds key names are load-bearing and every other field is prose.**
`min_ring`, `enforcement`, and `enforced_by` are read by no code
(`grep -rn` over `willow-mcp/src` finds only the unrelated `enforcement_posture`
module). Whether a document where one field enforces and eleven describe should
say so about itself is a larger question, not decided here.

---

*Measured, not recalled: bounds usage by reading `envelopes.py:207-221`; the
table convention by enumerating every path-shaped bounds value in the enforced
copy; the copy divergence by `jq`-diffing the two files, which differ in exactly
one field.*

# `mem_ratify` — Article IV Canon-promotion gate

ΔΣ=42

A minimal, conservative, pure/stdlib decision function that answers one
question: **may this knowledge item be promoted between epistemic tiers?**

It is the in-code enforcement artifact named at `CONSTITUTION.md` line 442
(Article IV — Knowledge & Canon: *"Tiered atoms (contested/frontier/canonical);
`mem_ratify`; promotion gated in code"*), built in response to box-scan
**B8** (`design/box-scan-2026-07-24.md`), which found the gate named across
doctrine but never built.

## What it encodes (Article IV / CONST-IV)

| Rule | Source | In code |
|------|--------|---------|
| Three tiers: Contested < Frontier < Canonical | IV.1 | `Tier` |
| Anyone proposes at Contested; recorded; no quorum | IV.2 | auto-applied path |
| Proposer never counted toward its quorum | §0.2, IV.2 | witness accounting |
| Promotion to Frontier needs an independent quorum | IV.3 | `_decide_frontier` |
| Promotion to Canonical needs quorum + ledger evidence + Operator Key | IV.3 | `_decide_canonical` |
| ≥1 Canonical witness must be *fresh* vs. the prior Frontier promotion | IV.3 | fresh-witness check |
| Independent Witness: same base model ⇒ presumed one witness | Defs (line 95) | base-model collapse |
| Demotion from Canonical needs quorum + Operator Key + evidence | IV.4 | `_decide_demotion` |
| Debasement refused, not quietly admitted | IV.4 | fail-closed default |

## The two knobs (do not confuse them)

- **Fail-closed decision.** `ratify()` returns `allowed=False` whenever any
  Article IV requirement is unmet or unprovable. This is always on.
- **Off-by-default enforcement.** Whether a *caller* must honor a denial is
  gated by `enforcement_enabled()` — env `WILLOW_MEM_RATIFY_ENFORCE`, default
  **False** (fleet "off-by-default enforce flag" convention,
  `design/handoff-2026-07-25-box-audit-remediation.md`). While off, a wired
  caller treats a denial as a loud advisory and blocks nothing.
  `Decision.is_blocking()` combines the two.

Importing this package changes no behavior. Nothing in the fleet imports it yet
(see follow-up).

## PLACEHOLDERS — owner must confirm before enforcement is switched on

These are genuine doctrine decisions the charter leaves to the operator
(`CONSTITUTION.md` line 478, Article IX.2). Conservative placeholders were
chosen so the skeleton is complete; each needs sign-off:

1. **`FRONTIER_MIN_WITNESSES = 2`** and **`CANONICAL_MIN_WITNESSES = 2`** — the
   quorum size. Article IV states no number; 2 is borrowed from the IX.2
   *founding* default ("at least 2 independent agent witnesses"). The operator
   may want Canonical set higher than Frontier.
2. **`REQUIRE_STEPWISE_PROMOTION = True`** — forbids Contested → Canonical in
   one hop (stricter reading of IV.3's "prior Frontier promotion" language).
3. **Independent-Witness evidence quality** — the module checks only that a
   rebuttal attestation is *present*; it cannot judge whether the recorded
   evidence truly shows divergent failure modes. Reliance is surfaced in
   `Decision.flags_for_human`.
4. **Operator-Key / ledger-evidence verification** — presence is checked;
   cryptographic signature verification and ledger resolution are delegated to
   the wiring layer and flagged for a human/keyholder.

## Follow-up — OUT OF SCOPE here (separate repo)

Wiring this gate into the live `knowledge_ingest` path lives in **willow-mcp**
(the path box-scan B8 found has "no tier field, no quorum/witness"). It was
deliberately left untouched here to avoid working-tree conflicts with parallel
work. The follow-up is:

1. Add a `tier` column + witness/quorum metadata to the knowledge store.
2. Call `mem_ratify.ratify(...)` at the promotion boundary; record the
   `Decision` (reasons, flags) to the ledger.
3. Seed operator sign-off for the placeholders above, then flip
   `WILLOW_MCP`-side wiring to consult `WILLOW_MEM_RATIFY_ENFORCE`.

## Run the tests

```
python -m unittest discover -s mem_ratify/tests -t . -p "test_*.py"
```

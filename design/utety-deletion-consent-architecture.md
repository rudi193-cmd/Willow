# ADR — Deletion = Consent: UTETY's Training Architecture

*Architecture Decision Record, draft for operator ratification. Does not build
anything. Source: the three vault research briefs (session 7a5806cc,
2026-07-14) — model-collapse, forgetting-and-memorization, illich-against-the-fleet —
and their convergence. Governs the family-facing training runtime for UTETY, where
the data subjects are children.*

---

## Status

**Proposed.** Blocks the family-facing runtime; is the biggest remaining gap
between UTETY's current classroom core and a child actually using it. Requires
operator ratification before any training fires (§0.4; corpus/seed consent
benchmark, human_required `5930E55E`).

## Context — the keystone the three briefs converged on

Three researchers, sent from unrelated directions, pointed at **one door**:

- **Model-collapse brief:** the loop is on the safe side (accumulate + strong base);
  the real hazard is the **preference step (DPO) narrowing the distribution** while
  every score still looks healthy — the mirror welded at the weight level. Fix:
  watch *diversity*, and make the reward **pluralistic**, not single-rubric.
- **Forgetting/memorization brief:** training on one real person is *continual
  learning*, not collapse. Forgetting is likely and cheap (replay + capped steps).
  **Memorization is the catastrophic one for a child** — a small corpus is seen so
  many times the model can be made to recite it back. Differential privacy is
  impractical at 3B-on-one-person; scrubbing is hygiene, not guarantee (stylometry
  survives).
- **Illich brief:** blesses the ends, demands the tool never become indispensable or
  definition-owning (see `illich-second-watershed-clause.md`).

**The worst possible design** — and the one to forbid outright — is the
**monolithic continue-from-previous checkpoint**: a single model thickening over
each version. It is worst for narrowing, worst for forgetting, worst for
memorization, and worst of all **it can never be cleanly undone.**

## The decision

**Frozen base + provenance-tagged, isolated, removable adapters + retrain-from-clean
deletion.**

1. **Frozen base.** The pretrained base is never continue-trained. It stays honest
   and unchanged; it is the clean root every deletion returns to.
2. **Per-subject isolated adapters.** Each person's/child's contribution lives in its
   own **provenance-tagged** adapter (LoRA-class), orthogonalized/consolidated so
   contributions do not entangle. A person's whole footprint in the model is one
   named, removable layer.
3. **Deletion = drop the adapter + retrain-from-clean.** When a parent withdraws
   consent, the honest deletion is not "unlearning" — it is dropping that adapter and
   re-fitting from the untouched base without that data. Adapters make this **cheap**,
   which is the only reason the guarantee is affordable.
4. **Pluralistic DPO reward.** The preference step optimizes a *panel* of rubrics,
   not one — the de-narrowing fix for the one genuine collapse-adjacent hazard.

## The load-bearing reason: approximate unlearning is a lie for a child

"Make the model forget" techniques are unreliable **and actively defeated by the
deployment step**: the **4-bit GGUF quantization** used to run the model on the
operator's own hardware **resurrects** supposedly-unlearned data (measured recovery
~21% → ~83%). So a deletion that relies on approximate unlearning would report
"forgotten" and then hand the child's data back the moment the model is compressed
for local use. For minors, that is unacceptable.

Therefore: **the only honest deletion is retrain-from-clean-base — and the deletion
guarantee IS the consent guarantee.** They are one act. A parent's right to withdraw
a child's data and the technical ability to actually remove it are the same
sentence, and only this architecture makes that sentence true.

## Consequences

- **Enables** a real, testable consent story for the family runtime: "you can remove
  your child, completely, and here is the mechanism" — provable, not asserted.
- **Costs** the engineering of adapter isolation + a retrain-from-clean pipeline +
  the detector suite below. Rejects the cheaper monolithic checkpoint.
- **Constitutional tie-ins:** deletion=consent is §0.4 (human key / consent) made
  physical for weights; frozen-base-honesty is §0.1-shaped (the base does not
  attest to a self it didn't earn); adapter-removability is the technical form of
  the founding letter's *"not a self but a record; the human holds the thread."*

## Detectors to wire (from brief open-thread #3) — run on the DEPLOYED 4-bit GGUF, not fp16

- **Forgetting:** held-out fresh-human perplexity.
- **Memorization:** canary-extraction + n-gram-overlap + loss-gap MIA.
- **Narrowing:** self-BLEU / distinct-n over generations.
- Wire these into the existing **echo-ladder** harness; a green fp16 number that
  goes red after quantization is exactly the failure this ADR exists to catch.

## Open questions for the operator

1. **Base-handling confirmation** (brief open-thread #1): re-fit-from-frozen-base vs
   continue-from-previous. This ADR rules *re-fit-from-frozen-base*; confirm.
2. Adapter granularity: per-child, per-family, or per-cohort — and how consolidation
   preserves per-subject deletability.
3. The retrain-from-clean **SLA**: how fast a withdrawal must take effect, and where
   the clean base + provenance manifests are custodied.

*Draft ADR — unratified. No training fires without the operator key.*

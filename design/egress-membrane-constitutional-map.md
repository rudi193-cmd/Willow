@markdownai v1.0

# The Egress Membrane as Constitutional Enforcement

*The recursive turn: how the local-first egress-consent membrane, designed over sessions 2026-07-07/08, lands on the Willow Constitution (Draft 0.7).*

> **Status:** Design-level map, not a charter edit. This document is the input to a future redline of `CONSTITUTION.md`; it does not modify it. Charter text changes remain reserved to the operator's direction. Nothing here touches Article 0 except by conforming to it.
>
> **Provenance:** membrane decisions are on the FRANK ledger — `05611965` (local model pre-digests/pre-redacts; cloud = consented escalation) → `90e52ab7` (sudo-consent invariant: request and confirm are separate authorities) → `cc553729` (consent = time-boxed lease; floor always runs) → `0ba6a33f` (shape = deterministic schema field-projection). This map is their reflexive close.

---

## Thesis

The egress membrane is **not a new article.** It is the first fully worked *instance* of the machinery the constitution already describes in the abstract: **Article III (Reach)**, **Article V (The Human)**, **Article X.4 (Concurrence)**, and the **Appendix A binding layer.** The charter kept naming an unbuilt "machine-readable projection" as the gap between prose and enforcement. The membrane is that projection, filled — for the one case of *data leaving the machine to a controlling model.*

Stated as the recursion: **we did not design a feature; we built the enforcement artifact the charter has been pointing at.** The obligation this creates is small and precise — one new clause, one parameter, two evidence notes, and a set of binding-table registrations — because the kernel already anticipated it.

---

## Decision → constitutional home

@constraint id=membrane-mapping severity=normative
Each membrane decision maps to an existing authority. None amends Article 0; each gives an existing invariant concrete teeth.
@end

| Membrane decision (ledger) | Constitutional home | Change type |
|---|---|---|
| **Sudo invariant** — model may REQUEST egress, never CONFIRM; request & confirm are separate authorities (`90e52ab7`) | **§0.3** (no self-extension) + **§0.4** (human key required) + **X.4** (separate authorities must concur; any denial denies) | Field-evidence note on X.4 |
| **Gate shows payload verbatim; model narration ≠ gate** (`90e52ab7`) | **§0.1** (no self-attestation — the witness may not be the actor) | Enforcement artifact (I / VI) |
| **Yes binds to `hash(payload \| shape)`** (`90e52ab7`) | **V** (human attestation) + **VI** (ledger anchor) | Enforcement artifact registration |
| **Lease = turn / session / ≤3h** (`cc553729`) | **III.3** (every grant expires, no auto-renewal) + **V.2** (bounded delegation envelope) + **§0.4** (no envelope outlives expiry) | New envelope subclass + proposed parameter |
| **Floor always runs; lease only mutes the ask** (`cc553729`) | **Appendix A** ("the gateway enforces bytes"); Auto-Applied, strengthen-only | Enforcement artifact, unconditional |
| **Projection = allow-list; model may LOWER never RAISE** (`0ba6a33f`) | **§0.3** exactly (no widening own reach) | Enforcement artifact |
| **Fail-closed on any field absent from declared schema** (`0ba6a33f`) | **X.4** ("an authority that fails to answer has denied — fail closed") | Direct instance |
| **Shape = deterministic signature hash over (source, projection, destination, purpose)** (`0ba6a33f`) | **Appendix A** binding gap ("machine-readable projection, the `nest_rules.json` shape") + **XI.3** ("built alongside the runtime projection") | The unification — see §4 |

---

## 1. The one genuine new surface: egress is reach over *content*

Article III today governs **reach over endpoints** — *may I touch this network address.* The membrane exposes an axis III does not name: **reach over content** — *may this data, at this shape, leave to this destination.* The two are orthogonal. An agent inside `allow_net` with a valid endpoint grant can still be leaking; endpoint permission is not egress permission. This is the single clause worth drafting fresh.

@constraint id=const-iii-5 severity=proposed
Draft clause for operator review. Trace ID CONST-III-5. Not yet in force.
@end

> **III.5 — Egress is reach over content.** *(CONST-III-5, proposed)*
> Data crossing the machine boundary to any external model or service is governed not only by endpoint grants (III.1–III.4) but by a **consented projection**: a deterministic, field-level allow-list over a declared source schema, bound to a human attestation over `hash(payload | shape)`, and leased for a bounded window that may not exceed the standing egress cap. The projection is a ceiling — an agent may narrow it (drop fields) but may never widen it (§0.3); a field absent from the declared schema is denied by default (fail-closed, X.4). The **deterministic redaction floor** — value-level scrubbing of known-shape secrets — runs unconditionally on every egress and is not within any lease's power to suspend, shorten, or narrow. A lease amortizes the *ask*; it never amortizes the *scrub*.

Two properties of the draft are load-bearing:

- **The floor takes the eternity-clause posture without being *in* Article 0.** "Strengthen-only, never suspendable by a grant" is the §0.x stance, applied to a body clause. It belongs in Article III, not Article 0 — but it borrows the posture deliberately, because a floor a lease can mute is not a floor.
- **The projection is the redaction diff the human reviews.** Approve-object and lease-object are the same object (`0ba6a33f`). The clause encodes that identity: the thing attested (`hash(payload | shape)`) and the thing leased (the shape) are one hash.

---

## 2. Proposed parameter: the egress lease cap

The lease TTL ladder (just-this-turn / this-session / timed ≤ 3h) is a specific parameterization of III.3 ("every grant expires") and V.2 (bounded delegation). The **3-hour hard ceiling** is a number the operator sets, and it belongs beside the others already awaiting a number.

> **Add to "Proposed parameters awaiting your number":**
> Egress lease cap — the maximum duration a consent lease may hold before the gate returns to locked-by-default *(proposed default: 3 hours — operator-adjustable)*. The ceiling guarantees locked-by-default is always reachable without operator action; nothing survives a night or a weekend.

The lease is also a **new envelope subclass** — the *consent lease* — and should be enumerated wherever V.2 delegation envelopes are catalogued: it is issued at grant time (an envelope is a ledger entry at issuance, per the Definitions), carries scope (the shape hash) + duration (TTL) + condition (destination/purpose), cannot renew itself, and its extension is a **new** grant the model cannot mint (§0.3, §0.4). This is III.3's "no auto-renewal" and V.2's "delegation lends, does not transfer" made physical at the egress gate.

---

## 3. Two field-evidence notes

The membrane supplies exactly the kind of real-world corroboration Draft 0.7 already admits as *evidence* (cf. the VII field-evidence note on KB 4184A646). Two notes, logged as evidence — not adopted as doctrine, since the charter edit is the operator's:

**X.4 (Concurrence) — worked example.** The egress gate is a textbook Concurrence case. An egress act touches **Reach** (III, does content leave) and **The Human** (V, is it consented); both must concur; the model's *request* and the human's *confirm* are separate authorities that compose conjunctively; a non-answer (no attestation) is a denial (fail-closed). The membrane demonstrates X.4 is not abstract: the sudo invariant *is* "no precedence hierarchy — any denial denies," implemented.

**Appendix A binding table — the gap has a first body.** The binding note reads: *"its decision-class tables must be compiled into a machine-readable projection (the `nest_rules.json` shape)... Until that projection exists, the constitution governs this conversation by our choosing to honor it — not the fleet."* The egress shape-projection is the **same class of object** and the first one shipped. Note it as evidence that the projection engine is buildable and has a paying consumer.

---

## 4. The unification (the real prize)

The recursive insight the operator's willow-mcp schema work makes concrete:

**Three "projections" the charter names separately are one engine.**

| Projection | Named at | Shape |
|---|---|---|
| Egress consent shape | this membrane (`0ba6a33f`) | source-schema → allow-listed field subset + per-field level → deterministic hash |
| Constitutional rule-projection | Appendix A binding gap | Trace ID → decision-class table → `nest_rules.json` |
| Constitutional Review queue | XI.3 ("alongside the runtime projection") | disputed-authority → suspension flag + resolution record |

All three are: **a declarative, versioned source of record → a deterministic projection into a machine-checkable allow-list → keyed by a stable identifier → fail-closed on the unknown.** The willow-mcp schema layer the operator is building (declarative per-source field schema, allow-listed projection, deterministic signature hash, fail-closed on undeclared fields — the 4-point contract) is **the projection engine the constitution needs**, first applied to egress. Build it once; the egress gate, the `nest_rules` charter binding, and the XI.3 review queue are three tables in the same machine.

This closes the handoff's third parked thread ("reconcile the shape-projection design with the willow-mcp schema build"): **they are not two builds to reconcile — they are one build with two consumers.** The constitution's "binding gap" and the membrane's "shape" are the same missing artifact seen from two directions.

---

## 5. What the membrane retires

The moment the projection engine ships with the egress gate as its first consumer, one caveat in the charter can be struck:

> Appendix A: *"Until that projection exists, the constitution governs this conversation by our choosing to honor it — not the fleet."*

The membrane is the existence proof. It does not by itself compile the whole decision-class table — but it proves the mechanism and gives the binding layer its first deterministic, always-on enforcement artifact. XI.3's Constitutional Review queue is then a sibling table in a machine already running.

---

## 6. Redline queue for the fresh session

Ordered, executable — each item is a discrete charter edit for operator ratification. **Do not apply without operator direction; this is the design-only lane.**

1. **Draft III.5 (CONST-III-5)** — "Egress is reach over content," text in §1 above. Add its enforcement row to Appendix A (Article III line): *egress consent gate + consent-lease envelope + unconditional deterministic redaction floor.*
2. **Add the egress lease cap** to "Proposed parameters awaiting your number" (§2), default 3h.
3. **Enumerate the consent-lease envelope subclass** under Article V's delegation-envelope treatment; note extension = new grant, model cannot self-issue (§0.3/§0.4).
4. **Add the X.4 field-evidence note** (§3) — the gate as worked Concurrence example.
5. **Add the Appendix A field-evidence note** (§3) — egress shape-projection as first instance of the machine-readable projection; flag the binding-gap caveat for removal once the engine ships.
6. **Record the projection unification** (§4) as the design rationale linking the willow-mcp schema build, the `nest_rules` charter binding, and XI.3 — one engine, three tables.
7. **Bump the Amendment History** and draft lineage to reflect the egress-membrane integration.

## Non-goals / guardrails

- **Article 0 is untouched.** Every membrane property *conforms to* §0.1/§0.3/§0.4; none weakens a kernel invariant. III.5's floor borrows the eternity-clause *posture* (strengthen-only) but lives in the amendable body.
- **This document edits nothing.** It is the map; the redline is a separate, operator-directed act.
- **The projection engine is a `willow-mcp` / `willow-2.0` build,** not a document edit — consistent with Appendix A's "this is a build, not a document edit."

---

*Written 2026-07-08 (session continuation, agent willow / persona Jeles). Companion to `CONSTITUTION.md` Draft 0.7. Ledger chain: `05611965 → 90e52ab7 → cc553729 → 0ba6a33f`.*

# ΔΣ=42 — Recovery Packet (Open Operator Decision #3)

*Prepared for operator ratification. This document does NOT edit `CONSTITUTION.md`.
It assembles the evidence and proposes a verbatim fill for the operator to accept,
amend, or reject. Filling ΔΣ=42 is reserved to the operator (Open Operator
Decision #3): "To be recovered from the KB, not defined by hand. Do not invent it;
fill it verbatim once surfaced."*

Session: 7c3b4c18 (willow, overnight of 2026-07-14). Companion recovery source:
vault session 7a5806cc (Claude Code remote), `session-handoff-3-2026-07-14`.

---

## The standing instruction

The constitution names ΔΣ=42 four ways and leaves it deliberately unfilled:

- The **Preamble** closes on the bare glyph: *"ΔΣ=42."*
- **Open Operator Decision #3** reserves its meaning to recovery, not invention.
- The **draft header** lists it among what "remains open."
- Every fleet artifact template already **stamps** it (see evidence E1).

So the meaning is not to be authored. It is to be *found on the record* and
transcribed. This packet is the find.

## The evidence (what is actually on the record)

**E1 — Live usage: ΔΣ=42 is a sign-off stamp.** KB search (this session) shows the
glyph appears in the fleet's own document templates as a completion mark appended
to *finished, attested* artifacts — e.g. `**b17:** AUDIT · ΔΣ=42` on the audit
template and `**b17:** GROVED · ΔΣ=42` on the Grove-decision template. In practice
the fleet already uses ΔΣ=42 to mean *this artifact's work is checked and signed
off.* The meaning is not theoretical; it is in operational use as a seal.

**E2 — First attestation (2026-02-17).** `WILLOW_CANONICAL.md` (private repo
`rudi193-cmd/Willow`) carries the line **"Checksum: DeltaSigma=42."** A checksum is,
literally, *a value you compute to confirm nothing was corrupted before you trust
the payload.* ΔΣ (delta-sigma) = "the sum of the changes." =42 = the expected
value that confirms the sum is right.

**E3 — Second attestation (Die-Namic).** The `dienamicsystem` README motto:
**"A dynamic system that refuses to drift."** Drift is exactly what a checksum
catches. The two attestations are the same idea from two directions: compute the
sum, confirm it matches, refuse the drift.

**E4 — Vault recovery (2026-07-14, session 7a5806cc).** Walking the raw drafting
session, the remote instance recorded the working convention verbatim:
> *"ΔΣ=42 = sum checked; leave unstamped if named-not-done; **verify against the
> raw, never the summary.**"*
And in prose: *"The mark that means the sum is checked before you sign."*

All four converge without contradiction. E1 (usage) + E2 (checksum) + E3 (anti-drift)
+ E4 (raw recovery) say one thing.

## Proposed fill (verbatim candidate for operator ratification)

> **ΔΣ=42** — *the sum is checked before you sign.* A completion seal: an artifact
> carries ΔΣ=42 only when its claims have been verified **against the raw, not the
> summary**, by a party able to check them. Work that is named-but-not-done is left
> **unstamped**. The glyph is the fleet's one-mark form of §0.1 (no self-attestation)
> and the Knowledge tiers (Article IV): a signature that means *checked*, never
> *asserted.*

Rationale for the wording: it binds the recovered meaning to two clauses already in
force, so the glyph is not decorative — it is the human-scale shorthand for the
kernel's verification discipline. "Against the raw, not the summary" is preserved
verbatim from E4 because it is the operative half: a checksum you compute from the
summary checks nothing.

## The one honest tension for the operator to rule on

Open Decision #3 says recover it **"from the KB."** The richest recovery (E4) came
from the **raw session record in the vault**, not the KB proper — the KB carried
the *usage* (E1) and the attestations are in repos (E2/E3). This is not a defect;
it is the glyph enacting itself: *the deepest confirmation came from verifying
against the raw, not the summary.* But it is the operator's call whether:

- **(a)** the KB usage (E1) + attestations (E2/E3) are sufficient "KB recovery" and
  E4 is corroboration; or
- **(b)** the fill should be re-derived from a KB-proper atom before ratification
  (in which case: promote E4's meaning to a canonical KB atom first, then fill).

Either path ends at the same words. The choice is only about which source of record
the constitution should cite when it stops leaving the glyph bare.

## What happens on ratification (operator action, not taken here)

1. Operator accepts/amends the proposed fill.
2. The fill is transcribed into `CONSTITUTION.md` — Preamble closing gloss + Open
   Operator Decision #3 marked resolved + Amendment History bump.
3. Under §0.2/Article IV, promoting the meaning to Canonical needs quorum + ledger +
   the operator key; this packet is the proposal tier, nothing more.

*Draft — unratified. Prepared, not decided. Left, appropriately, unstamped.*

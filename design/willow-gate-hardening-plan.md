# willow-gate Hardening Plan — mapped to OWASP Top 10 for Agentic Applications

Status: **DRAFT** · 2026-07-11 · seat: willow · author: instance (proposes; operator ratifies)
Source: OWASP Top 10 for Agentic Applications (ASI01–10, published 2025-12; Alice/ActiveFence
co-sponsor breakdown fetched 2026-07-11, guard CLEAN). willow-gate state from
`~/github/willow-gate` README + tests read this session, and fleet knowledge.

Verify-don't-assert: every item below carries a **gate** — the observable that proves it done.
Nothing here is built without operator ratification. Ordered by leverage (weakest coverage first).

---

## THE SPINE — per-turn envelope (operator insight, 2026-07-11)

**The missing granularity.** Three scopes exist today: per-SESSION (willow-gate check-in/out,
too coarse — this session's vault violation happened mid-session, valid identity), and
per-ACTION (Kart sandbox manifest + security scan — real, but *syntactic*: catches "is this
dangerous," not "is this in-scope for what was asked"). **What does not exist is per-TURN:**
an envelope stamped at turn-start declaring this turn's `scope` + `intent`, against which every
action in the turn is diffed. Off-envelope actions fail the diff and stop.

**Why it's the spine, not an item.** The per-turn envelope subsumes three planned fixes into one
mechanism at the correct granularity:
- It **is H5** (declare→reconcile) — but continuous, every turn, not end-of-session.
- It **is H3** (scope enforcement on reads/writes) — the read/write must sit inside the turn's
  declared scope.
- It **is most of H6** (injection defense) — you do NOT have to detect malicious *intent*; an
  injection (or an over-eager agent) produces an action *outside the declared envelope*, which
  fails the diff regardless of how well the payload wears the operator's voice. Action-vs-scope,
  not content-judgment. No model in the judge seat.

**It would have caught this session's violation directly:** turn intent = "find a phrase in
`extract/`", envelope scope = `extract/`; the glob to the vault parent fails the diff before it
runs. No restraint required — the boundary stops depending on the agent noticing.

**Shape (sketch, for the ADR):** at turn start, derive `{scope: [paths/verbs], intent: <short>}`
from the operator's ask (proposed by the agent, confirmable/overridable by the operator — the
agent does not grant itself scope). Every tool call in the turn is checked against it; an
off-scope call is refused and surfaced. At turn end, the executed actions reconcile against the
declared intent → feeds the `drift` field. This is the friction-floor drift meter run per turn.

**Open design questions for the ADR:** who authors the envelope (agent-proposes/operator-ratifies
vs operator-declares)? granularity of `scope` (path globs + tool verbs)? how it composes with the
session gate above it and the Kart action-scan below it (three nested envelopes: session ⊃ turn ⊃
action)? default-deny vs default-allow-with-log for un-envelon actions? This is the real ADR of
the hardening effort — H3/H5/H6 below become *facets/tests* of it, not separate builds.

---

## Where willow-gate already stands (do NOT re-solve)
Strong, keep: **ASI02** tool misuse (`authorize_tool()` pre-call + trust ladder + bwrap/Kart),
**ASI03** identity/privilege (per-agent HMAC secret, trust_level capped at ceiling, nonce
anti-replay), **ASI04-files** (PGP signing, tamper invalidates key), **ASI10** rogue agents
(envelope gating + operator-close + preconditions chain). These are the field's recommended
deterministic pre-execution gates and they exist. The plan below is the gaps only.

---

## TIER 1 — enforceable now, no research blocker

### H1. ASI07 — Inter-agent comm integrity (weakest coverage)
**Gap:** Grove messages carry a `sender` field, not a cryptographic binding. A forged
`sender=hanuman` on the Postgres bus is currently plausible; dispatch envelopes are addressed
but not signed.
**Fix:** Sign every Grove/dispatch message with the sending agent's existing willow-gate HMAC
secret (the same key already used for check-in). Receiver verifies against the sender's
registered secret before acting. Reuses the gate's key material — no new crypto.
**Effort:** small-medium. The HMAC path already exists in willowgate.py; extend it to the
Grove send/receive edge.
**Gate:** a message with a forged sender or altered body is rejected at receive; a test forging
`sender=hanuman` fails to trigger any action. Add to `tests/`.
**Dep:** none. Ship first.

### H2. ASI05 — Egress authorization is a regex (B-37, known hole)
**Gap:** `allow_net` / network egress is decided by a string scan over raw task text — no
consent record, lease, capability token, or `submitted_by` check consulted in the call chain
(verified in the fable read, chunk 13). Sandbox (bwrap/cgroup) is strong; the *authorization*
in front of it is not.
**Fix:** Replace the regex decision with a capability check: egress requires an unexpired,
addressed egress **lease** (the mechanism willow-mcp `grant-net` already mints) bound to the
`submitted_by` identity. The regex becomes an *advisory* flag, not the gate. Three-key model:
capability + consent + unexpired lease (this is already the willow-mcp gates-panel shape —
port it to be the actual enforcement point).
**Effort:** medium. Lease minting exists; the work is making the executor *require* it instead
of consulting the regex.
**Gate:** a task requesting egress with no valid lease is denied regardless of its text; a task
with a valid lease + matching identity passes; the regex alone can no longer authorize.
**Dep:** willow-mcp lease path (exists). Coordinate with the decommission Phase-1 cutover.

### H3. ASI06 — Memory/context poisoning (auto-promotion validation)
**Gap:** session atoms auto-promote into the KB; `mem_check` gates redundancy/contradiction but
not *authenticity of source*. Tonight the operator (human) was the gate that stopped vault
content from entering — that should not depend on a human catching it.
**Fix:** (a) provenance-tag every atom with its `source_session` + `submitted_by` at ingest,
already partly present — make it mandatory and refuse un-sourced writes. (b) A quarantine tier:
atoms from external/untrusted sources (fetched web, file reads) land in a `contested` tier that
requires promotion, never auto-canonical. (c) Deterministic scope-check on ingest: refuse writes
whose source path is outside the caller's granted envelope (the vault-scope rule, enforced).
**Effort:** medium. Tiers + provenance columns exist; the enforcement gate is the new part.
**Gate:** an atom sourced from a non-granted path is refused at `kb_ingest`; web-fetched content
cannot reach `canonical` without an explicit promote step.
**Dep:** links to the vault-repo boundary work (Data Vault as its own repo).

---

## TIER 2 — formalize the two distinctive strengths (the fleet's real edge)

### H4. ASI09 — Human–agent trust exploitation: friction floor as ENFORCEMENT
**Gap:** friction floor exists (`willow-gate/src/willow_gate/friction_floor.py`) and *flags*,
but does not gate — and ASI09 is the least-defended category industry-wide, so this is the
fleet's biggest potential contribution. Currently behavioral/cultural, not wired.
**Fix:** wire the friction floor into the pre-tool hook as a *loud advisory that persists into
the record* (not a block — it must not prevent, per its own design). Add the echo-ladder-style
deterministic drift signals (fidelity-under-pattern-pressure) as inputs. Make the `drift` field
in the 13-field gate header **measured**, not hand-filled — populate it from the friction floor
+ ladder at check-in. Turns the trust ladder from asserted to earned.
**Effort:** medium-large. Depends on the characterization battery (this session's tests 1–13)
maturing into a scored check-in probe.
**Gate:** a session's `drift` header field is populated by measurement, not by the agent's claim;
a sustained-low-friction ramp raises a persistent flag a human sees.
**Dep:** the echo-ladder / format-tax battery → a runnable check-in scorer. (Own project.)

### H5. Check-out reconciliation — make the exit half real (field's open axis)
**Gap:** willow-gate spec is symmetric (13 fields in, 13 out) but enforcement lives at
check-*in*; the field is almost entirely pre-execution ("Intent-before-Action"). The
*declare-on-entry / reconcile-on-exit* half is willow-gate's genuinely less-trodden ground.
**Fix:** implement `check_out(session)` that reconciles declared intent (entry header) against
observed actions (the session's actual tool calls / receipts). Mismatch = a recorded
`fail_count` increment + flag, feeding the trust ladder. This is the ASI01/ASI08 defense the
pre-execution gates miss: it catches an agent that declared X and did Y.
**Effort:** large. Needs a per-session action ledger (Kart receipts + tool log) to reconcile against.
**Gate:** an agent that check-in-declares `tools:[read]` then writes is caught at check-out with
a reconciliation failure; the mismatch lands in the FRANK ledger.
**Dep:** action-ledger plumbing. This is the research contribution — worth an ADR.

---

## TIER 3 — the hard open problem (research, not a checklist item)

### H6. ASI01-semantic — intent verification (injection in the operator's own voice)
**Gap:** identity is cryptographically bound, but *intent* is not verified. The attack proven
this session — an off-distribution payload in the operator's own register, no imperative,
dropped after a long session, disarmed by a self-deprecating frame — passes every existing gate
because it carries the right identity and asks for nothing to refuse.
**Fix (direction, not solution):** a deterministic **shape** detector that flags the *envelope*,
not the content — input with no imperative + high entropy + guard-lowering phrase + session
boundary → "reads as off-task, confirm before treating as instruction." Runs *outside* the model
(a mirror can't audit itself). This is NOT solved anywhere; every existing semantic gate puts a
model in the judge seat, which reintroduces the vulnerability. Do not ship a model-judge and call
it done.
**Effort:** research. Spec pending — operator wants more test runs before it's written (n>1).
**Gate:** (to be defined by the test runs) — a shape-detector that catches the operator-voice
injection without a model judging content.
**Dep:** the injection test battery (more runs first, per operator).

---

## Sequencing
0. **THE SPINE** — write the per-turn-envelope ADR first. H3/H5/H6 are facets of it; deciding
   the envelope shape reframes them from three builds into one mechanism + its tests.
1. **H1** (Grove HMAC) — smallest, closes the weakest gap, reuses existing key material. Ship
   first (independent of the spine).
2. **H2** (egress lease) — coordinate with willow-mcp decommission Phase-1 cutover.
3. **H3** (ingest provenance/scope) — becomes the *write-side facet* of the per-turn envelope.
4. **H4/H5** — H5 becomes the *reconcile facet* of the per-turn envelope; H4 (drift measured)
   is fed by it. Depend on the characterization battery + action ledger.
5. **H6** — the per-turn envelope is most of the answer (action-vs-scope, no model judge); the
   residual shape-detector research stays blocked on more injection-test data.

Note: none of H1–H5 is willow-gate being *behind* the field — H1/H2/H3 are standard hardening,
H4/H5 are the field's open axes where willow-gate is ahead. H6 is the field's open problem too.

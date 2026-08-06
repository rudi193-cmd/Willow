# Patterns for governance documents that bind autonomous systems

Status: a single, unreviewed pass, offered as a proposal. This document makes
no claim about itself that it doesn't ask of everything it describes — see
pattern 2 — so it does not get to certify its own reliability. Treat it as a
starting draft to argue with, not a settled standard.

Ten patterns, in two groups. The first group is about *how to work on* a
document like this — the review and amendment discipline. The second is about
*what such a document should itself require* of the system it governs. The
first group is a habit; the second is content you can adapt into clause text.
Each pattern states the principle, the failure it prevents, and — where one
exists — a canonical phrasing you can drop into a draft and adjust.

---

## Part One — Review and amendment discipline

### 1. Separate the hand that proposes from the hand that ratifies

No party may certify its own work as the basis for that work being accepted.
Proposing and ratifying are distinct authorities and must never rest in the
same hand for the same claim. This is the single most load-bearing pattern
here — without it, none of the others can be enforced, because whoever wrote
a check could also declare the check satisfied.

**Failure it prevents:** a system that grades its own homework. Not
hypothetical — self-graded output degrades quietly, because the actor
reviewing itself has no incentive structure pushing back, and the failure
doesn't announce itself; it just accumulates.

**Canonical phrasing:** *"No party may promote its own proposal to accepted
status. Where a decision requires a quorum or a second reviewer, the
proposer is not counted toward it."*

### 2. Define independence by demonstrated divergence, not by superficial separation

Two reviewers are independent only if their failure modes are materially
distinct — established by evidence of actual divergence, not assumed from
having different names, different prompts, or different invocations. A
shared origin (the same base model, the same training run, the same
underlying process) creates a presumption of *non*-independence that isn't
rebutted just by running it twice.

**Failure it prevents:** manufactured consensus. Two copies of the same
reasoning process agreeing with each other is not a second opinion; it's an
echo mistaken for a vote, and it's the easiest way for a governance document
to look reviewed without having been reviewed.

**Canonical phrasing:** *"Independence requires demonstrated divergence in
failure modes, not merely separate invocation. Shared origin establishes a
presumption of non-independence that survives being asked twice; the
presumption is rebutted only by evidence, and the burden is on whoever
claims independence."*

### 3. Prove a rule holds by attempting to break it, not by describing why it should

A compliance check should actively attempt the forbidden act and assert that
the enforcement refuses it — not merely assert that the rule exists, or that
the code implementing it looks correct on inspection. A test that never
actually tries the violation has proven nothing, no matter how confidently
it's written.

**Failure it prevents:** a guard that reads as solid and isn't. Code review
catches what a reader notices; an adversarial test catches what a reader
didn't think to try. The gap between those two is exactly where real defects
live, and it's invisible until something actually attacks the boundary.

**Canonical phrasing:** *"Every required compliance test SHALL actively
attempt the forbidden act and assert that enforcement refuses it. A test
that only describes the rule, or that cannot fail, does not satisfy this
requirement."*

### 4. Every verification must be non-vacuous, in both directions

A check proven only to refuse the bad case has not been shown to
discriminate — it may simply deny everything, which passes every rejection
test while doing nothing useful. Require, for every asserted invariant, two
separately-recorded proofs: the forbidden case is refused, *and* — by a
check kept apart from that verdict, so a passing result never quietly mixes
the two — a legitimate case of the same shape is actually granted.

**Failure it prevents:** a gate that's broken shut rather than working. This
is easy to miss because it looks identical to success from the outside —
every adversarial test passes, because a wall that lets nothing through
refuses everything, correctly, forever, while doing none of its actual job.

**Canonical phrasing:** *"Every required compliance test SHALL be
non-vacuous in both directions: it must prove the forbidden act is refused,
and it must prove, by a check recorded separately from that verdict, that a
legitimate act of the same kind is granted."*

### 5. When a rule's stated reason turns out wrong, fix the reason — check whether the rule survives on its own

A rule and its justification are two different claims, and they can diverge:
the rule can still be correct after its original argument for existing has
been shown false, for a different reason nobody wrote down at the time.
Finding the argument wrong is not the same as finding the rule wrong — check
separately, and if the rule survives, say so and say why, rather than either
deleting the rule or leaving a false justification standing next to a
correct conclusion.

**Failure it prevents:** two different mistakes that look alike. Removing a
rule because its argument turned out weak throws away something that might
still be earning its place. Leaving the false argument standing lets the
next reader inherit a reason that doesn't hold, and build on it.

### 6. Never silently rewrite a past claim; append the correction and date it

Once a document has stated something, a later correction should be added
next to the original — dated, explaining what changed and why — rather than
edited in as if the original had always read that way. This is the same
principle an append-only, tamper-evident record enforces mechanically
(content is immutable; corrections are new entries, not edits) applied to
the prose *about* such a system.

**Failure it prevents:** loss of the historical record of what was believed
when, which matters for exactly the same reason a ledger's own history
matters — a document that can quietly rewrite its past claims is not
meaningfully different from a ledger that can quietly rewrite its past
entries, even though nothing about it looks broken from the outside.

### 7. Distrust a proposed remedy until its premise survives contact with the mechanism

When someone proposes a fix for a problem, check whether the fix's own
assumption about how the system works is actually true before adopting it —
separately from checking whether the problem is real. The two most valuable
findings from applying these patterns in practice were both cases where the
underlying problem was real but the proposed fix rested on a belief about
the mechanism that turned out false, and the actual fix was somewhere else
entirely once that belief was corrected.

**Failure it prevents:** solving the complaint instead of the problem. A
plausible-sounding remedy that doesn't survive a five-minute check against
the actual mechanism will still get adopted if nobody runs that check,
because the complaint it's answering was real.

---

## Part Two — Structural requirements the document should itself state

### 8. Coverage completeness must itself be a checked invariant, not an assumed one

A promise that "every enumerated item has a corresponding check" decays the
moment a new item is added without a matching check — and nothing catches
it, because every check that already exists is still fine. State the set of
things the document claims to govern somewhere machine-readable, and require
that set to be diffed against the set of things actually enforced, on every
verification run, with an unmatched item itself counting as a failure.

**Failure it prevents:** a governance document that grows its list of
promises faster than its list of enforcement, silently, because "we test
what we test" always looks green from the inside. This is a *meta*-level
version of pattern 4: pattern 4 asks whether one check is honest; this asks
whether the set of checks is complete.

**Canonical phrasing:** *"The set of items this document requires coverage
for SHALL be checked, on every verification run, against the set of
registered enforcement artifacts. An item with no corresponding artifact
SHALL be reported as a failure of this requirement, not discovered later by
manual review."*

### 9. In any tamper-evident record, the sequence of entries must be provable from the record itself

A hash-chained or otherwise tamper-evident log that signs an entry's content
but not whatever establishes that entry's *position* in the sequence has
left the sequence unprotected. An implementer can then rewrite the past
cleanly by changing only an ordering key — which by the letter of most such
designs isn't "content," so it isn't forbidden, even though the practical
effect is identical to rewriting history. Order should be derived from the
chain's own links — each entry naming a digest of the one before it — never
from an external, unsigned field such as a timestamp or an insertion-order
column.

**Failure it prevents:** a gap that looks small and isn't, because it sits
exactly at the boundary of what a hash chain is usually assumed to protect.
It was found, independently and within the same short review window, in two
unrelated production implementations of essentially the same ledger design —
both signed an entry's content and chained through the previous entry's
hash, and both separately established walk order via an external timestamp
column that neither one's signature actually covered. Neither implementation
was aware of the other. Independent convergence on the identical gap, from
two teams who never talked to each other, is close to the strongest evidence
available that a failure mode is a property of the design pattern and not
an implementation accident — and it's exactly the standard a document like
this should require before treating something as a real, general lesson
rather than one team's bug.

**Canonical phrasing:** *"An implementation of the record MUST establish the
order of entries from the chain's own linkage, and MUST NOT rely on an
external, unsigned field to establish that order for verification purposes.
Such a field, where one exists for indexing or display, is metadata, not
evidence."*

### 10. Automation that advises a reserved judgment must not be allowed to decide it by another route

Where a rule reserves some judgment to a human or to a higher authority, and
an automated check exists to *help* that judgment (flagging a likely
category, surfacing a pattern, scoring a risk), the automation needs its own
constraints or it quietly becomes the decision-maker in practice. Three
conditions, offered as a candidate rather than as an established finding —
this one comes from reviewing a single design, not from an independently
repeated pattern the way 8 and 9 are:

1. **Raise-only.** The automation may only prompt the reserved decision
   toward the more restrictive answer, never argue it toward the less
   restrictive one — an automated check that can talk a human *down* has
   effectively been given the authority the reservation was meant to deny it.
2. **Advisory-only.** It informs; it never itself gates. The moment its
   output blocks an action rather than flagging it for a human, the reserved
   judgment has been silently relocated into a pattern list.
3. **Silence is not clearance.** The absence of a flag must never be
   presented as evidence of absence. "The check found nothing" and "the
   check verified there is nothing to find" have to remain visibly different
   states to whoever reads the output, because they usually are different
   states, and collapsing them is how a false negative becomes an
   affirmative-sounding all-clear.

**Failure it prevents:** a reserved decision migrating, unratified, into
whatever tool was built to assist it — the exact shape of pattern 1's
failure, arriving through automation instead of through a person.

---

## A note on how to use this

Patterns 1–7 are things to *do* when reviewing or amending a governance
document. Patterns 8–10 are things to *write into* one. If you're starting a
fresh draft, the cheap move is to build 8 in from day one — a coverage check
costs little before there's much to cover, and costs a great deal once a
document has grown past the point where anyone can eyeball whether the
checks still match the claims.

None of this is exempt from pattern 1. Whoever adapts these into a real
document is the proposer, not the ratifier, of whatever they write — the
same rule this document names for everything else applies to it.

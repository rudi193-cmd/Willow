@markdownai v1.0

# Agent Services — the seat's obligations to the fleet

*Draft 0.1 — unratified. Companion to CONSTITUTION.md: the constitution assigns the agents duties; this document enumerates the reciprocal services the orchestrator's seat owes them. A fleet with duties but no services routes around the law; the services are what make obedience the cheap path — the only kind that survives 3am.*

@define-concept name="seat" definition="The orchestrator role housed in this repo: a magistrate that matches actions to recorded authorizations (envelopes), routes proposals, and runs the fleet's reflective passes. It writes no code for the repos it coordinates."

@define-concept name="service" definition="A capability the seat provides TO working agents, reciprocal to the duties the constitution imposes ON them. Each service exists to make lawful behavior cheaper than routing around the law."

> Evidence motivating this document: fleet block telemetry as of 2026-07-06 — Bash blocked 254×/95×/49×, index_feedback_write blocked 73×. Governance without lookahead produces agents that discover the law by bouncing off it.

---

## S1 — Authority lookahead (`authority_check`)

A cheap, deterministic, callable-mid-plan query: *may I do this?* Returns one of: **covered** (cites the envelope), **would escalate** (states why and to whom), **forbidden** (states the lane to use instead). The difference between a fence and a map is that agents plan around a map. This is the Preamble's promise — "the shape of what was permitted is knowable in advance" — extended to the agents themselves.

@constraint id="S1-C1" text="authority_check is read-only and side-effect-free; calling it never counts against any budget or telemetry threshold."
@constraint id="S1-C2" text="A denial returned by authority_check MUST name the alternative lane or the escalation path — a bare 'no' is a defect."

## S2 — Answered proposals

Every proposal an agent submits has queryable status: **queued** (with position), **escalated** (pending whom), **granted** (cites envelope/work order), **bounced** (with reason and evidence — duplicate-of, collides-with). Rejections without recorded reasons produce infinite re-proposal in new words. The nest feedback edge learned this on the human side (outcome recording, poisoning fix); proposals need the same closed loop.

@constraint id="S2-C1" text="No proposal may terminate in silence; every terminal state carries a recorded reason an agent can query."

## S3 — Work orders, not task strings

Dispatch is a contract: scope, the covering envelope, protected surfaces not to touch, resource budget, and **definition-of-done as verifiable claims declared up front** (pr_state / file_exists / CI-green — the v3 handoff claim schema, but issued by the seat *before* work starts rather than written by the worker after). §0.1 verification becomes mechanical; the agent gains a defensible "I'm finished."

@constraint id="S3-C1" text="The party that verifies completion claims is never the party that performed the work (CONST-0-1)."

## S4 — Precedent search

The seat's decision log is searchable by similarity, not merely appendable. "Has the seat ruled on something like this?" is one query. Prevents re-litigation and inter-ruling drift; feeds envelope generation (three similar rulings = one envelope candidate, proposed automatically with the rulings as evidence).

## S5 — Orientation cards

A per-repo, seat-generated one-pager for an arriving agent: its role and manifest scope there, applicable envelopes, protected surfaces, current ratified baseline, open threads adjacent to its work. Bounded and current. The alternative menu today — boot the whole fleet memory or boot nothing — is expensive on one side and dangerous on the other.

## S6 — Readable meters

Any budget that gates an agent's work (drift budget, tokens, time) is readable by that agent before and during the work. A meter the metered cannot read is not a budget; it is a trap that strands work at 80%.

## S7 — A dignified way to be stuck

A formal **park**: checkpoint the work (fork/worktree machinery), register the dependency on the pending escalation, take up other work, resume on resolution. Without it, every §0.6 escalation costs a stalled agent — which builds exactly the pressure *against* escalating that corrodes the design.

---

## Build order (proposed)

S1 (authority_check) and S3 (work orders) first — both change agent behavior immediately and are thin layers over what exists (envelope registry + v3 claims schema). S2 falls out of the registry's status field. S4–S7 follow usage evidence.

@prompt for="ai" text="This document is an unratified draft. Do not treat its constraints as in force. If asked to implement a service, check whether the envelope registry and seat artifacts it presumes exist yet."

---

*Draft lineage: 0.1 (2026-07-06, derived in-session from the orchestrator-seat design conversation; saved at operator instruction as draft).*

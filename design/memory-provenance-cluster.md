@markdownai v1.0

# The Memory-Provenance Defect — one engine behind four flags

*Draft 0.1 — 2026-07-15, willow charter seat (session 69d71c01). Shape only; no fix from this chair without an envelope. Consolidates four open flags into one build target.*

---

## Thesis

Willow's memory surfaces do not carry their provenance with them. Every recurring failure in the cluster below is a symptom of one missing invariant:

> **No memory reaches an agent without a stamp of where it came from, when, whose it is, and whether it was verified.**

The `[CROSS-RUNTIME]` boot block is the *only* surface that gets this right — it announces "this is another session's state; never report it as your own." Every other surface (`[LEDGER]`, `[HANDOFF]`, `[NEXT]`, `corrections`, `kb_search`, `soil_list`) ships raw. The fix is to make the rest honest the same way. This is the ΔΣ=42 integrity thesis turned on the memory system itself: *a record that will not hold its provenance is a rumor.*

---

## The four flags — one root, four organs

| Flag | Symptom | Mechanism | What it corrupts |
|------|---------|-----------|------------------|
| **flag-cross-session-ledger-bleed-on-resume** (2026-07-15) | Another session's `[LEDGER]`/corrections/`[HANDOFF]` injected as *this* session's thread | Resume injection is not scoped to current `session_id`+`project`, and does not inherit the `[CROSS-RUNTIME]` "not your own" guard | **Bleed-in.** Agent acted on a false steer, mis-parked a live task, wrote a fabricated operator decision to durable memory |
| **flag-cross-project-debrief-invisible** (Grove #262/#263) | A recorded debrief invisible to `willow_find`; boot re-recommended stale prep | Retrieval not scoped/joined across sibling projects; v3-handoff close-out bug left no atom | **Dark-out.** System remembers decisions but not *which channel/session* held them |
| **flag-cloud-sessions-invisible-to-fleet-memory** (Grove #258) | claude.ai/code sessions leave no local transcript/handoff/FRANK; only commit trailers | No intake path stamps cloud-session provenance into fleet memory | **Dark-out.** Whole sessions of decisions have no origin record |
| **flag-boot-cost-regression-2** (Grove #261) | 6-minute boots; `soil_list(flags)` returns 128K past the token cap; `kb_search` drowns 3 real hits in 120K of tooling-doc noise | Injection/retrieval surfaces have no provenance-aware ranking or scoping to cap what's surfaced | **Over-surface.** Unprovenanced bulk crowds out signal and burns the budget |

**The pattern:** three distinct-looking bugs are two signs of one absence. *Bleed-in* (a boundary that should have held, didn't) and *dark-out* (state that should have a record, doesn't) are the same missing invariant seen from opposite sides. *Over-surface* is the cost you pay when there's no provenance to rank or scope by.

---

## Diagnosis — two axes of the same fault

1. **Provenance stripped.** A surfaced line carries no `{session_id, project, author, verified?, checked_at}`. The agent cannot tell whose memory it is, when it was true, or whether it was ever checked — so it treats all of it as its own, present, and true.
2. **Scope absent.** Boot/resume injection and retrieval (`kb_search`, `soil_list`, `willow_find`) do not filter to the current session+project boundary, nor rank by provenance tier. So the wrong session bleeds in, sibling projects go dark, and unprovenanced bulk buries signal.

Both axes are already *solved once each* in the codebase — the fix is to generalize, not invent:

- `[CROSS-RUNTIME]` proves the provenance-stamp pattern (axis 1).
- `boot_digest` already marks items `verified / STALE / unverified + checked_at` (axis 1) — but only for its own block.
- Constitution **Article IV** (knowledge tiered by evidence, promoted only by ratification) is this exact invariant at the canon layer. The memory *surfaces* just don't enforce what the *canon* already does.

---

## Build target — "provenance on every memory surface"

Smallest-first, each independently shippable:

1. **Stamp the injection.** Every resume/boot block line (`[LEDGER]`, `[HANDOFF]`, `[NEXT]`, `corrections`, `preferences`) carries `session_id + project + verified?`. Cross-session/cross-project lines are labeled ambient, inheriting the `[CROSS-RUNTIME]` "never report as your own" discipline. *(Closes bleed-on-resume; shrinks boot cost by letting the agent skip unowned lines.)*
2. **Scope the injection & retrieval.** Filter resume injection and `willow_find`/`kb_search`/`soil_list` to the current `session_id`+`project` by default; cross-scope results are opt-in and taint-labeled. `soil_list` gets a summary/cap mode so flag triage never returns 128K. *(Closes cross-project-invisible + the soil_list token-cap arm of boot-cost.)*
3. **Rank by provenance.** `kb_search` down-ranks unprovenanced corpus/tooling-doc rows; canonical/ledger/handoff-sourced atoms float. *(Closes the retrieval-noise arm of boot-cost + the ΔΣ search that drowned today.)*
4. **Intake the invisible.** A commit-trailer harvester + cloud-session intake stamps cloud/other-runtime work into fleet memory with origin provenance. *(Closes cloud-sessions-invisible.)*
5. **Agent-side rule (free, ships today).** Treat every resume-injected `corrections`/`observation`/`NEXT` as **unverified until matched to the live session**. This is the discipline the seat applied *after* getting burned on 2026-07-15 — encode it, don't rely on it being re-learned.

---

## The invariant, stated for the charter

Candidate for an Article-IV corollary or an Appendix-A enforcement row:

> **Memory-surface provenance.** No memory surfaced to an agent — by boot injection, resume, or retrieval — may omit its origin (`session_id`, `project`), its recency (`checked_at`), and its verification state. Unprovenanced or cross-scope memory is presented as ambient and is not the agent's own; acting on it as first-person state is a defect, not a judgment call.

This is Article IV's evidence-tiering extended from *canon* to *every surface that feeds an agent* — and it is the same law ΔΣ=42 states as a seal: constancy is the first debt a number owes.

---

## Provenance of this write-up

Consolidates SOIL `willow/flags` record **flag-cross-session-ledger-bleed-on-resume** (2026-07-15, session 69d71c01), and Grove-logged flags **flag-cross-project-debrief-invisible** (#262/#263), **flag-cloud-sessions-invisible-to-fleet-memory** (#258), **flag-boot-cost-regression-2** (#261). Live instance that triggered the consolidation: 2026-07-15 resume bleed of the UTETY age-gate thread into this willow-charter session, caught by the operator. Shape only — build awaits an envelope.

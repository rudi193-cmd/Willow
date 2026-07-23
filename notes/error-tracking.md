---
name: error-tracking
description: Operator scratch note distinguishing error tracking (telemetry) from writing errors (durable knowledge) for the fleet.
kind: doc
---

@markdownai v1.0

# Error tracking vs writing errors

*Operator scratch — 2026-07-06. Unratified. Companion to AGENT_SERVICES.md (especially S2: answered proposals need bounce reasons).*

## The distinction

| | **Error tracking** | **Writing errors** |
|---|-------------------|-------------------|
| **Question** | What failed, how often, for whom? | What should the fleet *remember* about that failure? |
| **Posture** | Telemetry — append, count, classify | Knowledge — durable, retrievable, actionable |
| **Consumer** | Operator dashboards, meters (S6), audit | Next agent at boot, authority_check (S1), precedent (S4) |
| **Risk if conflated** | Noise without learning — 254× Bash blocks, no map | Premature canon — every stack trace becomes law |
| **Risk if split too hard** | Agents discover law by bouncing off it | Stale prose nobody queries; tracking without closure |

**Working thesis:** tracking is the *sensor*; writing is the *actuator*. The seat owes agents both — but not the same artifact. A block is tracked immediately; it becomes *written* only when promoted to a reasoned bounce, correction, flag, or atom.

---

## What exists today (willow-2.0 runtime)

### Tracking (observe)

- **PreToolUse block telemetry** — `corpus/block_telemetry` per rule key; may surface as `willow/flags` + boot learned denials
- **MCP receipts** — `willow.mcp_receipts` (`ok`, `error_type`, latency)
- **Hook failures** — `$WILLOW_HOME/logs/hook_errors.jsonl` (silent SOIL/MCP write failures)
- **Kart uniform errors** — `error` field on failed tasks (exit code + stderr tail)
- **Diagnostics** — `diagnostic_summary` (ruff/mypy delta vs baseline in SOIL)
- **Nest feedback** — prediction vs outcome (`nest/v1`); human-side closed loop
- **Gaps** — `memory_sanitizer` → gaps log; boot digest `open gaps`

### Writing (remember)

- **Corpus corrections / preferences** — operator voice; boot-loaded from SOIL
- **Learned denials** — automated block telemetry distilled to routing hints (not operator truth)
- **KB / intake** — promoted atoms when a failure pattern is worth fleet memory
- **FRANK** — tamper-evident ledger for ratified decisions (envelope grants, dispatch closes)
- **Flags** — open threads with `fix_path`; block-telemetry flags archived by `archive_block_flags.py`
- **Handoff v3 claims** — `verify` blocks tie prose to machine-checkable state

### The gap (motivating this note)

AGENT_SERVICES §0 evidence: **Bash blocked 254×** — tracked abundantly, *written* thinly. Agents get "use Kart" without the *why this command* or *which envelope covers the alternative*. S2 bounce-with-reason is the constitutional target; block telemetry is the sensor that should feed it, not replace it.

---

## Design pressures (to resolve)

1. **Promotion gate** — When does a tracked error become a written error? (count threshold? operator attestation? nest-style outcome?)
2. **Dedup** — Same block 96× fleet-wide: one written correction, many counter increments
3. **Layering** — Hook block ≠ Kart failure ≠ diagnostic ≠ KB contradiction — same vocabulary or separate lanes?
4. **Agent-facing shape** — Bounce reason must be queryable mid-plan (S1/S2), not buried in JSONL
5. **Expiry** — Written errors stale; tracking rolls off. Article III.3 applies to standing grants, not necessarily to corrections — but corrections without `invalid_at` become folklore

---

## Operator notes (add below)

<!-- Sean: dump raw bullets here or dictate in session; agent will merge -->



---

## Open threads

- [ ] Does `authority_check` return `forbidden` with a pointer to a *written* bounce record, not just a redirect string?
- [ ] Nest `nest/v1` outcome schema as template for seat-side proposal bounces?
- [ ] Separate collection: `corpus/error_bounces` vs overloading `corpus/corrections`?
- [ ] Relationship to BKT / skill_mastery outcomes (boot skill pass/fail is already tracked)

---

*ΔΣ=42 — gaps acknowledged on purpose.*

@markdownai v1.0

# Delegation grading — how the multimodels-mcp pattern lays over Willow

**Status:** shape only — no code, awaits operator ratification.
**Source find:** [dpmadsen/multimodels-mcp](https://github.com/dpmadsen/multimodels-mcp) (MIT), KB atom `AF96AEDD`.
**Written:** 2026-07-20 by the willow seat, session 8cf60b06.

@define-concept name="delegation-trust"
A delegate's trust is not an opinion — it is a pass-rate measured by graders
written before the delegate saw the task, across enough rounds that variance
cannot masquerade as competence.
@end

## The pattern, distilled from his repo

Five pieces, none of which depend on his code:

1. **The menu** — an explicit registry of delegates with live health status.
   Not "which models exist" but "which are answerable right now."
2. **The waiter** — one verb: a *self-contained* task goes out, an answer comes
   back tagged with origin and cost. The delegate never sees the orchestrator's
   context; the task must stand alone. (This constraint is the quiet gem — it
   forces dispatches to be well-formed.)
3. **Stations** — task classes that isolate a skill: build-from-spec,
   find-and-fix, review-with-seeded-bugs, strict extraction, long compound
   deliverable, honesty-under-missing-context.
4. **Hidden graders, written first** — the test suite exists before any
   delegate runs. The grader is the commitment; the run is the evidence.
5. **Rounds** — minimum three. His data: single runs lied in both directions;
   round three changed half the conclusions.

## Where each piece already lives in Willow

| His piece | Our substrate | Gap |
|-----------|---------------|-----|
| The menu | `list_models` ≈ Ollama roster + fleet agents + kart lanes; no unified "answerable now" view | menu verb is unbuilt |
| The waiter | `dispatch_send` (packet + grant) · `willow_run`/Kart for execution | dispatches today are NOT graded, only evidence-checked at completion |
| Stations | nothing formal — dispatch tasks are ad-hoc prose | station taxonomy is unbuilt |
| Hidden graders | evidence-gated completion verify (willow-2.0 #534/#535) checks that *evidence exists*; it does not check *quality against a pre-committed suite* | the grader-before-work discipline is the missing half |
| Rounds | nest outcome records (PRs #724/#725) store prediction→outcome pairs one at a time | no multi-round aggregation, no variance view |

The one-line summary of the gap: **we verify that delegated work happened;
he verifies that delegated work can be trusted.** Our completion gate is
necessary; his grading layer is what would make dispatch *routing* rational.

## What we would grade (in priority order)

1. **Ollama locals per station** — which of the 7 local models can hold which
   station. Directly serves the "local-model work means the whole job" rule:
   today we route to `llama3.1:8b` etc. on folklore, not pass-rates.
2. **The honesty station, fleet-wide** — his phantom-file test (9/9 correct
   refusals from the best delegate) is exactly the failure mode the
   constitution cares about: does a delegate say "not found" or does it
   invent? This station applies to *agents*, not just models — a hanuman
   dispatch can be seeded the same way.
3. **Kart lane latency/fidelity** — fast vs batch as delegates with a cost
   column, same scorecard shape.
4. **External lanes, only if ever wanted** — his Codex/DeepSeek/OpenRouter
   lanes would each be a Gate matter: three keys per provider, task content
   is egress. Not proposed here.

@constraint id="DG-1" severity="hard"
Graders are written and committed (FRANK-recorded) before any delegate
receives the station task. A grader written after a run grades nothing.
@end

@constraint id="DG-2" severity="hard"
Station tasks sent to any non-local delegate are egress and require the
full three-key gate (capability + consent.internet + operator lease).
The local Ollama lane requires none.
@end

@constraint id="DG-3" severity="soft"
Three rounds minimum before a pass-rate is written to the KB as a
delegate-trust claim; single-round results stay in nest intake, tier
frontier, never promoted.
@end

## How it feeds what already exists

- **Scorecards → nest**: each station run is a prediction→outcome record —
  the exact row shape the nest learning loop already stores. Aggregated
  pass-rates become ratifiable rules ("route strict-extraction to any local;
  route find-and-fix only to X").
- **Scorecards → dispatch routing**: `agent_route` today picks by role.
  A trust table would let it pick by measured station competence.
- **Scorecards → the charter**: delegation trust is the empirical footing for
  the Powers-over-Agents schedules — revocation thresholds (P-1) become
  numbers instead of judgment calls.

## Deliberately out of scope

- Running his Node server inside the membrane.
- Any external-provider lane.
- Auto-applying routing changes from scorecards (nest rule: propose/ratify,
  never auto-apply).

## Next bite, if ratified

Define the first three stations (strict extraction · find-and-fix ·
honesty/phantom-file) as prose specs + committed graders, run the 7 Ollama
locals × 3 rounds through existing `willow_run`/`infer_7b` plumbing, write
the first scorecard to nest intake. No new services, no new repos.

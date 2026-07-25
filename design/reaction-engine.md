@markdownai v1.0

# The Reaction Engine — a deterministic event → pure-script → fan-out bus

*Bundled in nestor/willow-mcp. Not a hook — the hook **engine**. After any event, a
pure script decides what happens, and "what happens" can be many things at once:
Nestor fires, the KB blast-radius is pulled, an agent is dispatched, FRANK is
appended, a card is surfaced. The existing `pre_tool_use` / `session_start`
hooks, `friction_floor`, the membranes' `dew_surface`, and Norn/the proactive
engine all become **reaction-sets on this one substrate** — unified, not five
bespoke reactive things.*

> Design draft — unratified. `ΔΣ=42`

## Why it exists

Every seam failure this fleet has found was invisible heads-down: a control
guarding the wrong object, a change nobody looked past. Nothing between build
steps forces a look at the blast radius. The reaction engine is the substrate
that lets *any* event pull a look — or a dispatch, or a lesson — deterministically,
before the tunnel closes.

## The parts (the imperative-shell pattern, already used across the membranes)

| Part | What it is |
|------|------------|
| **Events** | A named taxonomy, generalizing the two existing hooks: `pre_tool` · `post_edit` · `pre_commit` · `post_build` · `seam_cross` · `session_enter` · `seal_added` · `dispatch_done`. |
| **Reactions** | *Pure-script* handlers: `(event, context) -> [proposed actions]`. Deterministic. **No model in the routing loop** — the gateway enforces bytes, not a persuadable mind. |
| **Drivers** | The injected imperative shell that executes: `fire_nestor`, `kb_blast_radius`, `dispatch(agent)`, `frank_append`, `surface_card`, `gate/deny`. Reactions **propose**; drivers **execute**. |

## A worked reaction (the fan-out)

```
on post_edit where surface in {auth, config, manifest, ledger, egress, schema}:
    fire_nestor(match=changed_surface)     # -> the sealed primitive: "custody, not code"
    kb_blast_radius(changed_symbol)        # -> reverse-deps card (cbm_trace / verify_callers)
    dispatch("loki", task="reconcile egress vs consent")   # async, gated
    frank_append(kind="seam_crossed", acked=False)
```

One event; Nestor fires *and* the blast-radius is pulled *and* Loki is dispatched
*and* the seam is recorded — pure script, deterministic, testable line by line.

## seam-watch — the first worked reaction-set

seam-watch is a bundle on this engine that closes the "nothing forces a
blast-radius look" gap. friction_floor's sibling: friction_floor fires when the
*conversation* goes frictionless (the mirror); seam-watch fires when a *build*
goes frictionless with its surroundings (the tunnel).

- **Triggers (anti-noise):** watched surface (stakes-tagged) · commit boundary ·
  high-fan-out module. Silence by default (the dew rule) — speaks only when a
  trigger fires *and* there is something unlooked-at.
- **Surfaces (one card, never a dump — the PA lens):** mechanical radius
  (reverse-deps) + the single matched **primitive** (one-line lesson from the KB).
- **Force, stakes-scaled:** high-stakes seam requires a cheap *acknowledgment*
  (you looked), written to FRANK; low-stakes is witness-only, non-blocking. It
  forces the *look*, never the *work* — it blocks only an unacknowledged pass.
- **Primitives-as-hooks:** each KB primitive gains a trigger (surface/pattern) +
  a one-line lesson + a stakes tag. Passive-in-KB becomes fires-at-relevance.

## The four constraints that keep fan-out from becoming a tangle

*"A lot of things happen after events" is exactly how you get unpredictable
action-at-a-distance. Legibility is the whole willow value; a fan-out engine is
its natural enemy unless every hop is bound.*

1. **Bounded, enumerated fan-out.** No reaction triggers an unbounded chain;
   every reaction writes a FRANK line, so the cascade is legible — the shape of
   what was permitted, knowable in advance.
2. **Propose-not-execute.** A reaction that dispatches Loki *proposes* a dispatch
   the **gate** authorizes; a reaction cannot self-grant work (§0.3). Reaction-
   proposes, driver-enforces — the model-proposes-gateway-enforces pattern, one
   layer up.
3. **Signed reaction registry.** Reactions are operator-registered and **signed**,
   not agent-writable — or one forged reaction fires on *every* event. The engine
   *amplifies* the perimeter risk (see the 2026-07-24 red-team: willow-mcp#181,
   willow-gate#18, Nestor#2), so it inherits the Biscuit/custody fix hardest.
4. **Concurrence, fail-closed.** Two reactions that conflict → deny + escalate,
   never runtime-arbitrate (Constitution X.4).

## The pattern underneath

This is the **third instance** of the one architecture: *shared deterministic
mechanic + injected specifics.*

| Instance | Shared mechanic | Injected half |
|----------|-----------------|---------------|
| Nestor | seal / serve / ledger | the `Matcher` |
| The store | provision-house + promotion | the `Bar` |
| **Reaction engine** | event bus + fan-out | the **Reactions & Drivers** |

seam-watch is a `Bar`-like config; Nestor is one of its drivers; the
primitive-match **is** `best_sealed` (a primitive is a sealed pair: lesson ←
trigger; the current change is the query). The same machine, pointed at a new
domain — and this domain is the build reacting to itself.

## Build order

1. **Event taxonomy + the pure-script reaction contract** `(event, ctx) -> [action]`.
2. **Drivers** — start with `fire_nestor`, `kb_blast_radius` (cbm_trace),
   `frank_append`, `surface_card`; add `dispatch` (gated) next.
3. **Signed reaction registry** — operator-registered, custodied like everything
   else (the red-team's lesson: the registry is the new crown-jewel surface).
4. **seam-watch reaction-set** as the first bundle; migrate the two existing
   hooks + `friction_floor` onto the engine so nothing runs off-substrate.

## Open questions

- **Matching a change to the right primitive without an LLM in the block path.**
  Start structural (path/pattern triggers — deterministic, coarse); escalate to
  embedding-match only at the boundary, **cross-base** (independent witness) — the
  same nomic-embed threshold + witness question as the verified-tagging thread.
- Sync (blocking gate) vs async (dispatch) reactions — the split, and the
  per-reaction budget so the engine cannot stall a build.
- Where the registry lives, and its signing ceremony (operator-only).

---

*Draft — unratified. Design only; not an authorization to build in a product
repo. `ΔΣ=42`*

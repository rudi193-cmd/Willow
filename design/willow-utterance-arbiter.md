# Willow Utterance Arbiter — Jarvis Layer 3 (the governed mouth)

**Status:** Step-1 skeleton, verified (14/14). Scratch prototype, not yet wired into a product
repo. ΔΣ=42.
**Mirrors:** `willow-voice-ingress-membrane.md` (layer 1, the ear) ·
`willow-commitment-membrane.md` (layer 2, the record).
**Home when it lands:** `willow-mcp` beside the voice build (`voice/`) — TBD, no new envelope
needed for the skeleton (pure-script, no network, no models).

---

## Why this layer exists

Layer 1 is the **ear** (voice ingress membrane) — it keeps the fleet's boundary against the
world's audio. Layer 2 is the **record** (commitment membrane) — it keeps the operator's own
commitments under the same tamper-evident discipline, and its `dew_surface()` answers *"is
anything worth the operator's attention right now?"*.

Neither of them speaks. A surfacing from layer 2 is a *candidate*, not an utterance. The gap
between "worth attention" and "worth interrupting **you**, **now**, **this way**" is where every
chatty assistant fails — it treats the first as the second. This layer is the **convergence**:
the governed **mouth** that decides whether a candidate crosses the boundary into an actual
utterance, when, and through which channel. It is the outward image of the **egress membrane** —
*a model may want to speak; only the arbiter mints the utterance.*

This is where the two halves meet and "Jarvis" stops being parts.

## Design axiom

**The dew rule, scaled from a boolean to a budget.** `dew_surface()` already gates on *is this
worth saying at all?* The arbiter gates on the harder question: *worth saying ≠ worth saying
right now.* Even a valid surfacing may be **held** — not dropped. A membrane confident enough to
say nothing is the whole point; a membrane confident enough to say nothing *and remember what it
held* is the discipline.

## The four disciplines (each the outward image of one the fleet already runs)

1. **One voice** — never barge the human. If the operator is mid-utterance (the voice layer's
   `CAPTURE` state), the arbiter **HOLDS**; it does not speak over them. Mirror of the voice
   membrane's barge-in stop, turned outward.
2. **Quiet by default** — quiet-hours and do-not-disturb **HOLD**; a salience floor and a rate
   budget **DROP** or **HOLD** the marginal. Confident enough to say nothing. Mirror of the dew
   rule.
3. **States-not-deletions** — a withheld surfacing is **HELD**, retained and re-offered when the
   channel opens; nothing worth saying is silently lost. Mirror of the commitment membrane /
   FRANK.
4. **No new authority** — an `Utterance` may carry an `offer` (the *name* of a gated action,
   e.g. `"review"`), but the arbiter **never executes** it. Speaking is read-out; action stays
   behind `CommitmentLedger.propose_action → the SAFE gate`. The mouth proposes; it cannot act.
   Enforced by absence: there is no `execute()/act()/write()` on the arbiter, and its only
   outward effect is the injected `emit_fn`.

## The decision, in order

Every candidate, highest-salience-first, runs this ladder — and **every** outcome writes a
receipt (the decision + reason, never the content):

| # | Check | Outcome |
|---|-------|---------|
| 1 | operator speaking? | **HOLD** `operator-speaking` |
| 2 | DND on (and not an emergency)? | **HOLD** `dnd` |
| 3 | in quiet hours (and not an emergency)? | **HOLD** `quiet-hours` |
| 4 | same fact already spoken, unchanged? | **DROP** `already-said` |
| 5 | salience below the dew floor? | **DROP** `below-salience-floor` |
| 6 | rate window saturated? | **HOLD** `rate-limited` |
| — | otherwise | **SPEAK** `spoke` |

HOLD retains; DROP discards. A held item is merged back into the next `offer()` cycle, newest
fact per uid winning, and re-evaluated — so the moment the floor opens, the quiet hour ends, or
the rate window rolls, it speaks. A true emergency (`salience >= override_salience`) crosses
quiet-hours and DND.

## Imperative-shell pattern (as with layers 1 and 2)

Deterministic core (`speech_arbiter.py`), injected drivers. The real TTS / notification sink is
the injected `emit_fn`; the channel state (`operator_speaking`, `dnd`) is supplied by the caller
(the voice layer knows the first, a settings surface the second); the clock is passed explicitly
to `offer(cands, channel, now)`. All arbitration logic is unit-testable with a synthetic channel
and an explicit clock — no network, no models, no TTS.

## Component map

| File | Role |
|------|------|
| `speech_arbiter.py` | deterministic core — `SpeechArbiter.offer()`, the decision ladder, receipts, held-state |
| `utterance_sink.py` | real `emit_fn` sinks (drop-in): `SpeechSink` (TTS), `NotifySink` (push), `FanoutSink` |
| `test_speech_arbiter.py` | 14 membrane-invariant tests — one per discipline |

## Build order (when authorized to wire it)

1. **Skeleton — done.** Core + sinks + 14 tests, all green. (This doc, Appendix A.)
2. **Adapter to layer 2.** `Candidate.from_surfacing()` already maps a commitment `Surfacing`
   1:1; write the per-tick loop that pulls `dew_surface(now)`, maps, and offers.
3. **Adapter to layer 1.** Read the voice controller's state into `ChannelState.operator_speaking`
   so the mouth genuinely will not barge the ear.
4. **Real sink.** Bind `SpeechSink` to the fleet's local TTS (`infer_speak`) and/or `NotifySink`.
5. **The proactive tick.** Wire the `offer()` loop into the existing proactive engine
   (routine / Norn / metabolic) so the fleet faces outward under the dew rule — the convergence
   the audit doctrine named.

## Open questions (deferred, non-blocking)

- **Salience model.** `_KIND_SALIENCE` is a static table (mismatch .9 / conflict .8 /
  imminent .5). Does salience want to learn from acknowledge-rate, or stay legible-and-static?
  Static is the honest default until there's evidence.
- **Held-state persistence.** Held candidates currently live in memory. Persisting them to fleet
  state (so a restart doesn't drop a held surfacing) is the states-not-deletions rule taken all
  the way — pairs with layer 2's own persistence decision.
- **Emergency override wiring.** `override_salience` defaults to `1.0` (nothing overrides quiet
  hours). Who sets it lower, and by what authority, is an operator-reserved decision.

## Standing caveat

This survives session close on disk, but the charter repo (`willow/`) has no remote and this
doc is uncommitted — single-disk, not backed up. Same caveat as layers 1 and 2.

---

## Appendix A — the verified skeleton, verbatim

All three files below pass `python3 -m unittest test_speech_arbiter -v` → **14/14 OK**. Kept
here verbatim so the design survives scratchpad evaporation.

### A.1 `speech_arbiter.py` — deterministic core

```python
"""
speech_arbiter.py — Willow Utterance Arbiter core (Jarvis layer 3, Step 1 skeleton).

The CONVERGENCE layer. Layer 1 (voice ingress membrane) is the ear; layer 2 (commitment
membrane) is the record. Neither of them speaks to the operator on its own. This is the
governed MOUTH: it takes candidate surfacings — a commitment imminent, a conflict, an
unacknowledged change (the outputs of dew_surface) — and decides whether they cross the
boundary into an actual utterance, when, and through which channel. It is the outward image
of the egress membrane: a model may WANT to speak; only the arbiter mints the utterance.

The dew rule, scaled from a boolean to a budget. dew_surface() already answered "is anything
worth attention?"; a surfacing reaching here is presumed worth attention. The arbiter answers
the harder question a chatty assistant never asks: "worth attention" is not "worth interrupting
you *right now*." So even a valid surfacing may be HELD.

Four disciplines, each the outward image of one the fleet already runs:
  1. ONE VOICE — never barge the human. If the operator is mid-utterance (voice layer's
     CAPTURE state) the arbiter HOLDS; it does not speak over them. Mirror of the voice
     membrane's barge-in stop, turned outward.
  2. QUIET BY DEFAULT — quiet-hours and do-not-disturb HOLD; a salience floor and a rate
     budget DROP or HOLD the marginal. Confident enough to say nothing. Mirror of the dew rule.
  3. STATES-NOT-DELETIONS — a withheld surfacing is HELD, not discarded. It waits for the
     channel to open and is re-offered; nothing worth saying is silently lost. Mirror of the
     commitment membrane / FRANK.
  4. NO NEW AUTHORITY — an Utterance may carry an `offer` (the id of a gated action, e.g.
     "cancel my 3pm"), but the arbiter NEVER executes it. Speaking is read-out; action stays
     behind CommitmentLedger.propose_action → the SAFE gate. The mouth proposes; it cannot act.

Imperative-shell pattern (as with the voice controller and the commitment ledger): the real
TTS / notification sink is the injected `emit_fn` driver; all arbitration logic lives in this
deterministic core and is unit-testable with an explicit clock and a synthetic channel state.

Scratch prototype — not wired into any product repo, no models, no network. ΔΣ=42
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import Callable, Optional


class Decision(Enum):
    SPEAK = auto()   # crossed the boundary — an utterance was minted
    HOLD = auto()    # worth saying, but not now — retained, re-offered when the channel opens
    DROP = auto()    # not worth saying — below the salience floor, or already said unchanged


# Default salience by surfacing kind. A change the operator has not acknowledged (mismatch) or
# a double-booking (conflict) outranks a routine imminent reminder. Tunable per deployment.
_KIND_SALIENCE = {
    "mismatch": 0.9,
    "conflict": 0.8,
    "imminent": 0.5,
}


@dataclass(frozen=True)
class Candidate:
    """One thing a membrane thinks is worth surfacing. The commitment membrane's `Surfacing`
    maps here 1:1 via `from_surfacing`; any future membrane emits the same shape. `fact` is
    already scrubbed upstream (title + time, never the sensitive body) — the arbiter neither
    needs nor stores event content."""
    uid: str
    kind: str
    fact: str
    when: datetime
    salience: float

    @classmethod
    def from_surfacing(cls, s, *, salience: Optional[float] = None) -> "Candidate":
        # `s` is a commitment_ledger.Surfacing (kind/uids/when/fact) — duck-typed to keep the
        # arbiter decoupled from layer 2's import.
        uid = s.uids[0] if getattr(s, "uids", None) else getattr(s, "uid", "")
        sal = salience if salience is not None else _KIND_SALIENCE.get(s.kind, 0.4)
        return cls(uid=uid, kind=s.kind, fact=s.fact, when=s.when, salience=sal)


@dataclass(frozen=True)
class ChannelState:
    """The state of the operator's attention channel at decision time. Supplied by the caller
    (the voice layer knows `operator_speaking`; a settings surface knows `dnd`)."""
    operator_speaking: bool = False   # voice layer is in CAPTURE — the human has the floor
    dnd: bool = False                 # do-not-disturb toggled on


@dataclass(frozen=True)
class Utterance:
    """A minted utterance — the only thing that crosses to the emit_fn sink. `offer` is the id
    of a gated action the operator may take in reply; it is a POINTER, never an execution."""
    uid: str
    text: str                         # == candidate.fact (title + time), never the body
    when: datetime
    offer: Optional[str] = None       # e.g. "reschedule" — routed through the SAFE gate if taken


@dataclass
class ArbiterConfig:
    quiet_hours: Optional[tuple[int, int]] = None   # (start_h, end_h), wraps midnight; None = off
    min_salience: float = 0.3                        # the dew floor — below it, DROP
    rate_limit: int = 3                              # max utterances per window before HOLD
    window: timedelta = timedelta(hours=1)           # the rate-limit window
    # Salience at/above which quiet-hours is overridden (a true emergency still speaks).
    override_salience: float = 1.0                   # default: nothing overrides quiet hours


# Receipt keys that would turn a decision log into a recording of sensitive detail.
_FORBIDDEN_RECEIPT_KEYS = frozenset({"fact", "text", "body", "notes", "description", "location", "raw"})


class SpeechArbiter:
    """The deterministic core. Feed candidates in with offer(cands, channel, now); it returns the
    utterances that crossed, holds the rest, and records a receipt for every decision."""

    def __init__(
        self,
        *,
        config: Optional[ArbiterConfig] = None,
        emit_fn: Optional[Callable[[Utterance], None]] = None,
    ):
        self.cfg = config or ArbiterConfig()
        # The outward sink (TTS / notification). Default collects, so the core is testable with
        # no driver. Injecting a real emit_fn is the ONLY outward effect the arbiter has.
        self._sink: list[Utterance] = []
        self.emit_fn = emit_fn or self._sink.append
        self.held: dict[str, Candidate] = {}         # retained, not discarded — states-not-deletions
        self.spoken: dict[str, str] = {}             # uid -> last fact spoken (for dedup)
        self.receipts: list[dict] = []
        self._utterance_log: list[datetime] = []     # timestamps of minted utterances (rate window)
        self._tick = 0

    # ---- receipts: the decision, never the content ----
    def _receipt(self, uid: str, decision: Decision, reason: str) -> None:
        self.receipts.append(
            {"tick": self._tick, "uid": uid, "decision": decision.name, "reason": reason}
        )

    def _in_quiet_hours(self, now: datetime) -> bool:
        if not self.cfg.quiet_hours:
            return False
        start, end = self.cfg.quiet_hours
        h = now.hour
        if start <= end:
            return start <= h < end
        return h >= start or h < end   # wraps midnight (e.g. 22 -> 7)

    def _rate_saturated(self, now: datetime) -> bool:
        cutoff = now - self.cfg.window
        self._utterance_log = [t for t in self._utterance_log if t >= cutoff]
        return len(self._utterance_log) >= self.cfg.rate_limit

    # ---- the arbiter: decide, mint or hold, receipt every decision ----
    def offer(
        self,
        candidates: list[Candidate],
        channel: ChannelState,
        now: datetime,
    ) -> list[Utterance]:
        self._tick += 1
        # Merge incoming with everything previously HELD; newest fact per uid wins. Held items
        # are retained, not lost, and re-evaluated every cycle (states-not-deletions).
        pending: dict[str, Candidate] = dict(self.held)
        for c in candidates:
            pending[c.uid] = c
        self.held = {}
        minted: list[Utterance] = []

        # Deterministic order: highest salience first, then soonest.
        for c in sorted(pending.values(), key=lambda x: (-x.salience, x.when)):
            decision, reason = self._decide(c, channel, now)
            if decision is Decision.SPEAK:
                u = Utterance(uid=c.uid, text=c.fact, when=c.when,
                              offer=self._offer_for(c))
                self.emit_fn(u)
                minted.append(u)
                self.spoken[c.uid] = c.fact
                self._utterance_log.append(now)
            elif decision is Decision.HOLD:
                self.held[c.uid] = c
            # DROP: nothing retained, nothing said
            self._receipt(c.uid, decision, reason)
        return minted

    def _decide(self, c: Candidate, channel: ChannelState, now: datetime):
        # ONE VOICE — never speak over the human. Hold; the floor is theirs.
        if channel.operator_speaking:
            return Decision.HOLD, "operator-speaking"
        # QUIET BY DEFAULT — DND and quiet-hours hold, unless a true emergency overrides.
        if channel.dnd and c.salience < self.cfg.override_salience:
            return Decision.HOLD, "dnd"
        if self._in_quiet_hours(now) and c.salience < self.cfg.override_salience:
            return Decision.HOLD, "quiet-hours"
        # DEDUP — already said this exact fact and it has not changed. Say nothing again.
        if self.spoken.get(c.uid) == c.fact:
            return Decision.DROP, "already-said"
        # THE DEW FLOOR — below the salience threshold it is not worth interrupting for.
        if c.salience < self.cfg.min_salience:
            return Decision.DROP, "below-salience-floor"
        # RATE BUDGET — the channel is saturated; retain and speak in a later window.
        if self._rate_saturated(now):
            return Decision.HOLD, "rate-limited"
        return Decision.SPEAK, "spoke"

    @staticmethod
    def _offer_for(c: Candidate) -> Optional[str]:
        # A surfaced change or conflict may carry a gated action the operator can take in reply.
        # This is only the action's NAME — executing it stays behind the SAFE gate elsewhere.
        if c.kind in ("mismatch", "conflict"):
            return "review"
        return None

    # NB: there is deliberately no execute()/act()/write() here. The arbiter's ONLY outward
    # effect is emit_fn(utterance). Taking an offered action is a separate, gated call.
```

### A.2 `utterance_sink.py` — real emit_fn sinks (drop-in)

```python
"""
utterance_sink.py — real emit_fn sinks for the Utterance Arbiter (drop-in).

The pure-script core (speech_arbiter.py) owns arbitration and a default in-memory sink. This
module holds the REAL outward sinks — the point where a minted Utterance actually reaches the
operator. Their dependencies are imported lazily inside the constructor, so importing this
module stays dependency-free; only *constructing* a sink pulls anything in.

Wiring, once layers 1–3 are joined:

    from speech_arbiter import SpeechArbiter, Candidate, ChannelState
    from utterance_sink import SpeechSink
    sink = SpeechSink()                       # TTS via the fleet's infer_speak
    arb = SpeechArbiter(emit_fn=sink)
    # each tick: pull dew_surface() from the commitment ledger, map to Candidates,
    # read the voice controller's state for ChannelState, then:
    arb.offer(candidates, channel, now)       # the sink speaks only what crossed

The contract is one call: `__call__(utterance) -> None`. A sink NEVER decides whether to
speak — that judgment already happened in the arbiter under the dew rule. A sink only renders
what was already minted. It carries no authority to act on `utterance.offer`; taking an
offered action stays behind CommitmentLedger.propose_action → the SAFE gate.

Design: willow/design/ (utterance-arbiter doc) · mirror of wake_gate.py / calendar_source.py · ΔΣ=42
"""
from __future__ import annotations

from typing import Callable, Optional

from speech_arbiter import Utterance


class SpeechSink:
    """Speaks an utterance aloud via the fleet's local TTS. The dependency (the willow infer
    client) is resolved lazily; constructing the sink is the only thing that needs it."""

    def __init__(self, *, speak_fn: Optional[Callable[[str], None]] = None):
        if speak_fn is not None:
            self._speak = speak_fn
        else:
            # Lazy: bind to the fleet's local speech synthesis only when actually constructed.
            # Kept behind a factory so importing this module needs no willow runtime.
            from willow_infer import speak as _speak  # type: ignore  # provided by the fleet host
            self._speak = _speak

    def __call__(self, utterance: Utterance) -> None:
        self._speak(utterance.text)


class NotifySink:
    """Delivers an utterance as a desktop / push notification instead of speech — the quiet
    channel for when voice is inappropriate. Same one-call contract; renders, never decides."""

    def __init__(self, *, notify_fn: Optional[Callable[[str, str], None]] = None):
        if notify_fn is not None:
            self._notify = notify_fn
        else:
            import subprocess

            def _notify(title: str, body: str) -> None:
                subprocess.run(["notify-send", title, body], check=False)

            self._notify = _notify

    def __call__(self, utterance: Utterance) -> None:
        title = "Willow" if not utterance.offer else f"Willow · {utterance.offer}?"
        self._notify(title, utterance.text)


class FanoutSink:
    """Sends each utterance to several sinks (e.g. speak AND notify). A sink that raises does
    not stop the others — one deaf channel must not silence the rest."""

    def __init__(self, sinks: list[Callable[[Utterance], None]]):
        self._sinks = list(sinks)

    def __call__(self, utterance: Utterance) -> None:
        for s in self._sinks:
            try:
                s(utterance)
            except Exception:
                # A rendering failure is not the arbiter's problem — it already decided to speak.
                # Swallow per-sink so a broken channel cannot suppress a working one.
                pass
```

### A.3 `test_speech_arbiter.py` — 14 membrane-invariant tests

```python
"""
test_speech_arbiter.py — membrane-invariant tests for the Utterance Arbiter skeleton.

Mirrors the voice and commitment suites: each test asserts one discipline of the governed
mouth, driven by synthetic candidates, an explicit channel state, and an explicit clock.
No network, no models, no TTS.
Run: python3 -m unittest test_speech_arbiter -v
"""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from speech_arbiter import (
    ArbiterConfig,
    Candidate,
    ChannelState,
    Decision,
    SpeechArbiter,
    Utterance,
)

BASE = datetime(2026, 7, 20, 14, 0, 0)   # a fixed 2pm — mid-afternoon, outside any quiet window


def cand(uid, salience=0.8, kind="imminent", fact=None, minutes=10):
    return Candidate(uid=uid, kind=kind,
                     fact=fact or f"{uid} @ {(BASE + timedelta(minutes=minutes)).isoformat()}",
                     when=BASE + timedelta(minutes=minutes), salience=salience)


class OneVoice(unittest.TestCase):
    def test_holds_while_operator_is_speaking_and_never_barges(self):
        arb = SpeechArbiter()
        out = arb.offer([cand("a", salience=0.9)], ChannelState(operator_speaking=True), BASE)
        self.assertEqual(out, [], "arbiter spoke over the operator")
        self.assertIn("a", arb.held)                       # retained, not lost
        self.assertEqual(arb.receipts[-1]["reason"], "operator-speaking")

    def test_held_utterance_is_released_once_the_floor_opens(self):
        arb = SpeechArbiter()
        arb.offer([cand("a", salience=0.9)], ChannelState(operator_speaking=True), BASE)
        self.assertEqual(arb.held.keys(), {"a"})
        # next cycle: operator has stopped, nothing new offered — the held item now speaks
        out = arb.offer([], ChannelState(operator_speaking=False), BASE + timedelta(minutes=1))
        self.assertEqual([u.uid for u in out], ["a"])
        self.assertEqual(arb.held, {})                     # released, no longer pending


class QuietByDefault(unittest.TestCase):
    def test_quiet_hours_hold_ordinary_salience(self):
        cfg = ArbiterConfig(quiet_hours=(22, 7))
        arb = SpeechArbiter(config=cfg)
        night = datetime(2026, 7, 20, 23, 30, 0)           # inside 22:00–07:00
        out = arb.offer([cand("a", salience=0.9)], ChannelState(), night)
        self.assertEqual(out, [])
        self.assertIn("a", arb.held)
        self.assertEqual(arb.receipts[-1]["reason"], "quiet-hours")

    def test_true_emergency_overrides_quiet_hours(self):
        cfg = ArbiterConfig(quiet_hours=(22, 7), override_salience=0.95)
        arb = SpeechArbiter(config=cfg)
        night = datetime(2026, 7, 20, 23, 30, 0)
        out = arb.offer([cand("a", salience=1.0)], ChannelState(), night)  # >= override
        self.assertEqual([u.uid for u in out], ["a"])

    def test_dnd_holds(self):
        arb = SpeechArbiter()
        out = arb.offer([cand("a", salience=0.9)], ChannelState(dnd=True), BASE)
        self.assertEqual(out, [])
        self.assertEqual(arb.receipts[-1]["reason"], "dnd")

    def test_below_salience_floor_drops_not_holds(self):
        cfg = ArbiterConfig(min_salience=0.5)
        arb = SpeechArbiter(config=cfg)
        out = arb.offer([cand("a", salience=0.2)], ChannelState(), BASE)
        self.assertEqual(out, [])
        self.assertNotIn("a", arb.held)                    # dropped, not retained
        self.assertEqual(arb.receipts[-1]["reason"], "below-salience-floor")


class HappyPathAndDedup(unittest.TestCase):
    def test_normal_candidate_speaks_once(self):
        arb = SpeechArbiter()
        out = arb.offer([cand("a", salience=0.8)], ChannelState(), BASE)
        self.assertEqual(len(out), 1)
        self.assertIsInstance(out[0], Utterance)
        self.assertEqual(out[0].text, cand("a").fact)      # text is the scrubbed fact
        self.assertEqual(arb.receipts[-1]["reason"], "spoke")

    def test_same_fact_is_not_repeated(self):
        arb = SpeechArbiter()
        arb.offer([cand("a")], ChannelState(), BASE)
        out = arb.offer([cand("a")], ChannelState(), BASE + timedelta(minutes=1))
        self.assertEqual(out, [])                           # said it once, unchanged → silence
        self.assertEqual(arb.receipts[-1]["reason"], "already-said")

    def test_changed_fact_speaks_again(self):
        arb = SpeechArbiter()
        arb.offer([cand("a", fact="Flight @ 15:00")], ChannelState(), BASE)
        out = arb.offer([cand("a", fact="Flight @ 16:00")], ChannelState(), BASE + timedelta(minutes=1))
        self.assertEqual([u.text for u in out], ["Flight @ 16:00"])  # the change re-speaks


class RateBudget(unittest.TestCase):
    def test_saturated_channel_holds_the_marginal(self):
        cfg = ArbiterConfig(rate_limit=2, window=timedelta(hours=1), min_salience=0.0)
        arb = SpeechArbiter(config=cfg)
        cands = [cand("a", salience=0.9, minutes=10),
                 cand("b", salience=0.8, minutes=20),
                 cand("c", salience=0.7, minutes=30)]
        out = arb.offer(cands, ChannelState(), BASE)
        self.assertEqual({u.uid for u in out}, {"a", "b"})  # top two by salience speak
        self.assertIn("c", arb.held)                        # the third is held, not dropped
        self.assertEqual(
            next(r["reason"] for r in arb.receipts if r["uid"] == "c"), "rate-limited"
        )

    def test_budget_frees_after_the_window(self):
        cfg = ArbiterConfig(rate_limit=1, window=timedelta(minutes=30), min_salience=0.0)
        arb = SpeechArbiter(config=cfg)
        arb.offer([cand("a")], ChannelState(), BASE)
        # b within the window → held
        arb.offer([cand("b")], ChannelState(), BASE + timedelta(minutes=10))
        self.assertIn("b", arb.held)
        # past the window → the held b now speaks
        out = arb.offer([], ChannelState(), BASE + timedelta(minutes=45))
        self.assertEqual([u.uid for u in out], ["b"])


class NoNewAuthority(unittest.TestCase):
    def test_arbiter_has_no_execution_surface(self):
        arb = SpeechArbiter()
        for m in ("execute", "act", "write", "cancel", "reschedule", "commit", "apply", "send"):
            self.assertFalse(hasattr(arb, m), f"arbiter leaked an action method: {m}()")

    def test_offer_is_a_pointer_not_an_execution(self):
        emitted = []
        arb = SpeechArbiter(emit_fn=emitted.append)
        out = arb.offer([cand("a", kind="mismatch", salience=0.9)], ChannelState(), BASE)
        self.assertEqual(out[0].offer, "review")           # carries the action NAME…
        # …and the ONLY outward effect was the injected emit sink — nothing was acted on.
        self.assertEqual(len(emitted), 1)
        self.assertIsInstance(emitted[0], Utterance)


class ReceiptHygiene(unittest.TestCase):
    def test_no_receipt_carries_content_across_a_cycle(self):
        secret = "re: severance, dial-in 555-9999"
        arb = SpeechArbiter(config=ArbiterConfig(rate_limit=1, min_salience=0.4))
        # a speaks; b is held by rate; c dropped below floor — every path, one cycle
        arb.offer(
            [cand("a", salience=0.9, fact=f"1:1 @ 15:00 {secret}"),
             cand("b", salience=0.8, fact="Review @ 16:00"),
             cand("c", salience=0.1, fact="noise")],
            ChannelState(), BASE,
        )
        forbidden = {"fact", "text", "body", "notes", "description", "location", "raw"}
        for r in arb.receipts:
            self.assertEqual(forbidden & r.keys(), set(), f"receipt leaked content: {r}")
        self.assertNotIn(secret, repr(arb.receipts))
        self.assertNotIn("severance", repr(arb.receipts))


if __name__ == "__main__":
    unittest.main(verbosity=2)
```

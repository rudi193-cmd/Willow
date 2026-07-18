# Willow Commitment Membrane — calendar as the operator's kept record

**Status:** design + **verified Step-1 skeleton in Appendix A** · **Author:** Willow (seat) · **Date:** 2026-07-17
**Cross-refs:** KB `48886881` (Jarvis audit — calendar is critical-path #2, scored 0%) · KB `6CAC0877` (calendar/desktop research — pure script, zero model) · KB `0E8C90C0` (Tally — the outward face of the governance seat)
**Related design:** `willow-voice-ingress-membrane.md` (this is its outward mirror)

---

## Design axiom

The voice ear is the **ingress** membrane — the fleet's boundary against the world's audio.
Calendar is the **outward** membrane — the operator's kept record of their own commitments.
The fleet keeps a tamper-evident record of *itself* (FRANK, envelopes, states-not-deletions);
the same discipline turned to face the human keeps *their* record: what was promised, what was
promised to them. Calendar events **are** the operator's commitments. So this is not "a calendar
connector" — it is Tally's half of the seat (KB `0E8C90C0`), and it must be built as a membrane,
not a productivity app.

The load-bearing idea, as with voice: **structure is the security model.** Three disciplines,
each the outward image of one the fleet already runs, and one rule of speech.

---

## The three disciplines (each mirrors a fleet discipline)

1. **Receipt-not-recording.** Store the commitment **fact** — title, when, who — never the
   sensitive event body/notes/location. Enforced by *the absence of a field to hold it* plus a
   receipt guard (`_FORBIDDEN_FACT_KEYS`). Mirror of the voice membrane's receipts.
2. **States-not-deletions.** A cancelled event becomes a **WITHDRAWN** state; a moved event keeps
   its old time in history and stays **ACTIVE**. Nothing is deleted. Mirror of FRANK / the
   envelope registry.
3. **No new authority.** The ledger **never writes the calendar.** A proposed mutation
   ("cancel my 3pm") routes through the existing SAFE gate (`propose_action` → `gate_fn`, default
   **deny**, fail-closed). A spoken or typed request hits the same stop. The membrane is
   read-in; action is gated-out. The `CalendarSource` contract is `fetch()` only — no
   create/update/delete exists to call.

## The rule of speech — the dew rule

`dew_surface(now)` is **silent by default.** It speaks only when the halves disagree:
- **imminent** — an active commitment starting within the lead window,
- **conflict** — two active commitments whose intervals overlap,
- **mismatch** — a change the operator has not yet acknowledged (the split-stick disagrees).

`acknowledge(uid)` restores silence (and is itself recorded — states-not-deletions). A surface
that speaks whenever it *can* is another chatty assistant; this one is confident enough to say
nothing. This is the constitution's axiom ("a human awake and watching does not scale") turned
around: a system awake and talking doesn't scale either.

---

## Component map — imperative shell

As with the voice controller, the deterministic **core** holds all discipline + dew logic and is
unit-testable with a stub source and an explicit clock; the real client is an injected **driver**.

| Piece | Off-the-shelf | Script or model |
|---|---|---|
| Ingest source | `caldav` (RFC-4791) or gcal-sync | **script** (injected driver) |
| Commitment ledger + state history | new — this core | **pure script** |
| Dew-rule surfacer | new — this core | **pure script** |
| SAFE gate | existing fleet gate | injected callable |
| Proactive delivery | existing routine / Norn / metabolic | **existing** (wiring only) |

No models anywhere in this layer — the Jarvis "script not model" thesis holds (KB `6CAC0877`).

---

## Build order

1. **Ledger + dew core** — commitment model, states-not-deletions, dew-rule surfacer, injected
   stub source. Unit-tested for the three disciplines + dew silence. **(Done — Appendix A.)**
2. **Real source** — implement `CalDavSource.fetch()` against the operator's provider (the one
   deferred decision: Google via gcal-sync vs a caldav host). The core does not change.
3. **Persist** — commitments + history into fleet state (SOIL/store), in-namespace.
4. **Deliver** — wire `dew_surface()` into the existing proactive engine (routine/Norn/metabolic)
   so it faces outward under the dew rule. This is where Jarvis layers 1 (voice out) and 2
   (commitments) converge into a surface that actually speaks.

## Open questions

- **Provider** (Step 2's only real input): Google (gcal-sync) vs caldav host (iCloud / Nextcloud
  / Fastmail). Deferred — it is the injected driver.
- **New invitations from others.** First-fetch treats every event as the acknowledged baseline.
  An event *created by someone else* (an invite) may warrant a one-word surface; needs
  organizer/attendee discrimination. Left as a Step-2 refinement.
- **Vanished events.** The skeleton withdraws only on an explicit `cancelled` status, never on an
  event merely dropping out of the fetch window (which would false-withdraw). Revisit with the
  real source's windowing semantics.
- **Home + envelope.** Lands as a willow-mcp sibling of the voice package (`voice/` → a
  `commitments/` package), covered by the same standing willow-mcp grants — no new envelope.

*Design + reference skeleton, not an authorization to build in a product repo. ΔΣ=42*

---

## Appendix A — verified Step-1 skeleton (reference code)

Built and verified 2026-07-17 (session 0002f1e4) as a scratch prototype — **not yet wired into
any product repo, no envelope**. Promoted here verbatim so it survives session close.
**Verification:** `python3 -m unittest test_commitment_ledger -v` → **10/10 pass.**

### A.1 — `commitment_ledger.py`

```python
"""
commitment_ledger.py — Willow Commitment Membrane core (Jarvis layer 2, Step 1 skeleton).

The OUTWARD mirror of the voice ingress membrane. Where the ear kept the fleet's boundary
against the world's audio, this keeps the operator's record of their own commitments —
Tally's half of the governance seat (KB 0E8C90C0), the same tamper-evident discipline
turned to face the human instead of the fleet.

Three disciplines, each the outward image of one the fleet already runs:
  1. RECEIPT-NOT-RECORDING — store the commitment FACT (title / when / who), never the
     sensitive event body/notes/location. Mirror of the voice membrane's receipts.
  2. STATES-NOT-DELETIONS — a cancelled event is a WITHDRAWN state, a moved event keeps its
     old time in history. Nothing is deleted. Mirror of FRANK / the envelope registry.
  3. NO NEW AUTHORITY — the ledger never writes the calendar. A proposed mutation ("cancel
     my 3pm") routes through the existing SAFE gate; a spoken or typed request hits the same
     stop. The membrane is read-in; action is gated-out.

And it obeys the DEW RULE: dew_surface() is silent by default. It speaks only when the
halves disagree — a commitment imminent, two commitments in conflict, or a change the
operator has not yet acknowledged (the split-stick mismatch). A surface that speaks whenever
it can is another chatty assistant; this one is confident enough to say nothing.

Imperative-shell pattern (as with the voice controller): the real caldav/gcal client is the
injected `source` driver; all discipline and dew logic live in this deterministic core and
are unit-testable with a stub source and an explicit clock.

Scratch prototype — not wired into any product repo, no models, no network. ΔΣ=42
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import Callable, Optional, Protocol, runtime_checkable


class CommitmentState(Enum):
    ACTIVE = auto()      # a live commitment (a move keeps it ACTIVE at a new time)
    WITHDRAWN = auto()   # cancelled — the record and its history are KEPT, never deleted


@dataclass(frozen=True)
class CalendarEvent:
    """Raw event from an injected source.

    `body` is the SENSITIVE content (description / notes / location) the membrane must not
    let cross into fleet memory verbatim. The ledger reads it to derive the fact, then drops
    it — it is never stored on a Commitment.
    """
    uid: str
    title: str
    start: datetime
    end: Optional[datetime] = None
    attendees: tuple[str, ...] = ()
    body: str = ""
    cancelled: bool = False


# Fields that would turn a stored commitment / receipt into a recording of sensitive detail.
_FORBIDDEN_FACT_KEYS = frozenset({"body", "notes", "description", "location", "raw"})


@dataclass
class StateChange:
    """One appended history entry. Records the fact of a transition, never event content."""
    tick: int
    state: CommitmentState
    when: datetime          # the commitment's start AS OF this change (moves are recorded)
    reason: str = ""


@dataclass
class Commitment:
    """The retained FACT of a commitment. Deliberately carries no body/notes/location —
    receipt-not-recording is enforced by the absence of a field to hold them."""
    uid: str
    title: str
    when: datetime
    end: Optional[datetime]
    who: tuple[str, ...]
    state: CommitmentState
    acknowledged: bool
    history: list[StateChange] = field(default_factory=list)


@dataclass
class Surfacing:
    """One thing the dew rule decided is worth the operator's attention. Minimal by design."""
    kind: str                 # "imminent" | "conflict" | "mismatch"
    uids: tuple[str, ...]
    when: datetime
    fact: str                 # title + time only — never the sensitive body


@runtime_checkable
class CalendarSource(Protocol):
    """Read-only ingest contract for a real calendar (caldav / gcal).

    fetch() returns the current events. There is deliberately NO create/update/delete here:
    the membrane ingests read-only, and mutations are proposals routed through the SAFE gate,
    never a direct ledger→calendar write. A real adapter (calendar_source.CalDavSource) fills
    body/attendees from live data; the ledger drops body at ingest regardless.
    """

    def fetch(self) -> list[CalendarEvent]: ...


class StubCalendarSource:
    """Deterministic synthetic source. No write methods — the read-only contract by example."""

    def __init__(self, events: Optional[list[CalendarEvent]] = None):
        self._events = list(events or [])

    def fetch(self) -> list[CalendarEvent]:
        return list(self._events)

    def set_events(self, events: list[CalendarEvent]) -> None:
        self._events = list(events)


class Refused(Exception):
    """Raised by the SAFE gate to refuse a proposed calendar mutation."""


@dataclass
class DewConfig:
    lead: timedelta = timedelta(minutes=15)   # how soon counts as "imminent"


class CommitmentLedger:
    """The deterministic core. Drive it with ingest() and read it with dew_surface(now)."""

    def __init__(
        self,
        *,
        source: CalendarSource,
        config: Optional[DewConfig] = None,
        gate_fn: Optional[Callable[[str, Commitment], bool]] = None,
    ):
        self.source = source
        self.cfg = config or DewConfig()
        # SAFE gate for any proposed mutation. Default DENIES — fail-closed, no new authority.
        self.gate_fn = gate_fn or (lambda action, commitment: False)
        self.commitments: dict[str, Commitment] = {}
        self.receipts: list[dict] = []
        self._tick = 0

    # ---- receipts: the fact, never the content ----
    def _receipt(self, event: str, **meta) -> None:
        leaked = _FORBIDDEN_FACT_KEYS & meta.keys()
        if leaked:
            raise AssertionError(f"receipt {event!r} would leak content via {sorted(leaked)}")
        self.receipts.append({"tick": self._tick, "event": event, **meta})

    # ---- ingest: read-only reconcile of the source against the ledger ----
    def ingest(self) -> None:
        self._tick += 1
        for ev in self.source.fetch():
            self._ingest_one(ev)

    def _ingest_one(self, ev: CalendarEvent) -> None:
        existing = self.commitments.get(ev.uid)
        if existing is None:
            state = CommitmentState.WITHDRAWN if ev.cancelled else CommitmentState.ACTIVE
            # First sight is the baseline — the calendar IS the operator's record, so a
            # freshly-seen live event is acknowledged; a first-seen cancellation is not.
            c = Commitment(
                uid=ev.uid, title=ev.title, when=ev.start, end=ev.end,
                who=tuple(ev.attendees), state=state,
                acknowledged=not ev.cancelled,
            )
            c.history.append(StateChange(self._tick, state, ev.start,
                                         "created" if not ev.cancelled else "first-seen cancelled"))
            self.commitments[ev.uid] = c
            self._receipt("ingest", uid=ev.uid, state=state.name)  # NB: no body
            return
        # cancellation
        if ev.cancelled and existing.state is not CommitmentState.WITHDRAWN:
            existing.state = CommitmentState.WITHDRAWN
            existing.acknowledged = False
            existing.history.append(StateChange(self._tick, CommitmentState.WITHDRAWN,
                                                existing.when, "cancelled"))
            self._receipt("withdraw", uid=ev.uid)
            return
        # reschedule (kept ACTIVE; old time preserved in history)
        if not ev.cancelled and ev.start != existing.when:
            old = existing.when
            existing.when = ev.start
            existing.end = ev.end
            existing.state = CommitmentState.ACTIVE
            existing.acknowledged = False
            existing.history.append(StateChange(self._tick, CommitmentState.ACTIVE, ev.start,
                                                f"moved from {old.isoformat()}"))
            self._receipt("move", uid=ev.uid)
            return
        # unchanged → no-op

    def acknowledge(self, uid: str) -> None:
        """Operator has seen the change — the halves match again. Recorded, not erased."""
        c = self.commitments.get(uid)
        if c is None:
            return
        self._tick += 1
        c.acknowledged = True
        c.history.append(StateChange(self._tick, c.state, c.when, "acknowledged"))
        self._receipt("acknowledge", uid=uid)

    # ---- the dew rule: silence unless the halves disagree ----
    def dew_surface(self, now: datetime) -> list[Surfacing]:
        out: list[Surfacing] = []
        active = [c for c in self.commitments.values() if c.state is CommitmentState.ACTIVE]
        # imminent — an active commitment starting within the lead window
        for c in active:
            if timedelta(0) <= (c.when - now) <= self.cfg.lead:
                out.append(Surfacing("imminent", (c.uid,), c.when, self._fact(c)))
        # conflict — two active commitments whose intervals overlap
        timed = sorted([c for c in active if c.end is not None], key=lambda c: c.when)
        for i in range(len(timed)):
            for j in range(i + 1, len(timed)):
                a, b = timed[i], timed[j]
                if a.when < b.end and b.when < a.end:
                    out.append(Surfacing("conflict", (a.uid, b.uid), max(a.when, b.when),
                                         f"{self._fact(a)} vs {self._fact(b)}"))
        # mismatch — a change the operator has not acknowledged (the split-stick disagrees)
        for c in self.commitments.values():
            if not c.acknowledged:
                out.append(Surfacing("mismatch", (c.uid,), c.when, self._fact(c)))
        return out

    @staticmethod
    def _fact(c: Commitment) -> str:
        return f"{c.title} @ {c.when.isoformat()}"   # title + time; never the body

    # ---- action: gated-out, never a direct write ----
    def propose_action(self, uid: str, action: str) -> bool:
        """Route a proposed mutation through the SAFE gate. The ledger NEVER writes the
        calendar itself — a spoken or typed 'cancel my 3pm' hits this same stop. Even an
        allowed action is executed by the gated source adapter, not here."""
        c = self.commitments.get(uid)
        if c is None:
            return False
        self._tick += 1
        try:
            allowed = bool(self.gate_fn(action, c))
        except Refused:
            allowed = False
        self._receipt("propose_action", uid=uid, action=action, allowed=allowed)
        return allowed
```

### A.2 — `calendar_source.py` (real adapter, guarded imports)

```python
"""
calendar_source.py — real CalendarSource adapters for the Commitment Membrane (drop-in).

The pure-script core (commitment_ledger.py) owns the read-only CalendarSource contract and a
synthetic StubCalendarSource. This module holds the REAL adapters. Their dependency (`caldav`)
is imported lazily inside the constructor, so importing this module stays dependency-free —
only *constructing* an adapter pulls the dep in.

Wiring, once you pick a provider:

    from commitment_ledger import CommitmentLedger, DewConfig
    from calendar_source import CalDavSource
    src = CalDavSource(url="https://caldav.fastmail.com/…", username=…, password=…)
    ledger = CommitmentLedger(source=src, gate_fn=safe_gate)
    ledger.ingest()
    for s in ledger.dew_surface(now):
        ...

The contract is READ-ONLY by design (fetch only). A cancel/reschedule is a proposal routed
through CommitmentLedger.propose_action → the SAFE gate, never a direct write from here.
Google-calendar users: swap CalDavSource for a gcal-sync-backed adapter against the same
`fetch() -> list[CalendarEvent]` contract; the ledger does not change.

Design: willow/design/willow-commitment-membrane.md · mirror of wake_gate.py · ΔΣ=42
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from commitment_ledger import CalendarEvent


class CalDavSource:
    """Read-only CalendarSource over any RFC-4791 server (iCloud / Nextcloud / Fastmail).

    fetch() pulls events in a window and maps each to a CalendarEvent. The event body/notes
    ARE read here (a real server returns them), but the ledger drops them at ingest — the
    membrane's receipt-not-recording rule does not depend on the adapter withholding them.
    """

    def __init__(
        self,
        url: str,
        *,
        username: str,
        password: str,
        calendar_name: Optional[str] = None,
        window_days: int = 14,
    ):
        import caldav  # lazy: only needed when actually constructed

        self._client = caldav.DAVClient(url=url, username=username, password=password)
        self._calendar_name = calendar_name
        self._window_days = window_days

    def fetch(self) -> list[CalendarEvent]:
        from datetime import timedelta

        principal = self._client.principal()
        calendars = principal.calendars()
        if self._calendar_name:
            calendars = [c for c in calendars if c.name == self._calendar_name]
        start = datetime.utcnow()
        end = start + timedelta(days=self._window_days)
        out: list[CalendarEvent] = []
        for cal in calendars:
            for ev in cal.search(start=start, end=end, event=True, expand=True):
                vobj = ev.vobject_instance.vevent
                uid = str(getattr(vobj, "uid", ev.url).value)
                title = str(getattr(vobj, "summary", "").value) if hasattr(vobj, "summary") else ""
                dtstart = vobj.dtstart.value
                dtend = vobj.dtend.value if hasattr(vobj, "dtend") else None
                status = str(getattr(vobj, "status", "").value).upper() if hasattr(vobj, "status") else ""
                attendees = tuple(
                    str(a.value) for a in getattr(vobj, "attendee_list", [])
                )
                body = str(getattr(vobj, "description", "").value) if hasattr(vobj, "description") else ""
                out.append(CalendarEvent(
                    uid=uid, title=title, start=dtstart, end=dtend,
                    attendees=attendees, body=body, cancelled=(status == "CANCELLED"),
                ))
        return out


class GCalSyncSource:
    """Placeholder for a Google-Calendar adapter (gcal-sync / local-store sync). Implement
    against the same read-only fetch() contract and swap it in; the ledger does not change.
    Not wired yet; raises so a premature swap fails loudly rather than silently no-ops."""

    def __init__(self, *args, **kwargs):
        raise NotImplementedError(
            "Google Calendar adapter not wired — implement fetch() -> list[CalendarEvent]"
        )
```

### A.3 — `test_commitment_ledger.py` (10 membrane-invariant tests, all passing)

```python
"""
test_commitment_ledger.py — membrane-invariant tests for the Commitment Membrane skeleton.

Mirrors the voice suite: each test asserts one discipline of the outward membrane, driven by
synthetic events and an explicit clock. No network, no models.
Run: python3 -m unittest test_commitment_ledger -v
"""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from commitment_ledger import (
    CalendarEvent,
    Commitment,
    CommitmentLedger,
    CommitmentState,
    DewConfig,
    StubCalendarSource,
)

BASE = datetime(2026, 7, 20, 9, 0, 0)   # a fixed Monday morning; all times relative to this


def ev(uid, minutes_from_base, dur_min=30, title="Standup", body="", cancelled=False, who=()):
    start = BASE + timedelta(minutes=minutes_from_base)
    return CalendarEvent(uid=uid, title=title, start=start,
                         end=start + timedelta(minutes=dur_min),
                         attendees=tuple(who), body=body, cancelled=cancelled)


class ReceiptNotRecording(unittest.TestCase):
    def test_sensitive_body_never_stored_or_logged(self):
        secret = "dial-in 555-9999, re: severance terms and the number"
        src = StubCalendarSource([ev("a", 120, title="1:1 w/ legal", body=secret)])
        ledger = CommitmentLedger(source=src)
        ledger.ingest()
        c = ledger.commitments["a"]
        # the fact is kept…
        self.assertEqual(c.title, "1:1 w/ legal")
        # …but the body is nowhere: no field holds it, and it is not in any receipt.
        forbidden = {"body", "notes", "description", "location", "raw"}
        self.assertEqual(set(vars(c)) & forbidden, set())
        blob = repr(c) + repr(ledger.receipts)
        self.assertNotIn(secret, blob)
        self.assertNotIn("severance", blob)


class StatesNotDeletions(unittest.TestCase):
    def test_cancel_withdraws_but_keeps_record_and_history(self):
        src = StubCalendarSource([ev("a", 120, title="Dentist")])
        ledger = CommitmentLedger(source=src)
        ledger.ingest()
        src.set_events([ev("a", 120, title="Dentist", cancelled=True)])
        ledger.ingest()
        c = ledger.commitments["a"]                 # still present — never deleted
        self.assertIn("a", ledger.commitments)
        self.assertIs(c.state, CommitmentState.WITHDRAWN)
        reasons = [h.reason for h in c.history]
        self.assertIn("created", reasons)
        self.assertIn("cancelled", reasons)

    def test_reschedule_keeps_old_time_in_history_and_stays_active(self):
        src = StubCalendarSource([ev("a", 120, title="Review")])
        ledger = CommitmentLedger(source=src)
        ledger.ingest()
        old = ledger.commitments["a"].when
        src.set_events([ev("a", 300, title="Review")])   # moved 3h later
        ledger.ingest()
        c = ledger.commitments["a"]
        self.assertIs(c.state, CommitmentState.ACTIVE)     # a move is still a live commitment
        self.assertEqual(c.when, BASE + timedelta(minutes=300))
        self.assertTrue(any(old.isoformat() in h.reason for h in c.history))  # old time preserved


class DewRuleSilence(unittest.TestCase):
    def test_silent_when_nothing_is_due(self):
        # three normal, acknowledged, non-overlapping future commitments
        src = StubCalendarSource([ev("a", 600), ev("b", 700), ev("c", 800)])
        ledger = CommitmentLedger(source=src)
        ledger.ingest()
        now = BASE                                        # hours before anything
        self.assertEqual(ledger.dew_surface(now), [], "dew spoke when nothing was due")

    def test_surfaces_imminent(self):
        src = StubCalendarSource([ev("a", 10, title="Call")])   # 10 min out
        ledger = CommitmentLedger(source=src, config=DewConfig(lead=timedelta(minutes=15)))
        ledger.ingest()
        surf = ledger.dew_surface(BASE)
        kinds = {s.kind for s in surf}
        self.assertIn("imminent", kinds)
        self.assertTrue(all("severance" not in s.fact for s in surf))

    def test_surfaces_conflict(self):
        # a and b overlap (both 10:00–10:30-ish)
        src = StubCalendarSource([ev("a", 60, dur_min=60, title="A"),
                                  ev("b", 90, dur_min=60, title="B")])
        ledger = CommitmentLedger(source=src)
        ledger.ingest()
        surf = ledger.dew_surface(BASE)
        conflicts = [s for s in surf if s.kind == "conflict"]
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(set(conflicts[0].uids), {"a", "b"})

    def test_unacknowledged_change_surfaces_then_goes_silent(self):
        src = StubCalendarSource([ev("a", 600, title="Flight")])
        ledger = CommitmentLedger(source=src)
        ledger.ingest()
        self.assertEqual(ledger.dew_surface(BASE), [])           # baseline: silent
        src.set_events([ev("a", 660, title="Flight")])           # rescheduled
        ledger.ingest()
        mism = [s for s in ledger.dew_surface(BASE) if s.kind == "mismatch"]
        self.assertEqual(len(mism), 1)                           # the change speaks once
        ledger.acknowledge("a")
        self.assertEqual([s for s in ledger.dew_surface(BASE) if s.kind == "mismatch"], [])  # then silent


class NoNewAuthority(unittest.TestCase):
    def test_default_gate_denies_and_ledger_has_no_write_path(self):
        src = StubCalendarSource([ev("a", 120)])
        ledger = CommitmentLedger(source=src)                    # default gate = deny
        ledger.ingest()
        self.assertFalse(ledger.propose_action("a", "cancel"))   # fail-closed
        # the read-only source exposes no mutation surface at all
        for m in ("create", "update", "delete", "write", "save", "put"):
            self.assertFalse(hasattr(src, m), f"read-only source leaked a {m}() method")

    def test_allowed_action_is_gated_not_a_direct_write(self):
        seen = []

        def gate(action, commitment):
            seen.append((action, commitment.uid))
            return action == "reschedule"

        src = StubCalendarSource([ev("a", 120)])
        ledger = CommitmentLedger(source=src, gate_fn=gate)
        ledger.ingest()
        self.assertTrue(ledger.propose_action("a", "reschedule"))
        self.assertFalse(ledger.propose_action("a", "delete"))
        self.assertEqual(seen, [("reschedule", "a"), ("delete", "a")])   # every action hit the gate
        # even the allowed action did not mutate the source events
        self.assertEqual(len(src.fetch()), 1)


class ReceiptHygieneWholeCycle(unittest.TestCase):
    def test_no_receipt_carries_content_across_a_full_cycle(self):
        src = StubCalendarSource([ev("a", 10, title="X", body="secret notes"),
                                  ev("b", 700, title="Y", body="more secrets")])
        ledger = CommitmentLedger(source=src, gate_fn=lambda a, c: True)
        ledger.ingest()
        ledger.propose_action("a", "cancel")
        ledger.acknowledge("a")
        src.set_events([ev("a", 40, title="X"), ev("b", 700, title="Y", cancelled=True)])
        ledger.ingest()
        forbidden = {"body", "notes", "description", "location", "raw"}
        for r in ledger.receipts:
            self.assertEqual(forbidden & r.keys(), set(), f"{r['event']} receipt leaked content")
        self.assertNotIn("secret", repr(ledger.receipts))


if __name__ == "__main__":
    unittest.main(verbosity=2)
```

*Appendix A is reference code promoted from a scratch prototype for durability, not an
authorization to build in a product repo. ΔΣ=42*

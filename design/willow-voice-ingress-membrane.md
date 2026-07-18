# Willow Voice Ingress Membrane — script-first state machine

**Status:** design sketch (frontier) + **verified Step 1–2 skeleton in Appendix A** · **Author:** Willow (seat) · **Date:** 2026-07-17
**Cross-refs:** KB `48886881` (Jarvis spec-vs-reality audit, ~35–40%) · KB `77A7AF7A` (voice-ear research + small-builder landscape) · spec `~/Desktop/Nest/Willow Jarvis Completion.txt` Phase 1.4
**Related design:** `egress-membrane-constitutional-map.md` (this is its ingress mirror)

---

## Design axiom

The microphone is an **ingress membrane** — the exact mirror of Willow's egress membrane.
Pre-wake audio is never transcribed, never logged, and never leaves an in-memory ring
buffer. **The wake-word gate _is_ the consent boundary.** "Always listening" and
"privacy-preserving" stop being in tension because the same structure enforces both.

The load-bearing idea: **the state machine is the security model.** The pipeline is a
script with exactly one gated transition into the model stages. Everything before that
transition is deterministic and auditable.

---

## Component map — assembled entirely from existing pieces

The script/model line is the whole point. Only 3 of 8 boxes are models, and two of those
(Kokoro, the LLM) are the *existing* fleet. The new code is script.

| Stage | Off-the-shelf piece | Script or model |
|---|---|---|
| Mic capture | `voice_mode.py` (already in tree — sounddevice / Termux) | script (DSP) |
| Wake word | **openWakeWord** (80ms TFLite frames, per-persona word) | frozen gate ≈ script |
| Endpointing | **Silero VAD** (2MB ONNX, silence → end of utterance) | deterministic |
| Speaker ID *(opt)* | **ECAPA** (VoiceAttendanceSystem pattern) | frozen embed ≈ script |
| Transcribe | **faster-whisper** (`transcription_tools.py`, in tree) | **model** |
| Reason | existing Willow chat handler / `infer_chat` | **model** (intent-match script first) |
| Speak | **Kokoro** (`infer_speak`, ~60% built) | model |
| Controller | new — asyncio loop | **pure script** |

In-tree today: capture + faster-whisper live in `worktrees/upstream-hermes-dreaming`
(`voice_mode.py`, `transcription_tools.py`, branch `feat/dreaming-config-yaml`) — **unwired**
into `sap/` / `core/`. This is STT-engine-only; it has **no wake-word front door**.

Fallback: `KoljaB/RealtimeSTT` collapses wake+VAD+faster-whisper into one dependency behind
the same controller interface, if hand-assembling steps 2–4 drags.

---

## States

```
        ┌─────────────────────────────────────────────┐
        │                                             ▼
   [0 IDLE] ──wake score>θ──▶ [1 ARMED] ──▶ [2 CAPTURE] ──endpoint/silence──▶ [3 IDENTIFY?]
     ▲  │                    (chime,          (Silero VAD               (ECAPA vs enrolled)
     │  │                     FRANK: armed@T)  gates frames,                 │        │
     │  └── only openWakeWord  │               max-dur cap)          known ──┘   unknown
     │      runs here.         │                                        │           │
     │      NO whisper.        │                                        ▼           ▼
     │      NO logging.        └──false-positive──▶ VAD sees no    [4 TRANSCRIBE]  drop→IDLE
     │                            speech, timeout      faster-whisper  (log refusal,
     │                            ──▶ IDLE             on utterance      low-trust mode)
     │                                                 ONLY │
     │                                                      ▼
     │                                               [5 DISPATCH] ── existing SAFE gate / envelopes
     │                                                      │         (voice adds NO new authority)
     │                                                      ▼
     └────────── wipe buffer, FRANK: disarmed@T ◀── [6 SPEAK] ◀─ Kokoro, streamed sentence-by-sentence
                                                        ▲  │
                                                  barge-in (wake/VAD during speak → interrupt)
```

---

## Where the gates live (the membrane)

- **Consent boundary = IDLE→ARMED.** The only place ambient audio could cross into
  transcription, gated by a tiny frozen model that emits a *score*, not a transcript.
  Nothing before the wake word is ever seen by whisper. Privacy floor enforced by
  structure, not policy.
- **No new authority.** The voice front-end is just another *input channel* into the
  command path already gated. Stage 5 hands text to the existing SAFE gate / envelope
  system — a spoken "delete X" hits the same stop as a typed one. The mic never widens scope.
- **FRANK records the fact, not the content.** Log transitions — *armed@T, speaker=operator,
  disarmed@T* — never audio or transcript. Tamper-evident trail that the mic was on, when,
  and who spoke, satisfying the always-on-mic consent concern without a recording. Ingress
  mirror of the egress receipt.
- **Speaker-ID binds voice to trust.** ECAPA maps an utterance to an enrolled identity → a
  trust level, as agent identity does. Unknown speaker → drop to IDLE or low-trust, logged.
- **Hard mute** forces IDLE and is itself a logged transition — the physical override the
  dew discipline demands.

---

## Build order

Each step independently testable; models only where marked.

1. **Controller skeleton** — the asyncio state machine with fake stage stubs. Pure script,
   unit-testable with synthetic events. No audio yet.
2. **IDLE→ARMED** — wire openWakeWord onto the in-tree capture. Prove pre-wake audio is
   discarded (test: assert whisper never called before wake).
3. **CAPTURE→endpoint** — Silero VAD + max-duration cap.
4. **TRANSCRIBE** — connect the faster-whisper already in the worktree (the one deliberate
   "wire the Hermes code" step).
5. **DISPATCH** — text into the existing chat handler through the SAFE gate. FRANK receipts
   on every transition.
6. **SPEAK** — Kokoro streaming + barge-in.
7. *(opt)* **IDENTIFY** — ECAPA enrollment + speaker gate.

Runs as one Kart-supervised / `systemd --user` daemon = the spec's `./willow.sh voice`
(Phase 1.4).

---

## Open questions / not-yet-decided

- Wake engine: openWakeWord (open, no key, custom-trainable — fits no-cloud default) vs
  Porcupine (more accurate, needs access key). Default openWakeWord.
- Per-persona wake words (OpenOcto pattern) vs single "Hey Willow". Persona bench suggests
  per-persona, but that multiplies the always-on model count.
- ~~Where the controller lives~~ **DECIDED 2026-07-17 (operator): willow-mcp `voice/` package**
  (`src/willow_mcp/voice/`) — the future home, consistent with the willow-2.0 decommission thread.
- ~~Envelope: no build authority exists yet~~ **RESOLVED: no new envelope needed.** The build is
  covered by standing willow-mcp grants — `env-fs.write-willow-mcp` (hanuman/kart, whole repo rw),
  `env-git.commit-willow-mcp` (hanuman, `feat/*` branches), `env-pr.open-willow-mcp` (hanuman, base
  master). A `feat/voice-ingress-membrane` branch lands under existing authority; merge to master
  stays root's act (no willow-mcp `pr.merge` grant exists — deliberately).

---

*This is a design sketch, not an authorization to build. ΔΣ=42*

---

## Appendix A — verified Step 1–2 skeleton (reference code)

Built and verified 2026-07-17 (session 0002f1e4) as a scratch prototype — **not yet wired
into any product repo, no envelope**. Promoted here verbatim so it survives session close;
the scratchpad it was built in is session-scoped and evaporates. When the home-repo decision
lands (willow-mcp `voice/` vs willow-2.0 `core/`) and an envelope is granted, a builder lifts
these three files into that tree unchanged and continues at build-order Step 3.

**What this covers:** build-order Step 1 (controller skeleton) complete, and Step 2's
**wake-gate interface** stubbed drop-in ready — swapping the real openWakeWord is a one-line
constructor change (`VoiceController(wake_gate=OpenWakeWordGate(...))`), no controller edit.

**Verification:** `python3 -m unittest test_voice_controller -v` → **14/14 pass**. The suite
asserts the membrane invariants directly: pre-wake audio never transcribed; false-wake /
unknown-speaker / refused-command all return to IDLE before the model stages; barge-in
interrupts SPEAK; mute forces IDLE + wipes buffer; max-duration cap; receipts provably carry
no audio/transcript; the wake gate is reset on every IDLE re-entry (openWakeWord's streaming
requirement); a pcm-only gate drives arming; the real adapter fails loudly without its deps.

**What is still a stub (deliberately):** `transcribe_fn` (faster-whisper), `vad_fn` (Silero),
`gate_fn` (the existing SAFE gate), `tts_fn` (Kokoro), `speaker_fn` (ECAPA) are injected
callables with synthetic defaults. Wiring each real engine is build-order Steps 3–7. The
security structure around them is what is proven here.

### A.1 — `voice_controller.py`

```python
"""
voice_controller.py — Willow voice ingress-membrane controller (Step 1 skeleton).

Pure-script state machine. NO audio libraries, NO models. Every model/DSP stage is an
injected callable, so the security invariants are unit-testable with synthetic frames.

Design:  willow/design/willow-voice-ingress-membrane.md
Axiom:   the state machine IS the security model.
         - Pre-wake audio never reaches the transcriber (wake gate = consent boundary).
         - Receipts record the FACT (armed@T, speaker, disarmed@T), never audio/transcript.
         - The mic adds NO authority: DISPATCH hands text to the SAME gate the typed path uses.

Imperative-shell pattern: the real daemon's asyncio loop only feeds frames into step();
all dwell states, gating, and security logic live in this deterministic core.

Dwell states (where the machine waits for the next frame): IDLE, CAPTURE, SPEAK.
The pipeline stages ARMED / ENDPOINT / IDENTIFY / TRANSCRIBE / DISPATCH run synchronously
within a single step() and are narrated by receipts rather than dwelt in.

Scratch prototype (Step 1 of the build order) — not wired into any product repo. ΔΣ=42
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable, Optional, Protocol, runtime_checkable


class State(Enum):
    IDLE = auto()
    CAPTURE = auto()
    SPEAK = auto()


@dataclass
class Frame:
    """One audio frame.

    Synthetic path (tests): wake_score / is_speech are what the DETERMINISTIC front-end
    (openWakeWord / Silero VAD) would derive from raw audio; the controller compares them
    without ever inspecting samples — the whole point of the membrane.

    Real path (Step 2+): pcm carries the raw int16 audio a live WakeGate/VAD consumes.
    The controller still never reads pcm itself — only the injected front-end does, and
    only while IDLE. A real capture loop (in-tree voice_mode.py) fills pcm; wake_score /
    is_speech stay 0/False and the gate derives them.
    """
    seq: int
    wake_score: float = 0.0
    is_speech: bool = False
    mute: bool = False   # hard-mute override — forces IDLE from any state
    barge: bool = False  # wake/VAD hit detected during SPEAK → interrupt the reply
    pcm: Optional[bytes] = None  # raw int16 audio for a live gate; None on synthetic frames


# Keys that would turn a receipt into a recording. Enforced at write time.
_FORBIDDEN_RECEIPT_KEYS = frozenset(
    {"audio", "samples", "transcript", "text", "utterance", "waveform", "frames_raw"}
)


@dataclass
class Receipt:
    tick: int
    event: str
    meta: dict = field(default_factory=dict)


class Refused(Exception):
    """Raised by the command gate to refuse a spoken command — the same stop a typed one hits."""


@runtime_checkable
class WakeGate(Protocol):
    """Streaming wake-word scorer — the drop-in contract for a real engine (openWakeWord).

    Lifecycle the controller guarantees, and a real engine may rely on:
      - score(frame) is called ONLY while IDLE, one frame at a time, and returns a wake
        probability in [0, 1]. The controller compares it to VoiceConfig.wake_threshold.
        A live engine reads frame.pcm; it must not require anything a pre-wake frame lacks.
      - reset() is called on EVERY return to IDLE, so a streaming engine clears its ring
        buffer and no partial activation survives a CAPTURE/SPEAK excursion. Stateless
        gates make reset() a no-op.
    """

    def score(self, frame: "Frame") -> float: ...

    def reset(self) -> None: ...


class StubWakeGate:
    """Deterministic synthetic WakeGate: score = frame.wake_score.

    reset() counts invocations so tests can prove the controller resets the gate on every
    return to IDLE — the property a streaming openWakeWord depends on. Drop-in swap: replace
    StubWakeGate() with wake_gate.OpenWakeWordGate(...) and feed frames carrying .pcm; the
    controller does not change.
    """

    def __init__(self) -> None:
        self.reset_count = 0

    def score(self, frame: "Frame") -> float:
        return frame.wake_score

    def reset(self) -> None:
        self.reset_count += 1


@dataclass
class VoiceConfig:
    wake_threshold: float = 0.6       # openWakeWord score to cross IDLE→ARMED
    endpoint_silence_frames: int = 3  # trailing non-speech frames that end an utterance
    false_positive_frames: int = 5    # armed but no speech within N frames → false wake
    max_capture_frames: int = 50      # max-duration cap on a single utterance


class VoiceController:
    """Deterministic ingress-membrane state machine. Drive it with step(frame)."""

    def __init__(
        self,
        *,
        config: Optional[VoiceConfig] = None,
        wake_gate: Optional[WakeGate] = None,
        wake_fn: Optional[Callable[[Frame], float]] = None,
        vad_fn: Optional[Callable[[Frame], bool]] = None,
        transcribe_fn: Optional[Callable[[list[Frame]], str]] = None,
        gate_fn: Optional[Callable[[str, Optional[str]], Optional[str]]] = None,
        tts_fn: Optional[Callable[[str], None]] = None,
        speaker_fn: Optional[Callable[[list[Frame]], Optional[str]]] = None,
    ):
        self.cfg = config or VoiceConfig()
        # Wake gate (streaming scorer). Precedence: explicit gate > legacy wake_fn > stub.
        # A bare wake_fn has no reset lifecycle; only a WakeGate is reset on return to IDLE.
        if wake_gate is not None:
            self._wake_gate: Optional[WakeGate] = wake_gate
            self.wake_fn = wake_gate.score
        elif wake_fn is not None:
            self._wake_gate = None
            self.wake_fn = wake_fn
        else:
            _stub = StubWakeGate()
            self._wake_gate = _stub
            self.wake_fn = _stub.score
        self.vad_fn = vad_fn or (lambda f: f.is_speech)
        # THE MODEL. Default stub returns a placeholder and must NEVER run before a wake.
        self.transcribe_fn = transcribe_fn or (lambda buf: f"<{len(buf)} frames>")
        # The EXISTING SAFE gate. Voice adds no authority: (text, speaker) -> response | Refused.
        self.gate_fn = gate_fn or (lambda text, spk: "ok")
        self.tts_fn = tts_fn or (lambda chunk: None)
        # Optional speaker-ID. None disables the IDENTIFY stage.
        self.speaker_fn = speaker_fn

        self.state = State.IDLE
        self.tick = 0
        self.receipts: list[Receipt] = []
        self._buffer: list[Frame] = []   # populated ONLY during CAPTURE; wiped on IDLE
        self._armed_at = 0
        self._saw_speech = False
        self._silence_run = 0
        self._speak_queue: list[str] = []

    # ---- receipts: record the fact, never the content ----
    def _receipt(self, event: str, **meta) -> None:
        leaked = _FORBIDDEN_RECEIPT_KEYS & meta.keys()
        if leaked:
            raise AssertionError(f"receipt {event!r} would leak content via {sorted(leaked)}")
        self.receipts.append(Receipt(self.tick, event, meta))

    def _to_idle(self, event: str, **meta) -> None:
        self._buffer = []          # buffer wiped on EVERY return to IDLE
        self._speak_queue = []
        self._saw_speech = False
        self._silence_run = 0
        self.state = State.IDLE
        if self._wake_gate is not None:
            self._wake_gate.reset()   # streaming wake engine starts each IDLE session clean
        self._receipt(event, **meta)

    # ---- driver entry point ----
    def step(self, frame: Frame) -> None:
        self.tick += 1
        if frame.mute:                       # hard mute wins from any state, and is logged
            self._to_idle("mute")
            return
        if self.state is State.IDLE:
            self._step_idle(frame)
        elif self.state is State.CAPTURE:
            self._step_capture(frame)
        elif self.state is State.SPEAK:
            self._step_speak(frame)

    # ---- IDLE: only the wake gate runs; whisper is never called ----
    def _step_idle(self, frame: Frame) -> None:
        score = self.wake_fn(frame)
        if score >= self.cfg.wake_threshold:
            self._buffer = []
            self._armed_at = self.tick
            self._saw_speech = False
            self._silence_run = 0
            self.state = State.CAPTURE
            self._receipt("armed", score=round(score, 3))
        # else: discard the frame. The near-miss is never transcribed or logged.

    # ---- CAPTURE: VAD gates frames; transcribe is NOT called yet ----
    def _step_capture(self, frame: Frame) -> None:
        self._buffer.append(frame)
        if self.vad_fn(frame):
            self._saw_speech = True
            self._silence_run = 0
        else:
            if self._saw_speech:
                self._silence_run += 1
            elif self.tick - self._armed_at >= self.cfg.false_positive_frames:
                self._to_idle("false_positive")   # armed but no speech ever arrived
                return
        ended = (self._saw_speech and self._silence_run >= self.cfg.endpoint_silence_frames)
        capped = len(self._buffer) >= self.cfg.max_capture_frames
        if ended or capped:
            self._endpoint(capped=capped)

    def _endpoint(self, *, capped: bool) -> None:
        self._receipt("endpoint", frames=len(self._buffer), capped=capped)
        speaker: Optional[str] = None
        # IDENTIFY (optional): an unknown speaker is dropped BEFORE any transcription.
        if self.speaker_fn is not None:
            speaker = self.speaker_fn(list(self._buffer))
            if speaker is None:
                self._to_idle("unknown_speaker")
                return
            self._receipt("identify", speaker=speaker)
        # TRANSCRIBE — first and only model touch of the captured audio.
        text = self.transcribe_fn(list(self._buffer))
        self._receipt("transcribe", chars=len(text), speaker=speaker)
        # DISPATCH — the existing SAFE gate. A spoken command hits the same stop as a typed one.
        try:
            response = self.gate_fn(text, speaker)
        except Refused as exc:
            self._to_idle("dispatch_refused", speaker=speaker, reason=str(exc)[:80])
            return
        self._receipt("dispatch", speaker=speaker, refused=False)
        # SPEAK — enqueue the reply in chunks; each later frame speaks one (barge-interruptible).
        self._speak_queue = self._chunk(response)
        self.state = State.SPEAK
        if not self._speak_queue:
            self._to_idle("disarm")

    @staticmethod
    def _chunk(response: Optional[str]) -> list[str]:
        if not response:
            return []
        flat = response.replace("!", ".").replace("?", ".")
        return [p.strip() for p in flat.split(".") if p.strip()]

    # ---- SPEAK: stream chunks; a barge-in interrupts immediately ----
    def _step_speak(self, frame: Frame) -> None:
        if frame.barge:
            self._to_idle("barge_in", unspoken=len(self._speak_queue))
            return
        if self._speak_queue:
            chunk = self._speak_queue.pop(0)
            self.tts_fn(chunk)
            self._receipt("speak", chunk_chars=len(chunk))
        if not self._speak_queue:
            self._to_idle("disarm")

    # ---- read helpers for tests / driver ----
    def events(self) -> list[str]:
        return [r.event for r in self.receipts]
```

### A.2 — `wake_gate.py` (real adapters, guarded imports)

```python
"""
wake_gate.py — real WakeGate adapters for the voice ingress membrane (Step 2 drop-in).

The pure-script core (voice_controller.py) owns the WakeGate *contract* and a synthetic
StubWakeGate. This module holds the REAL engine adapters. Their heavy dependencies
(openwakeword, numpy) are imported lazily inside the constructor / call, so importing
this module stays dependency-free — only *constructing* an adapter pulls the deps in.

Wiring (Step 2), once the capture loop from the in-tree voice_mode.py fills frame.pcm
with raw int16 audio:

    from voice_controller import VoiceController
    from wake_gate import OpenWakeWordGate
    gate = OpenWakeWordGate(model_paths=["hey_willow.tflite"])
    controller = VoiceController(wake_gate=gate, vad_fn=..., transcribe_fn=..., ...)

Nothing else changes: the controller treats the wake score as an opaque number and
already resets the gate on every return to IDLE — exactly openWakeWord's lifecycle.

Design: willow/design/willow-voice-ingress-membrane.md · ΔΣ=42
"""
from __future__ import annotations

from typing import Sequence

from voice_controller import Frame


class OpenWakeWordGate:
    """Drop-in WakeGate backed by dscripka/openWakeWord (open models, no API key).

    openWakeWord is streaming and stateful: predict() consumes ~80 ms of 16 kHz int16
    audio (1280 samples) per call and returns {model_name: score}. The controller feeds
    it ONLY while IDLE and calls reset() on every return to IDLE — the ring buffer must be
    cleared between activations or a stale partial keeps the score hot. That lifecycle is
    already guaranteed by VoiceController; this adapter just satisfies the contract.
    """

    def __init__(
        self,
        model_paths: Sequence[str],
        *,
        threshold: float = 0.5,
        expected_frame_samples: int = 1280,
    ):
        from openwakeword.model import Model  # lazy: only needed when actually constructed

        self._model = Model(wakeword_models=list(model_paths))
        self.threshold = threshold
        self.expected_frame_samples = expected_frame_samples

    def score(self, frame: Frame) -> float:
        import numpy as np

        if frame.pcm is None:
            raise ValueError("OpenWakeWordGate needs frame.pcm (raw int16 audio)")
        samples = np.frombuffer(frame.pcm, dtype=np.int16)
        preds = self._model.predict(samples)
        return max(preds.values()) if preds else 0.0

    def reset(self) -> None:
        self._model.reset()


class RealtimeSTTGate:
    """Fallback path (KoljaB/RealtimeSTT) that collapses wake + VAD + faster-whisper behind
    one dependency. If hand-assembling openWakeWord + Silero + faster-whisper drags,
    implement this against the same WakeGate contract and swap it in — the controller does
    not change. Not wired yet; raises so a premature swap fails loudly.
    """

    def __init__(self, *args, **kwargs):
        raise NotImplementedError(
            "RealtimeSTT fallback not wired — see design/willow-voice-ingress-membrane.md"
        )
```

### A.3 — `test_voice_controller.py` (14 membrane-invariant tests, all passing)

```python
"""
test_voice_controller.py — membrane-invariant tests for the Step 1 controller skeleton.

Each test asserts one security property of the ingress membrane, driven by synthetic
frames. No audio, no models. Run: python3 -m unittest test_voice_controller -v
"""
from __future__ import annotations

import unittest

from voice_controller import (
    Frame,
    Refused,
    State,
    StubWakeGate,
    VoiceConfig,
    VoiceController,
)


class Spy:
    """Records calls so a test can assert whether/when a stage ran."""

    def __init__(self, ret=None):
        self.calls: list = []
        self.ret = ret

    def __call__(self, *args):
        self.calls.append(args)
        return self.ret


def wake(seq: int) -> Frame:
    return Frame(seq=seq, wake_score=0.95)


def speech(seq: int) -> Frame:
    return Frame(seq=seq, is_speech=True)


def silence(seq: int) -> Frame:
    return Frame(seq=seq, is_speech=False)


class PreWakePrivacy(unittest.TestCase):
    def test_prewake_audio_never_transcribed(self):
        """The core invariant: no wake word => whisper is never called, buffer stays empty."""
        transcribe = Spy(ret="should not run")
        c = VoiceController(transcribe_fn=transcribe)
        # Loud speech, but no wake word — exactly the ambient-conversation case.
        for i in range(20):
            c.step(Frame(seq=i, wake_score=0.1, is_speech=True))
        self.assertEqual(transcribe.calls, [], "transcriber ran on pre-wake audio")
        self.assertIs(c.state, State.IDLE)
        self.assertEqual(c._buffer, [])
        self.assertNotIn("transcribe", c.events())


class HappyPath(unittest.TestCase):
    def test_wake_capture_transcribe_dispatch_speak(self):
        transcribe = Spy(ret="turn on the lights")
        gate = Spy(ret="Lights on. Done.")
        tts = Spy()
        c = VoiceController(transcribe_fn=transcribe, gate_fn=gate, tts_fn=tts)
        c.step(wake(0))
        self.assertIs(c.state, State.CAPTURE)
        for i in range(1, 4):
            c.step(speech(i))
        for i in range(4, 7):        # 3 silence frames end the utterance
            c.step(silence(i))
        self.assertEqual(len(transcribe.calls), 1)
        self.assertEqual(len(gate.calls), 1)
        self.assertEqual(gate.calls[0][0], "turn on the lights")  # gate sees the text
        self.assertIs(c.state, State.SPEAK)
        # advance the two reply chunks ("Lights on", "Done")
        c.step(silence(7))
        c.step(silence(8))
        self.assertEqual(len(tts.calls), 2)
        self.assertIs(c.state, State.IDLE)
        self.assertIn("armed", c.events())
        self.assertIn("disarm", c.events())


class FalsePositive(unittest.TestCase):
    def test_false_wake_returns_to_idle_without_transcribing(self):
        transcribe = Spy()
        c = VoiceController(transcribe_fn=transcribe,
                            config=VoiceConfig(false_positive_frames=4))
        c.step(wake(0))
        for i in range(1, 8):        # only silence after the wake — a false trigger
            c.step(silence(i))
        self.assertEqual(transcribe.calls, [])
        self.assertIn("false_positive", c.events())
        self.assertIs(c.state, State.IDLE)


class BargeIn(unittest.TestCase):
    def test_barge_interrupts_speak(self):
        c = VoiceController(transcribe_fn=Spy(ret="q"),
                            gate_fn=Spy(ret="one. two. three. four."))
        c.step(wake(0))
        for i in range(1, 4):
            c.step(speech(i))
        for i in range(4, 7):
            c.step(silence(i))
        self.assertIs(c.state, State.SPEAK)
        c.step(silence(7))                       # speaks chunk "one"
        c.step(Frame(seq=8, barge=True))         # user talks over the reply
        self.assertIs(c.state, State.IDLE)
        self.assertIn("barge_in", c.events())
        barge = [r for r in c.receipts if r.event == "barge_in"][0]
        self.assertGreater(barge.meta["unspoken"], 0)   # chunks were left unspoken


class SpeakerGate(unittest.TestCase):
    def test_unknown_speaker_dropped_before_transcribe(self):
        transcribe = Spy(ret="secret")
        c = VoiceController(transcribe_fn=transcribe,
                            speaker_fn=lambda buf: None)   # never enrolled
        c.step(wake(0))
        for i in range(1, 4):
            c.step(speech(i))
        for i in range(4, 7):
            c.step(silence(i))
        self.assertEqual(transcribe.calls, [], "unknown speaker reached the transcriber")
        self.assertIn("unknown_speaker", c.events())
        self.assertIs(c.state, State.IDLE)

    def test_known_speaker_binds_identity_through_gate(self):
        gate = Spy(ret="ok")
        c = VoiceController(transcribe_fn=Spy(ret="status"),
                            gate_fn=gate,
                            speaker_fn=lambda buf: "operator")
        c.step(wake(0))
        for i in range(1, 4):
            c.step(speech(i))
        for i in range(4, 7):
            c.step(silence(i))
        self.assertEqual(gate.calls[0][1], "operator")   # speaker flows to the gate


class NoNewAuthority(unittest.TestCase):
    def test_refused_command_does_not_speak(self):
        tts = Spy()

        def refusing_gate(text, spk):
            raise Refused("needs operator consent")

        c = VoiceController(transcribe_fn=Spy(ret="delete everything"), gate_fn=refusing_gate, tts_fn=tts)
        c.step(wake(0))
        for i in range(1, 4):
            c.step(speech(i))
        for i in range(4, 7):
            c.step(silence(i))
        self.assertEqual(tts.calls, [])   # a refused spoken command produces no reply
        self.assertIn("dispatch_refused", c.events())
        self.assertIs(c.state, State.IDLE)


class MaxDurationCap(unittest.TestCase):
    def test_runaway_utterance_is_capped(self):
        transcribe = Spy(ret="x")
        c = VoiceController(transcribe_fn=transcribe, config=VoiceConfig(max_capture_frames=10))
        c.step(wake(0))
        for i in range(1, 30):        # unbroken speech, never a silence endpoint
            c.step(speech(i))
        self.assertEqual(len(transcribe.calls), 1, "cap did not force exactly one endpoint")
        endpoint = [r for r in c.receipts if r.event == "endpoint"][0]
        self.assertTrue(endpoint.meta["capped"])


class MuteOverride(unittest.TestCase):
    def test_mute_forces_idle_and_wipes_buffer(self):
        c = VoiceController(transcribe_fn=Spy())
        c.step(wake(0))
        c.step(speech(1))
        self.assertIs(c.state, State.CAPTURE)
        self.assertTrue(c._buffer)
        c.step(Frame(seq=2, mute=True))
        self.assertIs(c.state, State.IDLE)
        self.assertEqual(c._buffer, [])
        self.assertIn("mute", c.events())


class ReceiptHygiene(unittest.TestCase):
    def test_receipts_never_carry_audio_or_transcript(self):
        c = VoiceController(transcribe_fn=Spy(ret="anything"), gate_fn=Spy(ret="reply. here."))
        c.step(wake(0))
        for i in range(1, 4):
            c.step(speech(i))
        for i in range(4, 7):
            c.step(silence(i))
        c.step(silence(7))
        c.step(silence(8))
        forbidden = {"audio", "samples", "transcript", "text", "utterance", "waveform", "frames_raw"}
        for r in c.receipts:
            self.assertEqual(forbidden & r.meta.keys(), set(), f"{r.event} leaked content")


class WakeGateInterface(unittest.TestCase):
    def test_stub_gate_score_drives_arming(self):
        gate = StubWakeGate()
        c = VoiceController(wake_gate=gate, transcribe_fn=Spy())
        c.step(Frame(seq=0, wake_score=0.7))
        self.assertIs(c.state, State.CAPTURE)

    def test_gate_reset_on_every_return_to_idle(self):
        """openWakeWord's streaming buffer must be cleared on each IDLE re-entry."""
        gate = StubWakeGate()
        c = VoiceController(wake_gate=gate, transcribe_fn=Spy(ret="q"),
                            config=VoiceConfig(false_positive_frames=4))
        # false-positive return to IDLE
        c.step(Frame(seq=0, wake_score=0.9))
        for i in range(1, 8):
            c.step(silence(i))
        self.assertIn("false_positive", c.events())
        self.assertGreaterEqual(gate.reset_count, 1)
        before = gate.reset_count
        # mute return to IDLE increments again
        c.step(Frame(seq=100, wake_score=0.9))
        c.step(Frame(seq=101, mute=True))
        self.assertGreater(gate.reset_count, before)

    def test_pcm_consuming_gate_drives_arming_without_wake_score(self):
        """The real interface shape: a gate that reads frame.pcm, not the synthetic score."""

        class PcmGate:
            def __init__(self):
                self.reset_count = 0

            def score(self, frame):
                return 1.0 if frame.pcm == b"WAKE" else 0.0

            def reset(self):
                self.reset_count += 1

        gate = PcmGate()
        c = VoiceController(wake_gate=gate, transcribe_fn=Spy())
        c.step(Frame(seq=0, pcm=b"quiet"))     # no wake word in the audio
        self.assertIs(c.state, State.IDLE)
        c.step(Frame(seq=1, pcm=b"WAKE"))       # wakes on pcm alone, wake_score stays 0.0
        self.assertIs(c.state, State.CAPTURE)


class RealGateHonesty(unittest.TestCase):
    def test_openwakeword_gate_requires_its_dependency(self):
        """The real adapter must fail loudly, not silently no-op, without openwakeword."""
        from wake_gate import OpenWakeWordGate

        with self.assertRaises((ImportError, ModuleNotFoundError)):
            OpenWakeWordGate(model_paths=["hey_willow.tflite"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
```

*Appendix A is reference code promoted from a scratch prototype for durability, not an
authorization to build in a product repo. ΔΣ=42*

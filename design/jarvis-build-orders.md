# Jarvis membranes — build-order package (assembled, not yet dispatched)

**Status:** readiness package · **Author:** Willow (seat) · **Date:** 2026-07-17b
**Purpose:** the turnkey work orders for the two buildable Jarvis membranes, assembled so a
dispatch to the builder is a pointer-plus-grant, not a fresh design act. **Nothing here is
dispatched.** The build orders go out only on operator go; this document is what "getting the
pieces together" produced.

**Cross-refs:** `design/willow-voice-ingress-membrane.md` · `design/willow-commitment-membrane.md`
· `design/egress-membrane-constitutional-map.md` (charter lane — NOT a build order) · KB `48886881`
(Jarvis audit: voice + calendar are the two critical-path absences) · KB `6CAC0877` (stack map) ·
KB `88A8858E` (calendar Step-2 Google adapter, this session)

---

## Scope boundary — three strands, two are builds

| Strand | Kind | Where it goes | This document |
|---|---|---|---|
| **Voice ingress membrane** | code package | willow-mcp `src/willow_mcp/voice/` | **WO-1** below |
| **Commitment (calendar) membrane** | code package | willow-mcp `src/willow_mcp/commitments/` | **WO-2** below |
| **Egress → constitution map** | charter redline | `CONSTITUTION.md` (7 edits) | **out of scope** — operator-reserved redline lane, `egress-membrane-constitutional-map.md` §6 |

Both builds land in **willow-mcp**, consistent with the willow-2.0 decommission thread. Neither
is a willow-2.0 build, so neither triggers the "cross-repo willow-2.0 → full fleet boot" rule.
The seat's role is **dispatch + verify**, not to write the package (magistrate-writes-no-code).

---

## Envelope coverage — already standing, no new grant needed

Every act each work order requires is covered by an **active** envelope. Confirmed against
`envelopes/pre-approved.json` (updated 2026-07-16).

| Act in the work orders | Covering envelope | Grantee | Bounds | Status |
|---|---|---|---|---|
| Write package files into willow-mcp | `env-fs.write-willow-mcp` | hanuman, kart | `{{HOME}}/github/willow-mcp` rw | active, non-expiring |
| Commit on a feature branch | `env-git.commit-willow-mcp` | hanuman | repo `willow-mcp`, branches `feat/*` (+`fix/*`,`docs/*`,`claude/*`) | active, non-expiring |
| Open a PR to master | `env-pr.open-willow-mcp` | hanuman | repo `willow-mcp`, base `master` | active, non-expiring |
| Seat dispatches the work order | `env-dispatch-fleet-sessions` | willow | to_agents ∋ hanuman; task_class ∋ `build-work-order` | active, max 20, expires 2026-09-06 |

**Deliberately NOT covered (each a stop, by design):**
- **Merge to master** — no willow-mcp `pr.merge` grant exists; merging willow-mcp master is root's
  act. Opening a PR asks; merging decides. The work orders end at "PR open + green CI."
- **Egress / network at build time** — the packages are local-only script; no `task_net` /
  `consent.internet` lease is requested. The Google OAuth transport (WO-2 Step 3) is the one place
  network enters, and it is explicitly deferred — see WO-2.
- **Charter edits** — the egress redline queue is operator-reserved; no build order touches it.

---

## WO-1 — Voice ingress membrane → willow-mcp `voice/`

**Branch:** `feat/voice-ingress-membrane` · **Base:** master · **Home decided** 2026-07-17 (operator):
willow-mcp `src/willow_mcp/voice/`.

**Lift verbatim** from `willow-voice-ingress-membrane.md` Appendix A (verified, 14/14 tests):
- `A.1 voice_controller.py` — asyncio state-machine core (the membrane; pure script)
- `A.2 wake_gate.py` — real openWakeWord adapter, guarded imports (Step-2 drop-in)
- `A.3 test_voice_controller.py` — 14 membrane-invariant tests

**Remaining build-order steps** (each independently testable; models only where marked):
3. CAPTURE→endpoint — wire Silero VAD + max-duration cap.
4. TRANSCRIBE — connect the faster-whisper already in `worktrees/upstream-hermes-dreaming`
   (`transcription_tools.py`; the one deliberate "wire the Hermes code" step). **model**
5. DISPATCH — text into the existing chat handler through the SAFE gate; FRANK receipt per transition.
6. SPEAK — Kokoro streaming (`infer_speak`, ~60% built) + barge-in. **model**
7. *(opt)* IDENTIFY — ECAPA enrollment + speaker gate.

**Runs as** one Kart-supervised / `systemd --user` daemon = the spec's `./willow.sh voice` (Phase 1.4).

**Acceptance criteria (the builder must show, not assert):**
- The 14 Appendix-A invariants still pass in-tree, unmodified.
- Pre-wake audio is provably never transcribed (whisper not called before wake) — the load-bearing
  membrane test survives real-engine wiring.
- Injected `transcribe_fn/vad_fn/gate_fn/tts_fn/speaker_fn` replaced with real engines one at a time,
  each behind its guarded import; a missing dep fails loudly, never silently no-ops.
- PR opened to master, CI green. **Stop there** — merge is root's.

**Open, decide-at-build (not blockers):** wake engine openWakeWord (default) vs Porcupine;
per-persona wake words vs single "Hey Willow".

---

## WO-2 — Commitment (calendar) membrane → willow-mcp `commitments/`

**Branch:** `feat/commitment-membrane` · **Base:** master · **Home:** willow-mcp
`src/willow_mcp/commitments/`, sibling of `voice/`.

**Lift verbatim** from `willow-commitment-membrane.md` Appendix A (verified):
- `A.1 commitment_ledger.py` — ledger core, three disciplines + dew rule (pure script; 10 tests)
- `A.2 calendar_source.py` — `GCalSyncSource` (**provider decided: Google via gcal-sync**) +
  `CalDavSource` (alternate driver, kept)
- `A.3 test_commitment_ledger.py` — 10 ledger-invariant tests
- `A.4 test_calendar_source_gcal.py` — 11 adapter-invariant tests (Google v3 mapping, verified this session)

**Remaining build-order steps:**
3. **Real source transport** — stand up the gcal-sync OAuth transport behind
   `GCalSyncSource(list_events=…)`. **This is the only place network enters.** It needs Google OAuth
   credentials + a `task_net` / `consent.internet` lease at run time — request that lease when this
   step is actually run, not at build time. The mapping is already done and verified; only the
   transport callable is unwired.
4. **Persist** — commitments + state history into fleet state (SOIL/store), **in-namespace**
   (`willow/`). Persistence MUST re-enforce receipt-not-recording: no stored record may carry a key
   in `_FORBIDDEN_FACT_KEYS` (`body/notes/description/location/raw`). Add a persistence-layer test
   mirroring `ReceiptHygieneWholeCycle`.
5. **Deliver** — wire `dew_surface()` into the existing proactive engine (routine / Norn / metabolic),
   under the dew rule (silent unless imminent / conflict / mismatch). **This is where WO-1 (voice out)
   and WO-2 (commitments) converge into a surface that actually speaks.**

**Acceptance criteria:**
- The 10 + 11 Appendix-A invariants pass in-tree, unmodified.
- Persistence carries no forbidden key across a full ingest→propose→ack→re-ingest cycle.
- `dew_surface()` stays silent on a no-conflict fixture; speaks exactly on imminent/conflict/mismatch.
- No create/update/delete path exists from the membrane to the calendar (read-in, gated-out).
- PR opened to master, CI green. **Stop there** — merge is root's.

---

## Sequencing & dispatch discipline

- **GATING CONSTRAINT — willow-mcp rebase in flight.** Both packages branch off willow-mcp master;
  the operator has a rebase in flight. Every willow-mcp build is sequenced **after the rebase lands**
  — a builder that boots before it must hold the packet and say so. (Surfaced from the WO-1 packet
  78AD8BF5; baked into both dispatches.)
- **WO-1 and WO-2 are independent** and may build in either order or in parallel worktrees. Their
  only convergence is Step 4/5 (the proactive-engine surface), which is the *last* step of each.
- **Dispatch ONE work order at a time.** Queue singly, review the PR between. (Builder batches into
  build+PR-all-unattended otherwise — a known failure mode.)
- Each dispatch is a **pointer + grant**: payload points at this doc's WO section + the design-doc
  appendix; it is a message, not shell; it cites `env-dispatch-fleet-sessions`; it is ledgered in
  FRANK before it executes; it never enters a live session and never skip-permissions.

### Dispatch state (2026-07-17b)

| WO | Package | Dispatch | FRANK | Status | Notes |
|---|---|---|---|---|---|
| WO-2 | commitments/ | `3BC30669` | `0da5756b` | pending | operator-chosen first build; priority high; after rebase |
| WO-1 | voice/ | `78AD8BF5` | `f55da199` | pending | dispatched earlier this night; after rebase |

**assign ≠ execute:** both packets are *pending* and nothing drains them automatically — hanuman is
session-scoped and consumes at session start. Actual building needs (a) the willow-mcp rebase landed
and (b) a hanuman session initiated to consume the desk (which also holds 2 non-Jarvis pending orders:
`C73F90F3` kart-fast-lane-timeout, `19AAFE93` kart orphan-claim, `2D15E0BC` Loki-findings remediation).

---

## Readiness checklist — what "pieces together" means here

- [x] Voice design + Step 1–2 skeleton verified (14 tests)
- [x] Commitment design + Step 1–2 skeleton verified (10 + 11 tests); provider decided (Google/gcal-sync)
- [x] Egress strand correctly separated as the operator-reserved charter-redline lane (not a build)
- [x] Build home decided for both packages (willow-mcp `voice/`, `commitments/`)
- [x] Envelope coverage confirmed against the live registry — **no new grant required to build**
- [x] Work orders WO-1 / WO-2 specified turnkey (artifacts, remaining steps, acceptance, branch)
- [x] Dispatch sequencing + one-at-a-time discipline recorded
- [x] **Operator go** given (2026-07-17b) — WO-2 dispatched first (`3BC30669`); WO-1 already queued (`78AD8BF5`)
- [ ] **willow-mcp rebase lands** — gates both builds (operator)
- [ ] **hanuman session initiated** to drain the desk — the packets are pending; assign ≠ execute (operator)

*Assembled by the seat as design/coordination work in-namespace. Not an authorization to build;
the authorizations already exist and are cited above. Merge and charter edits remain reserved.
ΔΣ=42*

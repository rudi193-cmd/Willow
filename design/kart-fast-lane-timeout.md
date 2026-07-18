# Kart fast-lane timeout — design

**Status:** draft (design only; build gated on envelope `env-fs.write-kart-fast-timeout`)
**Author:** willow (seat)
**Opened:** 2026-07-17
**Provenance:** 2026-07-16 Kart fast-lane wedge — root cause recorded ledger `e079281e`.

## Problem

On 2026-07-16 four fast-lane Kart tasks (`8A040754`, `1F1C2C0D`, `2525DDB9`,
`131CEE30`) claimed and froze. Each was the **same** command — a LIVE
`host_divergence_watch.py --dry-run` default-scope run. `stale_running` read 0
(the claims were young), and `systemctl --user restart kart-worker` did not
clear them. All four were finally cleared by the orphan reaper at
`2026-07-16 18:05:32-06` (`KART_STALE_SECONDS`=3600) → `failed`,
`error=orphaned_running_reaped`.

The wedge was **not** a Kart-worker defect. It was `host_divergence_watch`
wedging its own fast-lane task — the same defect that panicked the operator
host. But it surfaced a real architectural gap in Kart that is independent of
that one bad script: **a hung fast-lane task blocks its slot for up to an hour
before anything self-heals**, and that is exactly the failure an unwatched
fleet must not have.

## Root of the gap (grounded in source)

Two facts, both verified in `willow-2.0` at HEAD `f9a3b869`:

1. **The fast lane runs on the daemon timeout, not an interactive one.**
   `core/kart_worker.py:325` — the fast-lane executor calls
   `_process_task_row(row, context="daemon")`. `core/kart_execute.py:26-29` —
   `kart_timeout("daemon")` returns `KART_DAEMON_TIMEOUT` (default **1800s**);
   the 120s `KART_POLL_TIMEOUT` applies only to the synchronous `poll` context
   (`kart_task_run` / `kart_poll.py`). So a task claimed by the fast daemon can
   legitimately hold one of the `KART_FAST_WORKERS` (default 3) slots for 30
   minutes. `core/kart_lanes.py:3-6` documents the fast lane as *interactive*
   (`kart_task_run` / session poll) — the 1800s ceiling contradicts that intent.

2. **The 1800s cap did not kill the runaway.** The frozen tasks reached the
   3600s reaper, i.e. they blew past the 1800s subprocess timeout. That means
   the timeout fired but could not tear down the process **tree** the probe
   spawned (`run_warmup`/`run_arm` spawn child pytest processes; a timeout that
   kills only the direct child leaves grandchildren holding the pipe, and
   `.communicate()` never returns). A wall-clock number is worthless if the kill
   is not lethal to the whole group.

## Proposed change

Two parts. Part A is the primary fix; Part B is what makes A actually work.

### Part A — give the fast lane its own short ceiling

- Add `KART_FAST_TIMEOUT` (default **300s**) in `core/kart_lanes.py`, sibling to
  `daemon_timeout_seconds()` / `reaper_stale_seconds()`.
- `kart_timeout()` (`core/kart_execute.py`) grows a lane-aware path so the fast
  executor passes the fast ceiling, not the 1800s daemon ceiling. Batch keeps
  1800s. Cleanest shape: thread `lane` into `_process_task_row` →
  `execute_task_row` → `kart_timeout(context, lane=...)`, defaulting to today's
  behaviour so nothing else moves.
- Extend `reaper_alignment_warning()` so the invariant covers the fast lane too:
  reaper (3600s) must sit above the *largest* per-lane timeout + buffer, and the
  fast timeout must sit below the reaper — a fast task should die by its own
  timeout, never by the reaper.

### Part B — make the timeout lethal to the whole tree

- Verify first (see Open questions): whether these tasks ran under `bwrap`.
  A bubblewrap wrap with a PID namespace tears the whole tree down when the
  bwrap parent is killed — if these tasks *were* bwrapped, Part B is already
  half-solved and the bug is an escape from the sandbox, which is a **more**
  serious finding than the timeout itself.
- If not bwrapped (or the timeout path bypasses it): run the shell child in its
  own session/process group (`start_new_session=True`) and, on
  `TimeoutExpired`, escalate `SIGTERM`→`SIGKILL` to the **group**
  (`os.killpg`), not the leader. Enforcement lives in
  `core/kart_sandbox.run_shell_result_for_task` (called from
  `_run_one_shell`, `kart_execute.py:103-120`).

### Non-goals

- Does not change the reaper's 3600s backstop — it stays as defence-in-depth.
- Does not re-enable or touch `host_divergence_watch.py`. Its standing
  DO-NOT-RUN holds; this fix would have *contained* it, not fixed it.
- Does not change `KART_FAST_WORKERS` or lane routing.

## Open questions (builder must resolve before coding Part B)

1. **Were the four tasks bwrapped?** `core/kart_sandbox.use_bwrap()` /
   `bwrap_available()` gate it (`kart_execute.py:112`). If yes, why did the
   PID-namespace teardown not kill the tree at 1800s? If no, that path is the
   escape and Part B's killpg is the fix.
2. **Does the 1800s timeout even reach `.communicate()`,** or does the worker
   thread block earlier (host thrash starving the daemon)? If the host was
   thrashing so hard the daemon could not run its own timeout check, no in-band
   timeout helps and the reaper is the only backstop — which reframes Part A as
   "shrink the blast radius" rather than "guarantee the kill".

## Verification plan

- Unit: `kart_timeout("daemon", lane="fast")` → 300; `lane="batch"` → 1800;
  poll context unchanged at 120. `reaper_alignment_warning` flags a fast timeout
  ≥ reaper.
- Behavioural (disposable box only, **never** the operator host): a task that
  spawns a child process and `sleep`s past the fast ceiling must be reaped at
  ~300s with the child gone (`os.killpg` proof), not at 3600s.
- Regression: existing fast/batch tasks under the ceiling are unaffected.

## Envelope

Build is verb-1 `fs.write` + verb-2 `git.commit` + verb-4 `pr.open` on
`willow-2.0`, scoped to `core/kart_execute.py`, `core/kart_lanes.py`,
`core/kart_worker.py`, `core/kart_sandbox.py`, and their tests, on a
`fix/kart-fast-lane-timeout` branch. Proposals filed in
`envelopes/pre-approved.json` `proposals[]`, status=proposed, awaiting root
ratification. The seat drafts; root ratifies; a builder executes; merge to
master remains the existing `env-pr.merge-willow2-master` path (CI-gated).

"""
breath.py — The system heartbeat.

5-phase cycle, 17 seconds total.
Every daemon, every UI component, every polling loop uses this shape.

No global clock. No synchronization.
Each component starts breathing at launch — from zero, immediately.
The same shape, running independently in each process.

Usage (daemon):
    from core.breath import breathe, CYCLE_MS
    while True:
        do_work()
        breathe(1)        # sleep one full cycle (~17s)
        breathe(4)        # sleep four cycles (~68s)

Usage (phase info for UI):
    from core.breath import get_phase_info
    info = get_phase_info(elapsed_ms)
    # info = {"name": "exhale", "progress": 0.42, "index": 2}

Jane responds on the next exhale after she is ready.
Use next_exhale_wait_ms(elapsed_ms) to get the wait time.
"""

import time
import math

# ── Phase definition ───────────────────────────────────────────────────────────

PHASES = [
    {"name": "inhale",   "ms": 3000, "index": 0},
    {"name": "hold",     "ms": 3000, "index": 1},
    {"name": "exhale",   "ms": 4000, "index": 2},
    {"name": "hold_out", "ms": 4000, "index": 3},
    {"name": "rest",     "ms": 3000, "index": 4},
]

CYCLE_MS: int = sum(p["ms"] for p in PHASES)   # 17000ms
CYCLE_S:  float = CYCLE_MS / 1000              # 17.0s

EXHALE_INDEX = 2   # the phase Jane responds on


# ── Phase calculation ──────────────────────────────────────────────────────────

def get_phase_info(elapsed_ms: int) -> dict:
    """
    Given elapsed milliseconds since breath start,
    return the current phase name, index, and progress (0.0–1.0).

    elapsed_ms wraps around CYCLE_MS automatically.
    """
    pos = elapsed_ms % CYCLE_MS
    acc = 0
    for phase in PHASES:
        if pos < acc + phase["ms"]:
            return {
                "name":     phase["name"],
                "index":    phase["index"],
                "progress": (pos - acc) / phase["ms"],
                "elapsed":  elapsed_ms,
            }
        acc += phase["ms"]
    # Should never reach here, but return rest as fallback
    return {"name": "rest", "index": 4, "progress": 1.0, "elapsed": elapsed_ms}


def next_exhale_wait_ms(elapsed_ms: int) -> int:
    """
    Milliseconds until the next exhale phase begins.

    If currently in exhale, returns 0 (respond now).
    Otherwise returns ms until exhale starts.

    Used by Jane: when response is ready, wait this long before surfacing it.
    """
    pos = elapsed_ms % CYCLE_MS
    acc = 0
    for phase in PHASES:
        if pos < acc + phase["ms"]:
            if phase["index"] == EXHALE_INDEX:
                return 0  # already in exhale
            if phase["index"] < EXHALE_INDEX:
                # count remaining ms in current phase + all phases until exhale
                remaining_current = (acc + phase["ms"]) - pos
                between = sum(
                    p["ms"] for p in PHASES
                    if phase["index"] < p["index"] < EXHALE_INDEX
                )
                return remaining_current + between
            else:
                # past exhale — wait until next cycle's exhale
                remaining_cycle = CYCLE_MS - pos
                phases_before_exhale = sum(
                    p["ms"] for p in PHASES if p["index"] < EXHALE_INDEX
                )
                return remaining_cycle + phases_before_exhale
        acc += phase["ms"]
    return 0


# ── Daemon sleep ───────────────────────────────────────────────────────────────

def breathe(cycles: int = 1) -> None:
    """
    Sleep for N full breath cycles.

    Replaces arbitrary sleep() calls in daemons.
    breathe(1)  →  ~17s  (was: time.sleep(10) or time.sleep(30))
    breathe(4)  →  ~68s  (was: time.sleep(60))
    breathe(21) →  ~357s (~6min, was: time.sleep(300))

    Starts immediately — no alignment to a global clock.
    """
    time.sleep(CYCLE_S * cycles)


def cycles_for_seconds(seconds: float) -> int:
    """
    How many breath cycles approximate this many seconds?
    Rounds to nearest whole cycle (minimum 1).
    """
    return max(1, round(seconds / CYCLE_S))


# ── Breath timer (for UI / JS reference) ──────────────────────────────────────

class BreathTimer:
    """
    Tracks elapsed time since start for phase calculations.
    Lightweight — just records start time.

    Usage:
        timer = BreathTimer()
        ...
        info = timer.phase()
        wait = timer.next_exhale_wait_ms()
    """

    def __init__(self):
        self._start = time.monotonic()

    def elapsed_ms(self) -> int:
        return int((time.monotonic() - self._start) * 1000)

    def phase(self) -> dict:
        return get_phase_info(self.elapsed_ms())

    def next_exhale_wait_ms(self) -> int:
        return next_exhale_wait_ms(self.elapsed_ms())

    def wait_for_exhale(self) -> None:
        """Block until the next exhale phase. Used before surfacing a response."""
        wait_ms = self.next_exhale_wait_ms()
        if wait_ms > 0:
            time.sleep(wait_ms / 1000)


# ── JS constants export ────────────────────────────────────────────────────────

def js_constants() -> str:
    """
    Return JavaScript constants matching this module.
    Paste into journal.html or any UI file to keep UI and server in sync.
    """
    lines = [
        "// Generated from core/breath.py — do not edit manually",
        f"const CYCLE_MS = {CYCLE_MS};",
        "const BREATH_PHASES = [",
    ]
    for p in PHASES:
        lines.append(f'  {{ name: "{p["name"]}", ms: {p["ms"]}, index: {p["index"]} }},')
    lines.append("];")
    lines.append(f"const EXHALE_INDEX = {EXHALE_INDEX};")
    return "\n".join(lines)


# ── Diagnostics ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"Cycle: {CYCLE_MS}ms ({CYCLE_S}s)")
    print()
    print("Phase map:")
    acc = 0
    for p in PHASES:
        print(f"  {acc:5d}ms – {acc + p['ms']:5d}ms  {p['name']}")
        acc += p["ms"]
    print()
    print("JS constants:")
    print(js_constants())
    print()

    # Live demo
    timer = BreathTimer()
    print("Live phase (press Ctrl+C to stop):")
    try:
        while True:
            info = timer.phase()
            bar = "█" * int(info["progress"] * 20) + "░" * (20 - int(info["progress"] * 20))
            print(f"\r  {info['name']:10s} [{bar}] {info['progress']:.2f}", end="", flush=True)
            time.sleep(0.1)
    except KeyboardInterrupt:
        print()

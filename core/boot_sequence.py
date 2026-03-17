"""
boot_sequence.py — AIOS Boot Sequence (3² + 1)

Portable boot contract for any Willow node — CLI, server, agent, future hardware.
Three rings, three checks each, one gate. Same sequence everywhere.

Ring checks:
  Source:      gate (governance guards) | observe (telemetry) | validate (BASE 17 refs)
  Bridge:      open (server + compact pre-warm) | gate (retrieval) | learn (feedback)
  Continuity:  open (memory + corrections) | observe (enrichment) | close (handoff ready)

The 10th: bootloader reads all 9, presents status, generates prompt or degrades.

This module is the core implementation. Hook wrappers (in ~/.claude/hooks/) delegate here.
Server startup calls boot() directly. Any AIOS node calls boot().

Authority: Sean Campbell
System: Willow
ΔΣ=42
"""

import json
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional

_log = logging.getLogger("willow.boot")

# ─── Status Contract ────────────────────────────────────────────────────────

RINGS = {
    "source": ["gate", "observe", "validate"],
    "bridge": ["open", "gate", "learn"],
    "continuity": ["open", "observe", "close"],
}


@dataclass
class HookStatus:
    ring: str
    hook: str
    ready: bool
    detail: str = ""
    latency_ms: float = 0.0
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


@dataclass
class BootState:
    """Complete boot state for one AIOS instance."""
    statuses: dict = field(default_factory=dict)
    compact_index: dict = field(default_factory=dict)
    server_ok: bool = False
    booted_at: str = ""

    @property
    def ready_count(self) -> int:
        return sum(1 for s in self._all_statuses() if s.get("ready"))

    @property
    def total(self) -> int:
        return 9

    @property
    def all_ready(self) -> bool:
        return self.ready_count == self.total

    def _all_statuses(self) -> list:
        result = []
        for ring in RINGS:
            for hook in RINGS[ring]:
                result.append(self.statuses.get(ring, {}).get(hook, {"ready": False}))
        return result

    def report(self, ring: str, hook: str, ready: bool,
               detail: str = "", latency_ms: float = 0.0):
        if ring not in self.statuses:
            self.statuses[ring] = {}
        self.statuses[ring][hook] = asdict(HookStatus(
            ring=ring, hook=hook, ready=ready,
            detail=detail, latency_ms=latency_ms,
        ))

    def format(self) -> str:
        lines = [f"Boot: {self.ready_count}/{self.total} ready"]
        for ring_name in ["source", "bridge", "continuity"]:
            indicators = []
            ring_statuses = self.statuses.get(ring_name, {})
            for hook_name in RINGS[ring_name]:
                status = ring_statuses.get(hook_name, {})
                if status.get("ready"):
                    ms = status.get("latency_ms", 0)
                    indicators.append(f"✓ {hook_name} ({ms:.0f}ms)")
                else:
                    detail = status.get("detail", "not checked")
                    indicators.append(f"✗ {hook_name} ({detail})")
            lines.append(f"  {ring_name.title():12s}  {'  '.join(indicators)}")
        return "\n".join(lines)

    def format_compact_index(self) -> str:
        if not self.compact_index:
            return ""
        by_category = {}
        for cid, meta in self.compact_index.items():
            cat = meta.get("category", "unknown")
            if cat not in by_category:
                by_category[cat] = []
            label = meta.get("label", "")
            by_category[cat].append(f"{cid}" + (f" ({label})" if label else ""))
        lines = ["[BASE 17 — Available Compact Contexts]"]
        for cat, entries in sorted(by_category.items()):
            lines.append(f"  {cat}: {', '.join(entries)}")
        lines.append("Use [CTX:XXXXX] to reference. Content resolved on demand.")
        return "\n".join(lines)


# ─── Check Functions ────────────────────────────────────────────────────────

def _check_server(url: str = "http://localhost:8420", timeout: float = 3.0) -> tuple:
    """Check if Willow server is alive. Returns (ok, detail, latency_ms)."""
    import urllib.request
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(f"{url}/api/status", timeout=timeout) as r:
            data = json.loads(r.read())
            elapsed = (time.perf_counter() - t0) * 1000
            atoms = data.get("knowledge", {}).get("atoms", 0)
            entities = data.get("knowledge", {}).get("entities", 0)
            return True, f"server OK ({atoms} atoms, {entities} entities)", elapsed
    except Exception as e:
        elapsed = (time.perf_counter() - t0) * 1000
        return False, f"server unreachable: {e}", elapsed


def _check_compact_index(limit: int = 100) -> tuple:
    """Batch load BASE 17 compact index. Returns (ok, index_dict, detail, latency_ms)."""
    t0 = time.perf_counter()
    try:
        from core.compact import list_contexts
        contexts = list_contexts(limit=limit)
        elapsed = (time.perf_counter() - t0) * 1000
        index = {}
        for ctx in contexts:
            index[ctx["id"]] = {
                "category": ctx.get("category", ""),
                "label": ctx.get("label", ""),
            }
        return True, index, f"{len(index)} contexts indexed", elapsed
    except Exception as e:
        elapsed = (time.perf_counter() - t0) * 1000
        return False, {}, f"compact unavailable: {e}", elapsed


def _check_gate() -> tuple:
    """Check if gate.py governance module is available. Returns (ok, detail, latency_ms)."""
    t0 = time.perf_counter()
    try:
        from core.gate import Gatekeeper
        elapsed = (time.perf_counter() - t0) * 1000
        return True, "gate.py loaded", elapsed
    except Exception as e:
        elapsed = (time.perf_counter() - t0) * 1000
        return False, f"gate unavailable: {e}", elapsed


def _check_state() -> tuple:
    """Check if state.py definitions are available. Returns (ok, detail, latency_ms)."""
    t0 = time.perf_counter()
    try:
        from core.state import DecisionType, DecisionCode
        elapsed = (time.perf_counter() - t0) * 1000
        return True, f"state.py loaded ({len(DecisionCode)} codes)", elapsed
    except Exception as e:
        elapsed = (time.perf_counter() - t0) * 1000
        return False, f"state unavailable: {e}", elapsed


def _check_crown() -> tuple:
    """Check if Crown witness layer is available. Returns (ok, detail, latency_ms)."""
    t0 = time.perf_counter()
    try:
        from core.crown import init_witness
        elapsed = (time.perf_counter() - t0) * 1000
        return True, "crown witness available", elapsed
    except Exception as e:
        elapsed = (time.perf_counter() - t0) * 1000
        return False, f"crown unavailable: {e}", elapsed


def _check_breath() -> tuple:
    """Check if breath heartbeat is available. Returns (ok, detail, latency_ms)."""
    t0 = time.perf_counter()
    try:
        from core.breath import get_phase_info, CYCLE_S
        elapsed = (time.perf_counter() - t0) * 1000
        return True, f"breath online ({CYCLE_S}s cycle)", elapsed
    except Exception as e:
        elapsed = (time.perf_counter() - t0) * 1000
        return False, f"breath unavailable: {e}", elapsed


def _check_rings() -> tuple:
    """Check ring participation status. Returns (ok, detail, latency_ms)."""
    t0 = time.perf_counter()
    try:
        from core.rings import load_rings, ring_status
        status = ring_status()
        elapsed = (time.perf_counter() - t0) * 1000
        parts = []
        if status.get("source"):
            parts.append("source")
        if status.get("bridge"):
            parts.append("bridge")
        if status.get("continuity"):
            parts.append("continuity")
        return True, f"rings: {'+'.join(parts) or 'source only'}", elapsed
    except Exception as e:
        elapsed = (time.perf_counter() - t0) * 1000
        return False, f"rings unavailable: {e}", elapsed


def _check_db() -> tuple:
    """Check if database is reachable. Returns (ok, detail, latency_ms)."""
    t0 = time.perf_counter()
    try:
        from core.db import get_connection
        conn = get_connection()
        conn.execute("SELECT 1")
        conn.close()
        elapsed = (time.perf_counter() - t0) * 1000
        return True, "postgres connected", elapsed
    except Exception as e:
        elapsed = (time.perf_counter() - t0) * 1000
        return False, f"db unavailable: {e}", elapsed


def _check_pigeon() -> tuple:
    """Check if Pigeon transport is available. Returns (ok, detail, latency_ms)."""
    t0 = time.perf_counter()
    try:
        from core.pigeon import get_nest_path, AGENT_NAMES
        elapsed = (time.perf_counter() - t0) * 1000
        return True, f"pigeon ready ({len(AGENT_NAMES)} agents)", elapsed
    except Exception as e:
        elapsed = (time.perf_counter() - t0) * 1000
        return False, f"pigeon unavailable: {e}", elapsed


def _check_consent_gate() -> tuple:
    """Check if consent gate is available. Returns (ok, detail, latency_ms)."""
    t0 = time.perf_counter()
    try:
        from core.consent_gate import check_signal_consent
        elapsed = (time.perf_counter() - t0) * 1000
        return True, "consent gate loaded (fail-closed)", elapsed
    except Exception as e:
        elapsed = (time.perf_counter() - t0) * 1000
        return False, f"consent gate unavailable: {e}", elapsed


# ─── Boot Sequence ──────────────────────────────────────────────────────────

def boot(server_url: str = "http://localhost:8420",
         skip_server: bool = False) -> BootState:
    """
    Run the full AIOS boot sequence. 3² + 1.

    Returns BootState with all subsystem statuses.
    Can be called from:
      - Hook (bridge-open.py + bootloader.py)
      - Server startup (server.py)
      - Agent init (any AIOS node)
      - CLI (python -m core.boot_sequence)
    """
    state = BootState(booted_at=datetime.now().isoformat())

    # ── Source Ring ──────────────────────────────────────────────────

    # source-gate: governance guards (gate.py + state.py + consent_gate)
    gate_ok, gate_detail, gate_ms = _check_gate()
    state_ok, state_detail, state_ms = _check_state()
    consent_ok, consent_detail, consent_ms = _check_consent_gate()
    combined_ms = gate_ms + state_ms + consent_ms
    all_source_gate = gate_ok and state_ok
    detail_parts = []
    if gate_ok:
        detail_parts.append("gate")
    if state_ok:
        detail_parts.append("state")
    if consent_ok:
        detail_parts.append("consent")
    state.report("source", "gate",
                 ready=all_source_gate,
                 detail=f"{'+'.join(detail_parts)} loaded" if detail_parts else "no governance",
                 latency_ms=combined_ms)

    # source-observe: telemetry (db + crown witness)
    db_ok, db_detail, db_ms = _check_db()
    crown_ok, crown_detail, crown_ms = _check_crown()
    state.report("source", "observe",
                 ready=db_ok,
                 detail=f"db:{db_detail}, crown:{'ok' if crown_ok else 'down'}",
                 latency_ms=db_ms + crown_ms)

    # source-validate: BASE 17 ref validation
    compact_ok, compact_index, compact_detail, compact_ms = _check_compact_index()
    state.compact_index = compact_index
    state.report("source", "validate",
                 ready=compact_ok,
                 detail=compact_detail,
                 latency_ms=compact_ms)

    # ── Bridge Ring ─────────────────────────────────────────────────

    # bridge-open: server + MCP alive
    if skip_server:
        state.server_ok = True
        state.report("bridge", "open", ready=True,
                     detail="server check skipped (we ARE the server)", latency_ms=0)
    else:
        server_ok, server_detail, server_ms = _check_server(server_url)
        state.server_ok = server_ok
        state.report("bridge", "open",
                     ready=server_ok,
                     detail=server_detail,
                     latency_ms=server_ms)

    # bridge-gate: retrieval subsystem (pigeon + rings)
    pigeon_ok, pigeon_detail, pigeon_ms = _check_pigeon()
    rings_ok, rings_detail, rings_ms = _check_rings()
    state.report("bridge", "gate",
                 ready=pigeon_ok,
                 detail=f"pigeon:{'ok' if pigeon_ok else 'down'}, {rings_detail}",
                 latency_ms=pigeon_ms + rings_ms)

    # bridge-learn: feedback + breath
    breath_ok, breath_detail, breath_ms = _check_breath()
    state.report("bridge", "learn",
                 ready=True,
                 detail=f"breath:{'ok' if breath_ok else 'down'}",
                 latency_ms=breath_ms)

    # ── Continuity Ring ─────────────────────────────────────────────

    # continuity-open: memory subsystem (db must be up)
    state.report("continuity", "open",
                 ready=db_ok,
                 detail=f"memory:{'online' if db_ok else 'offline'}",
                 latency_ms=0)

    # continuity-observe: enrichment pipeline
    try:
        from core.pigeon import init_droppings_table
        state.report("continuity", "observe",
                     ready=True, detail="enrichment pipeline present", latency_ms=0)
    except Exception:
        state.report("continuity", "observe",
                     ready=False, detail="enrichment unavailable", latency_ms=0)

    # continuity-close: handoff readiness (always standby at boot)
    state.report("continuity", "close",
                 ready=True, detail="standby", latency_ms=0)

    return state


# ─── CLI Entry Point ────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

    state = boot()
    print(state.format())
    print()
    if state.compact_index:
        print(state.format_compact_index())
        print()
    if state.all_ready:
        print("AIOS ready.")
    else:
        degraded = state.total - state.ready_count
        print(f"AIOS degraded — {degraded} subsystem(s) offline.")
    sys.exit(0 if state.ready_count >= 6 else 1)

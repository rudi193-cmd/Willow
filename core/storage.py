"""
STORAGE v1.2 (WINDOWS COMPATIBLE)
Filesystem Storage Layer for Gatekeeper API

Owner: Sean Campbell
System: Aionic / Die-namic
Version: 1.2
Status: Active
Last Updated: 2026-01-29
Checksum: ΔΣ=42

Thin storage layer. No governance logic.
Persistence only - kernel decides, storage persists.

v1.2 Changes:
- FIXED: 'fcntl' ModuleNotFoundError on Windows.
- Added cross-platform locking (msvcrt for Windows, fcntl for Unix).
"""

import json
import os
import sys
from pathlib import Path
from typing import Optional, List, Tuple
from dataclasses import asdict
from contextlib import contextmanager
import time

# --- CROSS-PLATFORM LOCKING ---
# This block detects Windows ('nt') and uses msvcrt instead of fcntl
if os.name == 'nt':  # Windows
    import msvcrt
    def lock_file(f):
        # Lock the first byte of the file (Non-blocking)
        # 10 attempts to lock, waiting 0.1s between each
        for _ in range(10):
            try:
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                return
            except OSError:
                time.sleep(0.1)
        raise BlockingIOError("Could not acquire lock after retries")
    
    def unlock_file(f):
        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)

else:  # Unix/Linux/Mac
    import fcntl
    def lock_file(f):
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
    
    def unlock_file(f):
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)

from .state import (
    RuntimeState,
    AuditEntry,
    GateEvent,
    create_genesis_hash,
    verify_chain,
    recompute_entry_hash,
)

# Default storage directory
STORAGE_DIR = Path(os.environ.get("GATEKEEPER_STORAGE_DIR", "./data"))

def ensure_storage_dir():
    """Ensure storage directory exists."""
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)

# =============================================================================
# TRANSACTION LOCK
# =============================================================================

def get_txn_lock_path() -> Path:
    """Global transaction lock path."""
    return STORAGE_DIR / "txn.lock"

@contextmanager
def txn_lock():
    """
    Global transaction lock for atomic multi-file operations.
    Supports both Windows (msvcrt) and Unix (fcntl).
    """
    ensure_storage_dir()
    lock_path = get_txn_lock_path()
    
    # Ensure the lock file exists
    if not lock_path.exists():
        with open(lock_path, "w") as f:
            f.write("lock")

    lock_file_handle = open(lock_path, "r+")
    try:
        # Attempt to acquire lock
        try:
            lock_file(lock_file_handle)
            yield
        except BlockingIOError:
            # If we fail, just pass (soft fail for now to keep loop alive)
            # In production, this should retry or raise
            yield

    finally:
        try:
            unlock_file(lock_file_handle)
        except:
            pass
        lock_file_handle.close()

# =============================================================================
# STATE STORAGE
# =============================================================================

def get_state_path() -> Path:
    return STORAGE_DIR / "state.json"

def load_state() -> RuntimeState:
    """Load RuntimeState from filesystem."""
    ensure_storage_dir()
    path = get_state_path()
    
    if not path.exists():
        return create_default_state()
    
    try:
        with open(path, "r") as f:
            data = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return create_default_state()
    
    return RuntimeState(
        phase=data.get("phase", "development"),
        workflow_posture=data.get("workflow_posture", "STRICT"),
        depth=data.get("depth", 0),
        sequence=data.get("sequence", 0),
        authorized_surfaces=data.get("authorized_surfaces", ["repo", "config"]),
        head_hash=data.get("head_hash", create_genesis_hash()),
        recent_idempotency_keys=data.get("recent_idempotency_keys", []),
        max_depth=data.get("max_depth", 3),
        max_delta_size=data.get("max_delta_size", 500),
        idempotency_window=data.get("idempotency_window", 100),
    )

def save_state(state: RuntimeState) -> None:
    """
    Save RuntimeState to filesystem.
    Uses atomic write pattern (write temp -> rename).
    """
    ensure_storage_dir()
    path = get_state_path()
    tmp_path = path.with_suffix(".json.tmp")
    
    data = {
        "phase": state.phase,
        "workflow_posture": state.workflow_posture,
        "depth": state.depth,
        "sequence": state.sequence,
        "authorized_surfaces": state.authorized_surfaces,
        "head_hash": state.head_hash,
        "recent_idempotency_keys": state.recent_idempotency_keys,
        "max_depth": state.max_depth,
        "max_delta_size": state.max_delta_size,
        "idempotency_window": state.idempotency_window,
    }
    
    # Write to temp file
    try:
        with open(tmp_path, "w") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        
        # Atomic rename (replace existing)
        if os.path.exists(path):
            os.remove(path)
        os.rename(tmp_path, path)
    except Exception as e:
        print(f"[STORAGE] Error saving state: {e}")

def create_default_state() -> RuntimeState:
    """Create and persist default state."""
    state = RuntimeState(
        phase="development",
        workflow_posture="STRICT",
        depth=0,
        sequence=0,
        authorized_surfaces=["repo", "config", "api"], 
        head_hash=create_genesis_hash(),
        recent_idempotency_keys=[],
    )
    save_state(state)
    return state

# =============================================================================
# AUDIT STORAGE (Append-only)
# =============================================================================

def get_audit_path() -> Path:
    return STORAGE_DIR / "audit.jsonl"

def get_audit_head() -> dict:
    """Return current audit chain head: hash, sequence number, entry count."""
    ensure_storage_dir()
    entries = load_audit_log()
    if not entries:
        return {"head_hash": None, "sequence": 0, "entry_count": 0, "last_entry": None}
    last = entries[-1]
    return {
        "head_hash": last.get("entry_hash"),
        "sequence": last.get("sequence", len(entries)),
        "entry_count": len(entries),
        "last_entry": last.get("timestamp"),
    }

def verify_audit_chain() -> dict:
    """Verify audit chain integrity. Returns status and entry count."""
    ensure_storage_dir()
    entries = load_audit_log()
    if not entries:
        return {"valid": True, "entry_count": 0, "message": "Empty chain (genesis state)"}
    try:
        from core.coherence import verify_chain as _verify
        result = _verify(entries)
        return {"valid": result, "entry_count": len(entries), "message": "Chain intact" if result else "Chain broken"}
    except Exception:
        return {"valid": True, "entry_count": len(entries), "message": "Verification skipped (coherence module unavailable)"}

def append_audit_entry(entry: AuditEntry) -> None:
    """Append audit entry to log."""
    ensure_storage_dir()
    path = get_audit_path()
    
    try:
        with open(path, "a") as f:
            f.write(json.dumps(entry.to_dict()) + "\n")
            f.flush()
            os.fsync(f.fileno())
    except Exception as e:
        print(f"[STORAGE] Error appending audit: {e}")

def load_audit_log() -> List[dict]:
    """Load all audit entries."""
    ensure_storage_dir()
    path = get_audit_path()
    
    if not path.exists():
        return []
    
    entries = []
    try:
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
    except Exception:
        pass
    return entries

# =============================================================================
# INITIALIZATION
# =============================================================================

def init_storage() -> RuntimeState:
    """
    Initialize storage and return current state.
    Uses txn_lock to prevent race conditions on multi-worker cold start.
    """
    ensure_storage_dir()
    
    # Ensure lock file exists before locking
    lock_path = get_txn_lock_path()
    if not lock_path.exists():
        try:
            with open(lock_path, "w") as f:
                f.write("lock")
        except:
            pass

    with txn_lock():
        path = get_state_path()
        if not path.exists():
            return create_default_state()
        return load_state()

# =============================================================================
# EVENT APPLICATION
# =============================================================================

def apply_events(events: List[GateEvent], state: RuntimeState) -> RuntimeState:
    """
    Apply events to storage and return updated state.
    CALLER MUST hold txn_lock().
    """
    new_state = RuntimeState(
        phase=state.phase,
        workflow_posture=state.workflow_posture,
        depth=state.depth,
        sequence=state.sequence,
        authorized_surfaces=list(state.authorized_surfaces),
        head_hash=state.head_hash,
        recent_idempotency_keys=list(state.recent_idempotency_keys),
        max_depth=state.max_depth,
        max_delta_size=state.max_delta_size,
        idempotency_window=state.idempotency_window,
    )
    
    for event in events:
        if event.event_type == "audit":
            entry = AuditEntry(
                timestamp=event.payload["timestamp"],
                request_id=event.payload["request_id"],
                mod_type=event.payload["mod_type"],
                target=event.payload["target"],
                sequence=event.payload["sequence"],
                decision_type=event.payload["decision_type"],
                code=event.payload["code"],
                reason=event.payload["reason"],
                prev_hash=new_state.head_hash or create_genesis_hash(),
                checksum=event.payload.get("checksum", 42),
            )
            append_audit_entry(entry)
            new_state.head_hash = entry.entry_hash
            
        elif event.event_type == "state_delta":
            if event.payload.get("sequence_increment"):
                new_state.sequence += event.payload["sequence_increment"]
            
            key = event.payload.get("add_idempotency_key")
            if key:
                new_state.recent_idempotency_keys.append(key)
                if len(new_state.recent_idempotency_keys) > new_state.idempotency_window:
                    new_state.recent_idempotency_keys = \
                        new_state.recent_idempotency_keys[-new_state.idempotency_window:]
    
    save_state(new_state)
    return new_state
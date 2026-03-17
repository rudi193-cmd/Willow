"""
AIOS Minimal - Proof of Dual Commit Governance

Single daemon loop: Intake → Process → Route → Govern

NO Drive sync, NO Vision, NO knowledge base.
Just proves AI proposes + Human ratifies = Dual Commit works.

CHECKSUM: ΔΣ=42
"""

import os
import sys
import time
import shutil
from pathlib import Path
from datetime import datetime

# Core imports
sys.path.insert(0, str(Path(__file__).parent / "core"))
from core import gate, state, storage, llm_router

# Config
INTAKE_DIR = Path("data/intake")
ROUTES = {
    "documents": Path("data/artifacts/documents"),
    "code": Path("data/artifacts/code"),
    "images": Path("data/artifacts/images"),
    "unknown": Path("data/artifacts/unknown")
}
WATCH_INTERVAL = 10  # seconds

def init_dirs():
    """Create directory structure."""
    INTAKE_DIR.mkdir(parents=True, exist_ok=True)
    for route_path in ROUTES.values():
        route_path.mkdir(parents=True, exist_ok=True)

def extract_text(filepath: Path) -> str:
    """Extract text from file (basic)."""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()[:1000]  # First 1K chars
    except:
        return f"[Binary file: {filepath.suffix}]"

def classify_file(filename: str, content: str) -> str:
    """Use LLM to classify file into route."""
    llm_router.load_keys_from_json()
    prompt = f"""Classify this file into ONE category: documents, code, images, or unknown.

Filename: {filename}
Content preview: {content[:200]}

Reply with ONLY the category name, nothing else."""

    response = llm_router.ask(prompt, preferred_tier="free")
    if response:
        category = response.content.strip().lower()
        return category if category in ROUTES else "unknown"
    return "unknown"

def process_file(filepath: Path, gatekeeper: gate.Gatekeeper, current_state: state.RuntimeState):
    """Process single file through Dual Commit flow."""
    print(f"\n[PROCESS] {filepath.name}")
    content = extract_text(filepath)
    category = classify_file(filepath.name, content)
    target_dir = ROUTES[category]
    print(f"  AI proposes: {category}")

    request = state.ModificationRequest(
        mod_type=state.ModificationType.EXTERNAL,
        target=str(target_dir / filepath.name),
        new_value=str(filepath),
        reason=f"Route {filepath.name} to {category}",
        authority=state.Authority.AI,
        governance_state=state.GovernanceState.PROPOSED,
        sequence=current_state.sequence + 1,
        old_value=None
    )

    decision, events = gatekeeper.validate(request, current_state)
    print(f"  Gate decision: {decision.decision_type.name} ({decision.code.name})")

    new_state = storage.apply_events(events, current_state)
    storage.save_state(new_state)

    if decision.decision_type == state.DecisionType.APPROVE:
        shutil.move(str(filepath), str(target_dir / filepath.name))
        print(f"  ✓ Moved to {category}/")
    elif decision.decision_type == state.DecisionType.REQUIRE_HUMAN:
        print(f"  ⏸ Awaiting human approval (ID: {request.request_id[:8]})")
        print(f"    Use: POST /approve {{\"request_id\": \"{request.request_id}\"}}")
    else:
        print(f"  ✗ Rejected: {decision.reason}")
    
    return new_state

def main_loop():
    """Eternal intake → process → route loop."""
    print("=" * 60)
    print("AIOS MINIMAL - Dual Commit Daemon")
    print("=" * 60)
    init_dirs()
    llm_router.load_keys_from_json()
    gatekeeper = gate.Gatekeeper()
    current_state = storage.init_storage()
    print(f"Watching: {INTAKE_DIR.absolute()}")
    print(f"Routes: {list(ROUTES.keys())}")
    print(f"State sequence: {current_state.sequence}\n")

    cycle = 0
    while True:
        cycle += 1
        print(f"[Cycle {cycle}] {datetime.now().strftime('%H:%M:%S')}")
        pending = [f for f in INTAKE_DIR.glob("*") if f.is_file()]
        
        if pending:
            print(f"  Found {len(pending)} file(s)")
            for filepath in pending[:10]:
                current_state = process_file(filepath, gatekeeper, current_state)
        else:
            print("  (empty)")
        
        time.sleep(WATCH_INTERVAL)

if __name__ == "__main__":
    try:
        main_loop()
    except KeyboardInterrupt:
        print("\n\nShutdown complete. ΔΣ=42")

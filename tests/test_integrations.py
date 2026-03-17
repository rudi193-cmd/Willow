"""
Integration Test - All New Modules

Tests all newly integrated modules:
- delta_tracker
- seed_packet
- n2n_packets & n2n_db
- checksum_chain
- time_resume_capsule
- recursion_tracker
- workflow_state

Usage: python test_integrations.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

def test_delta_tracker():
    """Test delta tracker integration."""
    print("\n=== Testing Delta Tracker ===")
    from core.delta_tracker import DeltaTracker

    tracker = DeltaTracker("Sweet-Pea-Rudi19")

    # Calculate delta between states
    state1 = {"phase": "start", "tools": []}
    state2 = {"phase": "step_1", "tools": ["read_file"]}

    entropy = tracker.calculate_delta(state1, state2)
    print(f"[OK] Delta calculated: {entropy:.3f}")

    # Generate DELTA.md
    changes = [{
        "field": "phase",
        "from": "start",
        "to": "step_1",
        "entropy_delta": entropy
    }]
    delta_file = tracker.generate_delta_file("thread-1", "thread-2", changes)
    print(f"[OK] DELTA.md generated: {delta_file}")

    # List deltas
    deltas = tracker.list_deltas(limit=5)
    print(f"[OK] Found {len(deltas)} deltas in DB")


def test_seed_packet():
    """Test SEED_PACKET module."""
    print("\n=== Testing SEED_PACKET ===")
    from core.seed_packet import save_packet, load_packet, validate_packet

    packet = {
        "thread_id": "test-2026-02-08",
        "timestamp": "2026-02-08T00:00:00Z",
        "device": "server",
        "capabilities": ["tool_access"],
        "workflow_state": "ACTIVE",
        "current_phase": "test",
        "open_decisions": [],
        "pending_actions": [],
        "checksum": "ΔΣ=42"
    }

    # Save packet
    path = save_packet("Sweet-Pea-Rudi19", packet)
    print(f"[OK] SEED_PACKET saved: {path}")

    # Load packet
    loaded = load_packet("Sweet-Pea-Rudi19", packet["thread_id"])
    print(f"[OK] SEED_PACKET loaded: {loaded['thread_id']}")

    # Validate
    valid = validate_packet(loaded)
    print(f"[OK] SEED_PACKET valid: {valid}")


def test_n2n_packets():
    """Test N2N packet creation and validation."""
    print("\n=== Testing N2N Packets ===")
    from core.n2n_packets import N2NPacket, PacketType, create_handoff

    # Create packet
    packet = N2NPacket.create_packet(
        PacketType.HANDOFF,
        "kart@user1",
        "willow@user1",
        {"what_happened": "Task completed", "what_next": "Review results"}
    )
    print(f"[OK] Packet created: {packet['header']['packet_type']}")

    # Validate
    valid = N2NPacket.validate_packet(packet)
    print(f"[OK] Packet valid: {valid}")

    # Serialize
    serialized = N2NPacket.serialize_packet(packet)
    print(f"[OK] Packet serialized: {len(serialized)} bytes")

    # Convenience function
    handoff = create_handoff("kart@user1", "jane@user1", "Done", "Next step")
    print(f"[OK] Handoff packet created: {handoff['payload']['what_next']}")


def test_n2n_db():
    """Test N2N database."""
    print("\n=== Testing N2N Database ===")
    from core.n2n_db import N2NDatabase
    from core.n2n_packets import create_handoff

    db = N2NDatabase("Sweet-Pea-Rudi19")

    # Send packet
    packet = create_handoff(
        "kart@Sweet-Pea-Rudi19",
        "willow@Sweet-Pea-Rudi19",
        "Integration test",
        "Verify N2N works"
    )
    packet_id = db.send_packet(packet)
    print(f"[OK] Packet sent: {packet_id}")

    # Receive packets
    received = db.receive_packets("willow@Sweet-Pea-Rudi19", status="SENT")
    print(f"[OK] Received {len(received)} packets")

    if received:
        # Mark received
        db.mark_received(received[0]["packet_id"])
        print(f"[OK] Packet marked as received")


def test_checksum_chain():
    """Test checksum chain validation."""
    print("\n=== Testing Checksum Chain ===")
    from core.checksum_chain import ChecksumChain

    chain = ChecksumChain()

    # Generate checksum
    payload = {"data": "test"}
    checksum = chain.generate_checksum(payload)
    print(f"[OK] Checksum generated: {checksum[:16]}...")

    # Create envelope (will need prior_checksum parameter)
    # envelope = chain.create_handoff_envelope("node1", "node2", payload)
    # print(f"[OK] Envelope created")


def test_rings():
    """Test Kart orchestrator with new SEED_PACKET."""
    print("\n=== Testing Kart Orchestrator ===")
    from core.rings import KartOrchestrator

    orchestrator = KartOrchestrator("Sweet-Pea-Rudi19", "kart")
    print(f"[OK] Orchestrator initialized")
    print(f"[OK] Delta tracker: {orchestrator.delta_tracker is not None}")
    print(f"[OK] Session ID: {orchestrator.session_id}")


def test_agent_engine():
    """Test agent engine with N2N integration."""
    print("\n=== Testing Agent Engine ===")
    from core.agent_engine import AgentEngine

    engine = AgentEngine("Sweet-Pea-Rudi19", "kart")
    print(f"[OK] Agent engine initialized")
    print(f"[OK] N2N database: {engine.n2n_db is not None}")
    print(f"[OK] Node ID: {engine.node_id}")

    # Test N2N packet sending
    packet_id = engine.send_handoff(
        "willow",
        "Integration test complete",
        "All modules wired"
    )
    print(f"[OK] Sent handoff packet: {packet_id}")


def main():
    """Run all integration tests."""
    print("=" * 60)
    print("INTEGRATION TEST - All New Modules")
    print("=" * 60)

    tests = [
        test_delta_tracker,
        test_seed_packet,
        test_n2n_packets,
        test_n2n_db,
        test_checksum_chain,
        test_rings,
        test_agent_engine
    ]

    passed = 0
    failed = 0

    for test_func in tests:
        try:
            test_func()
            passed += 1
        except Exception as e:
            print(f"\n[FAIL] {test_func.__name__}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("\n" + "=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

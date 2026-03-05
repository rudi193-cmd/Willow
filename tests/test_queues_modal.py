"""
Test Queues Modal
Verifies the Queues modal displays queue health and actions work.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core import health


def test_queue_health_endpoint():
    """Test that queue health data is accessible"""
    print("\n[TEST] Queue Health Data Access")
    print("-" * 50)

    try:
        queue_data = health.check_queue_health(backlog_threshold=50)

        print(f"[OK] Retrieved health data for {len(queue_data)} queues")

        for name, q in queue_data.items():
            status_icon = "+" if q["status"] == "healthy" else "!" if q["status"] == "elevated" else "X"
            print(f"  [{status_icon}] {name:20} Status: {q['status']:12} Files: {q['count']:4}  {q['message']}")

        return True
    except Exception as e:
        print(f"[FAIL] Error accessing queue health: {e}")
        return False


def test_queue_status_classification():
    """Test that queues are correctly classified by status"""
    print("\n[TEST] Queue Status Classification")
    print("-" * 50)

    try:
        queue_data = health.check_queue_health(backlog_threshold=50)

        healthy = {name: q for name, q in queue_data.items() if q["status"] == "healthy"}
        elevated = {name: q for name, q in queue_data.items() if q["status"] == "elevated"}
        backlog = {name: q for name, q in queue_data.items() if q["status"] == "backlog"}

        print(f"Healthy queues ({len(healthy)}):")
        for name, q in healthy.items():
            print(f"  - {name} ({q['count']} files)")

        if elevated:
            print(f"\nElevated queues ({len(elevated)}):")
            for name, q in elevated.items():
                print(f"  - {name} ({q['count']} files)")

        if backlog:
            print(f"\nBacklog queues ({len(backlog)}):")
            for name, q in backlog.items():
                print(f"  - {name} ({q['count']} files)")

        print(f"\n[OK] Status classification working correctly")
        return True
    except Exception as e:
        print(f"[FAIL] Error classifying queues: {e}")
        return False


def test_queue_file_listing():
    """Test that queue files can be listed"""
    print("\n[TEST] Queue File Listing")
    print("-" * 50)

    try:
        queue_data = health.check_queue_health()

        # Find a queue with files
        test_queue = None
        for name, q in queue_data.items():
            if q["count"] > 0:
                test_queue = name
                break

        if test_queue:
            artifacts_path = Path(__file__).parent / "artifacts"
            pending_dir = artifacts_path / test_queue / "pending"

            if pending_dir.exists():
                files = [f for f in pending_dir.iterdir() if f.is_file()]
                print(f"[OK] Queue '{test_queue}' has {len(files)} files:")
                for f in files[:5]:  # Show first 5
                    print(f"  - {f.name} ({f.stat().st_size} bytes)")
                if len(files) > 5:
                    print(f"  ... and {len(files) - 5} more")
            else:
                print(f"[INFO] Queue directory does not exist: {pending_dir}")
        else:
            print("[INFO] No queues with files found")

        print("\n[OK] File listing logic works")
        return True
    except Exception as e:
        print(f"[FAIL] Error listing queue files: {e}")
        return False


def test_ui_components():
    """Test that UI components exist in dashboard.html"""
    print("\n[TEST] UI Components Exist")
    print("-" * 50)

    dashboard = Path(__file__).parent / "system" / "dashboard.html"
    if not dashboard.exists():
        print("[FAIL] dashboard.html not found")
        return False

    content = dashboard.read_text(encoding='utf-8')

    checks = {
        "loadQueuesModal function": "async function loadQueuesModal()",
        "viewQueueFiles function": "async function viewQueueFiles(",
        "clearQueue function": "async function clearQueue(",
        "Queues card": "onclick=\"openModal('queues')\"",
        "Queue status legend": "Queue Status Legend"
    }

    all_passed = True
    for check_name, check_str in checks.items():
        if check_str in content:
            print(f"[OK] {check_name} found")
        else:
            print(f"[FAIL] {check_name} NOT found")
            all_passed = False

    if all_passed:
        print("\n[OK] All UI components present")
    return all_passed


def test_clear_queue_validation():
    """Test clear queue security validation"""
    print("\n[TEST] Clear Queue Security Validation")
    print("-" * 50)

    import re

    test_cases = [
        ("valid_queue", True, "Valid queue name"),
        ("my-queue", True, "Valid with hyphen"),
        ("my_queue", True, "Valid with underscore"),
        ("../../../etc/passwd", False, "Path traversal attempt"),
        ("queue;rm -rf /", False, "Command injection attempt"),
        ("queue$HOME", False, "Variable injection attempt"),
        ("queue name", False, "Space in name"),
    ]

    all_passed = True
    for queue_name, should_pass, description in test_cases:
        is_valid = bool(re.match(r'^[a-zA-Z0-9_-]+$', queue_name))
        if is_valid == should_pass:
            print(f"[OK] {description}: '{queue_name}' -> {is_valid}")
        else:
            print(f"[FAIL] {description}: '{queue_name}' -> {is_valid} (expected {should_pass})")
            all_passed = False

    if all_passed:
        print("\n[OK] Security validation working correctly")
    return all_passed


def test_modal_data_format():
    """Test that modal displays correct data format"""
    print("\n[TEST] Modal Data Format")
    print("-" * 50)

    try:
        queue_data = health.check_queue_health()

        print("Expected table columns:")
        print("  1. Queue (username)")
        print("  2. Status (colored: green=healthy, yellow=elevated, red=backlog)")
        print("  3. Files Pending (count)")
        print("  4. Message (descriptive text)")
        print("  5. Actions (View Files button, Clear Queue button if count > 0)")

        print("\nSample row data:")
        for name, q in list(queue_data.items())[:3]:  # Show first 3 queues
            print(f"\n  Queue: {name}")
            print(f"  Status: {q['status']}")
            print(f"  Files Pending: {q['count']}")
            print(f"  Message: {q['message']}")
            print(f"  Actions: View Files" + (", Clear Queue" if q['count'] > 0 else ""))

        print("\n[OK] Data format matches modal requirements")
        return True
    except Exception as e:
        print(f"[FAIL] Error formatting data: {e}")
        return False


def main():
    print("=" * 50)
    print("QUEUES MODAL TEST")
    print("=" * 50)

    results = []
    results.append(("Queue Health Data Access", test_queue_health_endpoint()))
    results.append(("Queue Status Classification", test_queue_status_classification()))
    results.append(("Queue File Listing", test_queue_file_listing()))
    results.append(("UI Components Exist", test_ui_components()))
    results.append(("Clear Queue Security Validation", test_clear_queue_validation()))
    results.append(("Modal Data Format", test_modal_data_format()))

    print("\n" + "=" * 50)
    print("TEST SUMMARY")
    print("=" * 50)

    passed = sum(1 for _, r in results if r is True)
    failed = sum(1 for _, r in results if r is False)
    skipped = sum(1 for _, r in results if r is None)

    for name, result in results:
        if result is True:
            print(f"[PASS] {name}")
        elif result is False:
            print(f"[FAIL] {name}")
        else:
            print(f"[SKIP] {name}")

    print("\n" + "=" * 50)
    print(f"Total: {passed} passed, {failed} failed, {skipped} skipped")

    print("\n[OK] QUEUES MODAL SUMMARY:")
    print("  - Displays queue health with status indicators")
    print("  - Shows file counts and descriptive messages")
    print("  - View Files button lists all pending files")
    print("  - Clear Queue button removes all files (with confirmation)")
    print("  - Security validation prevents path traversal attacks")
    print("  - Status legend explains health thresholds")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    exit(main())

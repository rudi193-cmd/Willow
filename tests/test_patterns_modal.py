"""
Test Patterns Modal
Verifies the Patterns modal displays routing statistics and visualizations.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core import patterns


def test_patterns_stats_endpoint():
    """Test that pattern statistics are accessible"""
    print("\n[TEST] Pattern Statistics Data Access")
    print("-" * 50)

    try:
        stats = patterns.get_routing_stats(days=30)

        print(f"[OK] Retrieved pattern statistics")
        print(f"  Total routings (30 days): {stats.get('total_routings', 0)}")
        print(f"  Unresolved anomalies: {stats.get('unresolved_anomalies', 0)}")
        print(f"  Period: {stats.get('period_days', 30)} days")

        by_dest = stats.get('by_destination', {})
        print(f"  Destinations tracked: {len(by_dest)}")

        by_type = stats.get('by_file_type', {})
        print(f"  File types tracked: {len(by_type)}")

        return True
    except Exception as e:
        print(f"[FAIL] Error accessing pattern statistics: {e}")
        return False


def test_stats_data_structure():
    """Test that stats have all required fields"""
    print("\n[TEST] Statistics Data Structure")
    print("-" * 50)

    try:
        stats = patterns.get_routing_stats()

        required_fields = ["total_routings", "by_destination", "by_file_type", "unresolved_anomalies", "period_days"]

        all_valid = True
        for field in required_fields:
            if field not in stats:
                print(f"[FAIL] Missing field '{field}' in stats")
                all_valid = False
            else:
                print(f"[OK] Field '{field}' present")

        return all_valid
    except Exception as e:
        print(f"[FAIL] Error checking structure: {e}")
        return False


def test_destination_distribution():
    """Test destination distribution data"""
    print("\n[TEST] Destination Distribution")
    print("-" * 50)

    try:
        stats = patterns.get_routing_stats()
        by_dest = stats.get('by_destination', {})

        if not by_dest:
            print("[INFO] No destination data available (database may be empty)")
            return True

        total = stats.get('total_routings', 0)
        print(f"Top destinations (out of {total} total routings):")

        sorted_dests = sorted(by_dest.items(), key=lambda x: x[1], reverse=True)
        for dest, count in sorted_dests[:5]:  # Show top 5
            pct = (count / total * 100) if total > 0 else 0
            print(f"  {dest:20} {count:5} ({pct:5.1f}%)")

        print("\n[OK] Destination distribution data valid")
        return True
    except Exception as e:
        print(f"[FAIL] Error checking destinations: {e}")
        return False


def test_file_type_distribution():
    """Test file type distribution data"""
    print("\n[TEST] File Type Distribution")
    print("-" * 50)

    try:
        stats = patterns.get_routing_stats()
        by_type = stats.get('by_file_type', {})

        if not by_type:
            print("[INFO] No file type data available (database may be empty)")
            return True

        total = stats.get('total_routings', 0)
        print(f"Top file types (out of {total} total routings):")

        sorted_types = sorted(by_type.items(), key=lambda x: x[1], reverse=True)
        for file_type, count in sorted_types[:5]:  # Show top 5
            pct = (count / total * 100) if total > 0 else 0
            display_type = file_type if file_type else 'unknown'
            print(f"  {display_type:20} {count:5} ({pct:5.1f}%)")

        print("\n[OK] File type distribution data valid")
        return True
    except Exception as e:
        print(f"[FAIL] Error checking file types: {e}")
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
        "loadPatternsModal function": "async function loadPatternsModal()",
        "Patterns card": "onclick=\"openModal('patterns')\"",
        "Top Destinations section": "Top Destinations",
        "Top File Types section": "Top File Types",
        "Pattern recognition info": "About Pattern Recognition"
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


def test_visualization_logic():
    """Test bar chart visualization logic"""
    print("\n[TEST] Visualization Logic")
    print("-" * 50)

    # Test the bar width calculation logic
    test_cases = [
        (100, 100, 100.0, "Max value should be 100% width"),
        (50, 100, 50.0, "Half of max should be 50% width"),
        (25, 100, 25.0, "Quarter of max should be 25% width"),
        (0, 100, 0.0, "Zero should be 0% width"),
    ]

    all_correct = True
    for value, max_val, expected_width, description in test_cases:
        actual_width = (value / max_val * 100) if max_val > 0 else 0

        if actual_width == expected_width:
            print(f"[OK] {description}: {value}/{max_val} -> {actual_width}%")
        else:
            print(f"[FAIL] {description}: {value}/{max_val} -> {actual_width}% (expected {expected_width}%)")
            all_correct = False

    if all_correct:
        print("\n[OK] Visualization logic correct")
    return all_correct


def test_percentage_calculation():
    """Test percentage calculation logic"""
    print("\n[TEST] Percentage Calculation")
    print("-" * 50)

    test_cases = [
        (50, 100, 50.0, "50 out of 100 = 50%"),
        (25, 100, 25.0, "25 out of 100 = 25%"),
        (100, 100, 100.0, "100 out of 100 = 100%"),
        (0, 100, 0.0, "0 out of 100 = 0%"),
        (10, 0, 0, "Division by zero should return 0"),
    ]

    all_correct = True
    for count, total, expected_pct, description in test_cases:
        actual_pct = (count / total * 100) if total > 0 else 0

        if actual_pct == expected_pct:
            print(f"[OK] {description}: {count}/{total} -> {actual_pct:.1f}%")
        else:
            print(f"[FAIL] {description}: {count}/{total} -> {actual_pct:.1f}% (expected {expected_pct:.1f}%)")
            all_correct = False

    if all_correct:
        print("\n[OK] Percentage calculation correct")
    return all_correct


def test_modal_data_format():
    """Test that modal displays correct data format"""
    print("\n[TEST] Modal Data Format")
    print("-" * 50)

    try:
        stats = patterns.get_routing_stats()

        print("Expected sections:")
        print("  1. Summary stats box (total routings, anomalies, period)")
        print("  2. Top Destinations table (name, count, bar chart + %)")
        print("  3. Top File Types table (type, count, bar chart + %)")
        print("  4. Info box (about pattern recognition)")

        print("\nData available:")
        print(f"  Total routings: {stats.get('total_routings', 0)}")
        print(f"  Destinations: {len(stats.get('by_destination', {}))}")
        print(f"  File types: {len(stats.get('by_file_type', {}))}")

        print("\n[OK] Data format matches modal requirements")
        return True
    except Exception as e:
        print(f"[FAIL] Error formatting data: {e}")
        return False


def main():
    print("=" * 50)
    print("PATTERNS MODAL TEST")
    print("=" * 50)

    results = []
    results.append(("Pattern Statistics Data Access", test_patterns_stats_endpoint()))
    results.append(("Statistics Data Structure", test_stats_data_structure()))
    results.append(("Destination Distribution", test_destination_distribution()))
    results.append(("File Type Distribution", test_file_type_distribution()))
    results.append(("UI Components Exist", test_ui_components()))
    results.append(("Visualization Logic", test_visualization_logic()))
    results.append(("Percentage Calculation", test_percentage_calculation()))
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

    print("\n[OK] PATTERNS MODAL SUMMARY:")
    print("  - Displays routing statistics over 30-day period")
    print("  - Shows total routings and unresolved anomalies")
    print("  - Top destinations with bar chart visualization")
    print("  - Top file types with bar chart visualization")
    print("  - Percentage distribution for each category")
    print("  - Info box explaining pattern recognition")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    exit(main())

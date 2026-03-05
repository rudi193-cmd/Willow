"""
Test File Annotation System End-to-End
Tests database, module functions, API integration, and routing decision annotation.
"""

import sys
from pathlib import Path

# Add core to path
sys.path.insert(0, str(Path(__file__).parent))


def test_database():
    """Test 1: Database initialization"""
    print("\n[TEST 1] Database Initialization")
    print("-" * 50)

    from core import file_annotations

    # Initialize DB
    file_annotations.init_annotations_db()

    db_path = file_annotations.ANNOTATIONS_DB
    if db_path.exists():
        print(f"[OK] Database exists at: {db_path}")
        print(f"[OK] Database size: {db_path.stat().st_size} bytes")
        return True
    else:
        print(f"[FAIL] Database not found at: {db_path}")
        return False


def test_module_functions():
    """Test 2: Module functions"""
    print("\n[TEST 2] Module Functions")
    print("-" * 50)

    from core import file_annotations, patterns

    # Initialize patterns DB first (needed for routing_history)
    patterns.init_db()

    # Create a test routing decision
    routing_id = patterns.log_routing_decision(
        filename="test_file.py",
        file_type=".py",
        content_summary="Test Python script",
        routed_to=["test_node"],
        reason="Test routing",
        confidence=0.8
    )
    print(f"[OK] Created test routing decision with ID: {routing_id}")

    # Test provide_annotation
    try:
        file_annotations.provide_annotation(
            routing_id=routing_id,
            filename="test_file.py",
            routed_to=["test_node"],
            is_correct=False,
            notes="This should have gone to code_review, not test_node. It has imports and looks like production code.",
            corrected_destination=["code_review"],
            annotated_by="test_user"
        )
        print("[OK] provide_annotation() succeeded")
    except Exception as e:
        print(f"[FAIL] provide_annotation() failed: {e}")
        return False

    # Test get_unannotated_routings
    try:
        # Add another unannotated routing
        patterns.log_routing_decision(
            filename="another_file.md",
            file_type=".md",
            content_summary="Documentation file",
            routed_to=["documents"],
            reason="Markdown file",
            confidence=0.9
        )

        unannotated = file_annotations.get_unannotated_routings(limit=10)
        print(f"[OK] get_unannotated_routings() returned {len(unannotated)} entries")
        if len(unannotated) > 0:
            print(f"     First unannotated: {unannotated[0]['filename']}")
    except Exception as e:
        print(f"[FAIL] get_unannotated_routings() failed: {e}")
        return False

    # Test get_annotation_stats
    try:
        stats = file_annotations.get_annotation_stats()
        print(f"[OK] get_annotation_stats() returned:")
        print(f"     Total annotations: {stats['total_annotations']}")
        print(f"     Correct: {stats['correct_count']}, Incorrect: {stats['incorrect_count']}")
        print(f"     Accuracy: {stats['accuracy_rate']:.1f}%")
    except Exception as e:
        print(f"[FAIL] get_annotation_stats() failed: {e}")
        return False

    # Test get_annotations_by_file_type
    try:
        by_type = file_annotations.get_annotations_by_file_type()
        print(f"[OK] get_annotations_by_file_type() returned stats for {len(by_type)} file types")
    except Exception as e:
        print(f"[FAIL] get_annotations_by_file_type() failed: {e}")
        return False

    # Test get_recent_annotations
    try:
        recent = file_annotations.get_recent_annotations(limit=5)
        print(f"[OK] get_recent_annotations() returned {len(recent)} entries")
    except Exception as e:
        print(f"[FAIL] get_recent_annotations() failed: {e}")
        return False

    return True


def test_patterns_integration():
    """Test 3: Integration with patterns.py"""
    print("\n[TEST 3] Patterns Integration")
    print("-" * 50)

    try:
        from core import patterns, file_annotations

        # Create a routing and annotate it
        routing_id = patterns.log_routing_decision(
            filename="integration_test.js",
            file_type=".js",
            content_summary="JavaScript file",
            routed_to=["wrong_place"],
            reason="Extension-based routing",
            confidence=0.6
        )

        # Annotate it as wrong
        file_annotations.provide_annotation(
            routing_id=routing_id,
            filename="integration_test.js",
            routed_to=["wrong_place"],
            is_correct=False,
            notes="This is a React component and should go to frontend, not wrong_place",
            corrected_destination=["frontend"]
        )

        # Check that routing_history was updated
        conn = patterns._connect()
        result = conn.execute("SELECT user_corrected FROM routing_history WHERE id = ?", (routing_id,)).fetchone()
        conn.close()

        if result and result[0] == 1:
            print(f"[OK] routing_history.user_corrected flag updated correctly")
        else:
            print(f"[FAIL] routing_history.user_corrected flag not updated")
            return False

        print("[OK] Patterns integration verified")
        return True

    except Exception as e:
        print(f"[FAIL] Patterns integration test failed: {e}")
        return False


def test_server_endpoints():
    """Test 4: Server API endpoints"""
    print("\n[TEST 4] Server API Endpoints")
    print("-" * 50)

    import requests

    base_url = "http://127.0.0.1:8420"

    # Test GET /api/annotations/unannotated
    try:
        r = requests.get(f"{base_url}/api/annotations/unannotated?limit=5", timeout=5)
        if r.status_code == 200:
            data = r.json()
            print(f"[OK] GET /api/annotations/unannotated returned {data['count']} routings")
        else:
            print(f"[FAIL] GET /api/annotations/unannotated returned {r.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print(f"[SKIP] Server not running at {base_url}")
        print("       Start server with: python server.py")
        return None  # Skip, not failure
    except Exception as e:
        print(f"[FAIL] GET /api/annotations/unannotated failed: {e}")
        return False

    # Test GET /api/annotations/stats
    try:
        r = requests.get(f"{base_url}/api/annotations/stats", timeout=5)
        if r.status_code == 200:
            data = r.json()
            print(f"[OK] GET /api/annotations/stats returned stats")
            if data.get('overall'):
                print(f"     Total annotations: {data['overall'].get('total_annotations', 0)}")
                print(f"     Accuracy: {data['overall'].get('accuracy_rate', 0):.1f}%")
        else:
            print(f"[FAIL] GET /api/annotations/stats returned {r.status_code}")
            return False
    except Exception as e:
        print(f"[FAIL] GET /api/annotations/stats failed: {e}")
        return False

    # Test POST /api/annotations/provide
    try:
        from core import patterns

        # Create a routing to annotate
        routing_id = patterns.log_routing_decision(
            filename="api_test.txt",
            file_type=".txt",
            content_summary="API test file",
            routed_to=["test_dest"],
            reason="API test",
            confidence=0.5
        )

        payload = {
            "routing_id": routing_id,
            "filename": "api_test.txt",
            "routed_to": ["test_dest"],
            "is_correct": True,
            "notes": "This routing is correct - text files should go to test_dest"
        }
        r = requests.post(f"{base_url}/api/annotations/provide", json=payload, timeout=5)
        if r.status_code == 200:
            data = r.json()
            if data.get('success'):
                print(f"[OK] POST /api/annotations/provide succeeded")
            else:
                print(f"[FAIL] POST /api/annotations/provide failed: {data.get('error')}")
                return False
        else:
            print(f"[FAIL] POST /api/annotations/provide returned {r.status_code}")
            return False
    except Exception as e:
        print(f"[FAIL] POST /api/annotations/provide failed: {e}")
        return False

    return True


def test_ui_components():
    """Test 5: UI components"""
    print("\n[TEST 5] UI Components")
    print("-" * 50)

    dashboard_path = Path(__file__).parent / "system" / "dashboard.html"

    if not dashboard_path.exists():
        print(f"[FAIL] Dashboard not found at: {dashboard_path}")
        return False

    content = dashboard_path.read_text(encoding='utf-8')

    # Check for annotation section in Learning modal
    if 'File Routing Decisions (Verify & Annotate)' in content:
        print("[OK] Annotation section exists in Learning modal")
    else:
        print("[FAIL] Annotation section not found in Learning modal")
        return False

    # Check for openAnnotationForm function
    if 'function openAnnotationForm(' in content:
        print("[OK] openAnnotationForm() function exists")
    else:
        print("[FAIL] openAnnotationForm() function not found")
        return False

    # Check for annotation form container
    if 'id="annotation-form-container"' in content:
        print("[OK] Annotation form container exists")
    else:
        print("[FAIL] Annotation form container not found")
        return False

    # Check for submitAnnotation function
    if 'async function submitAnnotation()' in content:
        print("[OK] submitAnnotation() function exists")
    else:
        print("[FAIL] submitAnnotation() function not found")
        return False

    # Check for correct/wrong radio buttons
    if 'name="is-correct"' in content:
        print("[OK] Correct/Wrong radio buttons exist")
    else:
        print("[FAIL] Correct/Wrong radio buttons not found")
        return False

    return True


def main():
    """Run all tests"""
    print("=" * 50)
    print("FILE ANNOTATION SYSTEM - END-TO-END TEST")
    print("=" * 50)

    results = []

    results.append(("Database Initialization", test_database()))
    results.append(("Module Functions", test_module_functions()))
    results.append(("Patterns Integration", test_patterns_integration()))
    results.append(("Server API Endpoints", test_server_endpoints()))
    results.append(("UI Components", test_ui_components()))

    print("\n" + "=" * 50)
    print("TEST SUMMARY")
    print("=" * 50)

    passed = 0
    failed = 0
    skipped = 0

    for name, result in results:
        if result is True:
            print(f"[PASS] {name}")
            passed += 1
        elif result is False:
            print(f"[FAIL] {name}")
            failed += 1
        else:
            print(f"[SKIP] {name}")
            skipped += 1

    print("\n" + "=" * 50)
    print(f"Total: {passed} passed, {failed} failed, {skipped} skipped")

    if failed == 0:
        print("\n[OK] All tests passed!")
        return 0
    else:
        print(f"\n[FAIL] {failed} test(s) failed")
        return 1


if __name__ == "__main__":
    exit(main())

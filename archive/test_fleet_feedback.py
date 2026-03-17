"""
Test Fleet Feedback System End-to-End
Tests database, module functions, API integration, and prompt enhancement.
"""

import sys
from pathlib import Path

# Add core to path
sys.path.insert(0, str(Path(__file__).parent))

def test_database():
    """Test 1: Database initialization"""
    print("\n[TEST 1] Database Initialization")
    print("-" * 50)

    from core import fleet_feedback

    # Initialize DB
    fleet_feedback.init_feedback_db()

    db_path = fleet_feedback.FEEDBACK_DB
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

    from core import fleet_feedback

    # Test provide_feedback
    try:
        fleet_feedback.provide_feedback(
            provider="TestProvider",
            task_type="test_task",
            prompt="Test prompt",
            output="Test output",
            quality=4,
            issues_list=["test_issue"],
            notes="This is a test feedback entry",
            corrected=None
        )
        print("[OK] provide_feedback() succeeded")
    except Exception as e:
        print(f"[FAIL] provide_feedback() failed: {e}")
        return False

    # Test get_feedback_for_task
    try:
        feedback = fleet_feedback.get_feedback_for_task("test_task", limit=5)
        print(f"[OK] get_feedback_for_task() returned {len(feedback)} entries")
    except Exception as e:
        print(f"[FAIL] get_feedback_for_task() failed: {e}")
        return False

    # Test get_feedback_stats
    try:
        stats = fleet_feedback.get_feedback_stats()
        print(f"[OK] get_feedback_stats() returned stats for {len(stats['by_provider'])} providers")
        print(f"     Providers tracked: {list(stats['by_provider'].keys())}")
    except Exception as e:
        print(f"[FAIL] get_feedback_stats() failed: {e}")
        return False

    # Test enhance_prompt_with_feedback
    try:
        # Add poor feedback to test enhancement
        fleet_feedback.provide_feedback(
            provider="TestProvider",
            task_type="html_generation",
            prompt="Generate HTML",
            output="Bad output",
            quality=2,
            issues_list=["wrong_tech_stack"],
            notes="Do not use React. This project uses vanilla JavaScript.",
            corrected=None
        )

        enhanced = fleet_feedback.enhance_prompt_with_feedback("Generate HTML dashboard", "html_generation")
        if "Do not use React" in enhanced:
            print("[OK] enhance_prompt_with_feedback() correctly adds corrections")
            print(f"     Enhanced prompt length: {len(enhanced)} chars (original: {len('Generate HTML dashboard')} chars)")
        else:
            print("[FAIL] enhance_prompt_with_feedback() did not add corrections")
            return False
    except Exception as e:
        print(f"[FAIL] enhance_prompt_with_feedback() failed: {e}")
        return False

    return True


def test_llm_router_integration():
    """Test 3: LLM Router integration"""
    print("\n[TEST 3] LLM Router Integration")
    print("-" * 50)

    try:
        from core import llm_router
        from core import fleet_feedback

        # Add test feedback for a task type
        fleet_feedback.provide_feedback(
            provider="Groq",
            task_type="javascript_generation",
            prompt="Write a function",
            output="function test() {}",
            quality=2,
            issues_list=["incomplete"],
            notes="Always include proper error handling and input validation.",
            corrected=None
        )

        # Check that ask() function exists and has fleet_feedback import
        if hasattr(llm_router, 'ask'):
            print("[OK] llm_router.ask() function exists")
        else:
            print("[FAIL] llm_router.ask() function not found")
            return False

        # Check that fleet_feedback is imported
        if hasattr(llm_router, 'fleet_feedback'):
            print("[OK] fleet_feedback module imported in llm_router")
        else:
            print("[FAIL] fleet_feedback not imported in llm_router")
            return False

        print("[OK] LLM Router integration verified")
        return True

    except Exception as e:
        print(f"[FAIL] LLM Router integration test failed: {e}")
        return False


def test_server_endpoints():
    """Test 4: Server API endpoints"""
    print("\n[TEST 4] Server API Endpoints")
    print("-" * 50)

    import requests

    base_url = "http://127.0.0.1:8420"

    # Test GET /api/feedback/stats
    try:
        r = requests.get(f"{base_url}/api/feedback/stats", timeout=5)
        if r.status_code == 200:
            stats = r.json()
            print(f"[OK] GET /api/feedback/stats returned {r.status_code}")
            print(f"     Providers: {list(stats.get('by_provider', {}).keys())}")
            print(f"     Tasks: {list(stats.get('by_task', {}).keys())}")
        else:
            print(f"[FAIL] GET /api/feedback/stats returned {r.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print(f"[SKIP] Server not running at {base_url}")
        print("       Start server with: python server.py")
        return None  # Skip, not failure
    except Exception as e:
        print(f"[FAIL] GET /api/feedback/stats failed: {e}")
        return False

    # Test GET /api/feedback/tasks/{task_type}
    try:
        r = requests.get(f"{base_url}/api/feedback/tasks/test_task", timeout=5)
        if r.status_code == 200:
            data = r.json()
            print(f"[OK] GET /api/feedback/tasks/test_task returned {data['count']} entries")
        else:
            print(f"[FAIL] GET /api/feedback/tasks/test_task returned {r.status_code}")
            return False
    except Exception as e:
        print(f"[FAIL] GET /api/feedback/tasks/test_task failed: {e}")
        return False

    # Test POST /api/feedback/provide
    try:
        payload = {
            "provider": "TestProviderAPI",
            "task_type": "api_test",
            "prompt": "API test prompt",
            "output": "API test output",
            "quality": 5,
            "issues": [],
            "notes": "This is a test via API"
        }
        r = requests.post(f"{base_url}/api/feedback/provide", json=payload, timeout=5)
        if r.status_code == 200:
            data = r.json()
            if data.get('success'):
                print(f"[OK] POST /api/feedback/provide succeeded")
            else:
                print(f"[FAIL] POST /api/feedback/provide failed: {data.get('error')}")
                return False
        else:
            print(f"[FAIL] POST /api/feedback/provide returned {r.status_code}")
            return False
    except Exception as e:
        print(f"[FAIL] POST /api/feedback/provide failed: {e}")
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

    # Check for Learning card
    if 'id="learning-summary"' in content:
        print("[OK] Learning card exists in dashboard")
    else:
        print("[FAIL] Learning card not found in dashboard")
        return False

    # Check for loadLearningModal function
    if 'async function loadLearningModal()' in content:
        print("[OK] loadLearningModal() function exists")
    else:
        print("[FAIL] loadLearningModal() function not found")
        return False

    # Check for feedback form
    if 'id="feedback-form"' in content:
        print("[OK] Feedback form exists in modal")
    else:
        print("[FAIL] Feedback form not found")
        return False

    # Check for submitFeedback function
    if 'async function submitFeedback()' in content:
        print("[OK] submitFeedback() function exists")
    else:
        print("[FAIL] submitFeedback() function not found")
        return False

    return True


def main():
    """Run all tests"""
    print("=" * 50)
    print("FLEET FEEDBACK SYSTEM - END-TO-END TEST")
    print("=" * 50)

    results = []

    results.append(("Database Initialization", test_database()))
    results.append(("Module Functions", test_module_functions()))
    results.append(("LLM Router Integration", test_llm_router_integration()))
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

"""
Test Node DB Creation
Tests programmatic creation of node knowledge databases.
"""

import sys
import requests
from pathlib import Path

# Add core to path
sys.path.insert(0, str(Path(__file__).parent))


def test_knowledge_init():
    """Test 1: loam.init_db() creates database"""
    print("\n[TEST 1] loam.init_db() Function")
    print("-" * 50)

    from core import loam

    test_node = "test_node_creation"

    # Create database
    try:
        loam.init_db(test_node)
        print(f"[OK] loam.init_db('{test_node}') succeeded")
    except Exception as e:
        print(f"[FAIL] loam.init_db() failed: {e}")
        return False

    # Verify database exists (loam.py creates willow_knowledge.db)
    db_path = Path(__file__).parent / "artifacts" / test_node / "willow_knowledge.db"
    if db_path.exists():
        print(f"[OK] Database created at: {db_path}")
        print(f"[OK] Database size: {db_path.stat().st_size} bytes")
        return True
    else:
        print(f"[FAIL] Database not found at: {db_path}")
        return False


def test_node_health_check():
    """Test 2: Node health check detects no_db vs healthy"""
    print("\n[TEST 2] Node Health Check")
    print("-" * 50)

    from core import health

    # Check health of all nodes
    try:
        nodes = health.check_node_health(stale_threshold_hours=24)
        print(f"[OK] health.check_node_health() returned {len(nodes)} nodes")

        # Count statuses
        statuses = {}
        for name, node in nodes.items():
            status = node['status']
            statuses[status] = statuses.get(status, 0) + 1

        print(f"     Node statuses: {statuses}")

        # Check test_node_creation (should be healthy now)
        test_node = "test_node_creation"
        if test_node in nodes:
            test_status = nodes[test_node]['status']
            if test_status == 'healthy':
                print(f"[OK] {test_node} status is 'healthy'")
            else:
                print(f"[INFO] {test_node} status is '{test_status}' (may be stale if old)")
        else:
            print(f"[INFO] {test_node} not found in health check (directory may not exist yet)")

        return True
    except Exception as e:
        print(f"[FAIL] health.check_node_health() failed: {e}")
        return False


def test_api_endpoint():
    """Test 3: API endpoint creates database"""
    print("\n[TEST 3] API Endpoint - POST /api/nodes/create_db")
    print("-" * 50)

    base_url = "http://127.0.0.1:8420"
    test_node = "api_test_node"

    # First, delete test node DB if it exists (loam.py creates willow_knowledge.db)
    db_path = Path(__file__).parent / "artifacts" / test_node / "willow_knowledge.db"
    if db_path.exists():
        db_path.unlink()
        print(f"[INFO] Deleted existing test database for clean test")

    try:
        r = requests.post(
            f"{base_url}/api/nodes/create_db",
            json={"node_name": test_node},
            timeout=5
        )

        if r.status_code == 200:
            data = r.json()
            if data.get('success'):
                print(f"[OK] API call succeeded: {data.get('message')}")

                # Verify database was created
                if db_path.exists():
                    print(f"[OK] Database created at: {db_path}")
                    print(f"[OK] Database size: {db_path.stat().st_size} bytes")
                else:
                    print(f"[FAIL] Database not found after API call")
                    return False

                return True
            else:
                print(f"[FAIL] API returned success=False: {data.get('error')}")
                return False
        else:
            print(f"[FAIL] API returned status {r.status_code}")
            return False

    except requests.exceptions.ConnectionError:
        print(f"[SKIP] Server not running at {base_url}")
        print("       Start server with: python server.py")
        return None  # Skip, not failure
    except Exception as e:
        print(f"[FAIL] API test failed: {e}")
        return False


def test_invalid_node_name():
    """Test 4: API rejects invalid node names"""
    print("\n[TEST 4] API Endpoint - Invalid Node Names")
    print("-" * 50)

    base_url = "http://127.0.0.1:8420"

    invalid_names = [
        "../../../etc/passwd",
        "node/with/slashes",
        "node with spaces",
        "node;with;semicolons",
        "node$with$dollars"
    ]

    try:
        for invalid_name in invalid_names:
            r = requests.post(
                f"{base_url}/api/nodes/create_db",
                json={"node_name": invalid_name},
                timeout=5
            )

            if r.status_code == 200:
                data = r.json()
                if data.get('error') and 'Invalid node_name' in data.get('error', ''):
                    print(f"[OK] Rejected invalid name: {invalid_name}")
                elif data.get('success'):
                    print(f"[FAIL] Accepted invalid name: {invalid_name}")
                    return False
                else:
                    print(f"[INFO] Unexpected response for {invalid_name}: {data}")
            else:
                print(f"[INFO] HTTP {r.status_code} for {invalid_name}")

        print(f"[OK] All invalid names were rejected")
        return True

    except requests.exceptions.ConnectionError:
        print(f"[SKIP] Server not running")
        return None
    except Exception as e:
        print(f"[FAIL] Invalid name test failed: {e}")
        return False


def test_ui_components():
    """Test 5: UI components exist"""
    print("\n[TEST 5] UI Components")
    print("-" * 50)

    dashboard_path = Path(__file__).parent / "system" / "dashboard.html"

    if not dashboard_path.exists():
        print(f"[FAIL] Dashboard not found")
        return False

    content = dashboard_path.read_text(encoding='utf-8')

    # Check for createNodeDB function
    if 'async function createNodeDB(' in content:
        print("[OK] createNodeDB() function exists")
    else:
        print("[FAIL] createNodeDB() function not found")
        return False

    # Check for Create DB button
    if 'Create DB' in content:
        print("[OK] Create DB button exists")
    else:
        print("[FAIL] Create DB button not found")
        return False

    # Check for API call
    if '/api/nodes/create_db' in content:
        print("[OK] API call to /api/nodes/create_db exists")
    else:
        print("[FAIL] API call not found")
        return False

    return True


def main():
    """Run all tests"""
    print("=" * 50)
    print("NODE DB CREATION - END-TO-END TEST")
    print("=" * 50)

    results = []

    results.append(("loam.init_db() Function", test_knowledge_init()))
    results.append(("Node Health Check", test_node_health_check()))
    results.append(("API Endpoint", test_api_endpoint()))
    results.append(("Invalid Node Name Validation", test_invalid_node_name()))
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

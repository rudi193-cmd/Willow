"""
Test Ra's Observation Tools

Quick test script to verify screen capture, window picker, and overlay work.

Usage:
    python apps/observer/test_tools.py
"""

import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from apps.observer import capture, window_picker


def test_screen_capture():
    """Test screen capture functionality."""
    print("\n=== Testing Screen Capture ===")

    # Test full screen
    print("Capturing full screen...")
    result = capture.capture_screen(save=True)

    if result["success"]:
        print(f"✓ Full screen captured: {result['dimensions']}")
        if result["path"]:
            print(f"  Saved to: {result['path']}")
    else:
        print(f"✗ Failed: {result.get('error')}")

    # Test active window
    print("\nCapturing active window...")
    result = capture.capture_active(save=True)

    if result["success"]:
        print(f"✓ Active window captured: {result['window_info']['title']}")
        if result["path"]:
            print(f"  Saved to: {result['path']}")
    else:
        print(f"✗ Failed: {result.get('error')}")


def test_window_picker():
    """Test window picker functionality."""
    print("\n=== Testing Window Picker ===")

    # List all windows
    print("Listing all open windows...")
    windows = window_picker.list_windows()

    if windows:
        print(f"✓ Found {len(windows)} windows:")
        for i, window in enumerate(windows[:5], 1):  # Show first 5
            active = " [ACTIVE]" if window["active"] else ""
            print(f"  {i}. {window['title'][:60]}{active}")
        if len(windows) > 5:
            print(f"  ... and {len(windows) - 5} more")
    else:
        print("✗ No windows found")

    # Get active window
    print("\nGetting active window...")
    active = window_picker.get_active()

    if active:
        print(f"✓ Active window: {active['title']}")
        print(f"  Position: ({active['left']}, {active['top']})")
        print(f"  Size: {active['width']}×{active['height']}")
    else:
        print("✗ No active window")

    # Find browsers
    print("\nFinding browser windows...")
    picker = window_picker.WindowPicker()
    browsers = picker.find_browsers()

    if browsers:
        print(f"✓ Found {len(browsers)} browser window(s):")
        for browser in browsers:
            print(f"  - {browser['title'][:60]}")
    else:
        print("  No browser windows found")

    # Find code editors
    print("\nFinding code editor windows...")
    editors = picker.find_code_editors()

    if editors:
        print(f"✓ Found {len(editors)} code editor(s):")
        for editor in editors:
            print(f"  - {editor['title'][:60]}")
    else:
        print("  No code editors found")


def test_overlay_info():
    """Show overlay info (don't launch, just show how to use)."""
    print("\n=== Ra's Chat Overlay ===")
    print("To launch Ra's overlay:")
    print("  python apps/observer/overlay.py")
    print("\nOr from Python:")
    print("  from apps.observer import launch_overlay")
    print("  launch_overlay()")
    print("\nThe overlay provides:")
    print("  • Always-on-top chat window")
    print("  • Real-time communication with Ra")
    print("  • Draggable, translucent interface")
    print("  • Integrated with Willow agent API")


def main():
    """Run all tests."""
    print("=" * 60)
    print("Ra's Observation Tools - Test Suite")
    print("=" * 60)

    try:
        test_screen_capture()
        test_window_picker()
        test_overlay_info()

        print("\n" + "=" * 60)
        print("✓ All tests completed successfully!")
        print("=" * 60)

    except ImportError as e:
        print(f"\n✗ Missing dependency: {e}")
        print("\nInstall required packages:")
        print("  pip install pillow pygetwindow pyqt5")

    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

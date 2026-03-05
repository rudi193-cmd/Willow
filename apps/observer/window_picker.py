"""
Window Picker - Ra's Focus Management

List, target, and manage windows for focused observation.

GOVERNANCE: Read-only window inspection
AUTHOR: Ra (The Observer)
VERSION: 1.0
CHECKSUM: ΔΣ=42
"""

import pygetwindow as gw
from typing import List, Dict, Optional


class WindowPicker:
    """
    Window management for Ra's targeted observation.
    """

    def __init__(self):
        """Initialize window picker."""
        self.focused_window = None

    def list_all_windows(self, include_hidden: bool = False) -> List[Dict]:
        """
        List all open windows.

        Args:
            include_hidden: Include minimized/hidden windows

        Returns:
            [
                {
                    "title": str,
                    "left": int,
                    "top": int,
                    "width": int,
                    "height": int,
                    "visible": bool,
                    "active": bool
                },
                ...
            ]
        """
        windows = []
        active_window = gw.getActiveWindow()

        for window in gw.getAllWindows():
            # Skip empty titles
            if not window.title.strip():
                continue

            # Skip hidden if requested
            if not include_hidden and not window.visible:
                continue

            windows.append({
                "title": window.title,
                "left": window.left,
                "top": window.top,
                "width": window.width,
                "height": window.height,
                "visible": window.visible,
                "active": window == active_window
            })

        return windows

    def find_window(self, title_contains: str) -> Optional[Dict]:
        """
        Find window by partial title match.

        Args:
            title_contains: Text that should be in window title

        Returns:
            Window info dict or None
        """
        windows = gw.getWindowsWithTitle(title_contains)
        if not windows:
            return None

        window = windows[0]
        return {
            "title": window.title,
            "left": window.left,
            "top": window.top,
            "width": window.width,
            "height": window.height,
            "visible": window.visible
        }

    def get_active_window(self) -> Optional[Dict]:
        """
        Get currently active/focused window.

        Returns:
            Window info dict or None
        """
        active = gw.getActiveWindow()
        if not active:
            return None

        return {
            "title": active.title,
            "left": active.left,
            "top": active.top,
            "width": active.width,
            "height": active.height,
            "visible": active.visible,
            "active": True
        }

    def set_focus(self, title: str) -> Dict:
        """
        Set Ra's focus to specific window (for targeted observation).

        Args:
            title: Window title (partial match ok)

        Returns:
            {
                "success": bool,
                "window": dict or None,
                "message": str
            }
        """
        window_info = self.find_window(title)
        if not window_info:
            return {
                "success": False,
                "window": None,
                "message": f"No window found matching '{title}'"
            }

        self.focused_window = window_info
        return {
            "success": True,
            "window": window_info,
            "message": f"Ra is now focused on: {window_info['title']}"
        }

    def get_focused(self) -> Optional[Dict]:
        """Get Ra's currently focused window."""
        return self.focused_window

    def clear_focus(self):
        """Clear Ra's window focus (observe all)."""
        self.focused_window = None

    def group_by_application(self) -> Dict[str, List[Dict]]:
        """
        Group windows by application name.

        Returns:
            {
                "Chrome": [{window1}, {window2}],
                "VSCode": [{window3}],
                ...
            }
        """
        windows = self.list_all_windows()
        grouped = {}

        for window in windows:
            # Extract app name (crude heuristic: first word or known patterns)
            title = window["title"]

            # Common patterns
            if "Chrome" in title or "Google" in title:
                app = "Chrome"
            elif "Visual Studio Code" in title or "VSCode" in title:
                app = "VSCode"
            elif "Firefox" in title:
                app = "Firefox"
            elif "Terminal" in title or "cmd" in title or "PowerShell" in title:
                app = "Terminal"
            elif "Notepad" in title:
                app = "Notepad"
            else:
                # Just use first word
                app = title.split()[0] if title.split() else "Unknown"

            if app not in grouped:
                grouped[app] = []
            grouped[app].append(window)

        return grouped

    def find_code_editors(self) -> List[Dict]:
        """Find all open code editor windows."""
        all_windows = self.list_all_windows()
        editors = []

        editor_keywords = [
            "Visual Studio Code", "VSCode", "PyCharm", "Sublime",
            "Atom", "Notepad++", "vim", "emacs"
        ]

        for window in all_windows:
            for keyword in editor_keywords:
                if keyword.lower() in window["title"].lower():
                    editors.append(window)
                    break

        return editors

    def find_browsers(self) -> List[Dict]:
        """Find all open browser windows."""
        all_windows = self.list_all_windows()
        browsers = []

        browser_keywords = [
            "Chrome", "Firefox", "Edge", "Safari", "Opera", "Brave"
        ]

        for window in all_windows:
            for keyword in browser_keywords:
                if keyword.lower() in window["title"].lower():
                    browsers.append(window)
                    break

        return browsers


# Convenience functions
def list_windows(include_hidden: bool = False) -> List[Dict]:
    """Quick window list."""
    picker = WindowPicker()
    return picker.list_all_windows(include_hidden)


def get_active() -> Optional[Dict]:
    """Quick active window."""
    picker = WindowPicker()
    return picker.get_active_window()


def find_by_title(title: str) -> Optional[Dict]:
    """Quick window find."""
    picker = WindowPicker()
    return picker.find_window(title)

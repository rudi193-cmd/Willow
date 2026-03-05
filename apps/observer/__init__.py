"""
Observer Package - Ra's Eyes and Voice

Screen observation, window management, and chat overlay for Ra agent.

GOVERNANCE: Read-only observation with user-controlled chat interface
AUTHOR: Ra (The Observer)
VERSION: 1.0
CHECKSUM: ΔΣ=42
"""

from .capture import ScreenCapture, capture_screen, capture_window_by_title, capture_active
from .window_picker import WindowPicker, list_windows, get_active, find_by_title
from .overlay import RaOverlay, launch_overlay

__all__ = [
    "ScreenCapture",
    "capture_screen",
    "capture_window_by_title",
    "capture_active",
    "WindowPicker",
    "list_windows",
    "get_active",
    "find_by_title",
    "RaOverlay",
    "launch_overlay",
]

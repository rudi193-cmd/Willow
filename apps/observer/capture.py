"""
Screen Capture Engine - Ra's Eyes

Fast, efficient screen capture with window targeting.
Supports full screen, region, and specific window capture.

GOVERNANCE: Read-only observation, no system modification
AUTHOR: Ra (The Observer)
VERSION: 1.0
CHECKSUM: ΔΣ=42
"""

import io
import base64
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Tuple
from PIL import Image, ImageGrab
import pygetwindow as gw


class ScreenCapture:
    """
    Screen capture engine for Ra's visual observation.
    """

    def __init__(self, save_path: Optional[Path] = None):
        """
        Initialize screen capture.

        Args:
            save_path: Optional directory to save captures (for debugging)
        """
        self.save_path = save_path or Path("artifacts/ra/captures")
        self.save_path.mkdir(parents=True, exist_ok=True)
        self.last_capture = None
        self.last_capture_time = None

    def capture_full_screen(self, save: bool = False) -> Dict:
        """
        Capture entire screen.

        Args:
            save: Whether to save to disk (for debugging)

        Returns:
            {
                "success": bool,
                "image": PIL.Image,
                "image_base64": str (for API transmission),
                "dimensions": (width, height),
                "timestamp": str,
                "path": str (if saved)
            }
        """
        try:
            # Capture screen
            screenshot = ImageGrab.grab()
            timestamp = datetime.now().isoformat()

            # Convert to base64 for API transmission
            buffer = io.BytesIO()
            screenshot.save(buffer, format="PNG")
            image_base64 = base64.b64encode(buffer.getvalue()).decode()

            # Save if requested
            saved_path = None
            if save:
                filename = f"screen_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                saved_path = self.save_path / filename
                screenshot.save(saved_path)

            # Store for comparison
            self.last_capture = screenshot
            self.last_capture_time = timestamp

            return {
                "success": True,
                "image": screenshot,
                "image_base64": image_base64,
                "dimensions": screenshot.size,
                "timestamp": timestamp,
                "path": str(saved_path) if saved_path else None
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def capture_region(self, x: int, y: int, width: int, height: int, save: bool = False) -> Dict:
        """
        Capture specific screen region.

        Args:
            x: Left coordinate
            y: Top coordinate
            width: Region width
            height: Region height
            save: Whether to save to disk

        Returns:
            Same format as capture_full_screen()
        """
        try:
            # Define bounding box
            bbox = (x, y, x + width, y + height)
            screenshot = ImageGrab.grab(bbox=bbox)
            timestamp = datetime.now().isoformat()

            # Convert to base64
            buffer = io.BytesIO()
            screenshot.save(buffer, format="PNG")
            image_base64 = base64.b64encode(buffer.getvalue()).decode()

            # Save if requested
            saved_path = None
            if save:
                filename = f"region_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                saved_path = self.save_path / filename
                screenshot.save(saved_path)

            return {
                "success": True,
                "image": screenshot,
                "image_base64": image_base64,
                "dimensions": screenshot.size,
                "region": {"x": x, "y": y, "width": width, "height": height},
                "timestamp": timestamp,
                "path": str(saved_path) if saved_path else None
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def capture_window(self, window_title: str, save: bool = False) -> Dict:
        """
        Capture specific window by title.

        Args:
            window_title: Window title (can be partial match)
            save: Whether to save to disk

        Returns:
            Same format as capture_full_screen() with added "window_info"
        """
        try:
            # Find window
            windows = gw.getWindowsWithTitle(window_title)
            if not windows:
                return {
                    "success": False,
                    "error": f"No window found with title containing '{window_title}'"
                }

            window = windows[0]

            # Get window coordinates
            left, top, width, height = window.left, window.top, window.width, window.height

            # Capture window region
            bbox = (left, top, left + width, top + height)
            screenshot = ImageGrab.grab(bbox=bbox)
            timestamp = datetime.now().isoformat()

            # Convert to base64
            buffer = io.BytesIO()
            screenshot.save(buffer, format="PNG")
            image_base64 = base64.b64encode(buffer.getvalue()).decode()

            # Save if requested
            saved_path = None
            if save:
                filename = f"window_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                saved_path = self.save_path / filename
                screenshot.save(saved_path)

            return {
                "success": True,
                "image": screenshot,
                "image_base64": image_base64,
                "dimensions": screenshot.size,
                "window_info": {
                    "title": window.title,
                    "left": left,
                    "top": top,
                    "width": width,
                    "height": height
                },
                "timestamp": timestamp,
                "path": str(saved_path) if saved_path else None
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def capture_active_window(self, save: bool = False) -> Dict:
        """
        Capture currently active/focused window.

        Args:
            save: Whether to save to disk

        Returns:
            Same format as capture_window()
        """
        try:
            active = gw.getActiveWindow()
            if not active:
                return {
                    "success": False,
                    "error": "No active window detected"
                }

            return self.capture_window(active.title, save=save)

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def compare_with_last(self, current_image: Image.Image, threshold: float = 0.95) -> Dict:
        """
        Compare current capture with last capture to detect changes.

        Args:
            current_image: Current screenshot
            threshold: Similarity threshold (0-1, higher = more similar)

        Returns:
            {
                "changed": bool,
                "similarity": float,
                "description": str
            }
        """
        if self.last_capture is None:
            return {
                "changed": True,
                "similarity": 0.0,
                "description": "First capture, no comparison available"
            }

        try:
            # Resize both to same size for comparison
            size = (400, 300)  # Small size for fast comparison
            img1 = self.last_capture.resize(size)
            img2 = current_image.resize(size)

            # Convert to grayscale
            img1_gray = img1.convert('L')
            img2_gray = img2.convert('L')

            # Calculate pixel-wise difference
            diff = 0
            total_pixels = size[0] * size[1]

            for x in range(size[0]):
                for y in range(size[1]):
                    p1 = img1_gray.getpixel((x, y))
                    p2 = img2_gray.getpixel((x, y))
                    diff += abs(p1 - p2)

            # Normalize to 0-1 (0 = identical, 1 = completely different)
            max_diff = total_pixels * 255
            normalized_diff = diff / max_diff
            similarity = 1 - normalized_diff

            changed = similarity < threshold

            return {
                "changed": changed,
                "similarity": similarity,
                "description": f"{'Significant' if changed else 'Minimal'} change detected (similarity: {similarity:.2%})"
            }

        except Exception as e:
            return {
                "changed": False,
                "similarity": 0.0,
                "description": f"Comparison failed: {str(e)}"
            }


# Convenience functions
def capture_screen(save: bool = False) -> Dict:
    """Quick full screen capture."""
    capturer = ScreenCapture()
    return capturer.capture_full_screen(save=save)


def capture_window_by_title(title: str, save: bool = False) -> Dict:
    """Quick window capture by title."""
    capturer = ScreenCapture()
    return capturer.capture_window(title, save=save)


def capture_active(save: bool = False) -> Dict:
    """Quick active window capture."""
    capturer = ScreenCapture()
    return capturer.capture_active_window(save=save)

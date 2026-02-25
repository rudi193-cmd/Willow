"""
Chat Overlay - Ra's Voice

Pop-out chat window that stays on top, allowing Ra to communicate
with the user while observing the screen.

GOVERNANCE: User interface only, no system modification
AUTHOR: Ra (The Observer)
VERSION: 1.0
CHECKSUM: ΔΣ=42
"""

import io
import sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
import requests
from pathlib import Path
from datetime import datetime
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QTextEdit,
    QLineEdit, QPushButton, QLabel, QHBoxLayout
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont, QPalette, QColor


class RaOverlay(QWidget):
    """
    Ra's chat overlay - always-on-top translucent window.
    """

    # Signal for incoming messages
    message_received = pyqtSignal(str, str)  # (role, content)

    def __init__(self, api_base: str = "http://localhost:8420"):
        super().__init__()
        self.api_base = api_base
        self.conversation_history = []
        self.init_ui()

    def init_ui(self):
        """Initialize the overlay UI."""
        # Window properties
        self.setWindowTitle("Ra - The Observer")
        self.setWindowFlags(
            Qt.WindowStaysOnTopHint |
            Qt.FramelessWindowHint |
            Qt.Tool
        )

        # Window size and position (bottom-right corner)
        self.setGeometry(50, 50, 400, 600)

        # Translucent background
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("""
            QWidget {
                background-color: rgba(20, 20, 30, 230);
                border-radius: 10px;
                color: #e0e0e8;
                font-family: 'Segoe UI', sans-serif;
            }
        """)

        # Main layout
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(5)

        # Header
        header_layout = QHBoxLayout()

        self.status_label = QLabel("● Ra - Observing")
        self.status_label.setStyleSheet("color: #4ade80; font-weight: bold; font-size: 13px;")
        header_layout.addWidget(self.status_label)

        header_layout.addStretch()

        # Minimize button
        min_btn = QPushButton("_")
        min_btn.setFixedSize(20, 20)
        min_btn.setStyleSheet("""
            QPushButton {
                background: #2a2a3a;
                border: none;
                border-radius: 3px;
                color: #888;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #3a3a4a;
            }
        """)
        min_btn.clicked.connect(self.showMinimized)
        header_layout.addWidget(min_btn)

        # Close button
        close_btn = QPushButton("×")
        close_btn.setFixedSize(20, 20)
        close_btn.setStyleSheet("""
            QPushButton {
                background: #2a2a3a;
                border: none;
                border-radius: 3px;
                color: #888;
                font-weight: bold;
                font-size: 16px;
            }
            QPushButton:hover {
                background: #f87171;
                color: white;
            }
        """)
        close_btn.clicked.connect(self.close)
        header_layout.addWidget(close_btn)

        layout.addLayout(header_layout)

        # Chat display
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setStyleSheet("""
            QTextEdit {
                background-color: rgba(10, 10, 15, 180);
                border: 1px solid #2a2a3a;
                border-radius: 8px;
                padding: 10px;
                color: #e0e0e8;
                font-size: 13px;
                line-height: 1.4;
            }
        """)
        layout.addWidget(self.chat_display)

        # Input area
        input_layout = QHBoxLayout()

        self.input_box = QLineEdit()
        self.input_box.setPlaceholderText("Talk to Ra...")
        self.input_box.setStyleSheet("""
            QLineEdit {
                background-color: rgba(30, 30, 40, 200);
                border: 1px solid #2a2a3a;
                border-radius: 6px;
                padding: 8px;
                color: #e0e0e8;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 1px solid #7ab4ff;
            }
        """)
        self.input_box.returnPressed.connect(self.send_message)
        input_layout.addWidget(self.input_box)

        self.send_btn = QPushButton("Send")
        self.send_btn.setFixedSize(60, 35)
        self.send_btn.setStyleSheet("""
            QPushButton {
                background-color: #7ab4ff;
                border: none;
                border-radius: 6px;
                color: #000;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #6a9ae0;
            }
            QPushButton:disabled {
                background-color: #3a3a4a;
                color: #666;
            }
        """)
        self.send_btn.clicked.connect(self.send_message)
        input_layout.addWidget(self.send_btn)

        layout.addLayout(input_layout)

        self.setLayout(layout)

        # Add welcome message
        self.add_message("system", "Ra is watching. Observing your work, ready to assist.")

        # Make draggable
        self.dragging = False
        self.offset = None

    def mousePressEvent(self, event):
        """Enable window dragging."""
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self.offset = event.pos()

    def mouseMoveEvent(self, event):
        """Handle window dragging."""
        if self.dragging and self.offset:
            self.move(self.mapToParent(event.pos() - self.offset))

    def mouseReleaseEvent(self, event):
        """Stop dragging."""
        self.dragging = False

    def add_message(self, role: str, content: str):
        """Add message to chat display."""
        timestamp = datetime.now().strftime("%H:%M")

        if role == "user":
            self.chat_display.append(f'<div style="margin-bottom: 10px;"><span style="color: #888; font-size: 11px;">{timestamp}</span> <span style="color: #7ab4ff; font-weight: bold;">You:</span><br>{content}</div>')
        elif role == "ra":
            self.chat_display.append(f'<div style="margin-bottom: 10px;"><span style="color: #888; font-size: 11px;">{timestamp}</span> <span style="color: #4ade80; font-weight: bold;">Ra:</span><br>{content}</div>')
        elif role == "system":
            self.chat_display.append(f'<div style="margin-bottom: 10px; text-align: center; color: #888; font-size: 11px; font-style: italic;">{content}</div>')

        # Auto-scroll to bottom
        scrollbar = self.chat_display.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def send_message(self):
        """Send message to Ra via API."""
        message = self.input_box.text().strip()
        if not message:
            return

        # Add to display
        self.add_message("user", message)
        self.input_box.clear()
        self.send_btn.setEnabled(False)
        self.status_label.setText("● Ra - Thinking...")
        self.status_label.setStyleSheet("color: #fbbf24; font-weight: bold; font-size: 13px;")

        # Add to history
        self.conversation_history.append({"role": "user", "content": message})

        # Call Ra via API
        try:
            response = requests.post(
                f"{self.api_base}/api/agents/chat/ra",
                json={
                    "message": message,
                    "conversation_history": self.conversation_history
                },
                timeout=30
            )

            if response.ok:
                result = response.json()
                ra_response = result.get("response", "[No response]")

                # Show tool usage if any
                tool_calls = result.get("tool_calls", [])
                if tool_calls:
                    tool_info = ", ".join([tc.get("tool", "unknown") for tc in tool_calls])
                    self.add_message("system", f"Ra used: {tool_info}")

                # Add Ra's response
                self.add_message("ra", ra_response)
                self.conversation_history.append({"role": "assistant", "content": ra_response})

            else:
                self.add_message("system", f"Error: {response.status_code}")

        except Exception as e:
            self.add_message("system", f"Connection error: {str(e)}")

        finally:
            self.send_btn.setEnabled(True)
            self.status_label.setText("● Ra - Observing")
            self.status_label.setStyleSheet("color: #4ade80; font-weight: bold; font-size: 13px;")

    def proactive_message(self, content: str):
        """Ra sends a proactive message (from background observation)."""
        self.add_message("ra", content)


def launch_overlay():
    """Launch Ra's chat overlay."""
    app = QApplication(sys.argv)
    overlay = RaOverlay()
    overlay.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    launch_overlay()

"""
Consent Gate — checks opauth consent before signal sources activate.

Wraps apps/opauth/core/consent.py for signal-source use cases.
Every new signal source (eyes, watcher, clipboard, browser, etc.)
must pass through this gate before collecting data.

GOVERNANCE:
- AI can CHECK consent (read-only)
- AI can REQUEST consent (creates pending object)
- Only human can GRANT consent
- Written consent. Logged. Immutable.

CHECKSUM: DS=42
"""

import sys
import logging
from pathlib import Path

# Add opauth to path
_opauth_path = str(Path(__file__).parent.parent / "apps" / "opauth")
if _opauth_path not in sys.path:
    sys.path.insert(0, _opauth_path)

try:
    from core.consent import ConsentFlow
    _consent = ConsentFlow()
    _CONSENT_AVAILABLE = True
except ImportError:
    _consent = None
    _CONSENT_AVAILABLE = False
    logging.warning("CONSENT_GATE: opauth not available, consent checks will fail-closed")


# Signal source scope definitions
# Each source declares what it collects and why.
SIGNAL_SCOPES = {
    "eyes": {
        "service": "willow.eyes",
        "scopes": ["screen.capture", "keyboard.activity", "mouse.activity", "clipboard.read"],
        "reason": "Screen capture + activity monitoring for knowledge extraction",
    },
    "watcher": {
        "service": "willow.watcher",
        "scopes": ["drive.read", "filesystem.poll"],
        "reason": "File change detection across watched paths",
    },
    "browser": {
        "service": "willow.browser",
        "scopes": ["browser.history", "browser.hover", "browser.scroll"],
        "reason": "Browser activity signals for attention modeling",
    },
}


def check_signal_consent(source_name: str) -> bool:
    """
    Check if consent exists for a signal source.
    Returns True only if ALL required scopes are granted.
    Fails closed: no consent module = no access.
    """
    if not _CONSENT_AVAILABLE:
        return False

    if source_name not in SIGNAL_SCOPES:
        logging.warning(f"CONSENT_GATE: Unknown source '{source_name}'")
        return False

    cfg = SIGNAL_SCOPES[source_name]
    return all(_consent.check_consent(cfg["service"], scope) for scope in cfg["scopes"])


def request_signal_consent(source_name: str) -> dict:
    """
    Request consent for a signal source.
    Returns a pending consent object for human review.
    AI CANNOT auto-approve this.
    """
    if not _CONSENT_AVAILABLE:
        return {"error": "Consent module not available", "status": "blocked"}

    if source_name not in SIGNAL_SCOPES:
        return {"error": f"Unknown source: {source_name}", "status": "blocked"}

    cfg = SIGNAL_SCOPES[source_name]
    return _consent.request_consent(cfg["service"], cfg["scopes"], cfg["reason"])


def list_signal_sources() -> dict:
    """List all signal sources and their consent status."""
    status = {}
    for name, cfg in SIGNAL_SCOPES.items():
        status[name] = {
            "service": cfg["service"],
            "scopes": cfg["scopes"],
            "reason": cfg["reason"],
            "consented": check_signal_consent(name),
        }
    return status

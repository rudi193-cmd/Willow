"""
n2n_dispatcher.py — N2N Packet Router

App registry for the N2N system. External apps register handlers by PacketType.
When a packet arrives, the dispatcher routes it to the correct handler.

No HTTP. Direct Postgres via n2n_db / get_connection().

Registration pattern:
    from core.n2n_dispatcher import N2NDispatcher
    from core.n2n_packets import PacketType

    def my_handler(packet: dict) -> dict | None:
        payload = packet["payload"]
        # do work
        return {"status": "ok", "result": ...}

    N2NDispatcher.register("my_app", [PacketType.DELTA], my_handler)

Dispatch is called by N2NListener on every inbound packet.
If no handler is found for a packet, it is logged and dropped.

GOVERNANCE: Read-only routing. Handlers are responsible for their own writes.
CHECKSUM: ΔΣ=42
"""

import logging
from typing import Callable, Dict, List, Optional, Tuple
from core.n2n_packets import PacketType

log = logging.getLogger("n2n_dispatcher")

# Registry: (app_name, packet_type_value) -> handler
# app_name=None means "catch-all for this type"
_REGISTRY: Dict[Tuple[Optional[str], str], Callable] = {}


def register(app_name: Optional[str], packet_types: List[PacketType], handler: Callable) -> None:
    """
    Register a handler for one or more packet types.

    Args:
        app_name:     Name of the external app (e.g. "jac"). Use None for
                      a type-level catch-all (matches any packet of that type
                      regardless of payload["app"]).
        packet_types: List of PacketType values this handler responds to.
        handler:      Callable(packet: dict) -> dict | None.
                      Return value is a result payload (sent back as DELTA to
                      source node by the listener). Return None to skip reply.
    """
    for pt in packet_types:
        key = (app_name, pt.value)
        _REGISTRY[key] = handler
        log.debug("Registered handler: app=%s type=%s fn=%s", app_name, pt.value, handler.__name__)


def dispatch(packet: dict) -> Optional[dict]:
    """
    Route a packet to its registered handler.

    Routing precedence:
        1. (app_name, packet_type) — app-specific handler
        2. (None, packet_type)     — type-level catch-all

    Args:
        packet: Raw packet dict from N2NDatabase.receive_packets()

    Returns:
        Handler return value (result payload), or None if unhandled.
    """
    ptype = packet.get("packet_type", "")
    app   = packet.get("payload", {}).get("app", None)

    handler = None
    if app:
        handler = _REGISTRY.get((app, ptype))
    if handler is None:
        handler = _REGISTRY.get((None, ptype))

    if handler is None:
        log.debug("No handler for packet type=%s app=%s — dropped", ptype, app)
        return None

    try:
        return handler(packet)
    except Exception as e:
        log.error("Handler error (type=%s app=%s): %s", ptype, app, e)
        return None


def registered_apps() -> List[str]:
    """Return list of registered app names (for status/debug)."""
    return sorted({app for app, _ in _REGISTRY if app is not None})

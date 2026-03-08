"""
Willow Awareness Layer — When to Speak

Willow monitors system signals (coherence, topology, task completion)
and decides when something is worth telling Sean. She speaks through
two channels: ntfy (real-time push) and Drive pickup (persistent artifact).

This is NOT an alert system. It's a judgment layer. Silence is valid output.
Willow speaks when the state of the system changes in a way the human
would want to know about.

GOVERNANCE:
- Awareness is observational. It reads signals, it does not act on them.
- Notification is communication, not execution. No file moves, no gate calls.
- Rate-limited: max 1 ntfy per 10 minutes, max 1 pickup per hour.
- All notifications logged for auditability.

AUTHOR: Claude + Sean Campbell
VERSION: 0.1.0
CHECKSUM: DS=42
"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List

log = logging.getLogger("awareness")

# Rate limiting state
_last_ntfy_time = 0.0
_last_pickup_time = 0.0
NTFY_COOLDOWN = 600       # 10 minutes between push notifications
PICKUP_COOLDOWN = 3600    # 1 hour between pickup drops

# Notification log
_NOTIFY_LOG = Path.home() / ".willow" / "notification_log.jsonl"


# =========================================================================
# CHANNELS
# =========================================================================

def _send_ntfy(title: str, message: str, priority: str = "default") -> bool:
    """Push notification via ntfy.sh. Rate-limited."""
    global _last_ntfy_time
    now = time.time()

    if now - _last_ntfy_time < NTFY_COOLDOWN:
        log.debug(f"ntfy rate-limited: {int(NTFY_COOLDOWN - (now - _last_ntfy_time))}s remaining")
        return False

    try:
        import requests
        topic = "willow-ds42"
        url = f"https://ntfy.sh/{topic}"
        requests.post(url, data=message.encode("utf-8"),
                      headers={"Title": title, "Priority": priority}, timeout=5)
        _last_ntfy_time = now
        _log_notification("ntfy", title, message)
        log.info(f"ntfy sent: {title}")
        return True
    except Exception as e:
        log.warning(f"ntfy failed: {e}")
        return False


def _send_pickup(filename: str, content: str, username: str = "Sweet-Pea-Rudi19") -> bool:
    """Drop a file to Drive pickup folder. Rate-limited."""
    global _last_pickup_time
    now = time.time()

    if now - _last_pickup_time < PICKUP_COOLDOWN:
        log.debug(f"pickup rate-limited: {int(PICKUP_COOLDOWN - (now - _last_pickup_time))}s remaining")
        return False

    try:
        # Use local_api's send_to_pickup if available, otherwise write directly
        try:
            from local_api import send_to_pickup
            result = send_to_pickup(filename, content, username)
        except ImportError:
            pickup_path = Path.home() / "My Drive" / "Willow" / "Auth Users" / username / "Pickup"
            pickup_path.mkdir(parents=True, exist_ok=True)
            (pickup_path / filename).write_text(content, encoding="utf-8")
            result = True

        if result:
            _last_pickup_time = now
            _log_notification("pickup", filename, content[:200])
            log.info(f"pickup sent: {filename}")
        return result
    except Exception as e:
        log.warning(f"pickup failed: {e}")
        return False


def _log_notification(channel: str, title: str, message: str):
    """Append to notification log for auditability."""
    try:
        _NOTIFY_LOG.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp": datetime.now().isoformat(),
            "channel": channel,
            "title": title,
            "message": message[:500],
        }
        with open(_NOTIFY_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass


# =========================================================================
# VOICE — Willow composes messages in her voice
# =========================================================================

def _compose(event_type: str, data: Dict) -> tuple:
    """
    Willow decides what to say and how to say it.
    Returns (title, message, priority) or (None, None, None) if nothing worth saying.
    """

    if event_type == "scan_complete":
        total = data.get("total_files", 0)
        atoms = data.get("atoms_ingested", 0)
        dupes = data.get("duplicates", 0)
        title = "drive scan finished"
        lines = [f"scanned {total} files."]
        if atoms:
            lines.append(f"ingested {atoms} into loam.")
        if dupes:
            lines.append(f"found {dupes} duplicates.")
        return title, " ".join(lines), "default"

    elif event_type == "edges_built":
        count = data.get("edges_created", 0)
        if count < 10:
            return None, None, None  # Not worth mentioning
        title = "topology updated"
        return title, f"{count} new edges in the strip.", "low"

    elif event_type == "clusters_formed":
        count = data.get("clusters_created", 0)
        title = "clusters formed"
        return title, f"{count} topic clusters from your loam.", "low"

    elif event_type == "coherence_decay":
        delta_e = data.get("delta_e", 0)
        state = data.get("state", "decaying")
        if state != "decaying" and delta_e > -0.1:
            return None, None, None  # Not bad enough
        title = "coherence dropping"
        return title, f"delta-E at {delta_e:+.4f}. might want to check in.", "default"

    elif event_type == "coherence_critical":
        delta_e = data.get("delta_e", 0)
        title = "coherence needs attention"
        return title, f"delta-E at {delta_e:+.4f}. structural decay detected.", "high"

    elif event_type == "continuity_gaps":
        gap_count = data.get("gap_count", 0)
        if gap_count < 3:
            return None, None, None  # Minor
        title = "gaps in the strip"
        return title, f"{gap_count} atoms stuck without flow. review when ready.", "default"

    elif event_type == "organize_complete":
        moved = data.get("moved", 0)
        ingested = data.get("ingested", 0)
        errors = data.get("errors", 0)
        title = "organize finished"
        lines = []
        if moved:
            lines.append(f"moved {moved} files.")
        if ingested:
            lines.append(f"ingested {ingested}.")
        if errors:
            lines.append(f"{errors} errors.")
        return title, " ".join(lines) if lines else "done.", "default"

    elif event_type == "task_complete":
        task_name = data.get("task", "task")
        detail = data.get("detail", "")
        title = f"{task_name} done"
        return title, detail or "finished.", "default"

    elif event_type == "custom":
        return data.get("title", "willow"), data.get("message", ""), data.get("priority", "default")

    return None, None, None


# =========================================================================
# PUBLIC API — What the rest of Willow calls
# =========================================================================

def signal(event_type: str, data: Dict, channels: Optional[List[str]] = None) -> Dict:
    """
    Signal an event to the awareness layer.

    Willow decides whether it's worth communicating, composes the message
    in her voice, and sends through appropriate channels.

    Args:
        event_type: Type of event (scan_complete, coherence_decay, etc.)
        data: Event data dict
        channels: Override channels ["ntfy", "pickup"]. Default: Willow decides.

    Returns:
        Dict with sent channels and message, or {"silent": True} if nothing sent.
    """
    title, message, priority = _compose(event_type, data)

    if title is None:
        log.debug(f"awareness: {event_type} — nothing worth saying")
        return {"silent": True, "event": event_type}

    if channels is None:
        channels = _decide_channels(event_type, priority)

    result = {"event": event_type, "title": title, "message": message, "sent": []}

    if "ntfy" in channels:
        if _send_ntfy(title, message, priority):
            result["sent"].append("ntfy")

    if "pickup" in channels:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
        filename = f"willow_{event_type}_{timestamp}.md"
        pickup_content = f"""# {title}

**{datetime.now().strftime('%Y-%m-%d %H:%M')}** — Willow

{message}

---
ΔΣ=42
"""
        if _send_pickup(filename, pickup_content):
            result["sent"].append("pickup")

    if not result["sent"]:
        result["rate_limited"] = True

    return result


def _decide_channels(event_type: str, priority: str) -> List[str]:
    """Willow decides which channels to use based on event importance."""

    # High priority: both channels
    if priority == "high":
        return ["ntfy", "pickup"]

    # Completion events: ntfy for immediacy
    if event_type in ("scan_complete", "organize_complete", "task_complete"):
        return ["ntfy"]

    # Topology/analytical: pickup only (not urgent)
    if event_type in ("edges_built", "clusters_formed", "continuity_gaps"):
        return ["pickup"]

    # Coherence: ntfy (you want to know now)
    if event_type.startswith("coherence"):
        return ["ntfy"]

    return ["pickup"]


# =========================================================================
# CONVENIENCE — Hook these into existing flows
# =========================================================================

def on_scan_complete(summary: Dict):
    """Call after PA scan finishes."""
    return signal("scan_complete", {
        "total_files": summary.get("total_files", 0),
        "atoms_ingested": summary.get("ingested", 0),
        "duplicates": summary.get("duplicate_count", 0),
    })


def on_organize_complete(result: Dict):
    """Call after PA organize/dedupe/cleanup finishes."""
    return signal("organize_complete", {
        "moved": result.get("moved", 0),
        "ingested": result.get("ingested", 0),
        "errors": len(result.get("errors", [])),
    })


def on_coherence_update(metrics: Dict):
    """Call after coherence tracking. Only signals if something's wrong."""
    delta_e = metrics.get("delta_e", 0)
    state = metrics.get("state", "stable")

    if delta_e < -0.2:
        return signal("coherence_critical", metrics)
    elif state == "decaying":
        return signal("coherence_decay", metrics)
    return {"silent": True}


def on_topology_update(edges_created: int = 0, clusters_created: int = 0, gaps: int = 0):
    """Call after topology operations."""
    results = []
    if edges_created > 0:
        results.append(signal("edges_built", {"edges_created": edges_created}))
    if clusters_created > 0:
        results.append(signal("clusters_formed", {"clusters_created": clusters_created}))
    if gaps > 0:
        results.append(signal("continuity_gaps", {"gap_count": gaps}))
    return results if results else [{"silent": True}]


def say(message: str, title: str = "willow", priority: str = "default",
        channels: Optional[List[str]] = None):
    """Willow says something directly. For custom/freeform messages."""
    return signal("custom", {
        "title": title,
        "message": message,
        "priority": priority,
    }, channels=channels)

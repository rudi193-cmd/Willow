"""
n2n_listener.py — N2N Inbox Daemon

Polls the N2N packet inbox for a given node, dispatches inbound packets
to registered handlers via n2n_dispatcher. Runs as a background daemon thread.

No HTTP. Postgres only.

Usage (in Kart's startup or agent_engine):
    from core.n2n_listener import N2NListener

    listener = N2NListener(node_id="kart@Sweet-Pea-Rudi19", username="Sweet-Pea-Rudi19")
    listener.start()   # daemon thread — dies with the process
    ...
    listener.stop()    # clean shutdown

Concurrent dispatch: each packet is handled in its own thread (ThreadPoolExecutor).
Max 8 workers — handles bursts without unbounded thread growth.

Result packets: if a handler returns a non-None dict, the listener sends it
back to the source node as a DELTA packet automatically.

GOVERNANCE: Listener only reads + marks status. Handlers own their writes.
CHECKSUM: ΔΣ=42
"""

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from core.n2n_db import N2NDatabase
from core.n2n_packets import N2NPacket, PacketType
from core import n2n_dispatcher

log = logging.getLogger("n2n_listener")

_POLL_INTERVAL = 2.0   # seconds between inbox polls
_MAX_WORKERS   = 8     # concurrent handler threads


class N2NListener:
    """
    Daemon thread that polls the N2N inbox and dispatches packets.

    One listener per agent node. Start at agent boot, stop at shutdown.
    """

    def __init__(self, node_id: str, username: str, poll_interval: float = _POLL_INTERVAL):
        self.node_id       = node_id
        self.username      = username
        self.poll_interval = poll_interval
        self.db            = N2NDatabase(username)
        self._running      = False
        self._thread: Optional[threading.Thread] = None
        self._pool         = ThreadPoolExecutor(max_workers=_MAX_WORKERS, thread_name_prefix="n2n-worker")

    def start(self) -> None:
        """Start the listener daemon thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name=f"n2n-listener-{self.node_id}")
        self._thread.start()
        log.info("N2NListener started for %s", self.node_id)

    def stop(self) -> None:
        """Signal the listener to stop. Does not block."""
        self._running = False
        log.info("N2NListener stopping for %s", self.node_id)

    def _loop(self) -> None:
        """Main poll loop. Runs in daemon thread."""
        while self._running:
            try:
                packets = self.db.receive_packets(self.node_id, status="SENT")
                for packet in packets:
                    # Mark received immediately so it isn't double-dispatched
                    self.db.mark_received(packet["packet_id"])
                    # Dispatch concurrently
                    self._pool.submit(self._handle, packet)
            except Exception as e:
                log.error("Listener poll error: %s", e)
            time.sleep(self.poll_interval)

    def _handle(self, packet: dict) -> None:
        """Dispatch one packet and send result back if handler returns one."""
        packet_id = packet["packet_id"]
        try:
            result = n2n_dispatcher.dispatch(packet)
            self.db.mark_acknowledged(packet_id)

            # If handler returned a result payload, send it back as DELTA
            if result is not None:
                source_node = packet.get("source_node", "")
                if source_node:
                    reply = N2NPacket.create_packet(
                        packet_type=PacketType.DELTA,
                        source_node=self.node_id,
                        target_node=source_node,
                        payload={"app": packet.get("payload", {}).get("app"), "result": result},
                        intent=f"result:{packet_id}",
                    )
                    self.db.send_packet(reply)
        except Exception as e:
            log.error("Handler error for packet %s: %s", packet_id, e)

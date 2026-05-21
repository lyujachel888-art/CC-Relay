"""Send a message to the wrapper TCP listener identified by wrapper_id.
The wrapper writes the payload into its hosted Claude PTY (+ Enter)."""

import socket

from wrapper_registry import WrapperRegistry

WRAPPER_HOST = "127.0.0.1"
TIMEOUT_SEC = 3.0


def inject(registry: WrapperRegistry, wrapper_id: str, text: str) -> None:
    """Look up the wrapper's port via the registry, then send text over TCP.

    Raises:
      WrapperUnknown — wrapper id never registered
      WrapperOffline — wrapper is registered but heartbeat-stale
      OSError       — transport failure (caller decides whether to retry)
    """
    port = registry.lookup_port(wrapper_id)
    with socket.create_connection((WRAPPER_HOST, port), timeout=TIMEOUT_SEC) as s:
        s.sendall(text.encode("utf-8"))
        s.shutdown(socket.SHUT_WR)
        try:
            s.recv(64)
        except Exception:
            pass

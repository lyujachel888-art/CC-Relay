"""Send a message to the wrapper running on Windows side, which writes it
into the Claude Code PTY (+ Enter)."""

import socket

WRAPPER_HOST = "127.0.0.1"
WRAPPER_PORT = 8788
TIMEOUT_SEC = 3.0


def inject(text: str) -> None:
    """Connect to the wrapper, send UTF-8 text, close.

    The wrapper appends Enter and writes to the PTY itself. Raises on
    connection error or timeout — caller decides how to handle.
    """
    with socket.create_connection((WRAPPER_HOST, WRAPPER_PORT), timeout=TIMEOUT_SEC) as s:
        s.sendall(text.encode("utf-8"))
        # close write side so the wrapper's recv-until-empty loop exits
        s.shutdown(socket.SHUT_WR)
        # optionally consume the wrapper's ack so we don't get RST warnings
        try:
            s.recv(64)
        except Exception:
            pass

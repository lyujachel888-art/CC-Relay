import socket
import threading
from injector import inject, WRAPPER_HOST, WRAPPER_PORT


def _start_echo_server(port, captured: list, ready_event: threading.Event):
    """Tiny TCP server that accepts one connection, reads until EOF, captures bytes."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((WRAPPER_HOST, port))
    srv.listen(1)
    srv.settimeout(3.0)
    ready_event.set()
    try:
        conn, _ = srv.accept()
        with conn:
            buf = b""
            while True:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                buf += chunk
            captured.append(buf)
            try:
                conn.sendall(b"OK\n")
            except Exception:
                pass
    finally:
        srv.close()


def _run_test_against_port(port, text):
    import injector
    captured = []
    ready = threading.Event()
    t = threading.Thread(target=_start_echo_server, args=(port, captured, ready), daemon=True)
    t.start()
    assert ready.wait(2.0)
    # Patch the port the injector uses
    orig_port = injector.WRAPPER_PORT
    injector.WRAPPER_PORT = port
    try:
        inject(text)
    finally:
        injector.WRAPPER_PORT = orig_port
    t.join(timeout=3.0)
    return captured


def test_inject_sends_utf8_payload_to_socket():
    # use a high port unlikely to conflict
    captured = _run_test_against_port(58789, "hello world")
    assert captured == [b"hello world"]


def test_inject_sends_unicode():
    captured = _run_test_against_port(58790, "你好 world")
    assert captured == ["你好 world".encode("utf-8")]


def test_inject_raises_when_wrapper_unavailable():
    import pytest
    # Use a port no one is listening on
    import injector
    orig_port = injector.WRAPPER_PORT
    injector.WRAPPER_PORT = 58791  # unused, should refuse
    try:
        with pytest.raises((ConnectionRefusedError, OSError)):
            inject("nope")
    finally:
        injector.WRAPPER_PORT = orig_port

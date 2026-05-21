import socket
import threading

import pytest

from errors import WrapperOffline, WrapperUnknown
from injector import inject
from wrapper_registry import WrapperRegistry


def _start_dummy_listener(port_holder: list, received: list, stop: threading.Event):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    srv.settimeout(0.5)
    port_holder.append(srv.getsockname()[1])
    while not stop.is_set():
        try:
            conn, _ = srv.accept()
        except socket.timeout:
            continue
        try:
            buf = b""
            while True:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                buf += chunk
            received.append(buf.decode("utf-8", "replace"))
            conn.sendall(b"OK\n")
        finally:
            conn.close()
    srv.close()


def test_inject_routes_by_wrapper_id(fake_clock):
    port_holder: list = []
    received: list = []
    stop = threading.Event()
    t = threading.Thread(target=_start_dummy_listener, args=(port_holder, received, stop), daemon=True)
    t.start()
    while not port_holder:
        pass
    port = port_holder[0]

    reg = WrapperRegistry(timeout_sec=30, clock=fake_clock)
    reg.register(id="wrapper-rc", name="RC", cwd="E:\\X", port=port, pid=1)

    inject(reg, "wrapper-rc", "hello")

    # Wait briefly for listener thread
    import time as _t
    _t.sleep(0.2)
    stop.set()
    t.join(timeout=2)
    assert received and received[0] == "hello"


def test_inject_unknown_wrapper_raises(fake_clock):
    reg = WrapperRegistry(timeout_sec=30, clock=fake_clock)
    with pytest.raises(WrapperUnknown):
        inject(reg, "wrapper-zzz", "hi")


def test_inject_offline_wrapper_raises(fake_clock):
    reg = WrapperRegistry(timeout_sec=30, clock=fake_clock)
    reg.register(id="wrapper-rc", name="RC", cwd="E:\\X", port=1, pid=1)
    fake_clock.tick(60)
    with pytest.raises(WrapperOffline):
        inject(reg, "wrapper-rc", "hi")

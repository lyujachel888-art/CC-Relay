# bridge/tests/test_e2e_two_wrappers.py
"""End-to-end: bridge + two mock wrappers + simulated Feishu inbound.

Strategy:
  - Run bridge FastAPI in-process via TestClient (HTTP routes only)
  - Spin up two raw TCP servers acting as mock wrappers
  - POST /api/wrappers/register for each
  - Drive Router via direct calls (simulating /switch)
  - Call inject() and verify the right mock wrapper got the text
"""
import socket
import threading
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api_wrappers import attach_wrapper_routes
from config_store import ConfigStore
from injector import inject
from router import Router
from wrapper_registry import WrapperRegistry


class MockWrapper:
    def __init__(self):
        self.received: list = []
        self._stop = threading.Event()
        self._srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._srv.bind(("127.0.0.1", 0))
        self.port = self._srv.getsockname()[1]
        self._srv.listen(2)
        self._srv.settimeout(0.5)
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self):
        while not self._stop.is_set():
            try:
                conn, _ = self._srv.accept()
            except socket.timeout:
                continue
            except OSError:
                # Socket was closed by stop() — exit cleanly
                break
            try:
                buf = b""
                while True:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    buf += chunk
                self.received.append(buf.decode("utf-8", "replace"))
                conn.sendall(b"OK\n")
            finally:
                conn.close()

    def stop(self):
        self._stop.set()
        try:
            self._srv.close()
        except Exception:
            pass


@pytest.fixture
def setup(tmp_path):
    rc = MockWrapper()
    xyz = MockWrapper()
    yield rc, xyz, tmp_path
    rc.stop()
    xyz.stop()


def test_full_routing_two_wrappers(setup):
    rc, xyz, tmp_path = setup
    store = ConfigStore(tmp_path / "config.json")
    registry = WrapperRegistry(timeout_sec=30)
    router = Router(store=store, registry=registry)

    app = FastAPI()
    attach_wrapper_routes(app, registry=registry, store=store)
    client = TestClient(app)

    # Register both mock wrappers via the HTTP API (same way real wrapper does)
    r1 = client.post("/api/wrappers/register", json={
        "id": "wrapper-rc", "name": "RC", "cwd": "E:\\X", "port": rc.port, "pid": 1,
    })
    assert r1.status_code == 200
    r2 = client.post("/api/wrappers/register", json={
        "id": "wrapper-xyz", "name": "XYZ", "cwd": "E:\\Y", "port": xyz.port, "pid": 2,
    })
    assert r2.status_code == 200

    # Switch to RC, inject — RC should receive, XYZ should not
    router.set_active("wrapper-rc")
    wid = router.inbound()
    assert wid == "wrapper-rc"
    inject(registry, wid, "hello-rc")
    import time
    time.sleep(0.2)
    assert "hello-rc" in rc.received
    assert "hello-rc" not in xyz.received

    # Switch to XYZ
    router.set_active("wrapper-xyz")
    wid = router.inbound()
    assert wid == "wrapper-xyz"
    inject(registry, wid, "hello-xyz")
    time.sleep(0.2)
    assert "hello-xyz" in xyz.received
    assert "hello-xyz" not in rc.received


def test_inbound_returns_none_when_active_offline(setup):
    rc, _xyz, tmp_path = setup
    store = ConfigStore(tmp_path / "config.json")
    registry = WrapperRegistry(timeout_sec=0.5)  # short timeout
    router = Router(store=store, registry=registry)

    app = FastAPI()
    attach_wrapper_routes(app, registry=registry, store=store)
    client = TestClient(app)
    client.post("/api/wrappers/register", json={
        "id": "wrapper-rc", "name": "RC", "cwd": "E:\\X", "port": rc.port, "pid": 1,
    })
    router.set_active("wrapper-rc")
    assert router.inbound() == "wrapper-rc"

    import time
    time.sleep(0.8)  # exceed heartbeat timeout
    assert router.inbound() is None

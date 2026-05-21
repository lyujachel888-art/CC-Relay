from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from api_wrappers import attach_wrapper_routes
from config_store import ConfigStore
from server import create_app
from router import Router
from wrapper_registry import WrapperRegistry


@pytest.fixture
def client(tmp_path, fake_clock):
    feishu = MagicMock()
    store = ConfigStore(tmp_path / "config.json")
    registry = WrapperRegistry(timeout_sec=30, clock=fake_clock)
    router = Router(store=store, registry=registry)
    app = create_app(feishu, "test-token", registry=registry, router=router)
    attach_wrapper_routes(app, registry=registry, store=store)
    # Pre-register a wrapper so the header value is recognized
    registry.register(id="wrapper-rc", name="RC", cwd="E:\\X", port=1, pid=1)
    return TestClient(app), feishu


def test_hook_without_wrapper_id_header_rejected(client):
    c, _ = client
    resp = c.post(
        "/hook/user_prompt",
        json={"text": "hi"},
        headers={"Authorization": "Bearer test-token"},
    )
    assert resp.status_code == 400
    assert "wrapper" in resp.text.lower()


def test_hook_with_unknown_wrapper_id_rejected(client):
    c, _ = client
    resp = c.post(
        "/hook/user_prompt",
        json={"text": "hi"},
        headers={"Authorization": "Bearer test-token", "X-Wrapper-Id": "wrapper-zzz"},
    )
    assert resp.status_code == 400


def test_hook_with_known_wrapper_id_accepted(client):
    c, feishu = client
    resp = c.post(
        "/hook/user_prompt",
        json={"text": "hi"},
        headers={"Authorization": "Bearer test-token", "X-Wrapper-Id": "wrapper-rc"},
    )
    assert resp.status_code == 200

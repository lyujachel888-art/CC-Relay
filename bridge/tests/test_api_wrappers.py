from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api_wrappers import attach_wrapper_routes
from config_store import ConfigStore
from wrapper_registry import WrapperRegistry


@pytest.fixture
def client(tmp_path, fake_clock):
    store = ConfigStore(tmp_path / "config.json")
    registry = WrapperRegistry(timeout_sec=30, clock=fake_clock)
    app = FastAPI()
    attach_wrapper_routes(app, registry=registry, store=store)
    return TestClient(app), store, registry, fake_clock


def test_register_creates_entry(client):
    c, store, _, _ = client
    resp = c.post("/api/wrappers/register", json={
        "id": "wrapper-rc", "name": "RC", "cwd": "E:\\X", "port": 51234, "pid": 99,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["wrapper_id"] == "wrapper-rc"
    assert body["token"].startswith("wrp_")
    assert body["heartbeat_interval_sec"] == 15
    assert any(w["id"] == "wrapper-rc" for w in store.wrappers)


def test_register_conflict_returns_409(client):
    c, _, _, _ = client
    c.post("/api/wrappers/register", json={"id": "wrapper-rc", "name": "RC", "cwd": "E:\\X", "port": 51234, "pid": 1})
    resp = c.post("/api/wrappers/register", json={"id": "wrapper-rc", "name": "RC", "cwd": "E:\\X", "port": 51235, "pid": 2})
    assert resp.status_code == 409


def test_heartbeat_with_valid_token(client):
    c, _, _, _ = client
    reg_resp = c.post("/api/wrappers/register", json={"id": "wrapper-rc", "name": "RC", "cwd": "E:\\X", "port": 1, "pid": 1})
    token = reg_resp.json()["token"]
    hb = c.post("/api/wrappers/heartbeat",
                json={"id": "wrapper-rc"},
                headers={"Authorization": f"Bearer {token}"})
    assert hb.status_code == 200


def test_heartbeat_without_token_returns_401(client):
    c, _, _, _ = client
    c.post("/api/wrappers/register", json={"id": "wrapper-rc", "name": "RC", "cwd": "E:\\X", "port": 1, "pid": 1})
    hb = c.post("/api/wrappers/heartbeat", json={"id": "wrapper-rc"})
    assert hb.status_code == 401


def test_heartbeat_with_wrong_token_returns_403(client):
    c, _, _, _ = client
    c.post("/api/wrappers/register", json={"id": "wrapper-rc", "name": "RC", "cwd": "E:\\X", "port": 1, "pid": 1})
    hb = c.post("/api/wrappers/heartbeat",
                json={"id": "wrapper-rc"},
                headers={"Authorization": "Bearer wrp_fake"})
    assert hb.status_code == 403


def test_heartbeat_for_unknown_id_returns_404(client):
    c, _, _, _ = client
    hb = c.post("/api/wrappers/heartbeat",
                json={"id": "wrapper-zzz"},
                headers={"Authorization": "Bearer wrp_anything"})
    assert hb.status_code == 404


def test_deregister(client):
    c, _, registry, _ = client
    reg = c.post("/api/wrappers/register", json={"id": "wrapper-rc", "name": "RC", "cwd": "E:\\X", "port": 1, "pid": 1})
    token = reg.json()["token"]
    resp = c.post("/api/wrappers/deregister",
                  json={"id": "wrapper-rc"},
                  headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert registry.is_online("wrapper-rc") is False

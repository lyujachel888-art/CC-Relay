from pathlib import Path

import pytest

from config_store import ConfigStore
from router import Router
from wrapper_registry import WrapperRegistry


@pytest.fixture
def store(tmp_path):
    return ConfigStore(tmp_path / "config.json")


@pytest.fixture
def registry(fake_clock):
    return WrapperRegistry(timeout_sec=30, clock=fake_clock)


def test_inbound_returns_none_when_no_active(store, registry):
    router = Router(store=store, registry=registry)
    assert router.inbound() is None


def test_inbound_returns_active_when_online(store, registry):
    registry.register(id="wrapper-rc", name="RC", cwd="E:\\X", port=51234, pid=1)
    store.upsert_wrapper(id="wrapper-rc", name="RC", expected_cwd="E:\\X")
    store.set_active("wrapper-rc")
    router = Router(store=store, registry=registry)
    assert router.inbound() == "wrapper-rc"


def test_inbound_returns_none_when_active_offline(store, registry, fake_clock):
    registry.register(id="wrapper-rc", name="RC", cwd="E:\\X", port=51234, pid=1)
    store.upsert_wrapper(id="wrapper-rc", name="RC", expected_cwd="E:\\X")
    store.set_active("wrapper-rc")
    router = Router(store=store, registry=registry)
    fake_clock.tick(60)
    assert router.inbound() is None


def test_set_active_persists(store, registry):
    registry.register(id="wrapper-rc", name="RC", cwd="E:\\X", port=51234, pid=1)
    store.upsert_wrapper(id="wrapper-rc", name="RC", expected_cwd="E:\\X")
    router = Router(store=store, registry=registry)
    router.set_active("wrapper-rc")
    assert store.active_wrapper_id == "wrapper-rc"


def test_resolve_name_or_id_prefers_exact_id_match(store, registry):
    registry.register(id="wrapper-rc", name="RC", cwd="E:\\X", port=1, pid=1)
    registry.register(id="wrapper-xyz", name="XYZ", cwd="E:\\Y", port=2, pid=2)
    store.upsert_wrapper(id="wrapper-rc", name="RC", expected_cwd="E:\\X")
    store.upsert_wrapper(id="wrapper-xyz", name="XYZ", expected_cwd="E:\\Y")
    router = Router(store=store, registry=registry)
    assert router.resolve("wrapper-rc") == "wrapper-rc"
    assert router.resolve("xyz") == "wrapper-xyz"  # case-insensitive name match
    assert router.resolve("RC") == "wrapper-rc"
    assert router.resolve("nonexistent") is None


def test_list_for_switch_menu(store, registry, fake_clock):
    registry.register(id="wrapper-rc", name="RC", cwd="E:\\X", port=1, pid=1)
    store.upsert_wrapper(id="wrapper-rc", name="RC", expected_cwd="E:\\X")
    store.upsert_wrapper(id="wrapper-xyz", name="XYZ", expected_cwd="E:\\Y")
    store.set_active("wrapper-rc")
    router = Router(store=store, registry=registry)
    listing = router.list_wrappers()
    assert len(listing) == 2
    rc = next(w for w in listing if w["id"] == "wrapper-rc")
    xyz = next(w for w in listing if w["id"] == "wrapper-xyz")
    assert rc["online"] is True and rc["active"] is True
    assert xyz["online"] is False and xyz["active"] is False

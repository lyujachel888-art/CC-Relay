import pytest

from errors import BadToken, WrapperConflict, WrapperUnknown
from wrapper_registry import WrapperRegistry


def test_register_new_wrapper_returns_token(fake_clock):
    reg = WrapperRegistry(timeout_sec=30, clock=fake_clock)
    info = reg.register(id="wrapper-rc", name="RC", cwd="E:\\X", port=51234, pid=123)
    assert info.id == "wrapper-rc"
    assert info.token.startswith("wrp_")
    assert reg.is_online("wrapper-rc") is True


def test_register_same_id_when_online_conflicts(fake_clock):
    reg = WrapperRegistry(timeout_sec=30, clock=fake_clock)
    reg.register(id="wrapper-rc", name="RC", cwd="E:\\X", port=51234, pid=123)
    with pytest.raises(WrapperConflict):
        reg.register(id="wrapper-rc", name="RC", cwd="E:\\X", port=51235, pid=124)


def test_register_same_id_when_offline_succeeds(fake_clock):
    reg = WrapperRegistry(timeout_sec=30, clock=fake_clock)
    first = reg.register(id="wrapper-rc", name="RC", cwd="E:\\X", port=51234, pid=123)
    fake_clock.tick(60)  # past heartbeat timeout
    assert reg.is_online("wrapper-rc") is False
    second = reg.register(id="wrapper-rc", name="RC", cwd="E:\\X", port=51235, pid=124)
    assert second.token != first.token
    assert reg.lookup_port("wrapper-rc") == 51235


def test_heartbeat_updates_last_seen(fake_clock):
    reg = WrapperRegistry(timeout_sec=30, clock=fake_clock)
    info = reg.register(id="wrapper-rc", name="RC", cwd="E:\\X", port=51234, pid=123)
    fake_clock.tick(20)
    reg.heartbeat("wrapper-rc", info.token)
    fake_clock.tick(20)  # 40s since register, but only 20s since heartbeat
    assert reg.is_online("wrapper-rc") is True


def test_heartbeat_with_wrong_token_rejected(fake_clock):
    reg = WrapperRegistry(timeout_sec=30, clock=fake_clock)
    reg.register(id="wrapper-rc", name="RC", cwd="E:\\X", port=51234, pid=123)
    with pytest.raises(BadToken):
        reg.heartbeat("wrapper-rc", "wrp_fake")


def test_heartbeat_for_unknown_id_rejected(fake_clock):
    reg = WrapperRegistry(timeout_sec=30, clock=fake_clock)
    with pytest.raises(WrapperUnknown):
        reg.heartbeat("wrapper-zzz", "wrp_anything")


def test_deregister_marks_offline(fake_clock):
    reg = WrapperRegistry(timeout_sec=30, clock=fake_clock)
    info = reg.register(id="wrapper-rc", name="RC", cwd="E:\\X", port=51234, pid=123)
    reg.deregister("wrapper-rc", info.token)
    assert reg.is_online("wrapper-rc") is False


def test_lookup_port_for_offline_raises(fake_clock):
    from errors import WrapperOffline
    reg = WrapperRegistry(timeout_sec=30, clock=fake_clock)
    info = reg.register(id="wrapper-rc", name="RC", cwd="E:\\X", port=51234, pid=123)
    reg.deregister("wrapper-rc", info.token)
    with pytest.raises(WrapperOffline):
        reg.lookup_port("wrapper-rc")


def test_snapshot_returns_all_entries_without_token(fake_clock):
    reg = WrapperRegistry(timeout_sec=30, clock=fake_clock)
    a = reg.register(id="w-a", name="A", cwd="x", port=1, pid=10)
    reg.register(id="w-b", name="B", cwd="y", port=2, pid=20)
    fake_clock.tick(60)
    reg.heartbeat("w-a", a.token)  # only A is fresh after the tick
    rows = reg.snapshot()
    assert {r["id"] for r in rows} == {"w-a", "w-b"}
    assert all("token" not in r for r in rows)
    by_id = {r["id"]: r for r in rows}
    assert by_id["w-a"]["online"] is True
    assert by_id["w-b"]["online"] is False

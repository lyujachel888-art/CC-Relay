import json
from pathlib import Path

import pytest

from config_store import ConfigStore


def test_load_missing_file_returns_defaults(tmp_path):
    store = ConfigStore(tmp_path / "config.json")
    assert store.wrappers == []
    assert store.active_wrapper_id is None


def test_register_wrapper_persists_to_disk(tmp_path):
    p = tmp_path / "config.json"
    store = ConfigStore(p)
    store.upsert_wrapper(id="wrapper-rc", name="RC", expected_cwd="E:\\X")
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["version"] == 1
    assert data["wrappers"][0]["id"] == "wrapper-rc"


def test_upsert_same_id_updates_in_place(tmp_path):
    store = ConfigStore(tmp_path / "config.json")
    store.upsert_wrapper(id="wrapper-rc", name="RC", expected_cwd="E:\\X")
    store.upsert_wrapper(id="wrapper-rc", name="RC2", expected_cwd="E:\\X")
    assert len(store.wrappers) == 1
    assert store.wrappers[0]["name"] == "RC2"


def test_set_active_persists(tmp_path):
    p = tmp_path / "config.json"
    store = ConfigStore(p)
    store.upsert_wrapper(id="wrapper-rc", name="RC", expected_cwd="E:\\X")
    store.set_active("wrapper-rc")
    reloaded = ConfigStore(p)
    assert reloaded.active_wrapper_id == "wrapper-rc"


def test_atomic_write_no_partial_on_error(tmp_path, monkeypatch):
    p = tmp_path / "config.json"
    store = ConfigStore(p)
    store.upsert_wrapper(id="wrapper-rc", name="RC", expected_cwd="E:\\X")
    original = p.read_text(encoding="utf-8")

    # Simulate disk failure during write
    real_rename = Path.replace

    def boom(self, target):
        raise OSError("disk full")

    monkeypatch.setattr(Path, "replace", boom)
    with pytest.raises(OSError):
        store.upsert_wrapper(id="wrapper-xyz", name="XYZ", expected_cwd="E:\\Y")
    assert p.read_text(encoding="utf-8") == original
    # tmp file should be cleaned up
    assert not (p.parent / (p.name + ".tmp")).exists()


def test_load_corrupt_json_uses_backup(tmp_path):
    p = tmp_path / "config.json"
    p.write_text("{not valid json", encoding="utf-8")
    bak = p.with_suffix(".json.bak")
    bak.write_text(json.dumps({
        "version": 1,
        "wrappers": [{"id": "wrapper-rc", "name": "RC", "expected_cwd": "E:\\X"}],
        "active_wrapper_id": "wrapper-rc",
    }), encoding="utf-8")
    store = ConfigStore(p)
    assert store.active_wrapper_id == "wrapper-rc"
    assert len(store.wrappers) == 1

import os
from pathlib import Path
import pytest
from config import load_config


def test_load_config_reads_env(monkeypatch):
    monkeypatch.setenv("FEISHU_APP_ID", "aid")
    monkeypatch.setenv("FEISHU_APP_SECRET", "sec")
    monkeypatch.setenv("FEISHU_USER_OPEN_ID", "ou_test")

    cfg = load_config()

    assert cfg.app_id == "aid"
    assert cfg.app_secret == "sec"
    assert cfg.user_open_id == "ou_test"


def test_load_config_prefers_plugin_env(monkeypatch, tmp_path):
    """When ~/.claude/plugins/cc-relay/.env exists, its values are used."""
    fake_home = tmp_path
    plugin_dir = fake_home / ".claude" / "plugins" / "cc-relay"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / ".env").write_text(
        "FEISHU_APP_ID=plugin_aid\n"
        "FEISHU_APP_SECRET=plugin_sec\n"
        "FEISHU_USER_OPEN_ID=ou_plugin\n"
    )

    # Redirect Path.home() (the symbol imported into config module)
    import config
    monkeypatch.setattr(config.Path, "home", staticmethod(lambda: fake_home))

    # Clear any pre-existing env so we know the .env file was read
    monkeypatch.delenv("FEISHU_APP_ID", raising=False)
    monkeypatch.delenv("FEISHU_APP_SECRET", raising=False)
    monkeypatch.delenv("FEISHU_USER_OPEN_ID", raising=False)

    cfg = config.load_config()
    assert cfg.app_id == "plugin_aid"
    assert cfg.app_secret == "plugin_sec"
    assert cfg.user_open_id == "ou_plugin"


def test_load_config_falls_back_to_cwd_env_when_plugin_env_missing(monkeypatch, tmp_path):
    """When plugin .env is missing, behavior is the old load_dotenv() — i.e.
    env vars set by the caller still win."""
    fake_home = tmp_path  # no .claude/plugins/cc-relay/.env created
    import config
    monkeypatch.setattr(config.Path, "home", staticmethod(lambda: fake_home))

    monkeypatch.setenv("FEISHU_APP_ID", "cwd_aid")
    monkeypatch.setenv("FEISHU_APP_SECRET", "cwd_sec")
    monkeypatch.setenv("FEISHU_USER_OPEN_ID", "ou_cwd")

    cfg = config.load_config()
    assert cfg.app_id == "cwd_aid"
    assert cfg.user_open_id == "ou_cwd"

import os
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

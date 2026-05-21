from unittest.mock import MagicMock

import pytest

from config_store import ConfigStore
from router import Router
from wrapper_registry import WrapperRegistry
from long_conn import make_message_handler


@pytest.fixture
def deps(tmp_path, fake_clock):
    feishu = MagicMock()
    store = ConfigStore(tmp_path / "config.json")
    reg = WrapperRegistry(timeout_sec=30, clock=fake_clock)
    reg.register(id="wrapper-rc", name="RC", cwd="E:\\X", port=1, pid=1)
    reg.register(id="wrapper-xyz", name="XYZ", cwd="E:\\Y", port=2, pid=2)
    store.upsert_wrapper(id="wrapper-rc", name="RC", expected_cwd="E:\\X")
    store.upsert_wrapper(id="wrapper-xyz", name="XYZ", expected_cwd="E:\\Y")
    router = Router(store=store, registry=reg)
    return feishu, router, reg, store


def _fake_text_event(text: str):
    """Build a minimal lark message envelope shape the handler reads."""
    class _Sender:
        sender_id = type("S", (), {"open_id": "ou_test"})

    class _Msg:
        content = '{"text": "%s"}' % text
        message_type = "text"
        message_id = "mid_" + text

    class _Event:
        message = _Msg()
        sender = _Sender()

    class _Data:
        event = _Event()
    return _Data()


def test_switch_changes_active(deps):
    feishu, router, reg, store = deps
    handler = make_message_handler(feishu=feishu, router=router, registry=reg)
    handler(_fake_text_event("/switch XYZ"))
    assert store.active_wrapper_id == "wrapper-xyz"


def test_who_responds_with_active(deps):
    feishu, router, reg, store = deps
    store.set_active("wrapper-rc")
    handler = make_message_handler(feishu=feishu, router=router, registry=reg)
    handler(_fake_text_event("/who"))
    feishu.send_text.assert_called()
    msg = feishu.send_text.call_args[0][0]
    assert "RC" in msg or "wrapper-rc" in msg

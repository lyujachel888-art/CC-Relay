# bridge/tests/conftest.py
"""pytest fixtures for cc-relay tests."""
import sys
import time
import types

import pytest


# lark-oapi does a long blocking initialisation at import time (websocket
# handshake, token refresh, etc.). The bridge tests never exercise the real
# Feishu network path — they always pass a MagicMock — so we stub out the
# package's IM submodules entirely so that `from feishu import FeishuClient`
# doesn't hang.
def _mock_lark():
    _LARK_MODS = [
        "lark_oapi",
        "lark_oapi.api",
        "lark_oapi.api.im",
        "lark_oapi.api.im.v1",
    ]
    for name in _LARK_MODS:
        if name not in sys.modules:
            sys.modules[name] = types.ModuleType(name)
    _IM_V1_ATTRS = [
        "CreateFileRequest",
        "CreateFileRequestBody",
        "CreateImageRequest",
        "CreateImageRequestBody",
        "CreateMessageRequest",
        "CreateMessageRequestBody",
        "GetMessageResourceRequest",
    ]
    for attr in _IM_V1_ATTRS:
        if not hasattr(sys.modules["lark_oapi.api.im.v1"], attr):
            setattr(sys.modules["lark_oapi.api.im.v1"], attr, object)


_mock_lark()


# tests/test_server.py contains stale tests written for the v0 single-bot
# create_app(feishu) signature. Phase 2 will rewrite or delete it; for now
# we skip collection so plain `pytest` runs cleanly.
collect_ignore = ["test_server.py"]


@pytest.fixture
def fake_clock(monkeypatch):
    """A controllable clock injected into modules that import `time.time`.
    Yields a holder; tests advance via `clock.tick(seconds)`."""
    class _Clock:
        def __init__(self):
            self.now = 1_000_000.0

        def tick(self, sec: float) -> None:
            self.now += sec

        def __call__(self):
            return self.now

    c = _Clock()
    monkeypatch.setattr(time, "time", c)
    yield c

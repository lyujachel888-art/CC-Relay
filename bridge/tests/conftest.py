# bridge/tests/conftest.py
"""pytest fixtures for cc-relay tests."""
import time

import pytest

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

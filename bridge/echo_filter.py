"""Tracks recently feishu→PTY injected messages so we can suppress the
UserPromptSubmit echo (Claude TUI re-emits the injected text via the hook,
which would otherwise show up as a 🧑 push on the phone the user just typed
on)."""

import time
from threading import Lock

_TTL_SEC = 30.0
_MAX_ITEMS = 50
_lock = Lock()
_items: list = []  # list of (timestamp, text)


def _gc(now: float) -> None:
    global _items
    _items = [(t, x) for (t, x) in _items if now - t <= _TTL_SEC]


def mark_injected(text: str) -> None:
    """Record that `text` was just injected into the PTY from feishu."""
    with _lock:
        now = time.time()
        _gc(now)
        _items.append((now, text))
        if len(_items) > _MAX_ITEMS:
            _items.pop(0)


def claim_echo(text: str) -> bool:
    """If `text` matches a recently-injected message, consume it and return
    True (caller should suppress the push). Otherwise return False."""
    with _lock:
        now = time.time()
        _gc(now)
        for i, (_ts, t) in enumerate(_items):
            if t == text:
                _items.pop(i)
                return True
        return False

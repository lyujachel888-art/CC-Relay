"""Tracks recently feishu→PTY injected messages per wrapper, so we can
suppress the UserPromptSubmit echo from the matching wrapper's hook.

State is bucketed by wrapper_id — Phase 1 multi-wrapper requires that an
injection into wrapper-A doesn't claim wrapper-B's echo by accident."""

import time
from collections import defaultdict
from threading import Lock

_TTL_SEC = 30.0
_MAX_ITEMS_PER_WRAPPER = 50
_lock = Lock()
_items: dict = defaultdict(list)  # wrapper_id -> list of (timestamp, text)


def _gc(bucket: list, now: float) -> list:
    return [(t, x) for (t, x) in bucket if now - t <= _TTL_SEC]


def mark_injected(wrapper_id: str, text: str) -> None:
    with _lock:
        now = time.time()
        bucket = _gc(_items[wrapper_id], now)
        bucket.append((now, text))
        if len(bucket) > _MAX_ITEMS_PER_WRAPPER:
            bucket.pop(0)
        _items[wrapper_id] = bucket


def claim_echo(wrapper_id: str, text: str) -> bool:
    with _lock:
        now = time.time()
        bucket = _gc(_items.get(wrapper_id, []), now)
        for i, (_ts, t) in enumerate(bucket):
            if t == text:
                bucket.pop(i)
                _items[wrapper_id] = bucket
                return True
        _items[wrapper_id] = bucket
        return False

"""Per-wrapper tool_use push gating. set_paused("wrapper-rc", True) silences
tool-use & bash-result hooks from that wrapper only."""

from threading import Lock

_lock = Lock()
_paused: dict = {}  # wrapper_id -> bool


def is_tool_use_paused(wrapper_id: str) -> bool:
    with _lock:
        return _paused.get(wrapper_id, False)


def set_paused(wrapper_id: str, paused: bool) -> None:
    with _lock:
        _paused[wrapper_id] = paused

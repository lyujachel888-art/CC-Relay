"""Global push gating shared between the long-conn handler and the HTTP
server. Lets the user pause noisy event streams (🛠️ tool_use) without
killing the whole bridge."""

from threading import Lock

_lock = Lock()
_paused_tool_use = False


def is_tool_use_paused() -> bool:
    with _lock:
        return _paused_tool_use


def set_paused(paused: bool) -> None:
    global _paused_tool_use
    with _lock:
        _paused_tool_use = paused

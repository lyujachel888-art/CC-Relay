"""Per-wrapper tracking of files Claude has touched, plus a one-shot file
selection menu used by the `/files` slash command."""

import time
from threading import Lock
from typing import List, Optional, Tuple

_MAX_PER_WRAPPER = 100
_SELECTION_TTL = 120.0

_lock = Lock()
_items: dict = {}              # wrapper_id -> List[(ts, action, path)]
_selection: dict = {}          # wrapper_id -> (paths, until_ts)

_PROJECT_PREFIXES = (
    "E:\\MyProject\\RC\\",
    "E:/MyProject/RC/",
)


def record(wrapper_id: str, action: str, file_path: str) -> None:
    if not file_path:
        return
    with _lock:
        bucket = [(t, a, p) for (t, a, p) in _items.get(wrapper_id, []) if p != file_path]
        bucket.append((time.time(), action, file_path))
        if len(bucket) > _MAX_PER_WRAPPER:
            bucket.pop(0)
        _items[wrapper_id] = bucket


def list_recent(wrapper_id: str, n: int = 20) -> List[Tuple[float, str, str]]:
    with _lock:
        return list(_items.get(wrapper_id, [])[-n:])


def clear(wrapper_id: str) -> None:
    with _lock:
        _items[wrapper_id] = []


def to_project_relative(path: str) -> str:
    norm = path.replace("\\", "/")
    for pref in _PROJECT_PREFIXES:
        pn = pref.replace("\\", "/")
        if norm.lower().startswith(pn.lower()):
            return norm[len(pn):]
    return norm


def offer_selection(wrapper_id: str, paths: List[str]) -> None:
    with _lock:
        _selection[wrapper_id] = (list(paths), time.time() + _SELECTION_TTL)


def try_select(wrapper_id: str, text: str) -> Optional[str]:
    t = (text or "").strip()
    if not t.isdigit():
        return None
    with _lock:
        entry = _selection.get(wrapper_id)
        if not entry:
            return None
        paths, until = entry
        if not paths or time.time() > until:
            _selection.pop(wrapper_id, None)
            return None
        idx = int(t) - 1
        if not (0 <= idx < len(paths)):
            return None
        chosen = paths[idx]
        _selection.pop(wrapper_id, None)
        return chosen

"""Remember which files Claude has touched this run.

Populated by PostToolUse hook (Write / Edit / MultiEdit / NotebookEdit).
Consumed by the `/files` slash command from feishu so the user can see what
got generated and pick something to send back with `传 X`."""

import time
from pathlib import PurePosixPath
from threading import Lock
from typing import List, Optional, Tuple

_lock = Lock()
_items: List[Tuple[float, str, str]] = []  # (ts, action, file_path)
_MAX = 100

# When `/files` lists files, we remember the path-by-index mapping so the
# user can reply with a digit (e.g. "3") to upload that file back.
_SELECTION_TTL = 120.0
_sel_lock = Lock()
_selection: List[str] = []
_selection_until: float = 0.0

# Normalize paths so `/files` shows project-relative names.
_PROJECT_PREFIXES = (
    "E:\\MyProject\\RC\\",
    "E:/MyProject/RC/",
    "/mnt/e/MyProject/RC/",
)


def record(action: str, file_path: str) -> None:
    if not file_path:
        return
    with _lock:
        # De-dupe consecutive same-file events (Claude often edits a file in
        # a tight loop). Keep only the latest record of each path.
        global _items
        _items = [(t, a, p) for (t, a, p) in _items if p != file_path]
        _items.append((time.time(), action, file_path))
        if len(_items) > _MAX:
            _items.pop(0)


def list_recent(n: int = 20) -> List[Tuple[float, str, str]]:
    with _lock:
        return list(_items[-n:])


def clear() -> None:
    with _lock:
        _items.clear()


def to_project_relative(path: str) -> str:
    """Show "docs/x.html" instead of the absolute path."""
    norm = path.replace("\\", "/")
    for pref in _PROJECT_PREFIXES:
        pn = pref.replace("\\", "/")
        if norm.lower().startswith(pn.lower()):
            return norm[len(pn):]
    return norm


def offer_selection(paths: List[str]) -> None:
    """Remember `paths` so the next digit reply (within TTL) can pick one."""
    global _selection, _selection_until
    with _sel_lock:
        _selection = list(paths)
        _selection_until = time.time() + _SELECTION_TTL


def try_select(text: str) -> Optional[str]:
    """If `text` is a digit selecting an entry from the pending list, return
    its full path. Consumes the selection (one-shot)."""
    global _selection
    t = (text or "").strip()
    if not t.isdigit():
        return None
    with _sel_lock:
        if not _selection or time.time() > _selection_until:
            _selection = []
            return None
        idx = int(t) - 1
        if not (0 <= idx < len(_selection)):
            return None
        chosen = _selection[idx]
        _selection = []
        return chosen

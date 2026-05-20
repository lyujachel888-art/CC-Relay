"""Cache the latest hook event's transcript_path so the user can run
`/history` from feishu to get a quick summary without us having to walk
the disk for the newest .jsonl every time."""

import json
from pathlib import Path
from threading import Lock
from typing import List, Tuple

_lock = Lock()
_latest_transcript: str = ""


def remember(transcript_path: str) -> None:
    global _latest_transcript
    if not transcript_path:
        return
    with _lock:
        _latest_transcript = transcript_path


def current_transcript() -> str:
    with _lock:
        return _latest_transcript


def _wsl_path(win_path: str) -> Path:
    """The hook tells us a Windows path; bridge is in WSL — convert."""
    p = (win_path or "").replace("\\", "/")
    if len(p) >= 3 and p[1] == ":" and p[2] == "/":
        return Path(f"/mnt/{p[0].lower()}/{p[3:]}")
    return Path(p)


def recent_turns(transcript_win: str, n_turns: int = 5) -> List[Tuple[str, str]]:
    """Return up to `n_turns` recent (role, text) pairs. role is 'user' or
    'assistant'. Skips tool_use / tool_result / system entries."""
    path = _wsl_path(transcript_win)
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []

    out: List[Tuple[str, str]] = []
    for line in reversed(lines):
        try:
            obj = json.loads(line)
        except Exception:
            continue
        msg = obj.get("message") or {}
        role = msg.get("role")
        if role not in ("user", "assistant"):
            continue
        content = msg.get("content")
        text = ""
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            parts = [
                p.get("text", "")
                for p in content
                if isinstance(p, dict) and p.get("type") == "text"
            ]
            text = "\n".join(p for p in parts if p)
        text = text.strip()
        if not text:
            continue
        out.append((role, text))
        if len(out) >= n_turns * 2:  # rough cap; we'll trim below
            break
    out.reverse()
    return out[-n_turns * 2:]


def format_history(turns: List[Tuple[str, str]], per_turn_cap: int = 240) -> str:
    if not turns:
        return "📜 暂无历史"
    lines = ["📜 最近对话"]
    for role, text in turns:
        emoji = "🧑" if role == "user" else "🤖"
        snippet = text if len(text) <= per_turn_cap else text[:per_turn_cap] + "…"
        lines.append(f"\n{emoji} {snippet}")
    return "\n".join(lines)

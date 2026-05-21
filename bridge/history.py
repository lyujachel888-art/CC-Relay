"""Per-wrapper cache of the latest hook's transcript_path. Lets `/history`
from feishu summarize the active wrapper's recent dialog."""

import json
from pathlib import Path
from threading import Lock
from typing import List, Tuple

_lock = Lock()
_latest: dict = {}  # wrapper_id -> transcript path


def remember(wrapper_id: str, transcript_path: str) -> None:
    if not transcript_path:
        return
    with _lock:
        _latest[wrapper_id] = transcript_path


def current_transcript(wrapper_id: str) -> str:
    with _lock:
        return _latest.get(wrapper_id, "")


def recent_turns(transcript_path: str, n_turns: int = 5) -> List[Tuple[str, str]]:
    path = Path(transcript_path)
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
            parts = [p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"]
            text = "\n".join(p for p in parts if p)
        text = text.strip()
        if not text:
            continue
        out.append((role, text))
        if len(out) >= n_turns * 2:
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

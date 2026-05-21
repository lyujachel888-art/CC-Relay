"""Phone-friendly slash-command menu, per-wrapper state.

Phase 1 multi-wrapper: each wrapper has its own pending menu bucket so
switching wrappers mid-menu (or selecting on the wrong project) is safe."""

import time
from threading import Lock
from typing import List, Optional

COMMANDS: List[str] = [
    "/clear", "/compact", "/resume", "/model", "/cost", "/help",
    "/init", "/memory", "/agents", "/mcp", "/config", "/exit",
]

_TRIGGERS = {"/", "菜单", "命令", "指令", "menu", "cmd", "commands"}
MENU_TTL_SEC = 120.0
MENU_TITLE = "📋 可用指令"

_lock = Lock()
_pending: dict = {}  # wrapper_id -> (commands_list, until_ts)


def is_trigger(text: str) -> bool:
    return text.strip().lower() in _TRIGGERS


def build_menu_body() -> str:
    lines = ["**回复数字注入对应命令**", ""]
    for i, cmd in enumerate(COMMANDS, 1):
        lines.append(f"`{i:>2}.`  `{cmd}`")
    lines.append("")
    lines.append(f"*菜单 {int(MENU_TTL_SEC)}s 内有效；其它文字按 prompt 处理*")
    return "\n".join(lines)


def build_menu_text() -> str:
    return f"{MENU_TITLE}\n{build_menu_body()}"


def offer_menu(wrapper_id: str) -> None:
    with _lock:
        _pending[wrapper_id] = (list(COMMANDS), time.time() + MENU_TTL_SEC)


def try_consume_choice(wrapper_id: str, text: str) -> Optional[str]:
    t = text.strip()
    if not t.isdigit():
        return None
    with _lock:
        entry = _pending.get(wrapper_id)
        if not entry:
            return None
        cmds, until = entry
        if not cmds or time.time() > until:
            _pending.pop(wrapper_id, None)
            return None
        idx = int(t) - 1
        if not (0 <= idx < len(cmds)):
            return None
        cmd = cmds[idx]
        _pending.pop(wrapper_id, None)
        return cmd

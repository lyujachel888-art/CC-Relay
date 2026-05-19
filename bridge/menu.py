"""Phone-friendly slash-command menu.

Typing slash commands on a phone keyboard is painful (auto-complete fights you,
the `/` lives 2 layers deep). This module lets the user just type a keyword
(`/`, `菜单`, `cmd` …), receive a numbered menu, and then reply with a single
digit which we translate to the real command.
"""

import time
from threading import Lock
from typing import List, Optional

# Common Claude Code slash commands. Adjust freely — only what the user wants
# to be reachable from the phone.
COMMANDS: List[str] = [
    "/clear",
    "/compact",
    "/resume",
    "/model",
    "/cost",
    "/help",
    "/init",
    "/memory",
    "/agents",
    "/mcp",
    "/config",
    "/exit",
]

# Words that, on their own, open the menu. Kept narrow to avoid false hits on
# real prompts that happen to start with `?`.
_TRIGGERS = {"/", "菜单", "命令", "指令", "menu", "cmd", "commands"}

MENU_TTL_SEC = 120.0

_lock = Lock()
_pending: Optional[List[str]] = None
_pending_until: float = 0.0


def is_trigger(text: str) -> bool:
    return text.strip().lower() in _TRIGGERS


def build_menu_text() -> str:
    lines = ["📋 可用指令（回复数字注入）"]
    for i, cmd in enumerate(COMMANDS, 1):
        lines.append(f"{i}. {cmd}")
    lines.append("")
    lines.append(f"(菜单 {int(MENU_TTL_SEC)}s 内有效，直接发文字仍按 prompt 处理)")
    return "\n".join(lines)


def offer_menu() -> None:
    """Mark that a menu was just sent — start a TTL window for digit replies."""
    global _pending, _pending_until
    with _lock:
        _pending = list(COMMANDS)
        _pending_until = time.time() + MENU_TTL_SEC


def try_consume_choice(text: str) -> Optional[str]:
    """If `text` is a digit selecting an entry from the currently-pending
    menu, return the corresponding command and clear pending state. Else None."""
    global _pending, _pending_until
    t = text.strip()
    if not t.isdigit():
        return None
    with _lock:
        if not _pending or time.time() > _pending_until:
            _pending = None
            return None
        idx = int(t) - 1
        if not (0 <= idx < len(_pending)):
            return None
        cmd = _pending[idx]
        _pending = None  # consume — one digit per menu
        return cmd

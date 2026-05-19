"""Handle "传 X" / "send X" feishu commands that upload a local file back to
the user on feishu."""

from pathlib import Path
from typing import Optional

# WSL bridge can see Windows files via /mnt/<drive>/...
PROJECT_ROOT_WSL = Path("/mnt/e/MyProject/RC")
MAX_BYTES = 30 * 1024 * 1024  # feishu file message hard limit (~30MB)

_TRIGGERS = ("传 ", "传:", "传：", "send ", "上传 ")


def parse_send_command(text: str) -> Optional[str]:
    """If `text` starts with a send trigger, return the path argument. Else None."""
    t = text.lstrip()
    for trig in _TRIGGERS:
        if t.startswith(trig):
            return t[len(trig):].strip().strip('"').strip("'")
    return None


def resolve_to_wsl(user_path: str) -> Optional[Path]:
    """Map a Windows-style or relative path the user typed on the phone into
    a WSL path the bridge can actually open."""
    p = (user_path or "").strip().strip('"').strip("'").replace("\\", "/")
    if not p:
        return None
    # Windows-style absolute: E:/MyProject/...
    if len(p) >= 3 and p[1] == ":" and p[2] == "/":
        drive = p[0].lower()
        rest = p[3:]
        return Path(f"/mnt/{drive}/{rest}")
    # Already WSL absolute
    if p.startswith("/"):
        return Path(p)
    # Relative to project root
    return PROJECT_ROOT_WSL / p

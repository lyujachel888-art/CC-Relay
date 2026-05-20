"""Handle "传 X" / "send X" feishu commands that upload a local file back to
the user on feishu."""

from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MAX_BYTES = 30 * 1024 * 1024  # feishu file message hard limit (~30MB)

_TRIGGERS = ("传 ", "传:", "传：", "send ", "上传 ")


def parse_send_command(text: str) -> Optional[str]:
    """If `text` starts with a send trigger, return the path argument. Else None."""
    t = text.lstrip()
    for trig in _TRIGGERS:
        if t.startswith(trig):
            return t[len(trig):].strip().strip('"').strip("'")
    return None


def resolve_path(user_path: str) -> Optional[Path]:
    """Map a path the user typed on the phone into a Windows Path the bridge can open.

    Accepts Windows absolute paths (E:\\... or E:/...) and paths relative to the
    project root. Forward and back slashes are both accepted.
    """
    p = (user_path or "").strip().strip('"').strip("'")
    if not p:
        return None
    p = p.replace("/", "\\")
    # Windows absolute path: starts with drive letter + colon
    if len(p) >= 2 and p[1] == ":":
        return Path(p)
    # Relative to project root
    return PROJECT_ROOT / p


def is_within_project(path: Path) -> bool:
    """True iff path sits under the project root.

    Security allow-list for "传 X" uploads — rejects anything outside the project
    (e.g. C:\\Windows\\System32 or user home) so a phone client can't exfiltrate
    arbitrary files.
    """
    try:
        path.resolve(strict=False).relative_to(PROJECT_ROOT.resolve())
        return True
    except (ValueError, OSError):
        return False

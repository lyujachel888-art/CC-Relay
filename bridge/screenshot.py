"""Take a screenshot of the wrapper's Claude window by calling the PowerShell helper.

:author: jachel.lyu
"""

import logging
import subprocess
import time
from pathlib import Path

log = logging.getLogger("bridge.screenshot")

_CACHE_DIR = Path(__file__).resolve().parent.parent / ".feishu-cache"
_SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "screenshot.ps1"

DEFAULT_TITLE = "cc-bridge-wrapper"


def take(title_substring: str = DEFAULT_TITLE, timeout: int = 10) -> Path:
    """Capture a screenshot to .feishu-cache/ and return the Path."""
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    ts = int(time.time() * 1000)
    out_path = _CACHE_DIR / f"snap_{ts}.png"

    cmd = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", str(_SCRIPT_PATH),
        "-OutPath", str(out_path),
        "-TitleSubstring", title_substring or "",
    ]
    log.info("running screenshot: %r", cmd)
    proc = subprocess.run(cmd, capture_output=True, timeout=timeout)
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", "replace") or proc.stderr.decode("gbk", "replace")
        raise RuntimeError(
            f"screenshot failed rc={proc.returncode} stderr={stderr.strip()[:300]}"
        )
    if not out_path.exists():
        raise RuntimeError(f"screenshot script said ok but no file at {out_path}")
    log.info("screenshot ok: %s (%d bytes)", out_path, out_path.stat().st_size)
    return out_path

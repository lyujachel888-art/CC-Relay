"""Take a screenshot of (preferably) the wrapper's Claude window from WSL by
shelling out to a Windows-side PowerShell helper.

:author: jachel.lyu
"""

import logging
import subprocess
import time
from pathlib import Path

log = logging.getLogger("bridge.screenshot")

WSL_CACHE = Path("/mnt/e/MyProject/RC/.feishu-cache")
WIN_CACHE_PREFIX = r"E:\MyProject\RC\.feishu-cache"
WIN_SCRIPT_PATH = r"E:\MyProject\RC\scripts\screenshot.ps1"

DEFAULT_TITLE = "cc-bridge-wrapper"


def take(title_substring: str = DEFAULT_TITLE, timeout: int = 10) -> Path:
    """Capture a screenshot to .feishu-cache/ and return the WSL Path."""
    WSL_CACHE.mkdir(parents=True, exist_ok=True)
    ts = int(time.time() * 1000)
    fname = f"snap_{ts}.png"
    win_out = f"{WIN_CACHE_PREFIX}\\{fname}"
    wsl_out = WSL_CACHE / fname

    cmd = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", WIN_SCRIPT_PATH,
        "-OutPath", win_out,
        "-TitleSubstring", title_substring or "",
    ]
    log.info("running screenshot: %r", cmd)
    # NB: read bytes and decode tolerantly. PowerShell on a zh-CN Windows
    # often emits GBK in stderr, which crashes the default text-mode decoder.
    proc = subprocess.run(cmd, capture_output=True, timeout=timeout)
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", "replace") or proc.stderr.decode("gbk", "replace")
        raise RuntimeError(
            f"screenshot failed rc={proc.returncode} stderr={stderr.strip()[:300]}"
        )
    if not wsl_out.exists():
        raise RuntimeError(f"screenshot script said ok but no file at {wsl_out}")
    log.info("screenshot ok: %s (%s bytes)", wsl_out, wsl_out.stat().st_size)
    return wsl_out

"""Save Feishu-downloaded images and files to a local cache dir and return a
Windows-style absolute path that Claude (running in Windows) can read."""

import re
import time
from pathlib import Path

# bridge runs in WSL1; Claude runs on Windows. Same project, two views.
WSL_PROJECT_ROOT = Path("/mnt/e/MyProject/RC")
WIN_PROJECT_ROOT = r"E:\MyProject\RC"
CACHE_SUBDIR = ".feishu-cache"

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
_UNSAFE_FILENAME = re.compile(r"[\\/:*?\"<>|\x00-\x1f]")


def _cache_dir() -> Path:
    d = WSL_PROJECT_ROOT / CACHE_SUBDIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def _win_path(fname: str) -> str:
    return f"{WIN_PROJECT_ROOT}\\{CACHE_SUBDIR}\\{fname}"


def save_image_bytes(data: bytes, hint_name: str = "") -> str:
    """Write `data` to the cache dir; return its Windows-style absolute path.
    Used for inline images — picks a safe extension or defaults to .png."""
    suffix = Path(hint_name).suffix.lower() if hint_name else ""
    if suffix not in _IMAGE_SUFFIXES:
        suffix = ".png"

    ts = int(time.time() * 1000)
    fname = f"feishu_{ts}{suffix}"
    (_cache_dir() / fname).write_bytes(data)
    return _win_path(fname)


def save_file_bytes(data: bytes, file_name: str) -> str:
    """Write a generic file (PDF / docx / archive / …) to the cache dir,
    preserving the original filename when safe. Returns the Windows path."""
    base = (file_name or "").strip() or "file.bin"
    base = _UNSAFE_FILENAME.sub("_", base)
    # Bound length so the resulting filesystem path stays reasonable.
    if len(base) > 80:
        stem = Path(base).stem[:60]
        ext = Path(base).suffix[:16]
        base = stem + ext

    ts = int(time.time() * 1000)
    fname = f"{ts}_{base}"
    (_cache_dir() / fname).write_bytes(data)
    return _win_path(fname)

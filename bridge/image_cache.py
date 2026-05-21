"""Save Feishu-downloaded images and files to per-wrapper cache subdirs.

Phase 1 multi-wrapper: each wrapper gets its own subdir so two projects'
inline images don't clobber filename collisions or leak across contexts."""

import re
import time
from pathlib import Path

# Phase 1: bridge runs on Windows (post-WSL migration). Cache lives under the
# bridge module dir; can be overridden by tests via _BASE_DIR.
_BASE_DIR = Path(__file__).resolve().parent.parent / ".feishu-cache"

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
_UNSAFE_FILENAME = re.compile(r"[\\/:*?\"<>|\x00-\x1f]")


def _bucket_dir(wrapper_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_\-]", "_", wrapper_id) or "default"
    d = _BASE_DIR / safe
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_image_bytes(wrapper_id: str, data: bytes, hint_name: str = "") -> str:
    suffix = Path(hint_name).suffix.lower() if hint_name else ""
    if suffix not in _IMAGE_SUFFIXES:
        suffix = ".png"
    ts = int(time.time() * 1000)
    fname = f"feishu_{ts}{suffix}"
    out = _bucket_dir(wrapper_id) / fname
    out.write_bytes(data)
    return str(out)


def save_file_bytes(wrapper_id: str, data: bytes, file_name: str) -> str:
    base = (file_name or "").strip() or "file.bin"
    base = _UNSAFE_FILENAME.sub("_", base)
    if len(base) > 80:
        stem = Path(base).stem[:60]
        ext = Path(base).suffix[:16]
        base = stem + ext
    ts = int(time.time() * 1000)
    fname = f"{ts}_{base}"
    out = _bucket_dir(wrapper_id) / fname
    out.write_bytes(data)
    return str(out)

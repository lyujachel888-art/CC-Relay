"""Phase 1 minimal config.json persistence.

Schema (Phase 1):
  {
    "version": 1,
    "wrappers": [{"id": str, "name": str, "expected_cwd": str}, ...],
    "active_wrapper_id": str | null
  }

Phase 2 will extend with bots[] and mappings[]; Phase 1 keeps the schema small.
Atomic write: temp file -> fsync -> rename. On corrupt load, falls back to .bak.
"""

import json
import os
import shutil
from pathlib import Path
from threading import Lock
from typing import Optional


CURRENT_VERSION = 1


def _default_doc() -> dict:
    return {"version": CURRENT_VERSION, "wrappers": [], "active_wrapper_id": None}


class ConfigStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = Lock()
        self._doc = self._load_with_recovery()

    def _load_with_recovery(self) -> dict:
        if not self.path.exists():
            return _default_doc()
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            bak = self.path.with_suffix(self.path.suffix + ".bak")
            if bak.exists():
                try:
                    return json.loads(bak.read_text(encoding="utf-8"))
                except Exception:
                    pass
            return _default_doc()

    @property
    def wrappers(self) -> list:
        with self._lock:
            return list(self._doc.get("wrappers", []))

    @property
    def active_wrapper_id(self) -> Optional[str]:
        with self._lock:
            return self._doc.get("active_wrapper_id")

    def upsert_wrapper(self, *, id: str, name: str, expected_cwd: str) -> None:
        with self._lock:
            wrappers = self._doc.setdefault("wrappers", [])
            for w in wrappers:
                if w["id"] == id:
                    w["name"] = name
                    w["expected_cwd"] = expected_cwd
                    break
            else:
                wrappers.append({"id": id, "name": name, "expected_cwd": expected_cwd})
            self._save_locked()

    def set_active(self, wrapper_id: Optional[str]) -> None:
        with self._lock:
            self._doc["active_wrapper_id"] = wrapper_id
            self._save_locked()

    def _save_locked(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Backup current good state before overwriting
        if self.path.exists():
            bak = self.path.with_suffix(self.path.suffix + ".bak")
            shutil.copy2(self.path, bak)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            payload = json.dumps(self._doc, ensure_ascii=False, indent=2)
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())
            tmp.replace(self.path)
        except Exception:
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass
            raise

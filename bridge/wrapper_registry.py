"""In-memory registry of online wrappers. Tracks id → (host, port, pid, token,
last_seen) with a simple heartbeat timeout. Persistent wrapper metadata
(name, expected_cwd) is stored in config.json by `config_store`, not here."""

import hmac
import secrets
import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Callable

from errors import BadToken, WrapperConflict, WrapperOffline, WrapperUnknown


@dataclass
class WrapperInfo:
    id: str
    name: str
    cwd: str
    port: int
    pid: int
    token: str
    registered_at: float
    last_seen: float


@dataclass
class WrapperRegistry:
    timeout_sec: float = 30.0
    clock: Callable[[], float] = field(default_factory=lambda: time.time)
    _items: "dict[str, WrapperInfo]" = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock)

    def register(self, *, id: str, name: str, cwd: str, port: int, pid: int) -> WrapperInfo:
        with self._lock:
            now = self.clock()
            existing = self._items.get(id)
            if existing is not None and (now - existing.last_seen) <= self.timeout_sec:
                raise WrapperConflict(f"{id} is already registered and online")
            token = "wrp_" + secrets.token_urlsafe(24)
            info = WrapperInfo(
                id=id, name=name, cwd=cwd, port=port, pid=pid,
                token=token, registered_at=now, last_seen=now,
            )
            self._items[id] = info
            return info

    def heartbeat(self, id: str, token: str) -> None:
        with self._lock:
            info = self._items.get(id)
            if info is None:
                raise WrapperUnknown(id)
            if not hmac.compare_digest(info.token, token):
                raise BadToken(id)
            info.last_seen = self.clock()

    def deregister(self, id: str, token: str) -> None:
        with self._lock:
            info = self._items.get(id)
            if info is None:
                raise WrapperUnknown(id)
            if not hmac.compare_digest(info.token, token):
                raise BadToken(id)
            # mark stale; keep entry so id remains known until next register
            info.last_seen = 0.0

    def is_online(self, id: str) -> bool:
        with self._lock:
            info = self._items.get(id)
            if info is None:
                return False
            return (self.clock() - info.last_seen) <= self.timeout_sec

    def lookup_port(self, id: str) -> int:
        with self._lock:
            info = self._items.get(id)
            if info is None:
                raise WrapperUnknown(id)
            if (self.clock() - info.last_seen) > self.timeout_sec:
                raise WrapperOffline(id)
            return info.port

    def snapshot(self) -> "list[dict]":
        """Read-only copy for /api/wrappers GET."""
        with self._lock:
            now = self.clock()
            return [
                {
                    "id": w.id, "name": w.name, "cwd": w.cwd,
                    "port": w.port, "pid": w.pid,
                    "online": (now - w.last_seen) <= self.timeout_sec,
                    "last_seen": w.last_seen,
                }
                for w in self._items.values()
            ]

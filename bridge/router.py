"""Phase 1 router: single bot, multiple wrappers.

Phase 2 will extend to M:N with per-bot active state and mappings table.
For Phase 1 there is exactly one active_wrapper_id (in config.json) and
exactly one bot (configured via .env).
"""

from typing import Optional

from config_store import ConfigStore
from wrapper_registry import WrapperRegistry


class Router:
    def __init__(self, *, store: ConfigStore, registry: WrapperRegistry):
        self._store = store
        self._registry = registry

    def inbound(self) -> Optional[str]:
        """Return wrapper_id to inject incoming Feishu messages into.
        None if active wrapper is offline / unset."""
        active = self._store.active_wrapper_id
        if not active:
            return None
        if not self._registry.is_online(active):
            return None
        return active

    def set_active(self, wrapper_id: Optional[str]) -> None:
        self._store.set_active(wrapper_id)

    def resolve(self, name_or_id: str) -> Optional[str]:
        """Resolve a user-supplied identifier to a wrapper id.
        Checks: exact id, then case-insensitive name match."""
        if not name_or_id:
            return None
        needle = name_or_id.strip()
        for w in self._store.wrappers:
            if w["id"] == needle:
                return w["id"]
        low = needle.lower()
        for w in self._store.wrappers:
            if w["name"].lower() == low:
                return w["id"]
        return None

    def list_wrappers(self) -> list:
        """For /switch menu — name, online, active per wrapper."""
        active = self._store.active_wrapper_id
        out = []
        for w in self._store.wrappers:
            out.append({
                "id": w["id"],
                "name": w["name"],
                "online": self._registry.is_online(w["id"]),
                "active": w["id"] == active,
            })
        return out

"""Async fan-out of hook events to SSE subscribers.

Slow subscribers drop events (bounded queue) rather than blocking the
publisher. This keeps a stuck HUD client from stalling the bridge.
"""
import asyncio
import logging
from typing import Any, Dict, List

log = logging.getLogger("bridge.event_broadcast")


class EventBroadcaster:
    def __init__(self, maxsize: int = 100) -> None:
        self._maxsize = maxsize
        self._subscribers: List[asyncio.Queue] = []

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=self._maxsize)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        try:
            self._subscribers.remove(q)
        except ValueError:
            pass

    async def publish(self, event: Dict[str, Any]) -> None:
        for q in list(self._subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                log.debug("dropped event for slow subscriber: %s", event.get("type"))

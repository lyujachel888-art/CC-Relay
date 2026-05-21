"""Async fan-out of hook events to SSE subscribers.

Slow subscribers drop events (bounded queue) rather than blocking the
publisher. This keeps a stuck HUD client from stalling the bridge.

Thread-safety note: ``publish`` may be called from any thread / event loop.
Each subscriber queue is coupled to the event loop that called ``subscribe``;
we use ``loop.call_soon_threadsafe`` so that ``await q.get()`` in the
subscriber's loop wakes up correctly even when the publisher runs in a
different loop or a plain background thread.
"""
import asyncio
import logging
from typing import Any, Dict, List, Tuple

log = logging.getLogger("bridge.event_broadcast")

Event = Dict[str, Any]


class EventBroadcaster:
    def __init__(self, maxsize: int = 100) -> None:
        self._maxsize = maxsize
        # Each entry is (queue, owning_loop)
        self._subscribers: List[Tuple[asyncio.Queue[Event], asyncio.AbstractEventLoop]] = []

    def subscribe(self) -> asyncio.Queue[Event]:
        q: asyncio.Queue[Event] = asyncio.Queue(maxsize=self._maxsize)
        loop = asyncio.get_running_loop()
        self._subscribers.append((q, loop))
        return q

    def unsubscribe(self, q: asyncio.Queue[Event]) -> None:
        self._subscribers = [(sq, lp) for sq, lp in self._subscribers if sq is not q]

    async def publish(self, event: Event) -> None:
        for q, loop in list(self._subscribers):
            try:
                loop.call_soon_threadsafe(_put_nowait_silent, q, event)
            except RuntimeError:
                # loop is closed; subscriber is gone
                pass


def _put_nowait_silent(q: "asyncio.Queue[Event]", event: Event) -> None:
    """Silently drop the event if the queue is full (called inside subscriber loop)."""
    try:
        q.put_nowait(event)
    except asyncio.QueueFull:
        log.debug("dropped event for slow subscriber")

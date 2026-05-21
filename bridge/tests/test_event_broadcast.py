import asyncio
import pytest
from event_broadcast import EventBroadcaster


@pytest.mark.asyncio
async def test_subscribe_returns_queue_that_receives_published_events():
    bc = EventBroadcaster()
    q = bc.subscribe()

    await bc.publish({"type": "tool_use", "project": "RC", "text": "Bash: ls"})
    event = await asyncio.wait_for(q.get(), timeout=0.5)

    assert event == {"type": "tool_use", "project": "RC", "text": "Bash: ls"}


@pytest.mark.asyncio
async def test_publish_fanouts_to_all_subscribers():
    bc = EventBroadcaster()
    q1, q2 = bc.subscribe(), bc.subscribe()

    await bc.publish({"type": "stop", "project": "Bot"})

    assert (await asyncio.wait_for(q1.get(), timeout=0.5))["project"] == "Bot"
    assert (await asyncio.wait_for(q2.get(), timeout=0.5))["project"] == "Bot"


@pytest.mark.asyncio
async def test_unsubscribe_stops_delivery_to_that_queue():
    bc = EventBroadcaster()
    q1, q2 = bc.subscribe(), bc.subscribe()
    bc.unsubscribe(q1)

    await bc.publish({"type": "stop"})

    assert q1.empty()
    assert not q2.empty()


@pytest.mark.asyncio
async def test_slow_subscriber_drops_events_instead_of_blocking_publisher():
    """A subscriber that never reads must not block publish() for others."""
    bc = EventBroadcaster(maxsize=2)
    slow = bc.subscribe()
    fast = bc.subscribe()

    for i in range(10):
        await bc.publish({"i": i})

    # fast subscriber gets first 2 events, then drops kick in
    assert fast.qsize() == 2
    # slow subscriber: full queue, dropped excess
    assert slow.qsize() == 2

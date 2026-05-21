import asyncio
import httpx
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from server import create_app


def test_user_prompt_endpoint_calls_feishu_with_prefix():
    mock_feishu = MagicMock()
    app = create_app(mock_feishu, expected_token="TOKEN")
    client = TestClient(app)

    resp = client.post("/hook/user_prompt", json={"text": "what time is it"}, headers={"Authorization": "Bearer TOKEN"})

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    # user_prompt now sends a header card (emoji + label title, body text)
    mock_feishu.send_header_card.assert_called_once_with("🧑 你说", "what time is it", color="blue")


def test_assistant_reply_endpoint_calls_feishu_with_prefix():
    mock_feishu = MagicMock()
    app = create_app(mock_feishu, expected_token="TOKEN")
    client = TestClient(app)

    resp = client.post("/hook/assistant_reply", json={"text": "it is noon"}, headers={"Authorization": "Bearer TOKEN"})

    assert resp.status_code == 200
    # assistant_reply sends a markdown card for short text (no [project] chip, no meta)
    mock_feishu.send_markdown_card.assert_called_once_with("it is noon", title="🤖 Claude", color="violet", with_actions=True)


def test_user_prompt_swallows_feishu_errors_returns_ok():
    """Hook should never block Claude Code; if feishu fails, still return ok."""
    mock_feishu = MagicMock()
    mock_feishu.send_header_card.side_effect = RuntimeError("network down")
    app = create_app(mock_feishu, expected_token="TOKEN")
    client = TestClient(app)

    resp = client.post("/hook/user_prompt", json={"text": "hi"}, headers={"Authorization": "Bearer TOKEN"})

    assert resp.status_code == 200
    assert resp.json()["ok"] is False


async def test_events_endpoint_streams_published_events():
    import asyncio
    import json
    from event_broadcast import EventBroadcaster

    mock_feishu = MagicMock()
    bc = EventBroadcaster()
    app = create_app(mock_feishu, expected_token="TOKEN", broadcaster=bc, sse_idle_timeout=2.0)

    transport = httpx.ASGITransport(app=app)

    # Schedule the publish as a task so it runs concurrently with the ASGI app's
    # SSE generator, which blocks on q.get() until an event arrives.
    async def _publish():
        # A short sleep lets the ASGI generator reach subscribe() + q.get() before
        # we put anything into the queue.
        await asyncio.sleep(0.05)
        await bc.publish({"type": "tool_use", "project": "RC", "text": "ls"})

    pub_task = asyncio.create_task(_publish())

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/events")

    await pub_task

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")

    found = False
    for line in resp.text.splitlines():
        if line.startswith("data: "):
            payload = json.loads(line[len("data: "):])
            assert payload == {"type": "tool_use", "project": "RC", "text": "ls"}
            found = True
            break
    assert found, "no SSE data frame received within timeout"


async def test_user_prompt_publishes_to_broadcaster():
    from event_broadcast import EventBroadcaster
    bc = EventBroadcaster()
    q = bc.subscribe()
    app = create_app(MagicMock(), expected_token="T", broadcaster=bc)

    import httpx
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/hook/user_prompt",
            json={"text": "[RC] do something"},
            headers={"Authorization": "Bearer T"},
        )

    event = await asyncio.wait_for(q.get(), timeout=0.5)
    assert event["type"] == "user_prompt"
    assert event["project"] == "RC"
    assert event["text"] == "do something"


async def test_bash_result_publishes_with_fail_meta():
    from event_broadcast import EventBroadcaster
    bc = EventBroadcaster()
    q = bc.subscribe()
    app = create_app(MagicMock(), expected_token="T", broadcaster=bc)

    import httpx
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/hook/bash_result",
            json={"text": "[RC] $ ls\n\nError: not found", "meta": "fail"},
            headers={"Authorization": "Bearer T"},
        )

    event = await asyncio.wait_for(q.get(), timeout=0.5)
    assert event["type"] == "bash_result"
    assert event["meta"] == "fail"

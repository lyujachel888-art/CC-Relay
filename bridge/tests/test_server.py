import httpx
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from server import create_app


def test_user_prompt_endpoint_calls_feishu_with_prefix():
    mock_feishu = MagicMock()
    app = create_app(mock_feishu)
    client = TestClient(app)

    resp = client.post("/hook/user_prompt", json={"text": "what time is it"})

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    mock_feishu.send_text.assert_called_once_with("🧑 what time is it")


def test_assistant_reply_endpoint_calls_feishu_with_prefix():
    mock_feishu = MagicMock()
    app = create_app(mock_feishu)
    client = TestClient(app)

    resp = client.post("/hook/assistant_reply", json={"text": "it is noon"})

    assert resp.status_code == 200
    mock_feishu.send_text.assert_called_once_with("🤖 it is noon")


def test_user_prompt_swallows_feishu_errors_returns_ok():
    """Hook should never block Claude Code; if feishu fails, still return ok."""
    mock_feishu = MagicMock()
    mock_feishu.send_text.side_effect = RuntimeError("network down")
    app = create_app(mock_feishu)
    client = TestClient(app)

    resp = client.post("/hook/user_prompt", json={"text": "hi"})

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

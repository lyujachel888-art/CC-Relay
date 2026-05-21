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


def test_events_endpoint_streams_published_events():
    from event_broadcast import EventBroadcaster

    mock_feishu = MagicMock()
    bc = EventBroadcaster()
    app = create_app(mock_feishu, expected_token="TOKEN", broadcaster=bc, sse_idle_timeout=0.5)
    client = TestClient(app)

    import threading, time, asyncio

    def publish_later():
        time.sleep(0.1)
        loop = asyncio.new_event_loop()
        loop.run_until_complete(bc.publish({"type": "tool_use", "project": "RC", "text": "ls"}))
        loop.close()

    threading.Thread(target=publish_later, daemon=True).start()

    with client.stream("GET", "/events") as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        for chunk in resp.iter_lines():
            if chunk.startswith("data: "):
                import json
                payload = json.loads(chunk[len("data: "):])
                assert payload == {"type": "tool_use", "project": "RC", "text": "ls"}
                break

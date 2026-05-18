from unittest.mock import MagicMock
from feishu import FeishuClient


def test_send_text_calls_lark_create_message():
    mock_lark = MagicMock()
    fc = FeishuClient(
        app_id="aid",
        app_secret="sec",
        user_open_id="ou_test",
        lark_client=mock_lark,
    )

    fc.send_text("hello world")

    mock_lark.im.v1.message.create.assert_called_once()


def test_send_text_includes_text_in_request_content():
    """Verify the text is JSON-encoded into the request content field."""
    import json
    mock_lark = MagicMock()
    fc = FeishuClient("aid", "sec", "ou_test", lark_client=mock_lark)

    fc.send_text("你好 world")

    call = mock_lark.im.v1.message.create.call_args
    req = call[0][0]
    # Lark's request object stores body via .request_body; inspect serialized content
    # The internal structure differs across SDK versions; assert the text appears in any
    # string representation of the request.
    assert "你好 world" in str(req.request_body.__dict__) or "\\u4f60\\u597d" in str(req.request_body.__dict__)

from unittest.mock import MagicMock, patch
from long_conn import make_message_handler


@patch("long_conn.inject")
def test_handler_extracts_text_and_injects(mock_inject):
    handler = make_message_handler()

    fake_event = MagicMock()
    fake_event.event.message.content = '{"text":"hello there"}'
    fake_event.event.sender.sender_id.open_id = "ou_abc"

    handler(fake_event)

    mock_inject.assert_called_once_with("hello there")


@patch("long_conn.inject")
def test_handler_ignores_empty_text(mock_inject):
    handler = make_message_handler()
    fake_event = MagicMock()
    fake_event.event.message.content = '{"text":""}'
    fake_event.event.sender.sender_id.open_id = "ou_abc"

    handler(fake_event)

    mock_inject.assert_not_called()


@patch("long_conn.inject")
def test_handler_ignores_non_text_content(mock_inject):
    handler = make_message_handler()
    fake_event = MagicMock()
    # Non-JSON content (e.g., image)
    fake_event.event.message.content = '{"image_key":"img_xxx"}'
    fake_event.event.sender.sender_id.open_id = "ou_abc"

    handler(fake_event)

    mock_inject.assert_not_called()


@patch("long_conn.inject")
@patch("builtins.print")
def test_handler_logs_sender_open_id(mock_print, mock_inject):
    """For first-run setup we need open_id printed to stdout."""
    handler = make_message_handler()
    fake_event = MagicMock()
    fake_event.event.message.content = '{"text":"hi"}'
    fake_event.event.sender.sender_id.open_id = "ou_first_time"

    handler(fake_event)

    printed = " ".join(str(c) for c in mock_print.call_args_list)
    assert "ou_first_time" in printed

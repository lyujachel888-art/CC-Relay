from unittest.mock import patch
from injector import inject_to_tmux


@patch("injector.subprocess.run")
def test_inject_sends_text_then_enter(mock_run):
    inject_to_tmux("cc1", "hello world")

    assert mock_run.call_count == 2
    mock_run.assert_any_call(
        ["tmux", "send-keys", "-t", "cc1", "--", "hello world"],
        check=True,
    )
    mock_run.assert_any_call(
        ["tmux", "send-keys", "-t", "cc1", "Enter"],
        check=True,
    )


@patch("injector.subprocess.run")
def test_inject_handles_multiline_text(mock_run):
    inject_to_tmux("cc1", "line1\nline2")

    # Multiline text is passed as a single send-keys argument; tmux handles newlines
    mock_run.assert_any_call(
        ["tmux", "send-keys", "-t", "cc1", "--", "line1\nline2"],
        check=True,
    )

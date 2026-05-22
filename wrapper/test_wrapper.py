"""Unit tests for wrapper.py socket connection handling logic.

Only tests handle_connection() — no PTY or real socket required.
Uses a socket.socketpair() for a real in-process byte pipe.
"""
import os
import socket
import sys
import tempfile
import threading
from pathlib import Path
from unittest.mock import MagicMock, call

# Make sure the wrapper module is importable without winpty installed
# by patching the import at sys.modules level before importing.
import types
_winpty_stub = types.ModuleType("winpty")
_winpty_stub.PtyProcess = object  # placeholder class
sys.modules.setdefault("winpty", _winpty_stub)

# Now import the function under test
sys.path.insert(0, str(Path(__file__).parent))
from wrapper import handle_connection
import wrapper as wrapper_mod


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _send_and_collect(payload_bytes: bytes) -> tuple[list, bytes]:
    """Create a socket pair, send payload from one end, call handle_connection
    on the other end, return (write_calls, response_bytes)."""
    write_func = MagicMock()
    client, server = socket.socketpair()
    try:
        # Send payload then close the write side so recv loop sees EOF
        client.sendall(payload_bytes)
        client.shutdown(socket.SHUT_WR)

        response = handle_connection(server, write_func)
    finally:
        client.close()
        server.close()

    return write_func.call_args_list, response


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_normal_payload_writes_text_then_cr():
    """A normal text payload should call write_func twice: text then '\\r'."""
    calls, response = _send_and_collect(b"hello world")
    assert calls == [call("hello world"), call("\r")], f"unexpected calls: {calls}"
    assert response == b"OK\n"


def test_trailing_newlines_stripped():
    """Trailing \\r\\n on the payload should be stripped before forwarding."""
    calls, response = _send_and_collect(b"some command\r\n")
    assert calls == [call("some command"), call("\r")], f"unexpected calls: {calls}"
    assert response == b"OK\n"


def test_empty_payload_returns_empty():
    """An empty payload (or only whitespace stripped to empty) should not call
    write_func and should respond with EMPTY."""
    calls, response = _send_and_collect(b"")
    assert calls == [], f"expected no write calls, got: {calls}"
    assert response == b"EMPTY\n"


def test_only_crlf_payload_returns_empty():
    """A payload of just \\r\\n strips to empty — same as empty."""
    calls, response = _send_and_collect(b"\r\n")
    assert calls == [], f"expected no write calls, got: {calls}"
    assert response == b"EMPTY\n"


# ---------------------------------------------------------------------------
# _resolve_cwd tests
# ---------------------------------------------------------------------------

def test_resolve_cwd_uses_env_when_dir_exists(monkeypatch):
    """When CLAUDE_CWD is set and points to a real dir, it wins."""
    from wrapper import _resolve_cwd
    with tempfile.TemporaryDirectory() as d:
        monkeypatch.setenv("CLAUDE_CWD", d)
        cwd, src = _resolve_cwd()
        # Compare via realpath to neutralize symlinks (e.g. /var vs /private/var)
        assert os.path.realpath(cwd) == os.path.realpath(d)
        assert src == "env CLAUDE_CWD"


def test_resolve_cwd_falls_back_when_env_dir_missing(monkeypatch, tmp_path):
    """If CLAUDE_CWD points to a non-existent path, fall back to process cwd."""
    from wrapper import _resolve_cwd
    monkeypatch.setenv("CLAUDE_CWD", str(tmp_path / "does_not_exist"))
    monkeypatch.chdir(tmp_path)
    cwd, src = _resolve_cwd()
    assert os.path.realpath(cwd) == os.path.realpath(str(tmp_path))
    assert src == "process cwd"


def test_resolve_cwd_no_env_uses_getcwd(monkeypatch, tmp_path):
    """No CLAUDE_CWD set → process cwd."""
    from wrapper import _resolve_cwd
    monkeypatch.delenv("CLAUDE_CWD", raising=False)
    monkeypatch.chdir(tmp_path)
    cwd, src = _resolve_cwd()
    assert os.path.realpath(cwd) == os.path.realpath(str(tmp_path))
    assert src == "process cwd"


if __name__ == "__main__":
    tests = [
        test_normal_payload_writes_text_then_cr,
        test_trailing_newlines_stripped,
        test_empty_payload_returns_empty,
        test_only_crlf_payload_returns_empty,
        test_resolve_cwd_uses_env_when_dir_exists,
        test_resolve_cwd_falls_back_when_env_dir_missing,
        test_resolve_cwd_no_env_uses_getcwd,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except Exception as exc:
            print(f"  FAIL  {t.__name__}: {exc}")
            failed += 1
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(failed)


# ---------------------------------------------------------------------------
# register_to_bridge tests (B1+B2 fix)
# ---------------------------------------------------------------------------


def _patch_http_post(monkeypatch, return_value):
    """Replace wrapper._http_post with a MagicMock returning a fixed (status, body)."""
    mock = MagicMock(return_value=return_value)
    monkeypatch.setattr(wrapper_mod, "_http_post", mock)
    return mock


def test_register_returns_ok(monkeypatch):
    _patch_http_post(monkeypatch, (200, {"token": "T-123"}))
    kind, tok = wrapper_mod.register_to_bridge("w1", "n1", "/cwd", 1234, 9999)
    assert kind == "ok"
    assert tok == "T-123"


def test_register_returns_conflict(monkeypatch):
    _patch_http_post(monkeypatch, (409, {}))
    kind, tok = wrapper_mod.register_to_bridge("w1", "n1", "/cwd", 1234, 9999)
    assert kind == "conflict"
    assert tok is None


def test_register_returns_transport_on_zero(monkeypatch):
    _patch_http_post(monkeypatch, (0, {}))
    kind, tok = wrapper_mod.register_to_bridge("w1", "n1", "/cwd", 1234, 9999)
    assert kind == "transport"
    assert tok is None


def test_register_returns_transport_on_5xx(monkeypatch):
    _patch_http_post(monkeypatch, (500, {}))
    kind, tok = wrapper_mod.register_to_bridge("w1", "n1", "/cwd", 1234, 9999)
    assert kind == "transport"
    assert tok is None


def test_register_does_not_exit_on_conflict(monkeypatch):
    """409 must no longer call sys.exit — caller decides what to do."""
    _patch_http_post(monkeypatch, (409, {}))
    # If register_to_bridge calls sys.exit, this test process dies; pytest
    # would report it as an error, not a passed test.
    kind, _ = wrapper_mod.register_to_bridge("w1", "n1", "/cwd", 1234, 9999)
    assert kind == "conflict"

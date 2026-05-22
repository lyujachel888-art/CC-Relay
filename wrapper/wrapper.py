"""Wrapper that runs claude.exe in a ConPTY and accepts external input via TCP socket.

:author: jachel.lyu
"""

import ctypes
import logging
import os
import shutil
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Optional

from winpty import PtyProcess


def current_term_size() -> tuple:
    """Return (rows, cols) of the current terminal, with a sane fallback."""
    try:
        s = shutil.get_terminal_size(fallback=(140, 40))
        return (s.lines, s.columns)
    except Exception:
        return (40, 140)


def resize_watcher(proc: PtyProcess, stop_event: threading.Event):
    """Poll the host terminal size and propagate changes to the child PTY.
    Windows has no SIGWINCH so polling is the only option."""
    last = current_term_size()
    while not stop_event.is_set() and proc.isalive():
        time.sleep(1.0)
        cur = current_term_size()
        if cur != last:
            try:
                proc.setwinsize(*cur)
                logging.info("resized PTY to rows=%d cols=%d", *cur)
            except Exception as e:
                logging.warning("setwinsize err: %s", e)
            last = cur


def set_console_utf8() -> None:
    """Switch the current process's console code page to UTF-8 (65001) so that
    text written into the ConPTY is interpreted as UTF-8 (not GBK/cp936) by the
    child process. Must be called BEFORE spawning the child."""
    try:
        k32 = ctypes.windll.kernel32
        k32.SetConsoleCP(65001)
        k32.SetConsoleOutputCP(65001)
    except Exception as e:
        logging.warning("set_console_utf8 failed: %s", e)


# Window title pattern: "云匣-{name}". bridge/screenshot.py searches for windows
# whose title contains "云匣-" so it can target a specific wrapper. The name part
# comes from --Name CLI arg or auto-derived CWD basename (see main()).
CONSOLE_TITLE_PREFIX = "云匣-"


def set_console_title(title: str) -> None:
    try:
        ctypes.windll.kernel32.SetConsoleTitleW(title)
    except Exception as e:
        logging.warning("SetConsoleTitle failed: %s", e)


def title_keeper(title: str, stop_event: threading.Event):
    """Claude's TUI emits OSC title-set sequences (\\x1b]0;...\\x07) that
    overwrite our window title — periodically force it back so the bridge's
    screenshot helper can still find this window by title."""
    while not stop_event.is_set():
        time.sleep(0.5)
        try:
            ctypes.windll.kernel32.SetConsoleTitleW(title)
        except Exception:
            pass

def _find_claude() -> str:
    """Locate claude.exe: env override → PATH → %LOCALAPPDATA% default install."""
    override = os.environ.get("CLAUDE_EXE")
    if override:
        return override
    found = shutil.which("claude")
    if found:
        return found
    local_app = os.environ.get("LOCALAPPDATA", "")
    if local_app:
        candidate = Path(local_app) / "AnthropicClaude" / "claude.exe"
        if candidate.exists():
            return str(candidate)
    raise FileNotFoundError(
        "claude.exe not found. Add claude to PATH or set the CLAUDE_EXE environment variable."
    )

import argparse
import hashlib
import json as _json
import re as _re
import urllib.request as _urlreq
import urllib.error as _urlerr

BRIDGE_URL = os.environ.get("BRIDGE_URL", "http://127.0.0.1:8787")
REGISTER_RETRY_INTERVAL = 30.0  # seconds between standalone-mode retries
DEFAULT_HEARTBEAT_INTERVAL = 15.0


def _resolve_cwd() -> tuple[str, str]:
    """Pick the cwd the child Claude process should run in.

    Priority:
      1. $CLAUDE_CWD env var, if it points to an existing dir
      2. os.getcwd() — the wrapper's own process cwd

    Returns (cwd_path, source_label) where source_label is "env CLAUDE_CWD"
    or "process cwd" for logging.
    """
    env_cwd = os.environ.get("CLAUDE_CWD")
    if env_cwd and os.path.isdir(env_cwd):
        return env_cwd, "env CLAUDE_CWD"
    if env_cwd:
        logging.warning("CLAUDE_CWD=%r not a directory, ignoring", env_cwd)
    return os.getcwd(), "process cwd"


def _sanitize_for_id(s: str) -> str:
    s = s.lower()
    s = _re.sub(r"[^a-z0-9]+", "-", s)
    s = _re.sub(r"-+", "-", s).strip("-")
    return s or "default"


def _derive_default_id(cwd: str) -> str:
    base = _sanitize_for_id(Path(cwd).name)
    return f"wrapper-{base}"


def _id_with_collision_suffix(base_id: str, cwd: str) -> str:
    h = hashlib.sha1(cwd.encode("utf-8")).hexdigest()[:4]
    return f"{base_id}-{h}"


def pick_free_port() -> int:
    """Ask the OS for a free local TCP port.

    Note: there is a small TOCTOU window between this function returning and
    the caller binding to the port. Another process could (theoretically) grab
    it in between. On localhost-only single-user systems this is acceptable;
    Phase 2 may refactor to bind once and pass the socket through.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
    finally:
        s.close()


def _http_post(url: str, payload: dict, token: str = "", timeout: float = 3.0) -> tuple:
    """Return (status_code, json_body). status_code = 0 on transport error."""
    body = _json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = _urlreq.Request(url, data=body, headers=headers, method="POST")
    try:
        resp = _urlreq.urlopen(req, timeout=timeout)
        return resp.status, _json.loads(resp.read().decode("utf-8") or "{}")
    except _urlerr.HTTPError as e:
        try:
            return e.code, _json.loads(e.read().decode("utf-8") or "{}")
        except Exception:
            return e.code, {}
    except Exception:
        return 0, {}


def register_to_bridge(wrapper_id: str, name: str, cwd: str, port: int, pid: int) -> Optional[str]:
    """Return token on success, None on failure. 409 = id conflict (caller exits)."""
    status, body = _http_post(
        f"{BRIDGE_URL}/api/wrappers/register",
        {"id": wrapper_id, "name": name, "cwd": cwd, "port": port, "pid": pid},
    )
    if status == 200:
        logging.info("registered to bridge id=%s", wrapper_id)
        return body.get("token", "")
    if status == 409:
        logging.error("bridge rejected register: id=%s already online", wrapper_id)
        sys.stderr.write(f"FATAL: wrapper id '{wrapper_id}' already registered\n")
        sys.exit(3)
    logging.warning("register failed (status=%d), entering standalone mode", status)
    return None


CLAUDE_EXE = _find_claude()
LISTEN_HOST = "127.0.0.1"
LOG_FILE = Path(__file__).parent / "wrapper.log"


def setup_logging():
    logging.basicConfig(
        filename=str(LOG_FILE),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(threadName)s: %(message)s",
    )


def pty_to_stdout(proc: PtyProcess, stop_event: threading.Event):
    """Drain PTY output and forward to our stdout, until PTY exits."""
    out = sys.stdout.buffer
    while not stop_event.is_set() and proc.isalive():
        try:
            data = proc.read(4096)
        except EOFError:
            break
        if data:
            buf = data.encode("utf-8", "replace") if isinstance(data, str) else data
            out.write(buf)
            out.flush()
        else:
            # tiny sleep to avoid busy loop
            time.sleep(0.01)
    stop_event.set()
    logging.info("pty_to_stdout exiting")


# When msvcrt.getwch() reads an arrow/function key on Windows it returns a
# 2-char sequence: a prefix (\x00 or \xe0) followed by a scan code char.
# Claude's TUI (Node.js Ink) expects POSIX-style ANSI escape sequences, so
# we translate the most common ones here.
_EXTENDED_PREFIXES = ("\x00", "\xe0")
_EXT_KEY_MAP = {
    "H": "\x1b[A",   # Up
    "P": "\x1b[B",   # Down
    "M": "\x1b[C",   # Right
    "K": "\x1b[D",   # Left
    "G": "\x1b[H",   # Home
    "O": "\x1b[F",   # End
    "I": "\x1b[5~",  # PageUp
    "Q": "\x1b[6~",  # PageDown
    "S": "\x1b[3~",  # Delete (forward delete, not Backspace)
    "R": "\x1b[2~",  # Insert
}


def stdin_to_pty(proc: PtyProcess, stop_event: threading.Event):
    """Read keystrokes from the wrapper's stdin and forward to the child PTY.
    Uses msvcrt.getwch() which blocks until a key is pressed — no polling
    overhead, no input latency."""
    import msvcrt
    while not stop_event.is_set() and proc.isalive():
        try:
            ch = msvcrt.getwch()  # blocks until next key
        except Exception as e:
            logging.warning("stdin read err: %s", e)
            break

        # Extended key sequence (arrows, Home/End, PageUp/Down, Delete, F1-F12 …)
        if ch in _EXTENDED_PREFIXES:
            try:
                scan = msvcrt.getwch()
            except Exception as e:
                logging.warning("extended-key read err: %s", e)
                break
            mapped = _EXT_KEY_MAP.get(scan)
            if mapped is None:
                logging.info("unmapped ext key: prefix=U+%04X scan=%r", ord(ch), scan)
                continue
            logging.info("ext key %r -> %r", scan, mapped)
            try:
                proc.write(mapped)
            except Exception as e:
                logging.warning("PTY write err: %s", e)
                break
            continue

        # Windows console returns Backspace as \x08 (BS), but Claude's TUI
        # (Node.js Ink + readline, modeled on POSIX) expects \x7f (DEL).
        if ch == "\x08":
            ch = "\x7f"

        if ord(ch) < 0x20 or ord(ch) == 0x7f:
            logging.info("kbd ctrl: U+%04X", ord(ch))

        try:
            proc.write(ch)
        except Exception as e:
            logging.warning("PTY write err: %s", e)
            break
    stop_event.set()
    logging.info("stdin_to_pty exiting")


def handle_connection(conn: socket.socket, write_func):
    """Read entire payload from a connected socket, call write_func with text + \\r.

    Returns the response bytes that were sent back to the client.
    """
    conn.settimeout(2.0)
    chunks = []
    while True:
        buf = conn.recv(4096)
        if not buf:
            break
        chunks.append(buf)
    payload = b"".join(chunks).decode("utf-8", "replace").rstrip("\r\n")
    if payload:
        logging.info("inject %d chars: %r", len(payload), payload[:80])
        write_func(payload)
        time.sleep(0.08)  # let Claude TUI render the input before submitting
        write_func("\r")
        response = b"OK\n"
    else:
        response = b"EMPTY\n"
    conn.sendall(response)
    return response


def socket_to_pty_on(proc: PtyProcess, port: int, stop_event: threading.Event):
    """Listen on 127.0.0.1:port; for each accepted connection, read entire
    payload (UTF-8 text), write it + '\\r' to the PTY."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((LISTEN_HOST, port))
    srv.listen(5)
    srv.settimeout(0.5)
    logging.info("socket listening on %s:%d", LISTEN_HOST, port)
    while not stop_event.is_set() and proc.isalive():
        try:
            conn, _ = srv.accept()
        except socket.timeout:
            continue
        except OSError as e:
            logging.warning("accept err: %s", e)
            break
        try:
            handle_connection(conn, proc.write)
        except Exception as e:
            logging.warning("conn handling err: %s", e)
        finally:
            try:
                conn.close()
            except Exception:
                pass
    try:
        srv.close()
    except Exception:
        pass
    stop_event.set()


def kick_tui(proc: PtyProcess):
    """Claude's TUI doesn't render until it receives some input — spike showed
    a single \\r is enough. Send it after a short delay so the proc is fully up."""
    time.sleep(0.4)
    try:
        proc.write("\r")
    except Exception as e:
        logging.warning("kick err: %s", e)


def heartbeat_thread(wrapper_id: str, token_holder: dict, stop_event: threading.Event,
                     interval: float = DEFAULT_HEARTBEAT_INTERVAL):
    """Send heartbeats while bridge is reachable. On failure, drop token and try
    to re-register from the registration_loop side."""
    while not stop_event.is_set():
        if stop_event.wait(interval):
            return
        tok = token_holder.get("token", "")
        if not tok:
            continue
        status, _ = _http_post(
            f"{BRIDGE_URL}/api/wrappers/heartbeat",
            {"id": wrapper_id},
            token=tok,
        )
        if status in (401, 403, 404):
            logging.warning("heartbeat rejected (status=%d), token cleared", status)
            token_holder["token"] = ""
        elif status == 0:
            logging.info("heartbeat transport error; bridge may be restarting")
            token_holder["token"] = ""


def registration_loop(wrapper_id: str, name: str, cwd: str, port: int, pid: int,
                      token_holder: dict, stop_event: threading.Event,
                      interval: float = REGISTER_RETRY_INTERVAL):
    """While token is empty, keep trying to register every `interval` seconds."""
    while not stop_event.is_set():
        if not token_holder.get("token"):
            tok = register_to_bridge(wrapper_id, name, cwd, port, pid)
            if tok:
                token_holder["token"] = tok
        if stop_event.wait(interval):
            return


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Claude Code wrapper for cc-relay bridge.")
    p.add_argument("--id", dest="id", default=None, help="explicit wrapper id (default: derive from cwd)")
    p.add_argument("--name", dest="name", default=None, help="friendly display name (default: basename of cwd)")
    return p.parse_args()


def main() -> None:
    setup_logging()
    args = parse_args()

    cwd, cwd_src = _resolve_cwd()
    wrapper_id = args.id or _derive_default_id(cwd)
    wrapper_name = args.name or Path(cwd).name
    wrapper_port = pick_free_port()
    wrapper_pid = os.getpid()

    print(f"[wrapper] id={wrapper_id} name={wrapper_name} port={wrapper_port}", flush=True)
    logging.info("wrapper id=%s name=%s port=%d cwd=%s (from %s)",
                 wrapper_id, wrapper_name, wrapper_port, cwd, cwd_src)

    # Try initial registration. If bridge is down, fall into standalone mode
    # (claude still hosts locally; registration_loop retries every 30s).
    token = register_to_bridge(wrapper_id, wrapper_name, cwd, wrapper_port, wrapper_pid) or ""
    token_holder = {"token": token}
    if not token:
        print("[wrapper] WARN bridge offline, running standalone (will retry every 30s)", flush=True)

    if not os.path.isfile(CLAUDE_EXE):
        sys.stderr.write(f"FATAL: claude.exe not found at {CLAUDE_EXE}\n")
        sys.exit(2)

    console_title = f"{CONSOLE_TITLE_PREFIX}{wrapper_name}"

    set_console_utf8()
    set_console_title(console_title)

    # Inject env so post_hook.py can include X-Wrapper-Id header
    env = os.environ.copy()
    env["WRAPPER_ID"] = wrapper_id

    # Wrap in cmd /c so we can run `chcp 65001` inside the ConPTY before
    # claude.exe starts — this switches the child console's input/output code
    # page to UTF-8, so wrapper-injected UTF-8 bytes are decoded correctly.
    # $CLAUDE_ARGS is set by claude-shim.ps1 when the user passes flags like
    # `claude --dangerously-skip-permissions`. Empty / unset = no extra args.
    claude_args = os.environ.get("CLAUDE_ARGS", "").strip()
    if claude_args:
        logging.info("claude_args from env: %r", claude_args)
        cmd = ["cmd", "/c", f"chcp 65001 >nul && {CLAUDE_EXE} {claude_args}"]
    else:
        cmd = ["cmd", "/c", f"chcp 65001 >nul && {CLAUDE_EXE}"]
    rows, cols = current_term_size()
    logging.info("spawn cmdline=%r initial size rows=%d cols=%d", cmd, rows, cols)
    proc = PtyProcess.spawn(cmd, dimensions=(rows, cols), cwd=cwd, env=env)
    logging.info("spawned claude pid=%s cwd=%s", proc.pid, cwd)

    stop_event = threading.Event()
    threads = [
        threading.Thread(target=pty_to_stdout, name="pty-out", args=(proc, stop_event), daemon=True),
        threading.Thread(target=stdin_to_pty, name="stdin-in", args=(proc, stop_event), daemon=True),
        threading.Thread(target=lambda: socket_to_pty_on(proc, wrapper_port, stop_event),
                         name="sock-in", daemon=True),
        threading.Thread(target=kick_tui, name="kick", args=(proc,), daemon=True),
        threading.Thread(target=resize_watcher, name="resize", args=(proc, stop_event), daemon=True),
        threading.Thread(target=title_keeper, name="title", args=(console_title, stop_event), daemon=True),
        threading.Thread(target=heartbeat_thread, name="hb",
                         args=(wrapper_id, token_holder, stop_event), daemon=True),
        threading.Thread(target=registration_loop, name="reg-retry",
                         args=(wrapper_id, wrapper_name, cwd, wrapper_port, wrapper_pid,
                               token_holder, stop_event),
                         daemon=True),
    ]
    for t in threads:
        t.start()

    try:
        while proc.isalive():
            time.sleep(0.2)
    except KeyboardInterrupt:
        logging.info("KeyboardInterrupt, terminating PTY")
        try:
            proc.write("\x03")
            time.sleep(0.3)
        except Exception:
            pass

    stop_event.set()
    # Best-effort deregister
    tok = token_holder.get("token", "")
    if tok:
        _http_post(f"{BRIDGE_URL}/api/wrappers/deregister",
                   {"id": wrapper_id}, token=tok)

    try:
        proc.terminate(force=True)
    except Exception:
        pass
    logging.info("wrapper exiting")


if __name__ == "__main__":
    main()

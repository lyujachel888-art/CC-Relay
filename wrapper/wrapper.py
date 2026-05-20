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


# Fixed window title so bridge/screenshot.py can find this console by title.
CONSOLE_TITLE = "cc-bridge-wrapper"


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

CLAUDE_EXE = _find_claude()
LISTEN_HOST = "127.0.0.1"
LISTEN_PORT = 8788
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


def socket_to_pty(proc: PtyProcess, stop_event: threading.Event):
    """Listen on 127.0.0.1:8788; for each accepted connection, read entire
    payload (UTF-8 text), write it + '\\r' to the PTY."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((LISTEN_HOST, LISTEN_PORT))
    srv.listen(5)
    srv.settimeout(0.5)  # so we can periodically check stop_event
    logging.info("socket listening on %s:%d", LISTEN_HOST, LISTEN_PORT)
    while not stop_event.is_set() and proc.isalive():
        try:
            conn, addr = srv.accept()
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
    logging.info("socket_to_pty exiting")


def kick_tui(proc: PtyProcess):
    """Claude's TUI doesn't render until it receives some input — spike showed
    a single \\r is enough. Send it after a short delay so the proc is fully up."""
    time.sleep(0.4)
    try:
        proc.write("\r")
    except Exception as e:
        logging.warning("kick err: %s", e)


def main():
    setup_logging()
    logging.info("starting wrapper; claude=%s", CLAUDE_EXE)

    if not os.path.isfile(CLAUDE_EXE):
        sys.stderr.write(f"FATAL: claude.exe not found at {CLAUDE_EXE}\n")
        sys.exit(2)

    set_console_utf8()
    logging.info("console codepage set to UTF-8 (65001)")

    set_console_title(CONSOLE_TITLE)
    logging.info("console title set to %r", CONSOLE_TITLE)

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # Wrap in cmd /c so we can run `chcp 65001` inside the ConPTY before
    # claude.exe starts — this switches the child console's input/output code
    # page to UTF-8, so wrapper-injected UTF-8 bytes are decoded correctly.
    cmd = ["cmd", "/c", f"chcp 65001 >nul && {CLAUDE_EXE}"]
    rows, cols = current_term_size()
    logging.info("spawn cmdline=%r initial size rows=%d cols=%d", cmd, rows, cols)
    proc = PtyProcess.spawn(cmd, dimensions=(rows, cols), cwd=project_root)
    logging.info("spawned claude (via cmd /c chcp 65001) pid=%s cwd=%s", proc.pid, project_root)

    stop_event = threading.Event()
    threads = [
        threading.Thread(target=pty_to_stdout, name="pty-out", args=(proc, stop_event), daemon=True),
        threading.Thread(target=stdin_to_pty,  name="stdin-in", args=(proc, stop_event), daemon=True),
        threading.Thread(target=socket_to_pty, name="sock-in", args=(proc, stop_event), daemon=True),
        threading.Thread(target=kick_tui,      name="kick", args=(proc,), daemon=True),
        threading.Thread(target=resize_watcher, name="resize", args=(proc, stop_event), daemon=True),
        threading.Thread(target=title_keeper, name="title", args=(CONSOLE_TITLE, stop_event), daemon=True),
    ]
    for t in threads:
        t.start()

    # Block until PTY dies
    try:
        while proc.isalive():
            time.sleep(0.2)
    except KeyboardInterrupt:
        logging.info("KeyboardInterrupt, terminating PTY")
        try:
            proc.write("\x03")  # send Ctrl+C to claude first
            time.sleep(0.3)
        except Exception:
            pass

    stop_event.set()
    try:
        proc.terminate(force=True)
    except Exception:
        pass
    logging.info("wrapper exiting")


if __name__ == "__main__":
    main()

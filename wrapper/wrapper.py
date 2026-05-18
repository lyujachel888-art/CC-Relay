"""Wrapper that runs claude.exe in a ConPTY and accepts external input via TCP socket."""

import logging
import os
import socket
import sys
import threading
import time
from pathlib import Path

from winpty import PtyProcess

CLAUDE_EXE = r"C:\Users\Jachel\.local\bin\claude.exe"
LISTEN_HOST = "127.0.0.1"
LISTEN_PORT = 8788
PTY_COLS = 140
PTY_ROWS = 40
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


def stdin_to_pty(proc: PtyProcess, stop_event: threading.Event):
    """Read raw bytes from stdin (one byte at a time) and forward to PTY.
    On Windows, use msvcrt.getwch() / getch() for raw char input."""
    import msvcrt
    while not stop_event.is_set() and proc.isalive():
        if msvcrt.kbhit():
            try:
                ch = msvcrt.getwch()  # returns a unicode char
            except Exception as e:
                logging.warning("stdin read err: %s", e)
                break
            try:
                proc.write(ch)
            except Exception as e:
                logging.warning("PTY write err: %s", e)
                break
        else:
            time.sleep(0.01)
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

    proc = PtyProcess.spawn([CLAUDE_EXE], dimensions=(PTY_ROWS, PTY_COLS))
    logging.info("spawned claude pid=%s", proc.pid)

    stop_event = threading.Event()
    threads = [
        threading.Thread(target=pty_to_stdout, name="pty-out", args=(proc, stop_event), daemon=True),
        threading.Thread(target=stdin_to_pty,  name="stdin-in", args=(proc, stop_event), daemon=True),
        threading.Thread(target=socket_to_pty, name="sock-in", args=(proc, stop_event), daemon=True),
        threading.Thread(target=kick_tui,      name="kick", args=(proc,), daemon=True),
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

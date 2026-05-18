"""Spike v2: spawn claude.exe and exercise it — wait longer, send input, see what happens.

Goal: determine if pywinpty's ConPTY wrapping lets Claude render its TUI and
accept input.
"""
import sys
import time
from pathlib import Path

from winpty import PtyProcess

CLAUDE_EXE = r"C:\Users\Jachel\.local\bin\claude.exe"
HERE = Path(__file__).parent


def _drain(proc: PtyProcess, seconds: float, tag: str) -> bytes:
    end = time.time() + seconds
    chunks: list[bytes] = []
    while time.time() < end:
        if not proc.isalive():
            print(f"  [{tag}] proc exited", flush=True)
            break
        try:
            data = proc.read(8192)
        except EOFError:
            print(f"  [{tag}] EOF", flush=True)
            break
        if data:
            buf = data.encode("utf-8", "replace") if isinstance(data, str) else data
            chunks.append(buf)
        else:
            time.sleep(0.05)
    out = b"".join(chunks)
    print(f"  [{tag}] {len(out)} bytes", flush=True)
    return out


def main():
    print("Spawning claude.exe in PTY (140x40)...")
    proc = PtyProcess.spawn([CLAUDE_EXE], dimensions=(40, 140))
    print(f"  pid={proc.pid}, alive={proc.isalive()}", flush=True)

    log = []

    # Phase A: just wait 10 seconds
    log.append(b"=== PHASE A: idle 10s ===\n")
    log.append(_drain(proc, 10.0, "idle"))

    # Phase B: send a return
    print("Sending \\r")
    proc.write("\r")
    log.append(b"\n=== PHASE B: after \\r ===\n")
    log.append(_drain(proc, 3.0, "after-enter"))

    # Phase C: type "hello"
    print("Typing 'hello'")
    proc.write("hello")
    log.append(b"\n=== PHASE C: after typing hello ===\n")
    log.append(_drain(proc, 3.0, "after-hello"))

    # Phase D: send return
    print("Sending \\r")
    proc.write("\r")
    log.append(b"\n=== PHASE D: after submit ===\n")
    log.append(_drain(proc, 8.0, "after-submit"))

    out_path = HERE / "spike_output_v2.log"
    out_path.write_bytes(b"".join(log))
    total = sum(len(c) for c in log if not c.startswith(b"==="))
    print(f"Wrote {out_path}, ~{total} bytes of PTY output total", flush=True)

    try:
        proc.terminate(force=True)
    except Exception:
        pass


if __name__ == "__main__":
    main()

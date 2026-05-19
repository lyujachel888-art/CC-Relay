"""Cross-platform Claude Code hook handler — POSTs message to local bridge.

Usage:  python post_hook.py {user_prompt | stop}
Reads JSON event from stdin, extracts relevant text, POSTs to bridge.
Must always exit 0 (never block Claude on hook failure).
"""
import json
import sys
import traceback
import urllib.request
from datetime import datetime
from pathlib import Path

BRIDGE_BASE = "http://127.0.0.1:8787"
TIMEOUT = 3.0
LOG_PATH = Path(__file__).resolve().parent / "post_hook.log"


def log(line: str) -> None:
    try:
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat(timespec='seconds')} {line}\n")
    except Exception:
        pass


def post(url: str, text: str) -> None:
    safe = text.encode("utf-8", "replace").decode("utf-8", "replace")
    body = json.dumps({"text": safe}, ensure_ascii=False).encode("utf-8", "replace")
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        resp = urllib.request.urlopen(req, timeout=TIMEOUT)
        log(f"POST {url} ok status={resp.status} text_len={len(safe)}")
    except Exception as e:
        log(f"POST {url} FAIL {type(e).__name__}: {e}")


def extract_last_assistant_text(transcript_path: Path) -> str:
    """Walk JSONL from the end, return the most recent assistant message text."""
    try:
        lines = transcript_path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return ""
    for line in reversed(lines):
        try:
            obj = json.loads(line)
        except Exception:
            continue
        msg = obj.get("message") or {}
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = [p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"]
            text = "\n".join(p for p in parts if p)
            if text:
                return text
    return ""


def main() -> None:
    if len(sys.argv) < 2:
        log("ERR no hook_type arg")
        return
    hook_type = sys.argv[1]
    log(f"--- invoked hook_type={hook_type}")

    # Claude Code writes the hook event as UTF-8 JSON to our stdin. On Windows
    # Python defaults stdin encoding to the ANSI codepage (cp936 on zh-CN), so
    # multibyte characters get mojibake. Read raw bytes and decode as UTF-8.
    try:
        raw = sys.stdin.buffer.read()
        data = json.loads(raw.decode("utf-8", "replace"))
    except Exception as e:
        log(f"ERR stdin parse {type(e).__name__}: {e}")
        return
    log(f"stdin keys={list(data.keys())}")

    if hook_type == "user_prompt":
        text = (data.get("prompt") or "").strip()
        log(f"user_prompt text({len(text)})={text!r}")
        if text:
            post(BRIDGE_BASE + "/hook/user_prompt", text)
    elif hook_type == "stop":
        tp = data.get("transcript_path") or ""
        if tp:
            text = extract_last_assistant_text(Path(tp))
            if text:
                post(BRIDGE_BASE + "/hook/assistant_reply", text)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log("FATAL " + traceback.format_exc())
    sys.exit(0)

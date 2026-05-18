"""Cross-platform Claude Code hook handler — POSTs message to local bridge.

Usage:  python post_hook.py {user_prompt | stop}
Reads JSON event from stdin, extracts relevant text, POSTs to bridge.
Must always exit 0 (never block Claude on hook failure).
"""
import json
import sys
import urllib.request
from pathlib import Path

BRIDGE_BASE = "http://127.0.0.1:8787"
TIMEOUT = 3.0


def post(url: str, text: str) -> None:
    body = json.dumps({"text": text}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        urllib.request.urlopen(req, timeout=TIMEOUT).read()
    except Exception:
        pass


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
        return
    hook_type = sys.argv[1]

    try:
        data = json.load(sys.stdin)
    except Exception:
        return

    if hook_type == "user_prompt":
        text = (data.get("prompt") or "").strip()
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
        # Never propagate — hooks must always exit 0
        pass
    sys.exit(0)

"""Cross-platform Claude Code hook handler — POSTs message to local bridge.

Usage:  python post_hook.py {user_prompt | stop | pre_tool}
Reads JSON event from stdin, extracts relevant text, POSTs to bridge.
Must always exit 0 (never block Claude on hook failure).

Env vars:
  SKIP_TOOL_HOOK=1   suppress pre_tool POSTs (keep user_prompt/stop)
  SKIP_ALL_HOOK=1    suppress all POSTs (useful when bridge is down)
"""
import json
import os
import sys
import traceback
import urllib.request
from datetime import datetime
from pathlib import Path

BRIDGE_BASE = "http://127.0.0.1:8787"
# Short timeout: PreToolUse runs synchronously before every tool call, so a
# dead bridge must not stall Claude. 1s is enough for a local loopback POST.
TIMEOUT = 1.0
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


def project_prefix(data: dict) -> str:
    """Return '[basename]' from data['cwd'], or '' if missing."""
    cwd = data.get("cwd") or ""
    name = Path(cwd).name if cwd else ""
    return f"[{name}] " if name else ""


def summarize_tool(tool_name: str, tool_input: dict) -> str:
    """Short one-line summary of what the tool is doing."""
    if not isinstance(tool_input, dict):
        return ""
    if tool_name == "Bash":
        return (tool_input.get("command") or "").strip().splitlines()[0] if tool_input.get("command") else ""
    if tool_name in ("Edit", "Write", "Read", "MultiEdit", "NotebookEdit"):
        return tool_input.get("file_path") or tool_input.get("notebook_path") or ""
    if tool_name == "Glob":
        return tool_input.get("pattern") or ""
    if tool_name == "Grep":
        p = tool_input.get("pattern") or ""
        loc = tool_input.get("path") or ""
        return f"{p}  ({loc})" if loc else p
    if tool_name == "WebFetch":
        return tool_input.get("url") or ""
    if tool_name == "WebSearch":
        return tool_input.get("query") or ""
    if tool_name == "TodoWrite":
        todos = tool_input.get("todos") or []
        return f"{len(todos)} todos"
    if tool_name == "Task":
        return tool_input.get("description") or tool_input.get("subagent_type") or ""
    return ""


def extract_stop_summary(transcript_path: Path) -> tuple:
    """Walk JSONL from the end. Returns (last_text, output_tokens, duration_ms).

    - last_text: text of the most recent assistant message
    - output_tokens: output_tokens of that same assistant message
    - duration_ms: durationMs from the most recent system/turn_duration record
    """
    try:
        lines = transcript_path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return ("", 0, 0)

    last_text = ""
    output_tokens = 0
    duration_ms = 0

    for line in reversed(lines):
        try:
            obj = json.loads(line)
        except Exception:
            continue

        if duration_ms == 0 and obj.get("type") == "system" and obj.get("subtype") == "turn_duration":
            duration_ms = int(obj.get("durationMs") or 0)

        if not last_text:
            msg = obj.get("message") or {}
            if msg.get("role") == "assistant":
                output_tokens = int((msg.get("usage") or {}).get("output_tokens") or 0)
                content = msg.get("content")
                if isinstance(content, str):
                    last_text = content
                elif isinstance(content, list):
                    parts = [p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"]
                    last_text = "\n".join(p for p in parts if p)

        if last_text and duration_ms:
            break

    return (last_text, output_tokens, duration_ms)


def main() -> None:
    if len(sys.argv) < 2:
        log("ERR no hook_type arg")
        return
    hook_type = sys.argv[1]
    if os.environ.get("SKIP_ALL_HOOK") == "1":
        log(f"skip-all hook_type={hook_type}")
        return
    if hook_type == "pre_tool" and os.environ.get("SKIP_TOOL_HOOK") == "1":
        log("skip-tool pre_tool")
        return
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

    prefix = project_prefix(data)

    if hook_type == "user_prompt":
        text = (data.get("prompt") or "").strip()
        log(f"user_prompt text({len(text)})={text!r}")
        if text:
            post(BRIDGE_BASE + "/hook/user_prompt", prefix + text)
    elif hook_type == "stop":
        tp = data.get("transcript_path") or ""
        if tp:
            text, out_tokens, dur_ms = extract_stop_summary(Path(tp))
            if text:
                meta = []
                if dur_ms:
                    meta.append(f"{dur_ms / 1000:.1f}s")
                if out_tokens:
                    meta.append(f"{out_tokens} tok")
                header = (prefix + f"({' · '.join(meta)})").rstrip() if meta else prefix.rstrip()
                body = f"{header}\n{text}" if header else text
                post(BRIDGE_BASE + "/hook/assistant_reply", body)
    elif hook_type == "pre_tool":
        tool_name = data.get("tool_name") or "?"
        summary = summarize_tool(tool_name, data.get("tool_input") or {})
        # Truncate the summary so it stays one line on phone
        if len(summary) > 200:
            summary = summary[:200] + "…"
        body = f"{tool_name}: {summary}" if summary else tool_name
        log(f"pre_tool {tool_name} summary({len(summary)})")
        post(BRIDGE_BASE + "/hook/tool_use", prefix + body)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log("FATAL " + traceback.format_exc())
    sys.exit(0)

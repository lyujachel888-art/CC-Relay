"""Cross-platform Claude Code hook handler — POSTs message to local bridge.

Usage:  python post_hook.py {user_prompt | stop | pre_tool}
Reads JSON event from stdin, extracts relevant text, POSTs to bridge.
Must always exit 0 (never block Claude on hook failure).

Env vars:
  SKIP_TOOL_HOOK=1   suppress pre_tool POSTs (keep user_prompt/stop)
  SKIP_ALL_HOOK=1    suppress all POSTs (useful when bridge is down)

:author: jachel.lyu
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
TOKEN_PATH = Path(__file__).resolve().parent / ".bridge_token"


def _read_token() -> str:
    try:
        return TOKEN_PATH.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def log(line: str) -> None:
    try:
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat(timespec='seconds')} {line}\n")
    except Exception:
        pass


def post(url: str, text: str, transcript_path: str = "", task_type: str = "", meta: str = "") -> None:
    safe = text.encode("utf-8", "replace").decode("utf-8", "replace")
    payload = {"text": safe}
    if transcript_path:
        payload["transcript_path"] = transcript_path
    if task_type:
        payload["task_type"] = task_type
    if meta:
        payload["meta"] = meta
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8", "replace")
    headers = {"Content-Type": "application/json"}
    token = _read_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
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


def _is_bash_failed(resp: str) -> bool:
    """CC prefixes failed bash output with 'Exit code N:' or 'Error:'."""
    import re
    low = resp.strip().lower()
    return bool(re.match(r"exit code\s+[1-9]", low) or re.match(r"error:", low))


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

    transcript_path = data.get("transcript_path") or ""

    if hook_type == "user_prompt":
        text = (data.get("prompt") or "").strip()
        log(f"user_prompt text({len(text)})={text!r}")
        if text:
            post(BRIDGE_BASE + "/hook/user_prompt", prefix + text, transcript_path)
    elif hook_type == "stop":
        if transcript_path:
            text, out_tokens, dur_ms = extract_stop_summary(Path(transcript_path))
            if text:
                meta_bits = []
                if dur_ms:
                    meta_bits.append(f"{dur_ms / 1000:.1f}s")
                if out_tokens:
                    meta_bits.append(f"{out_tokens} tok")
                meta = " · ".join(meta_bits)
                post(BRIDGE_BASE + "/hook/assistant_reply",
                     prefix + text, transcript_path, meta=meta)
    elif hook_type == "pre_tool":
        tool_name = data.get("tool_name") or "?"
        summary = summarize_tool(tool_name, data.get("tool_input") or {})
        # Truncate the summary so it stays one line on phone
        if len(summary) > 200:
            summary = summary[:200] + "…"
        body = f"{tool_name}: {summary}" if summary else tool_name
        log(f"pre_tool {tool_name} summary({len(summary)})")
        post(BRIDGE_BASE + "/hook/tool_use", prefix + body)
    elif hook_type in ("task_created", "task_completed"):
        subject = (data.get("task_subject") or data.get("task_description") or "(no subject)").strip()
        task_type = "created" if hook_type == "task_created" else "completed"
        log(f"{hook_type} subject={subject!r}")
        post(BRIDGE_BASE + "/hook/task", prefix + subject, task_type=task_type)
    elif hook_type == "post_tool":
        tn = data.get("tool_name") or ""
        ti = data.get("tool_input") or {}
        fp = ti.get("file_path") or ti.get("notebook_path") or ""
        if tn in ("Write", "Edit", "MultiEdit", "NotebookEdit") and fp:
            log(f"post_tool {tn} {fp!r}")
            post(BRIDGE_BASE + "/hook/file_touched", f"{tn}|{fp}")
    elif hook_type == "post_bash":
        ti = data.get("tool_input") or {}
        cmd = (ti.get("command") or "").strip()
        cmd_short = cmd.splitlines()[0][:120] if cmd else "?"
        response = data.get("tool_response") or ""
        log(f"post_bash keys={list(data.keys())} cmd={cmd_short!r}")
        resp_text = (
            response.get("output") or response.get("stdout") or json.dumps(response)
            if isinstance(response, dict) else str(response)
        )
        failed = _is_bash_failed(resp_text)
        preview = resp_text.strip()[:400]
        if len(resp_text.strip()) > 400:
            preview += "…"
        body = f"$ {cmd_short}\n\n{preview}" if preview else f"$ {cmd_short}"
        log(f"post_bash failed={failed}")
        post(BRIDGE_BASE + "/hook/bash_result", prefix + body, meta="fail" if failed else "ok")
    elif hook_type == "notification":
        message = (data.get("message") or data.get("title") or "").strip()
        log(f"notification keys={list(data.keys())} message={message!r}")
        if message:
            post(BRIDGE_BASE + "/hook/notification", prefix + message)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log("FATAL " + traceback.format_exc())
    sys.exit(0)

"""FastAPI hook server for cc-relay — receives Claude Code hook POSTs and
forwards them to Feishu as text messages or interactive cards.

:author: jachel.lyu
"""
import hmac
import logging
import re

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

import files_tracker
from auth import HEADER_PREFIX
from echo_filter import claim_echo
from feishu import FeishuClient
from history import remember as remember_transcript
from push_state import is_tool_use_paused

log = logging.getLogger("bridge.server")

# Matches the "[project] " prefix that post_hook.py adds, so we can compare
# the prompt against the raw text the feishu user typed.
_PROJECT_PREFIX = re.compile(r"^\[[^\]]+\]\s+")


class HookPayload(BaseModel):
    text: str
    transcript_path: str = ""  # optional, sent by user_prompt / stop hooks
    task_type: str = ""        # "created" | "completed" for /hook/task
    meta: str = ""             # short meta (e.g. "15.2s · 1137 tok") shown in header


def create_app(feishu: FeishuClient, expected_token: str,
               registry=None, router=None) -> FastAPI:
    app = FastAPI()

    def _check_auth(authorization: str) -> None:
        """Reject the request if the Authorization header doesn't carry the
        bridge token. Uses constant-time comparison so a remote prober can't
        learn the token byte-by-byte from response timing."""
        if not authorization or not authorization.startswith(HEADER_PREFIX):
            raise HTTPException(status_code=401, detail="missing token")
        supplied = authorization[len(HEADER_PREFIX):].strip()
        if not hmac.compare_digest(supplied, expected_token):
            raise HTTPException(status_code=403, detail="bad token")

    def _check_wrapper_id(x_wrapper_id: str) -> str:
        """Phase 1 切换日：每个 /hook/* 请求必须携带 X-Wrapper-Id 并指向已知
        wrapper（最近见过即可，允许刚下线的 wrapper 继续把延迟 hook 发上来）。"""
        if not x_wrapper_id:
            raise HTTPException(status_code=400, detail="missing X-Wrapper-Id header")
        if registry is None:
            raise HTTPException(status_code=400, detail=f"unknown wrapper {x_wrapper_id}")
        if registry.is_online(x_wrapper_id):
            return x_wrapper_id
        # also allow recently-offline so deferred hooks still route
        known = any(w.get("id") == x_wrapper_id for w in registry.snapshot())
        if not known:
            raise HTTPException(status_code=400, detail=f"unknown wrapper {x_wrapper_id}")
        return x_wrapper_id

    @app.post("/hook/user_prompt")
    async def user_prompt(payload: HookPayload,
                          authorization: str = Header(default=""),
                          x_wrapper_id: str = Header(default="")):
        _check_auth(authorization)
        wid = _check_wrapper_id(x_wrapper_id)
        if payload.transcript_path:
            remember_transcript(wid, payload.transcript_path)
        raw = _PROJECT_PREFIX.sub("", payload.text, count=1)
        if claim_echo(wid, raw):
            log.info("suppressing feishu echo: %r", raw[:60])
            return {"ok": True, "skipped": "feishu-echo"}
        return _push_header_card(feishu, "🧑", "你说", payload.text, color="blue")

    @app.post("/hook/assistant_reply")
    async def assistant_reply(payload: HookPayload,
                              authorization: str = Header(default=""),
                              x_wrapper_id: str = Header(default="")):
        _check_auth(authorization)
        wid = _check_wrapper_id(x_wrapper_id)
        if payload.transcript_path:
            remember_transcript(wid, payload.transcript_path)
        chip, body = _split_prefix(payload.text)
        title_bits = ["🤖"]
        if chip:
            title_bits.append(chip)
        title_bits.append("Claude")
        if payload.meta:
            title_bits.append(f"· {payload.meta}")
        title = " ".join(title_bits)

        if len(body) > 25000:
            log.info("assistant_reply too big for card (%d chars), falling back to text", len(body))
            return _push(feishu, f"🤖 {payload.text}")
        try:
            feishu.send_markdown_card(body, title=title, color="violet", with_actions=True)
            return {"ok": True}
        except Exception as e:
            log.exception("failed to push assistant card: %s", e)
            return {"ok": False, "error": str(e)}

    @app.post("/hook/tool_use")
    async def tool_use(payload: HookPayload,
                       authorization: str = Header(default=""),
                       x_wrapper_id: str = Header(default="")):
        _check_auth(authorization)
        wid = _check_wrapper_id(x_wrapper_id)
        if is_tool_use_paused(wid):
            return {"ok": True, "skipped": "paused"}
        return _push(feishu, f"🛠️ {payload.text}")

    @app.post("/hook/file_touched")
    async def file_touched(payload: HookPayload,
                           authorization: str = Header(default=""),
                           x_wrapper_id: str = Header(default="")):
        _check_auth(authorization)
        wid = _check_wrapper_id(x_wrapper_id)
        # payload.text format: "<action>|<file_path>"
        action, _, fp = payload.text.partition("|")
        files_tracker.record(wid, action.strip() or "?", fp.strip())
        return {"ok": True}

    @app.post("/hook/task")
    async def task_event(payload: HookPayload,
                         authorization: str = Header(default=""),
                         x_wrapper_id: str = Header(default="")):
        _check_auth(authorization)
        _check_wrapper_id(x_wrapper_id)
        if payload.task_type == "created":
            return _push_header_card(feishu, "🆕", "新任务", payload.text, color="green")
        if payload.task_type == "completed":
            return _push_header_card(feishu, "✅", "完成", payload.text, color="turquoise")
        return _push(feishu, payload.text)

    @app.post("/hook/notification")
    async def notification(payload: HookPayload,
                           authorization: str = Header(default=""),
                           x_wrapper_id: str = Header(default="")):
        _check_auth(authorization)
        _check_wrapper_id(x_wrapper_id)
        return _push_header_card(feishu, "🔔", "通知", payload.text, color="orange")

    @app.post("/hook/bash_result")
    async def bash_result(payload: HookPayload,
                          authorization: str = Header(default=""),
                          x_wrapper_id: str = Header(default="")):
        _check_auth(authorization)
        wid = _check_wrapper_id(x_wrapper_id)
        if is_tool_use_paused(wid):
            return {"ok": True, "skipped": "paused"}
        failed = payload.meta == "fail"
        color = "red" if failed else "green"
        icon = "❌" if failed else "✅"
        return _push_header_card(feishu, icon, "Bash", payload.text, color=color)

    return app


def _push(feishu: FeishuClient, text: str) -> dict:
    try:
        feishu.send_text(text)
        return {"ok": True}
    except Exception as e:
        log.exception("failed to push to feishu: %s", e)
        return {"ok": False, "error": str(e)}


def _push_card(feishu: FeishuClient, md: str) -> dict:
    try:
        feishu.send_markdown_card(md)
        return {"ok": True}
    except Exception as e:
        log.exception("failed to push card to feishu: %s", e)
        return {"ok": False, "error": str(e)}


def _split_prefix(text: str) -> tuple:
    """Split off the "[project] " prefix added by post_hook. Returns
    (header_chip, body)."""
    m = _PROJECT_PREFIX.match(text)
    if m:
        return m.group(0).strip(), text[len(m.group(0)):]
    return "", text


def _push_header_card(feishu: FeishuClient, emoji: str, label: str, text: str, color: str) -> dict:
    """Send a small colored-header card. `text` may carry the [project] prefix."""
    chip, body = _split_prefix(text)
    title_bits = [emoji]
    if chip:
        title_bits.append(chip)
    title_bits.append(label)
    title = " ".join(title_bits)
    try:
        feishu.send_header_card(title, body, color=color)
        return {"ok": True}
    except Exception as e:
        log.exception("failed to push header card: %s", e)
        return {"ok": False, "error": str(e)}

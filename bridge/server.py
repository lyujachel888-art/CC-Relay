import hmac
import logging
import re

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from auth import HEADER_PREFIX
from echo_filter import claim_echo
from feishu import FeishuClient

log = logging.getLogger("bridge.server")

# Matches the "[project] " prefix that post_hook.py adds, so we can compare
# the prompt against the raw text the feishu user typed.
_PROJECT_PREFIX = re.compile(r"^\[[^\]]+\]\s+")


class HookPayload(BaseModel):
    text: str


def create_app(feishu: FeishuClient, expected_token: str) -> FastAPI:
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

    @app.post("/hook/user_prompt")
    async def user_prompt(payload: HookPayload, authorization: str = Header(default="")):
        _check_auth(authorization)
        raw = _PROJECT_PREFIX.sub("", payload.text, count=1)
        if claim_echo(raw):
            log.info("suppressing feishu echo: %r", raw[:60])
            return {"ok": True, "skipped": "feishu-echo"}
        return _push(feishu, f"🧑 {payload.text}")

    @app.post("/hook/assistant_reply")
    async def assistant_reply(payload: HookPayload, authorization: str = Header(default="")):
        _check_auth(authorization)
        # Render as a feishu interactive card so markdown (bold, headers,
        # code blocks, lists, links) actually renders on the phone.
        # Cards have a ~30KB JSON limit — fall back to plain text if longer.
        md = f"🤖 {payload.text}"
        if len(md) > 25000:
            log.info("assistant_reply too big for card (%d chars), falling back to text", len(md))
            return _push(feishu, md)
        return _push_card(feishu, md)

    @app.post("/hook/tool_use")
    async def tool_use(payload: HookPayload, authorization: str = Header(default="")):
        _check_auth(authorization)
        return _push(feishu, f"🛠️ {payload.text}")

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

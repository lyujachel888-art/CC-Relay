import logging
import re

from fastapi import FastAPI
from pydantic import BaseModel

from echo_filter import claim_echo
from feishu import FeishuClient

log = logging.getLogger("bridge.server")

# Matches the "[project] " prefix that post_hook.py adds, so we can compare
# the prompt against the raw text the feishu user typed.
_PROJECT_PREFIX = re.compile(r"^\[[^\]]+\]\s+")


class HookPayload(BaseModel):
    text: str


def create_app(feishu: FeishuClient) -> FastAPI:
    app = FastAPI()

    @app.post("/hook/user_prompt")
    async def user_prompt(payload: HookPayload):
        raw = _PROJECT_PREFIX.sub("", payload.text, count=1)
        if claim_echo(raw):
            log.info("suppressing feishu echo: %r", raw[:60])
            return {"ok": True, "skipped": "feishu-echo"}
        return _push(feishu, f"🧑 {payload.text}")

    @app.post("/hook/assistant_reply")
    async def assistant_reply(payload: HookPayload):
        return _push(feishu, f"🤖 {payload.text}")

    @app.post("/hook/tool_use")
    async def tool_use(payload: HookPayload):
        return _push(feishu, f"🛠️ {payload.text}")

    return app


def _push(feishu: FeishuClient, text: str) -> dict:
    try:
        feishu.send_text(text)
        return {"ok": True}
    except Exception as e:
        log.exception("failed to push to feishu: %s", e)
        return {"ok": False, "error": str(e)}

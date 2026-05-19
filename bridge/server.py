import logging
from fastapi import FastAPI
from pydantic import BaseModel
from feishu import FeishuClient

log = logging.getLogger("bridge.server")


class HookPayload(BaseModel):
    text: str


def create_app(feishu: FeishuClient) -> FastAPI:
    app = FastAPI()

    @app.post("/hook/user_prompt")
    async def user_prompt(payload: HookPayload):
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

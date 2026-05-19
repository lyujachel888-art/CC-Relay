import json
from typing import Optional
import lark_oapi as lark
from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody


class FeishuClient:
    """Thin wrapper around lark-oapi for sending text messages to a single user."""

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        user_open_id: str,
        lark_client: Optional[object] = None,
    ):
        if lark_client is None:
            lark_client = (
                lark.Client.builder()
                .app_id(app_id)
                .app_secret(app_secret)
                .build()
            )
        self._client = lark_client
        self._user_open_id = user_open_id

    def send_text(self, text: str) -> None:
        req = (
            CreateMessageRequest.builder()
            .receive_id_type("open_id")
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(self._user_open_id)
                .msg_type("text")
                .content(json.dumps({"text": text}, ensure_ascii=False))
                .build()
            )
            .build()
        )
        resp = self._client.im.v1.message.create(req)
        if not getattr(resp, "success", lambda: True)():
            code = getattr(resp, "code", "?")
            msg = getattr(resp, "msg", "?")
            log_id = getattr(resp, "get_log_id", lambda: "?")()
            raise RuntimeError(f"feishu send failed code={code} msg={msg} log_id={log_id}")

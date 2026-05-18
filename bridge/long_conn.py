import json
import logging
from typing import Callable

import lark_oapi as lark

from injector import inject

log = logging.getLogger("bridge.long_conn")


def make_message_handler() -> Callable:
    """Build a handler that injects incoming Feishu messages into the wrapper PTY."""

    def handler(data) -> None:
        try:
            content_raw = data.event.message.content
            content = json.loads(content_raw)
            text = (content.get("text") or "").strip()
        except (json.JSONDecodeError, AttributeError, TypeError) as e:
            log.warning("could not parse message content: %s", e)
            return

        try:
            open_id = data.event.sender.sender_id.open_id
        except AttributeError:
            open_id = "<unknown>"

        # Print the sender's open_id loudly — first-run user needs this to fill .env
        print(
            f"[long_conn] sender open_id={open_id} text={text!r}",
            flush=True,
        )

        if not text:
            return

        try:
            inject(text)
        except Exception as e:
            log.exception("injection failed: %s", e)

    return handler


def start_ws_client(app_id: str, app_secret: str) -> None:
    """Block on lark WebSocket client. Run in a background thread."""
    handler = make_message_handler()

    event_handler = (
        lark.EventDispatcherHandler.builder("", "")
        .register_p2_im_message_receive_v1(handler)
        .build()
    )

    ws_client = lark.ws.Client(
        app_id,
        app_secret,
        event_handler=event_handler,
        log_level=lark.LogLevel.INFO,
    )
    ws_client.start()

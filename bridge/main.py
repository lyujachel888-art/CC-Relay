"""Entry point for cc-relay — starts the FastAPI hook server and the Feishu
WebSocket long-connection client.

:author: jachel.lyu
"""
import logging
import threading

import uvicorn

from auth import ensure_token
from config import load_config
from feishu import FeishuClient
from server import create_app
from long_conn import start_ws_client


__version__ = "0.1.0"
__author__ = "jachel.lyu"
_BANNER = f"CC Relay v{__version__} — Claude Code ↔ Feishu 实时双向中继"


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    log = logging.getLogger("bridge.main")
    log.info(_BANNER)

    cfg = load_config()
    log.info("loaded config: app_id=%s open_id=%s", cfg.app_id, cfg.user_open_id)

    feishu = FeishuClient(cfg.app_id, cfg.app_secret, cfg.user_open_id)
    token = ensure_token()
    log.info("hook token loaded (%d chars)", len(token))
    app = create_app(feishu, token)

    # Long-conn runs in background thread; FastAPI runs in main thread.
    # feishu is passed so non-text messages can be answered with a hint.
    ws_thread = threading.Thread(
        target=start_ws_client,
        args=(cfg.app_id, cfg.app_secret, feishu),
        daemon=True,
        name="lark-ws",
    )
    ws_thread.start()
    log.info("lark websocket client started in background")

    try:
        feishu.send_startup_card()
        log.info("startup card sent")
    except Exception as e:
        log.warning("startup card failed (non-fatal): %s", e)

    log.info("FastAPI listening on http://127.0.0.1:8787")
    uvicorn.run(app, host="127.0.0.1", port=8787, log_level="warning")


if __name__ == "__main__":
    main()

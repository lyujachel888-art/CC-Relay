import logging
import threading

import uvicorn

from auth import ensure_token
from config import load_config
from feishu import FeishuClient
from server import create_app
from long_conn import start_ws_client


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    log = logging.getLogger("bridge.main")

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

    log.info("FastAPI listening on http://127.0.0.1:8787")
    uvicorn.run(app, host="127.0.0.1", port=8787, log_level="warning")


if __name__ == "__main__":
    main()

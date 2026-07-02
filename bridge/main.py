"""Entry point for cc-relay — starts the FastAPI hook server and the Feishu
WebSocket long-connection client.

:author: jachel.lyu
"""
import sys
import threading
import time

_loading_done = threading.Event()


def _show_loading_animation() -> None:
    """Braille spinner while the slow lark_oapi import chain runs."""
    chars = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    print("正在加载 CC Relay 渡桥服务（首次启动需 15-60 秒）...", file=sys.stderr, flush=True)
    i = 0
    while not _loading_done.wait(0.1):
        print(f"\r{chars[i]} 加载中", end="", file=sys.stderr, flush=True)
        i = (i + 1) % len(chars)
    print("\r✓ 加载完成      ", file=sys.stderr, flush=True)


_loading_start = time.time()
_loading_thread = threading.Thread(target=_show_loading_animation, daemon=True)
_loading_thread.start()

import logging
from pathlib import Path

import uvicorn

from api_wrappers import attach_wrapper_routes
from auth import ensure_token
from config import load_config
from config_store import ConfigStore
from feishu import FeishuClient
from router import Router
from server import create_app
from long_conn import start_ws_client
from wrapper_registry import WrapperRegistry

_loading_done.set()
_loading_thread.join(timeout=1)
print(f"加载耗时: {time.time() - _loading_start:.1f}s\n", file=sys.stderr, flush=True)


__version__ = "0.2.13"
__author__ = "jachel.lyu"
_BANNER = f"CC Relay v{__version__} — Claude Code ↔ 飞书 多云匣渡桥"


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    log = logging.getLogger("bridge.main")
    log.info(_BANNER)

    cfg = load_config()
    log.info("已加载配置: app_id=%s open_id=%s", cfg.app_id, cfg.user_open_id)

    config_path = Path(__file__).resolve().parent / "config.json"
    store = ConfigStore(config_path)
    registry = WrapperRegistry()
    router = Router(store=store, registry=registry)
    log.info("config.json=%s 已知云匣数=%d 活跃=%s",
             config_path, len(store.wrappers), store.active_wrapper_id)

    feishu = FeishuClient(cfg.app_id, cfg.app_secret, cfg.user_open_id)
    token = ensure_token()
    log.info("hook token 已加载 (%d 字符)", len(token))

    app = create_app(feishu, token, registry=registry, router=router)
    attach_wrapper_routes(app, registry=registry, store=store)

    ws_thread = threading.Thread(
        target=start_ws_client,
        args=(cfg.app_id, cfg.app_secret, feishu, router, registry),
        daemon=True,
        name="lark-ws",
    )
    ws_thread.start()
    log.info("飞书 WebSocket 客户端已在后台启动")

    try:
        feishu.send_startup_card()
        log.info("启动卡片已发送")
    except Exception as e:
        log.warning("启动卡片发送失败 (非致命): %s", e)

    log.info("渡桥 FastAPI 监听 http://127.0.0.1:8787")
    uvicorn.run(app, host="127.0.0.1", port=8787, log_level="warning")


if __name__ == "__main__":
    main()

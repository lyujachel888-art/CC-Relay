import json
import logging
from typing import Callable, Optional

import lark_oapi as lark

from echo_filter import mark_injected
from feishu import FeishuClient
from image_cache import save_file_bytes, save_image_bytes
from injector import inject
from menu import build_menu_text, is_trigger, offer_menu, try_consume_choice
from sender import MAX_BYTES, parse_send_command, resolve_to_wsl

log = logging.getLogger("bridge.long_conn")

_UNSUPPORTED_HINT = {
    "audio":      "🎙️ 暂不支持语音，请发文字",
    "media":      "🎞️ 暂不支持视频",
    "sticker":    "😀 暂不支持表情包",
    "share_chat": "💬 暂不支持分享群名片",
}


def flatten_post(
    content: dict,
    feishu: Optional[FeishuClient] = None,
    message_id: str = "",
) -> str:
    """Flatten a Feishu rich-text (post) message into plain text.

    Post format: {"title": "...", "content": [[elem, elem, ...], [elem, ...], ...]}
    Each row is a list of inline elements (text / a / at / img / code_inline / ...).
    Inline images are downloaded to the cache dir and inlined as a local path
    so Claude can read them.
    """
    lines = []
    title = (content.get("title") or "").strip()
    if title:
        lines.append(title)
    for row in content.get("content") or []:
        if not isinstance(row, list):
            continue
        parts = []
        for elem in row:
            if not isinstance(elem, dict):
                continue
            tag = elem.get("tag")
            if tag in ("text", "code_inline", "md"):
                parts.append(elem.get("text") or "")
            elif tag == "a":
                txt = elem.get("text") or ""
                href = elem.get("href") or ""
                parts.append(f"{txt}({href})" if txt and href else (txt or href))
            elif tag == "at":
                parts.append("@" + (elem.get("user_name") or elem.get("user_id") or ""))
            elif tag == "img":
                ik = elem.get("image_key", "")
                if feishu and message_id and ik:
                    try:
                        data, fname = feishu.download_resource(message_id, ik, "image")
                        win_path = save_image_bytes(data, fname)
                        parts.append(f"[图片:{win_path}]")
                    except Exception as e:
                        log.warning("post-img download failed: %s", e)
                        parts.append("[图片下载失败]")
                else:
                    parts.append("[图片]")
            elif tag == "emotion":
                parts.append(f"[{elem.get('emoji_type') or 'emoji'}]")
        if parts:
            lines.append("".join(parts))
    return "\n".join(lines)


def make_message_handler(feishu: Optional[FeishuClient] = None) -> Callable:
    """Build a handler that injects incoming Feishu text into the wrapper PTY.

    Non-text messages get a hint pushed back to the user so they know why
    nothing happened on the Claude side.
    """

    def reply_hint(hint: str) -> None:
        if feishu is None:
            return
        try:
            feishu.send_text(hint)
        except Exception as e:
            log.warning("failed to push hint: %s", e)

    def handler(data) -> None:
        try:
            msg = data.event.message
            content_raw = msg.content
            msg_type = getattr(msg, "message_type", None) or "?"
        except (AttributeError, TypeError) as e:
            log.warning("could not read message envelope: %s", e)
            return

        try:
            content = json.loads(content_raw) if content_raw else {}
        except json.JSONDecodeError as e:
            log.warning("could not parse message content: %s", e)
            return

        try:
            open_id = data.event.sender.sender_id.open_id
        except AttributeError:
            open_id = "<unknown>"

        print(
            f"[long_conn] sender open_id={open_id} type={msg_type} content={content!r}",
            flush=True,
        )

        if msg_type == "post":
            message_id = getattr(msg, "message_id", "")
            text = flatten_post(content, feishu=feishu, message_id=message_id).strip()
            if not text:
                reply_hint("⚠️ 富文本消息内容为空")
                return
            mark_injected(text)
            try:
                inject(text)
            except Exception as e:
                log.exception("injection failed: %s", e)
                reply_hint(f"⚠️ 注入失败: {e}")
            return

        if msg_type == "image":
            image_key = content.get("image_key", "")
            message_id = getattr(msg, "message_id", "")
            if not image_key or not message_id:
                reply_hint("⚠️ 图片消息缺少 image_key/message_id")
                return
            if feishu is None:
                reply_hint("⚠️ feishu client 未注入，无法下载图片")
                return
            try:
                data, fname = feishu.download_resource(message_id, image_key, "image")
                win_path = save_image_bytes(data, fname)
            except Exception as e:
                log.exception("image download failed: %s", e)
                reply_hint(f"⚠️ 图片下载失败: {e}")
                return
            prompt = f"请看一下这张飞书发来的图片：{win_path}"
            mark_injected(prompt)
            try:
                inject(prompt)
            except Exception as e:
                log.exception("injection failed: %s", e)
                reply_hint(f"⚠️ 注入失败: {e}")
            return

        if msg_type == "file":
            file_key = content.get("file_key", "")
            file_name = content.get("file_name", "") or "file.bin"
            message_id = getattr(msg, "message_id", "")
            if not file_key or not message_id:
                reply_hint("⚠️ 文件消息缺少 file_key/message_id")
                return
            if feishu is None:
                reply_hint("⚠️ feishu client 未注入，无法下载文件")
                return
            try:
                data, suggested = feishu.download_resource(message_id, file_key, "file")
                win_path = save_file_bytes(data, suggested or file_name)
            except Exception as e:
                log.exception("file download failed: %s", e)
                reply_hint(f"⚠️ 文件下载失败: {e}")
                return
            prompt = f"请看一下这个飞书发来的文件（{file_name}）：{win_path}"
            mark_injected(prompt)
            try:
                inject(prompt)
            except Exception as e:
                log.exception("injection failed: %s", e)
                reply_hint(f"⚠️ 注入失败: {e}")
            return

        if msg_type != "text":
            hint = _UNSUPPORTED_HINT.get(msg_type, f"⚠️ 暂不支持的消息类型: {msg_type}")
            reply_hint(hint)
            return

        text = (content.get("text") or "").strip()
        if not text:
            return

        # Menu shortcut: typing a trigger word pops up the numbered menu.
        if is_trigger(text):
            offer_menu()
            reply_hint(build_menu_text())
            return

        # File upload shortcut: "传 <path>" / "send <path>" — read the file
        # locally and push it back to the user as a feishu file/image.
        send_target = parse_send_command(text)
        if send_target is not None:
            if feishu is None:
                reply_hint("⚠️ feishu client 未注入，无法上传")
                return
            wsl_path = resolve_to_wsl(send_target)
            if wsl_path is None or not wsl_path.exists():
                reply_hint(f"⚠️ 找不到: {send_target}")
                return
            if not wsl_path.is_file():
                reply_hint(f"⚠️ 不是文件: {send_target}")
                return
            size = wsl_path.stat().st_size
            if size > MAX_BYTES:
                reply_hint(f"⚠️ 文件 {size/1024/1024:.1f}MB 超过 30MB 限制")
                return
            try:
                feishu.upload_file_and_send(wsl_path)
                reply_hint(f"📤 已发送 {wsl_path.name} ({size/1024:.1f}KB)")
            except Exception as e:
                log.exception("send file failed")
                reply_hint(f"⚠️ 上传失败: {e}")
            return

        # If a menu is currently active and this text is a digit, translate.
        chosen_cmd = try_consume_choice(text)
        if chosen_cmd:
            reply_hint(f"▶ 执行 {chosen_cmd}")
            text = chosen_cmd

        # Mark before injecting so the racing UserPromptSubmit hook (which
        # POSTs back here within ~100ms) will find it and suppress the echo.
        mark_injected(text)
        try:
            inject(text)
        except Exception as e:
            log.exception("injection failed: %s", e)
            reply_hint(f"⚠️ 注入失败: {e}")

    return handler


def start_ws_client(app_id: str, app_secret: str, feishu: Optional[FeishuClient] = None) -> None:
    """Block on lark WebSocket client. Run in a background thread."""
    handler = make_message_handler(feishu)

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

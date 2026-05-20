"""Feishu long-connection (WebSocket) client for cc-relay — receives inbound
messages from Feishu and injects them into the Claude PTY.

:author: jachel.lyu
"""
import json
import logging
from collections import deque
from typing import Callable, Optional

import lark_oapi as lark
from lark_oapi.event.callback.model.p2_card_action_trigger import (
    CallBackToast,
    P2CardActionTriggerResponse,
)

from echo_filter import mark_injected
from feishu import FeishuClient
from image_cache import save_file_bytes, save_image_bytes
from injector import inject
import time as _time
import files_tracker
import screenshot as screenshot_mod
from history import current_transcript, format_history, recent_turns

# debounce window for /snap; multiple rapid triggers within this many seconds
# reuse the latest screenshot instead of re-shooting.
_SNAP_DEBOUNCE_SEC = 5.0
_last_snap_ts = 0.0

# Dedup ring for feishu message_ids — lark's long-conn occasionally re-delivers
# unacked messages, which without this would cause us to re-process them.
_seen_msg_ids: deque = deque(maxlen=500)
from menu import MENU_TITLE, build_menu_body, build_menu_text, is_trigger, offer_menu, try_consume_choice
from push_state import is_tool_use_paused, set_paused
from sender import MAX_BYTES, is_within_project, parse_send_command, resolve_path

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

    def do_send_file(raw_path: str) -> None:
        """Resolve `raw_path`, validate, upload to feishu, push status hint."""
        if feishu is None:
            reply_hint("⚠️ feishu client 未注入，无法上传")
            return
        file_path = resolve_path(raw_path)
        if file_path is None or not file_path.exists():
            reply_hint(f"⚠️ 找不到: {raw_path}")
            return
        if not file_path.is_file():
            reply_hint(f"⚠️ 不是文件: {raw_path}")
            return
        if not is_within_project(file_path):
            reply_hint(f"⛔ 拒绝: 路径在工程目录之外 ({file_path})")
            return
        size = file_path.stat().st_size
        if size > MAX_BYTES:
            reply_hint(f"⚠️ 文件 {size/1024/1024:.1f}MB 超过 30MB 限制")
            return
        try:
            feishu.upload_file_and_send(file_path)
            reply_hint(f"📤 已发送 {file_path.name} ({size/1024:.1f}KB)")
        except Exception as e:
            log.exception("send file failed")
            reply_hint(f"⚠️ 上传失败: {e}")

    def push_menu_card() -> None:
        """Send the slash-command menu as a styled card (or fall back to text)."""
        if feishu is None:
            return
        try:
            feishu.send_header_card(MENU_TITLE, build_menu_body(), color="orange")
        except Exception as e:
            log.warning("menu card failed, falling back to text: %s", e)
            try:
                feishu.send_text(build_menu_text())
            except Exception:
                pass

    def handler(data) -> None:
        try:
            msg = data.event.message
            content_raw = msg.content
            msg_type = getattr(msg, "message_type", None) or "?"
            msg_id = getattr(msg, "message_id", "") or ""
        except (AttributeError, TypeError) as e:
            log.warning("could not read message envelope: %s", e)
            return

        # lark long-conn occasionally redelivers the same message — drop dupes.
        if msg_id:
            if msg_id in _seen_msg_ids:
                log.info("duplicate message_id %s — skipped", msg_id)
                return
            _seen_msg_ids.append(msg_id)

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

        # Bridge-local control commands (NOT forwarded to Claude).
        low = text.lower()
        # Strip Unicode variation selectors so emoji menu names match regardless
        # of whether the Feishu client sends e.g. 🗑 or 🗑️.
        _menu = text.strip().replace('️', '')

        if low in ("/pause", "/p") or _menu == "⏸ 暂停通知":
            set_paused(True)
            reply_hint("⏸ 已暂停 🛠️ tool_use 推送（/resume 恢复）")
            return
        if low in ("/resume", "/r") or _menu == "▶ 恢复通知":
            set_paused(False)
            reply_hint("▶ 已恢复 🛠️ tool_use 推送")
            return
        if low in ("/status", "/s"):
            reply_hint(f"📊 tool_use 推送：{'⏸ 暂停中' if is_tool_use_paused() else '▶ 启用'}")
            return
        if _menu == "🗑 清屏":
            mark_injected("/clear")
            try:
                inject("/clear")
            except Exception as e:
                log.exception("injection failed: %s", e)
                reply_hint(f"⚠️ 注入失败: {e}")
            return
        if low == "/files" or low.startswith("/files ") or _menu == "📂 文件":
            n = 20
            parts = low.split()
            if len(parts) >= 2 and parts[1].isdigit():
                n = max(1, min(50, int(parts[1])))
            items = files_tracker.list_recent(n)
            if not items:
                reply_hint("📂 还没有追踪到生成/修改的文件")
                return
            files_tracker.offer_selection([fp for _, _, fp in items])
            body_lines = [f"**最近 {len(items)} 个修改/生成的文件**", "**回复数字直接上传到飞书**", ""]
            for i, (_ts, action, fp) in enumerate(items, 1):
                rel = files_tracker.to_project_relative(fp)
                body_lines.append(f"`{i:>2}.`  `{action}`  `{rel}`")
            body_lines.append("")
            body_lines.append(f"*选择 120s 内有效；或发 `传 <路径>` 自定义*")
            if feishu is not None:
                try:
                    feishu.send_header_card("📂 本会话文件", "\n".join(body_lines), color="indigo")
                except Exception as e:
                    log.warning("files card failed: %s", e)
                    reply_hint("\n".join(body_lines))
            return
        if low in ("/snap", "/screenshot", "/截图", "/shot") or _menu == "📸 截图":
            global _last_snap_ts
            now = _time.time()
            if now - _last_snap_ts < _SNAP_DEBOUNCE_SEC:
                log.info("/snap debounced (Δ=%.2fs since last)", now - _last_snap_ts)
                reply_hint(f"⏳ 上一张截图刚发过 ({now - _last_snap_ts:.1f}s)，请稍后再试")
                return
            _last_snap_ts = now
            log.info("/snap triggered by text command %r", text)
            if feishu is None:
                reply_hint("⚠️ feishu 不可用")
                return
            try:
                path = screenshot_mod.take()
            except Exception as e:
                log.exception("screenshot failed")
                reply_hint(f"⚠️ 截图失败: {e}")
                return
            try:
                feishu.upload_file_and_send(path)
                reply_hint(f"📸 截图已发送 ({path.stat().st_size/1024:.1f}KB)")
            except Exception as e:
                log.exception("screenshot upload failed")
                reply_hint(f"⚠️ 上传失败: {e}")
            return
        if low == "/history" or low.startswith("/history ") or _menu == "📜 历史":
            n = 5
            parts = low.split()
            if len(parts) >= 2 and parts[1].isdigit():
                n = max(1, min(20, int(parts[1])))
            tp = current_transcript()
            if not tp:
                reply_hint("📜 还没有捕获到 transcript（先聊一句）")
                return
            reply_hint(format_history(recent_turns(tp, n)))
            return

        # Menu shortcut: typing a trigger word pops up the numbered menu.
        if is_trigger(text):
            offer_menu()
            push_menu_card()
            return

        # File selection pending? A bare digit picks the file to upload.
        chosen_file = files_tracker.try_select(text)
        if chosen_file:
            reply_hint(f"📤 选中 #{text}: {files_tracker.to_project_relative(chosen_file)}")
            do_send_file(chosen_file)
            return

        # File upload shortcut: "传 <path>" / "send <path>".
        send_target = parse_send_command(text)
        if send_target is not None:
            do_send_file(send_target)
            return

        # If a slash-command menu is pending, translate the digit to the command.
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


def _toast(content: str, level: str = "info") -> P2CardActionTriggerResponse:
    """Build a toast response — feishu shows this as a flash at the top."""
    resp = P2CardActionTriggerResponse({})
    toast = CallBackToast({})
    toast.type = level
    toast.content = content
    resp.toast = toast
    return resp


def make_card_action_handler(feishu: Optional[FeishuClient] = None) -> Callable:
    """Build a handler for card-button taps from the phone."""

    def handler(data) -> P2CardActionTriggerResponse:
        try:
            value = data.event.action.value or {}
        except AttributeError:
            value = {}
        action = (value.get("action") or "").lower()
        log.info("card action: %r", value)

        if action == "inject":
            text = value.get("text") or ""
            if text:
                mark_injected(text)
                try:
                    inject(text)
                    return _toast(f"已发送: {text}")
                except Exception as e:
                    log.exception("card-action inject failed: %s", e)
                    return _toast(f"注入失败: {e}", level="error")
            return _toast("空内容", level="warning")
        elif action == "interrupt":
            try:
                inject("\x1b")
                return _toast("已发送 ESC")
            except Exception as e:
                log.exception("card-action interrupt failed: %s", e)
                return _toast(f"中断失败: {e}", level="error")
        elif action == "menu":
            offer_menu()
            if feishu is not None:
                try:
                    feishu.send_header_card(MENU_TITLE, build_menu_body(), color="orange")
                except Exception as e:
                    log.exception("menu push failed: %s", e)
                    return _toast(f"菜单推送失败: {e}", level="error")
            return _toast("菜单已发送")
        elif action == "file_help":
            if feishu is None:
                return _toast("feishu 不可用", level="error")
            items = files_tracker.list_recent(20)
            try:
                if items:
                    files_tracker.offer_selection([fp for _, _, fp in items])
                    lines = [
                        f"**本会话修改/生成的 {len(items)} 个文件**",
                        "**回复数字直接上传到飞书**",
                        "",
                    ]
                    for i, (_ts, act, fp) in enumerate(items, 1):
                        rel = files_tracker.to_project_relative(fp)
                        lines.append(f"`{i:>2}.`  `{act}`  `{rel}`")
                    lines.append("")
                    lines.append("*选择 120s 内有效；或发 `传 <路径>` 自定义*")
                    feishu.send_header_card("📂 本会话文件", "\n".join(lines), color="indigo")
                    return _toast("📂 文件列表已发")
                else:
                    feishu.send_header_card(
                        "📎 文件收发用法",
                        (
                            "**🔼 手机 → Claude**\n"
                            "直接在聊天发送 **图片 / 文件**，Claude 会读取。\n\n"
                            "**🔽 Claude → 手机**\n"
                            "`传 docs/xxx.html`        （工程相对路径）\n"
                            "`传 E:\\\\MyProject\\\\RC\\\\x.pdf`  （Windows 绝对）\n"
                            "`/files`               （查看 Claude 改过的文件）\n\n"
                            "**限制**：≤ 30MB，仅工程目录内"
                        ),
                        color="wathet",
                    )
                    return _toast("📎 用法已发（暂无追踪到的文件）")
            except Exception as e:
                log.exception("file_help push failed: %s", e)
                return _toast(f"推送失败: {e}", level="error")
        elif action == "pause":
            set_paused(True)
            return _toast("⏸ 已暂停工具通知")
        elif action == "resume":
            set_paused(False)
            return _toast("▶ 已恢复工具通知")
        elif action == "snap":
            if feishu is None:
                return _toast("feishu 不可用", level="error")
            try:
                path = screenshot_mod.take()
                feishu.upload_file_and_send(path)
                return _toast(f"📸 截图已发 ({path.stat().st_size // 1024}KB)")
            except Exception as e:
                log.exception("card-action snap failed: %s", e)
                return _toast(f"截图失败: {e}", level="error")
        elif action == "history":
            if feishu is None:
                return _toast("feishu 不可用", level="error")
            tp = current_transcript()
            if not tp:
                return _toast("还没有捕获到 transcript（先聊一句）", level="warning")
            try:
                feishu.send_header_card("📜 历史对话", format_history(recent_turns(tp, 5)), color="wathet")
                return _toast("📜 历史已发")
            except Exception as e:
                log.exception("card-action history failed: %s", e)
                return _toast(f"历史推送失败: {e}", level="error")
        else:
            return _toast(f"未知动作: {action}", level="warning")

    return handler


def start_ws_client(app_id: str, app_secret: str, feishu: Optional[FeishuClient] = None) -> None:
    """Block on lark WebSocket client. Run in a background thread."""
    handler = make_message_handler(feishu)
    card_handler = make_card_action_handler(feishu)

    event_handler = (
        lark.EventDispatcherHandler.builder("", "")
        .register_p2_im_message_receive_v1(handler)
        .register_p2_card_action_trigger(card_handler)
        .build()
    )

    ws_client = lark.ws.Client(
        app_id,
        app_secret,
        event_handler=event_handler,
        log_level=lark.LogLevel.INFO,
    )
    ws_client.start()

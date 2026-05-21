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
    wrapper_id: str = "",
) -> str:
    """Flatten a Feishu rich-text (post) message into plain text.

    Post format: {"title": "...", "content": [[elem, elem, ...], [elem, ...], ...]}
    Each row is a list of inline elements (text / a / at / img / code_inline / ...).
    Inline images are downloaded to the active wrapper's cache subdir and
    inlined as a local path so Claude can read them. If `wrapper_id` is empty
    the image element is rendered as a placeholder (no download attempted).
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
                if feishu and message_id and ik and wrapper_id:
                    try:
                        data, fname = feishu.download_resource(message_id, ik, "image")
                        win_path = save_image_bytes(wrapper_id, data, fname)
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


def make_message_handler(feishu: Optional[FeishuClient] = None,
                         router=None, registry=None) -> Callable:
    """Handler injects incoming Feishu text into the bot's currently-active
    wrapper (looked up via router). Non-text messages get a feishu hint."""

    def reply_hint(hint: str) -> None:
        if feishu is None:
            return
        try:
            feishu.send_text(hint)
        except Exception as e:
            log.warning("failed to push hint: %s", e)

    def _active_wid() -> Optional[str]:
        if router is None:
            return None
        return router.inbound()

    def _route_and_inject(text: str) -> None:
        wid = _active_wid()
        if not wid:
            reply_hint("⚠️ 当前无活跃且在线的 wrapper，请 /switch 切换或先启动 wrapper")
            return
        mark_injected(wid, text)
        try:
            inject(registry, wid, text)
        except Exception as e:
            log.exception("injection failed: %s", e)
            reply_hint(f"⚠️ 注入失败: {e}")

    def do_send_file(raw_path: str) -> None:
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

        # ---- Rich-text / media branches ----
        if msg_type == "post":
            message_id = getattr(msg, "message_id", "")
            # Pass the active wrapper id so inline images get cached in the
            # right per-wrapper subdir; if no active wrapper, images render
            # as placeholders rather than crashing.
            wid_for_post = _active_wid() or ""
            text = flatten_post(
                content,
                feishu=feishu,
                message_id=message_id,
                wrapper_id=wid_for_post,
            ).strip()
            if not text:
                reply_hint("⚠️ 富文本消息内容为空")
                return
            _route_and_inject(text)
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
            wid = _active_wid()
            if not wid:
                reply_hint("⚠️ 没有活跃 wrapper，无法处理图片")
                return
            try:
                data_bytes, fname = feishu.download_resource(message_id, image_key, "image")
                win_path = save_image_bytes(wid, data_bytes, fname)
            except Exception as e:
                log.exception("image download failed: %s", e)
                reply_hint(f"⚠️ 图片下载失败: {e}")
                return
            prompt = f"请看一下这张飞书发来的图片：{win_path}"
            mark_injected(wid, prompt)
            try:
                inject(registry, wid, prompt)
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
            wid = _active_wid()
            if not wid:
                reply_hint("⚠️ 没有活跃 wrapper，无法处理文件")
                return
            try:
                data_bytes, suggested = feishu.download_resource(message_id, file_key, "file")
                win_path = save_file_bytes(wid, data_bytes, suggested or file_name)
            except Exception as e:
                log.exception("file download failed: %s", e)
                reply_hint(f"⚠️ 文件下载失败: {e}")
                return
            prompt = f"请看一下这个飞书发来的文件（{file_name}）：{win_path}"
            mark_injected(wid, prompt)
            try:
                inject(registry, wid, prompt)
            except Exception as e:
                log.exception("injection failed: %s", e)
                reply_hint(f"⚠️ 注入失败: {e}")
            return

        if msg_type != "text":
            hint = _UNSUPPORTED_HINT.get(msg_type, f"⚠️ 暂不支持的消息类型: {msg_type}")
            reply_hint(hint)
            return

        # ---- Text-message commands ----
        text = (content.get("text") or "").strip()
        if not text:
            return

        low = text.lower()
        _menu = text.strip().replace('️', '')  # strip variation selectors

        # Pause/resume — bucketed by wrapper
        if low in ("/pause", "/p") or _menu == "⏸ 暂停通知":
            wid = _active_wid()
            if not wid:
                reply_hint("⚠️ 没有活跃 wrapper")
                return
            set_paused(wid, True)
            reply_hint("⏸ 已暂停 🛠️ tool_use 推送（/resume 恢复）")
            return
        if low in ("/resume", "/r") or _menu == "▶ 恢复通知":
            wid = _active_wid()
            if not wid:
                reply_hint("⚠️ 没有活跃 wrapper")
                return
            set_paused(wid, False)
            reply_hint("▶ 已恢复 🛠️ tool_use 推送")
            return
        if low in ("/status", "/s"):
            wid = _active_wid()
            if not wid:
                reply_hint("⚠️ 没有活跃 wrapper")
                return
            reply_hint(f"📊 tool_use 推送：{'⏸ 暂停中' if is_tool_use_paused(wid) else '▶ 启用'}")
            return

        if _menu == "🗑 清屏":
            _route_and_inject("/clear")
            return

        # /files — per-wrapper file list
        if low == "/files" or low.startswith("/files ") or _menu == "📂 文件":
            wid = _active_wid()
            if not wid:
                reply_hint("⚠️ 没有活跃 wrapper")
                return
            n = 20
            parts = low.split()
            if len(parts) >= 2 and parts[1].isdigit():
                n = max(1, min(50, int(parts[1])))
            items = files_tracker.list_recent(wid, n)
            if not items:
                reply_hint("📂 还没有追踪到生成/修改的文件")
                return
            files_tracker.offer_selection(wid, [fp for _, _, fp in items])
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

        # /snap — global (screenshot is wrapper-window agnostic for now)
        if low in ("/snap", "/screenshot", "/截图", "/shot") or _menu == "📸 截图":
            global _last_snap_ts
            now = _time.time()
            if now - _last_snap_ts < _SNAP_DEBOUNCE_SEC:
                reply_hint(f"⏳ 上一张截图刚发过 ({now - _last_snap_ts:.1f}s)，请稍后再试")
                return
            _last_snap_ts = now
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

        # /history — per-wrapper transcript
        if low == "/history" or low.startswith("/history ") or _menu == "📜 历史":
            wid = _active_wid()
            if not wid:
                reply_hint("⚠️ 没有活跃 wrapper")
                return
            n = 5
            parts = low.split()
            if len(parts) >= 2 and parts[1].isdigit():
                n = max(1, min(20, int(parts[1])))
            tp = current_transcript(wid)
            if not tp:
                reply_hint("📜 还没有捕获到 transcript（先聊一句）")
                return
            reply_hint(format_history(recent_turns(tp, n)))
            return

        if low in ("/who", "/whoami"):
            if router is None:
                reply_hint("⚠️ router 未初始化")
                return
            wid = router.inbound()
            if not wid:
                lst = router.list_wrappers()
                if not lst:
                    reply_hint("⚠️ 未注册任何 wrapper")
                else:
                    lines = ["📂 已注册项目（无活跃）："]
                    for w in lst:
                        dot = "●" if w["online"] else "○"
                        lines.append(f"  {dot} {w['name']}  ({w['id']})")
                    lines.append("\n用 `/switch 名称` 选择")
                    reply_hint("\n".join(lines))
                return
            for w in router.list_wrappers():
                if w["id"] == wid:
                    online = "🟢 在线" if w["online"] else "⚪ 离线"
                    reply_hint(f"📁 当前活跃：**{w['name']}** ({w['id']}) — {online}")
                    return
            reply_hint(f"📁 当前活跃：{wid}")
            return

        if low.startswith("/switch"):
            if router is None:
                reply_hint("⚠️ router 未初始化")
                return
            parts = text.split(maxsplit=1)
            if len(parts) < 2:
                lst = router.list_wrappers()
                if not lst:
                    reply_hint("⚠️ 未注册任何 wrapper")
                    return
                lines = ["📂 选择项目（回复 `/switch 名称`）："]
                for w in lst:
                    dot = "●" if w["online"] else "○"
                    active = " ⭐" if w["active"] else ""
                    lines.append(f"  {dot} {w['name']}  ({w['id']}){active}")
                reply_hint("\n".join(lines))
                return
            target = parts[1].strip()
            resolved = router.resolve(target)
            if not resolved:
                reply_hint(f"⚠️ 未找到项目 '{target}'。可用：" + ", ".join(w["name"] for w in router.list_wrappers()))
                return
            router.set_active(resolved)
            for w in router.list_wrappers():
                if w["id"] == resolved:
                    state = "🟢 在线" if w["online"] else "⚪ 离线（启动 wrapper 后即可发消息）"
                    reply_hint(f"✅ 已切换到 **{w['name']}** ({w['id']}) — {state}")
                    return
            reply_hint(f"✅ 已切换到 {resolved}")
            return

        # Menu trigger — show numbered command list
        if is_trigger(text):
            wid = _active_wid()
            if not wid:
                reply_hint("⚠️ 没有活跃 wrapper")
                return
            offer_menu(wid)
            push_menu_card()
            return

        # Bare digit → resolve as menu choice or file selection (per-wrapper)
        wid_for_select = _active_wid()
        if wid_for_select:
            chosen_file = files_tracker.try_select(wid_for_select, text)
            if chosen_file:
                reply_hint(f"📤 选中 #{text}: {files_tracker.to_project_relative(chosen_file)}")
                do_send_file(chosen_file)
                return

        # "传 <path>" — upload file
        send_target = parse_send_command(text)
        if send_target is not None:
            do_send_file(send_target)
            return

        # If a menu choice is pending (per-wrapper), translate the digit to the command
        if wid_for_select:
            chosen_cmd = try_consume_choice(wid_for_select, text)
            if chosen_cmd:
                reply_hint(f"▶ 执行 {chosen_cmd}")
                text = chosen_cmd

        # Default: inject into active wrapper
        _route_and_inject(text)

    return handler


def _toast(content: str, level: str = "info") -> P2CardActionTriggerResponse:
    """Build a toast response — feishu shows this as a flash at the top."""
    resp = P2CardActionTriggerResponse({})
    toast = CallBackToast({})
    toast.type = level
    toast.content = content
    resp.toast = toast
    return resp


def make_card_action_handler(feishu: Optional[FeishuClient] = None,
                             router=None, registry=None) -> Callable:

    def _route_inject(text: str) -> tuple:
        if router is None or registry is None:
            return False, "router 未初始化"
        wid = router.inbound()
        if not wid:
            return False, "无活跃 wrapper"
        mark_injected(wid, text)
        try:
            inject(registry, wid, text)
            return True, ""
        except Exception as e:
            return False, str(e)

    def handler(data) -> P2CardActionTriggerResponse:
        try:
            value = data.event.action.value or {}
        except AttributeError:
            value = {}
        action = (value.get("action") or "").lower()
        log.info("card action: %r", value)

        if action == "inject":
            text = value.get("text") or ""
            if not text:
                return _toast("空内容", level="warning")
            ok, err = _route_inject(text)
            return _toast(f"已发送: {text}" if ok else f"注入失败: {err}",
                          level="error" if not ok else "info")

        if action == "interrupt":
            ok, err = _route_inject("\x1b")
            return _toast("已发送 ESC" if ok else f"中断失败: {err}",
                          level="error" if not ok else "info")

        if action == "menu":
            wid = router.inbound() if router else None
            if not wid:
                return _toast("无活跃 wrapper", level="warning")
            offer_menu(wid)
            if feishu is not None:
                try:
                    feishu.send_header_card(MENU_TITLE, build_menu_body(), color="orange")
                except Exception as e:
                    log.exception("menu push failed: %s", e)
                    return _toast(f"菜单推送失败: {e}", level="error")
            return _toast("菜单已发送")

        if action == "file_help":
            if feishu is None:
                return _toast("feishu 不可用", level="error")
            wid = router.inbound() if router else None
            if not wid:
                return _toast("无活跃 wrapper", level="warning")
            items = files_tracker.list_recent(wid, 20)
            try:
                if items:
                    files_tracker.offer_selection(wid, [fp for _, _, fp in items])
                    lines = [
                        f"**本会话修改/生成的 {len(items)} 个文件**",
                        "**回复数字直接上传到飞书**", "",
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

        if action == "pause":
            wid = router.inbound() if router else None
            if not wid:
                return _toast("无活跃 wrapper", level="warning")
            set_paused(wid, True)
            return _toast("⏸ 已暂停工具通知")

        if action == "resume":
            wid = router.inbound() if router else None
            if not wid:
                return _toast("无活跃 wrapper", level="warning")
            set_paused(wid, False)
            return _toast("▶ 已恢复工具通知")

        if action == "snap":
            if feishu is None:
                return _toast("feishu 不可用", level="error")
            try:
                path = screenshot_mod.take()
                feishu.upload_file_and_send(path)
                return _toast(f"📸 截图已发 ({path.stat().st_size // 1024}KB)")
            except Exception as e:
                log.exception("card-action snap failed: %s", e)
                return _toast(f"截图失败: {e}", level="error")

        if action == "history":
            if feishu is None:
                return _toast("feishu 不可用", level="error")
            wid = router.inbound() if router else None
            if not wid:
                return _toast("无活跃 wrapper", level="warning")
            tp = current_transcript(wid)
            if not tp:
                return _toast("还没有捕获到 transcript（先聊一句）", level="warning")
            try:
                feishu.send_header_card("📜 历史对话", format_history(recent_turns(tp, 5)), color="wathet")
                return _toast("📜 历史已发")
            except Exception as e:
                log.exception("card-action history failed: %s", e)
                return _toast(f"历史推送失败: {e}", level="error")

        return _toast(f"未知动作: {action}", level="warning")

    return handler


def start_ws_client(app_id: str, app_secret: str,
                    feishu: Optional[FeishuClient] = None,
                    router=None, registry=None) -> None:
    """Block on lark WebSocket client. Run in a background thread."""
    handler = make_message_handler(feishu, router, registry)
    card_handler = make_card_action_handler(feishu, router, registry)

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

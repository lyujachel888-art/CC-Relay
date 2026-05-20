"""Feishu (Lark) API client used by cc-relay to send messages, cards, images
and files to the configured user.

:author: jachel.lyu
"""
import json
import re
import unicodedata
from pathlib import Path
from typing import Optional, Tuple
import lark_oapi as lark
from lark_oapi.api.im.v1 import (
    CreateFileRequest,
    CreateFileRequestBody,
    CreateImageRequest,
    CreateImageRequestBody,
    CreateMessageRequest,
    CreateMessageRequestBody,
    GetMessageResourceRequest,
)


# Feishu's interactive-card markdown renderer supports a subset of CommonMark:
# bold / italic / strike / inline code / fenced code / lists / links work.
# ATX headers (# ## ###) and blockquotes (>) and GFM tables (|...|) do NOT
# render — they show as literal source text. Rewrite them into things that do.
_RE_FENCED = re.compile(r"```[\s\S]*?```", re.MULTILINE)
_RE_HEADER = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
_RE_QUOTE  = re.compile(r"^>\s?(.*)$", re.MULTILINE)
# A GFM table: pipe-row + separator-row (|---|---|) + one or more pipe-rows.
_RE_TABLE = re.compile(
    r"((?:^\|[^\n]+\|[ \t]*\n)"        # header row
    r"(?:^\|[ \t:|\-]+\|[ \t]*\n)"     # separator row
    r"(?:^\|[^\n]+\|[ \t]*\n?)+)",     # at least one body row
    re.MULTILINE,
)


def _display_width(s: str) -> int:
    """Visual width when rendered in a monospace font (CJK = 2 cols)."""
    w = 0
    for c in s:
        w += 2 if unicodedata.east_asian_width(c) in ("F", "W") else 1
    return w


_RE_SEPARATOR_CELL = re.compile(r"^[-:\s]+$")


# Feishu's `file_type` enum for upload. Anything not in this list goes as "stream".
_FILE_TYPE_BY_SUFFIX = {
    ".pdf": "pdf",
    ".doc": "doc", ".docx": "doc",
    ".xls": "xls", ".xlsx": "xls",
    ".ppt": "ppt", ".pptx": "ppt",
    ".mp4": "mp4", ".mov": "mp4",
    ".mp3": "opus", ".wav": "opus", ".ogg": "opus", ".opus": "opus",
}


def _guess_feishu_file_type(suffix: str) -> str:
    return _FILE_TYPE_BY_SUFFIX.get(suffix.lower(), "stream")


def _parse_gfm_table(block: str) -> Optional[dict]:
    """Parse a GFM markdown table block. Returns a feishu v2 `table` element,
    or None if it doesn't look like a real table."""
    rows = []
    for line in block.strip().split("\n"):
        line = line.strip()
        if not (line.startswith("|") and line.endswith("|")):
            continue
        cells = [c.strip() for c in line[1:-1].split("|")]
        rows.append(cells)

    data_rows = [r for r in rows if not all(_RE_SEPARATOR_CELL.match(c or "") for c in r)]
    if len(data_rows) < 2:
        return None

    col_count = max(len(r) for r in data_rows)
    for r in data_rows:
        r.extend([""] * (col_count - len(r)))

    headers, body = data_rows[0], data_rows[1:]
    columns = [
        {
            "name": f"c{i}",
            "display_name": headers[i] if i < len(headers) else f"列{i + 1}",
            "width": "auto",
            "data_type": "text",
        }
        for i in range(col_count)
    ]
    payload_rows = [{f"c{i}": (r[i] if i < len(r) else "") for i in range(col_count)} for r in body]
    # page_size must be a positive int (feishu rejects 0). Cap at 50 — small
    # tables show entirely, huge ones get paginated. Min 1 for empty bodies.
    page_size = max(1, min(50, len(payload_rows)))
    return {
        "tag": "table",
        "page_size": page_size,
        "row_height": "low",
        "header_style": {
            "background_style": "grey-100",
            "bold": True,
            "lines": 1,
        },
        "columns": columns,
        "rows": payload_rows,
    }


def _default_action_bar() -> dict:
    """Three quick-action buttons appended to every 🤖 card.

    v2 schema rejected the old `action` tag — buttons go inside a column_set,
    one per column, and use `behaviors: [{type: callback, value: ...}]` to
    trigger a card.action.trigger event we can handle on the long-conn side.
    """

    def col_btn(label: str, btn_type: str, value: dict) -> dict:
        return {
            "tag": "column",
            "width": "weighted",
            "weight": 1,
            "elements": [
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": label},
                    "type": btn_type,
                    "width": "fill",
                    "behaviors": [{"type": "callback", "value": value}],
                }
            ],
        }

    return {
        "tag": "column_set",
        "horizontal_spacing": "small",
        "columns": [
            col_btn("继续", "primary", {"action": "inject", "text": "继续"}),
            col_btn("📎 文件", "default", {"action": "file_help"}),
            col_btn("打断", "danger", {"action": "interrupt"}),
        ],
    }


def _md_to_v2_elements(md: str) -> list:
    """Split `md` into a sequence of v2 card elements: markdown segments
    separated by native `table` elements wherever a GFM table appears."""
    elements: list = []
    last_end = 0

    def push_md(text: str) -> None:
        text = text.strip()
        if text:
            elements.append({"tag": "markdown", "content": _adapt_md_for_feishu(text)})

    for m in _RE_TABLE.finditer(md):
        push_md(md[last_end:m.start()])
        tbl = _parse_gfm_table(m.group(1))
        if tbl is not None:
            elements.append(tbl)
        else:
            # Couldn't parse — pass through as markdown so user at least sees it.
            push_md(m.group(1))
        last_end = m.end()
    push_md(md[last_end:])

    if not elements:
        elements.append({"tag": "markdown", "content": _adapt_md_for_feishu(md)})
    return elements


def _adapt_md_for_feishu(md: str) -> str:
    """Rewrite parts of the markdown that feishu's card renderer drops."""
    # Protect fenced code blocks from any transformation below.
    code_blocks: list = []

    def _stash(m):
        code_blocks.append(m.group(0))
        return f"\x00CODE{len(code_blocks) - 1}\x00"

    work = _RE_FENCED.sub(_stash, md)

    # Tables are handled separately as native v2 card `table` elements; this
    # adapter only operates on the in-between markdown segments, which by
    # construction contain no GFM tables.

    # # / ## / ### …  →  **bold** with surrounding blank lines.
    def _header_repl(m):
        return f"\n**{m.group(2)}**\n"
    work = _RE_HEADER.sub(_header_repl, work)

    # > quoted  →  italic
    def _quote_repl(m):
        body = m.group(1).strip()
        return f"*{body}*" if body else ""
    work = _RE_QUOTE.sub(_quote_repl, work)

    # Restore code blocks (originals + table-wrapped ones).
    def _unstash(m):
        idx = int(m.group(1))
        return code_blocks[idx]
    work = re.sub(r"\x00CODE(\d+)\x00", _unstash, work)

    return work


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

    def send_header_card(
        self,
        title: str,
        body_md: str,
        color: str = "blue",
    ) -> None:
        """Compact v2 card with a colored header bar + markdown body.

        color: feishu template name — blue/green/orange/red/purple/turquoise/
                yellow/wathet/violet/carmine/indigo/grey.
        """
        card = {
            "schema": "2.0",
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": color,
            },
            "body": {
                "elements": [
                    {"tag": "markdown", "content": _adapt_md_for_feishu(body_md)},
                ],
            },
        }
        self._send_simple("interactive", json.dumps(card, ensure_ascii=False))

    def send_markdown_card(
        self,
        md: str,
        title: str = "",
        color: str = "violet",
        with_actions: bool = True,
    ) -> None:
        """Send `md` as a feishu v2 interactive card. GFM tables become native
        `table` elements, everything else stays as markdown. Optional colored
        header bar (when title is set) and action button row."""
        elements = _md_to_v2_elements(md)
        if with_actions:
            elements.append(_default_action_bar())
        card = {
            "schema": "2.0",
            "config": {"wide_screen_mode": True},
            "body": {"elements": elements},
        }
        if title:
            card["header"] = {
                "title": {"tag": "plain_text", "content": title},
                "template": color,
            }
        req = (
            CreateMessageRequest.builder()
            .receive_id_type("open_id")
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(self._user_open_id)
                .msg_type("interactive")
                .content(json.dumps(card, ensure_ascii=False))
                .build()
            )
            .build()
        )
        resp = self._client.im.v1.message.create(req)
        if not getattr(resp, "success", lambda: True)():
            code = getattr(resp, "code", "?")
            msg = getattr(resp, "msg", "?")
            log_id = getattr(resp, "get_log_id", lambda: "?")()
            raise RuntimeError(
                f"feishu card send failed code={code} msg={msg} log_id={log_id}"
            )

    def upload_file_and_send(self, path: Path) -> None:
        """Upload a local file/image and send it to the user.
        Picks file vs image upload based on the path's extension."""
        suffix = path.suffix.lower()
        image_suffixes = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
        if suffix in image_suffixes:
            with path.open("rb") as f:
                req = (
                    CreateImageRequest.builder()
                    .request_body(
                        CreateImageRequestBody.builder()
                        .image_type("message")
                        .image(f)
                        .build()
                    )
                    .build()
                )
                resp = self._client.im.v1.image.create(req)
            if not getattr(resp, "success", lambda: True)():
                raise RuntimeError(
                    f"feishu image upload failed code={getattr(resp,'code','?')} msg={getattr(resp,'msg','?')}"
                )
            image_key = resp.data.image_key
            self._send_simple("image", json.dumps({"image_key": image_key}))
            return

        # Otherwise upload as a generic file.
        file_type = _guess_feishu_file_type(suffix)
        with path.open("rb") as f:
            req = (
                CreateFileRequest.builder()
                .request_body(
                    CreateFileRequestBody.builder()
                    .file_type(file_type)
                    .file_name(path.name)
                    .file(f)
                    .build()
                )
                .build()
            )
            resp = self._client.im.v1.file.create(req)
        if not getattr(resp, "success", lambda: True)():
            raise RuntimeError(
                f"feishu file upload failed code={getattr(resp,'code','?')} msg={getattr(resp,'msg','?')}"
            )
        file_key = resp.data.file_key
        self._send_simple("file", json.dumps({"file_key": file_key}))

    def _send_simple(self, msg_type: str, content: str) -> None:
        req = (
            CreateMessageRequest.builder()
            .receive_id_type("open_id")
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(self._user_open_id)
                .msg_type(msg_type)
                .content(content)
                .build()
            )
            .build()
        )
        resp = self._client.im.v1.message.create(req)
        if not getattr(resp, "success", lambda: True)():
            raise RuntimeError(
                f"feishu send {msg_type} failed code={getattr(resp,'code','?')} msg={getattr(resp,'msg','?')}"
            )

    def send_startup_card(self) -> None:
        """Send a persistent quick-action card when bridge starts.
        Replaces the native bot menu (which can't be configured via API for P2P chats)."""

        def col_btn(label: str, action_value: dict, btn_type: str = "default") -> dict:
            return {
                "tag": "column",
                "width": "weighted",
                "weight": 1,
                "elements": [{
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": label},
                    "type": btn_type,
                    "width": "fill",
                    "behaviors": [{"type": "callback", "value": action_value}],
                }],
            }

        card = {
            "schema": "2.0",
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": "🚀 CC Relay 已连接"},
                "template": "green",
            },
            "body": {
                "elements": [
                    {
                        "tag": "column_set",
                        "horizontal_spacing": "small",
                        "columns": [
                            col_btn("📋 菜单", {"action": "menu"}),
                            col_btn("📸 截图", {"action": "snap"}),
                            col_btn("📜 历史", {"action": "history"}),
                        ],
                    },
                    {
                        "tag": "column_set",
                        "horizontal_spacing": "small",
                        "columns": [
                            col_btn("🗑️ 清屏", {"action": "inject", "text": "/clear"}),
                            col_btn("⏸ 暂停", {"action": "pause"}),
                            col_btn("▶ 恢复", {"action": "resume"}),
                        ],
                    },
                ]
            },
        }
        self._send_simple("interactive", json.dumps(card, ensure_ascii=False))

    def download_resource(
        self, message_id: str, file_key: str, resource_type: str = "image"
    ) -> Tuple[bytes, str]:
        """Download an image/file attached to a message. Returns (bytes, suggested_filename)."""
        req = (
            GetMessageResourceRequest.builder()
            .message_id(message_id)
            .file_key(file_key)
            .type(resource_type)
            .build()
        )
        resp = self._client.im.v1.message_resource.get(req)
        if not getattr(resp, "success", lambda: True)():
            code = getattr(resp, "code", "?")
            msg = getattr(resp, "msg", "?")
            raise RuntimeError(f"feishu download failed code={code} msg={msg}")
        data = resp.file.read() if getattr(resp, "file", None) else b""
        file_name = getattr(resp, "file_name", "") or ""
        return data, file_name

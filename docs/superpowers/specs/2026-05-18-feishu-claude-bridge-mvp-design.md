# 飞书 ↔ Claude Code 双向桥接 MVP 设计

**状态**: Spike / 可行性验证
**日期**: 2026-05-18
**作者**: Jachel + Claude

## 目标

打通最小双向通讯链路：
- Claude Code 终端里发生的对话 → 实时推送到手机飞书
- 手机飞书里发的消息 → 注入到 Claude Code 终端，作为下一轮 user prompt

终端体验保持原样（Windows Terminal 窗口），飞书作为远程伴侣，可以离开电脑后继续推进对话。

## 架构

```
┌─────────────────────────────────────────┐
│ Windows Terminal                        │
│  └─ wsl -- tmux new -A -s cc1 claude    │
│         └─ Claude Code (WSL/Ubuntu)     │
│              │                          │
│              │ hooks (Stop / UserPrompt)│
│              ▼                          │
│      ┌──────────────────────┐           │
│      │ bridge service (Py)  │           │
│      │  • FastAPI: hook in  │           │
│      │  • lark-oapi 长连接  │           │
│      └──────────┬───────────┘           │
│                 │ tmux send-keys -t cc1 │
│                 ▼                       │
│            (back to Claude Code)        │
└─────────────────────────────────────────┘
              │            ▲
   推消息API  │            │ 长连接订阅事件
              ▼            │
        ┌─────────────────────┐
        │  飞书开放平台        │
        │  (自建应用)          │
        └─────────────────────┘
              │            ▲
              ▼            │
        ┌─────────────────────┐
        │  手机飞书 APP        │
        │  (与机器人私聊)      │
        └─────────────────────┘
```

## 组件

### 1. WSL + tmux 容器
- WSL Ubuntu，Claude Code 装在 WSL 端
- 启动命令：`wsl -- tmux new-session -A -s cc1 claude`
- Windows Terminal 看到的就是 Claude Code TUI，无视觉差异

### 2. Claude Code hooks（WSL 端 `~/.claude/settings.json`）
- `UserPromptSubmit`：用户在终端按回车 → POST 提问到 bridge
- `Stop`：Claude 答完一段 → POST 回复到 bridge
- hook 用 shell 脚本，curl 本地 bridge

### 3. Bridge service（Python，WSL 端前台跑）
- 监听 `127.0.0.1:8787`（只暴露给本机，hook 用 `curl http://127.0.0.1:8787/...`）
- **入口 1：FastAPI HTTP**
  - `POST /hook/user_prompt` → 调飞书 API 发"🧑 <内容>"
  - `POST /hook/assistant_reply` → 调飞书 API 发"🤖 <内容>"
  - hook 脚本职责：读 stdin JSON 拿 `transcript_path` → 解析最后一条消息 → POST body
- **入口 2：lark-oapi 长连接客户端**
  - 订阅 `im.message.receive_v1` 事件
  - 收到消息 → 调 `tmux send-keys -t cc1 -- "<text>" Enter`

### 4. 飞书自建应用
- 新建 1 人企业（用户当前是个人账号，需先注册）
- 开发者后台创建自建应用，启用：
  - 机器人能力
  - `im:message`（发送消息）
  - `im:message.group_at_msg` / `im:message.p2p_msg` 事件订阅
- 用**长连接模式**（避免公网映射），SDK 自动处理

## 数据流

**Claude → 手机方向：**
```
用户输回车 → UserPromptSubmit hook → curl POST /hook/user_prompt
                                          → lark.send_message("🧑 ...")
                                              → 手机飞书弹通知

Claude 答完  → Stop hook              → curl POST /hook/assistant_reply
                                          → lark.send_message("🤖 ...")
                                              → 手机飞书弹通知
```

**手机 → Claude 方向：**
```
手机发消息 → 飞书云 → 长连接 push 到本地 lark-oapi client
                          → tmux send-keys -t cc1 -- "<text>" Enter
                              → Claude Code 接到提问，开始回答
                                  → Stop hook 又触发推回手机（闭环）
```

## MVP 范围（明确写下不做什么）

**做：**
- 1 个 Claude Code 窗口（session 名硬编码 `cc1`）
- 推送用户提问 + Claude 最终文本回复
- 接收任何手机消息 → 直接 send-keys

**不做（明确推迟）：**
- 多窗口路由
- 推送 thinking / tool call 详情
- 指令解析（/stop /reset 等）
- 长消息分片、Markdown 渲染优化
- 鉴权（任何人发消息到这个机器人都会被注入 — MVP 假定只有自己加机器人）
- 错误重试、断线重连完善
- 生产化部署（systemd / 开机自启 / 日志轮转）

## 验收标准

1. 在 Windows Terminal 启动 `wsl -- tmux new -A -s cc1 claude`，看到 Claude Code TUI 正常
2. 在终端问"现在几点"，手机飞书机器人在 2 秒内收到"🧑 现在几点"
3. Claude 答完后，手机飞书机器人收到"🤖 现在是..."
4. 关电脑屏幕，从手机飞书发"那今天星期几"，5 秒内：
   - 终端 Claude Code 出现这句提问
   - Claude 开始作答
   - 手机收到回答
5. 整个回合无人工干预

## 技术栈

| 组件 | 选型 | 理由 |
|---|---|---|
| Bridge 语言 | Python 3.11+ | 飞书官方 SDK `lark-oapi` 最完善 |
| HTTP 框架 | FastAPI + uvicorn | 极简，hook 只接 2 个端点 |
| 飞书 SDK | `lark-oapi` 官方包 | 自带 WebSocket 长连接客户端 |
| 进程管理 | 前台跑（MVP） | 后续加 systemd |
| 终端复用 | tmux | send-keys 注入成熟 |

## 后续（不在 MVP）

- 多窗口路由（飞书消息前缀 `@cc2 xxx`）
- 富格式（代码块用飞书的 code block 元素）
- 推送 tool call 摘要（带折叠）
- 安全：消息签名校验、白名单 user_id
- 跨设备：Mac / Linux 原生

# CC Relay

**Claude Code ↔ 飞书 实时双向中继桥**

在手机飞书上实时查看 Claude 的回复、工具调用进度和 Bash 结果，并直接向 Claude 发送指令——全程无需离开手机。

```
手机飞书  ←→  飞书开放平台  ←→  bridge (Windows · FastAPI)  ←→  wrapper (ConPTY)  ←→  Claude Code
```

## 功能

| 类别 | 说明 |
|------|------|
| **实时推送** | 用户输入、Claude 回复、工具调用、Bash 结果、任务创建/完成、系统通知 |
| **双向控制** | 手机发消息直接注入 Claude；卡片按钮一键「继续 / 打断」 |
| **文件收发** | 手机发图片/文件 → bridge 保存并告知 Claude；Claude 生成的文件可一键上传飞书 |
| **截图推送** | `/snap` 截取 Claude Code 窗口并发飞书 |
| **会话历史** | `/history` 展示最近 5 轮对话摘要 |

## 系统要求

- **Windows 10/11**（bridge 和 wrapper 均为纯 Windows Python，无需 WSL）
- Python 3.11+
- Claude Code CLI（`claude` 在 PATH，或安装于 `%LOCALAPPDATA%\AnthropicClaude\`）
- 飞书企业自建应用（见下方配置）

## 安装

```powershell
git clone https://github.com/lyujachel888-art/CC-Relay-.git
cd CC-Relay-

# bridge 依赖（隔离 venv）
cd bridge
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
cd ..

# wrapper 依赖（系统 Python，ConPTY 需要直接访问 Windows API）
pip install pywinpty
```

## 飞书开放平台配置

> Bridge 使用**长连接（WebSocket）**，无需公网 IP 或 Webhook 回调地址。

### 配置步骤总览

| # | 操作 |
|---|------|
| ① | 创建企业自建应用，记录 App ID / App Secret |
| ② | 功能 › 机器人 — 启用，接收方式选**长连接** |
| ③ | 权限管理 — 开通 `im:message`、`im:resource` |
| ④ | 事件与回调 — 订阅 `im.message.receive_v1`、`card.action.trigger`（长连接模式） |
| ⑤ | 机器人 › 自定义菜单 — 配置 6 个菜单项 |
| ⑥ | 版本管理 — 创建并发布新版本（权限和菜单变更后必须发布才生效） |
| ⑦ | 获取自己的 `open_id`，填入 `bridge/.env` |

---

### ① 创建应用

路径：**open.feishu.cn › 开发者后台 › 创建企业自建应用**

填写应用名（如 *CC Relay*），类型选「机器人」。进入「凭证与基础信息」复制 **App ID**（`cli_xxx`）和 **App Secret**。

---

### ② 开启机器人

路径：**应用详情 › 功能 › 机器人**

启用机器人，消息接收方式选**长连接**，无需填写 Webhook 地址。

---

### ③ API 权限

路径：**应用详情 › 权限管理 › 搜索并开通**

| 权限 | 用途 |
|------|------|
| `im:message` | 发送文本、交互卡片、图片、文件 |
| `im:resource` | 上传截图/文件；下载用户发来的图片/文件 |

---

### ④ 事件订阅

路径：**应用详情 › 事件与回调 › 添加事件**（接收方式选**长连接**）

| 事件 | 触发时机 | Bridge 处理 |
|------|----------|-------------|
| `im.message.receive_v1` | 用户发送任何消息 | 命令识别或注入 Claude |
| `card.action.trigger` | 点击卡片按钮 | 执行继续 / 打断 / 文件等操作 |

Bridge 支持的消息类型：`text` / `post`（富文本）/ `image` / `file`

---

### ⑤ 自定义菜单

路径：**应用详情 › 功能 › 机器人 › 自定义菜单**

每项类型选**「发送消息」**，发送内容与菜单名完全一致（含 emoji 和空格）：

| 层级 | 菜单名 | 发送内容 |
|------|--------|----------|
| 顶级 1 | 📸 截图 | `📸 截图` |
| 顶级 2 | 📂 文件 | `📂 文件` |
| 顶级 3 | 🛠️ 更多 | （父级，不发送） |
| └ 子 1 | 📜 历史 | `📜 历史` |
| └ 子 2 | 🗑️ 清屏 | `🗑️ 清屏` |
| └ 子 3 | ⏸ 暂停通知 | `⏸ 暂停通知` |
| └ 子 4 | ▶ 恢复通知 | `▶ 恢复通知` |
| └ 子 5 | 🔍 当前项目 | `🔍 当前项目` |
| └ 子 6 | 🔄 切换项目 | `🔄 切换项目` |

> 飞书客户端可能附加 emoji 变体选择符（U+FE0F），bridge 已做兼容处理。

---

### ⑥ 发布版本

路径：**应用详情 › 版本管理与发布 › 创建版本**

创建版本后申请发布。企业内部自建应用通常直接生效。发布后在飞书搜索应用名，发起与机器人的单聊。

---

### ⑦ 获取 open_id 并配置 .env

启动 bridge 后在飞书给机器人发任意消息，控制台会打印：

```
INFO bridge.long_conn: recv ... sender open_id=ou_xxxxxxxxxxxx type=text ...
```

复制 `ou_` 开头的值，填入 `bridge/.env`：

```ini
# bridge/.env（从 bridge/.env.example 复制）
FEISHU_APP_ID=cli_xxxxxxxxxxxxxxxxxxxxxx
FEISHU_APP_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
FEISHU_USER_OPEN_ID=ou_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

> `.env` 已在 `.gitignore` 中排除，不要提交到 git。

---

## 环境变量参考

### bridge/.env（必填）

| 变量 | 说明 |
|------|------|
| `FEISHU_APP_ID` | 飞书 App ID，格式 `cli_xxx` |
| `FEISHU_APP_SECRET` | 飞书 App Secret |
| `FEISHU_USER_OPEN_ID` | 消息推送目标用户，格式 `ou_xxx` |

### Shell 环境变量（可选，在运行 claude 的终端中设置）

| 变量 | 值 | 说明 |
|------|----|------|
| `SKIP_TOOL_HOOK` | `1` | 静默工具调用通知，保留用户输入和 Claude 回复推送 |
| `SKIP_ALL_HOOK` | `1` | 关闭所有 hook 上报（bridge 停止时使用） |
| `CLAUDE_EXE` | 完整路径 | 强制指定 `claude.exe` 路径（默认自动查找） |

```powershell
$env:SKIP_TOOL_HOOK = "1"   # 仅本次终端会话生效
claude
```

### 端口

| 端口 | 用途 | 涉及文件 |
|------|------|----------|
| `8787` | Bridge HTTP，接收 hook POST | `bridge/main.py`、`hooks/post_hook.py` |
| 动态端口 | 每个 wrapper TCP 监听端口（启动时由 OS 分配，通过 `/api/wrappers/register` 上报给 bridge） | `wrapper/wrapper.py`（`pick_free_port()`）、`bridge/injector.py`（通过 `WrapperRegistry.lookup_port` 查询） |

### Bridge Token

首次启动自动生成随机 token，写入 `hooks/.bridge_token`。hook 脚本读取同一文件做 Bearer Token 鉴权，无需手动配置。

---

## Claude Code Hooks 配置

将 `.claude/settings.json` 复制到目标项目的 `.claude/settings.json`，或直接在本仓库目录下运行 Claude Code。

当前注册的 hook 事件：

| 事件 | 飞书推送内容 |
|------|-------------|
| `UserPromptSubmit` | 🧑 用户输入（蓝色卡片） |
| `Stop` | 🤖 Claude 回复全文（紫色卡片 + 操作按钮） |
| `PreToolUse` | 🛠️ 工具调用一行摘要 |
| `PostToolUse (Write/Edit)` | 记录文件改动（供 `/files` 命令使用） |
| `PostToolUse (Bash)` | ✅/❌ Bash 命令和输出摘要 |
| `TaskCreated` | 🆕 新任务（绿色卡片） |
| `TaskCompleted` | ✅ 任务完成（青色卡片） |
| `Notification` | 🔔 系统通知（橙色卡片） |

---

## 启动

```powershell
# 终端 1 — bridge（FastAPI + 飞书长连接）
powershell -ExecutionPolicy Bypass -File scripts\launch_bridge.ps1

# 终端 2 — wrapper（在你要工作的项目目录下运行）
cd E:\MyProject\YourProject
powershell -ExecutionPolicy Bypass -File E:\MyProject\RC\scripts\launch_claude_wrapper.ps1

# 同时跑多个项目？在不同项目目录里各自启动 wrapper 即可。wrapper id
# 默认从 cwd 派生（如 E:\MyProject\RC → wrapper-rc）。撞名时自动追加哈希后缀。
# 也可显式指定：
#   .\scripts\launch_claude_wrapper.ps1 -Id custom-id -Name Custom
```

启动后飞书收到「🚀 CC Relay 已连接」卡片即表示就绪。

---

## 多 wrapper 切换

也可通过飞书菜单"更多 → 🔍 当前项目" / "更多 → 🔄 切换项目"快捷触发。

| 命令 | 行为 |
|------|------|
| `/who` | 显示当前活跃 wrapper |
| `/switch` | 列出所有已注册 wrapper（标注在线/离线） |
| `/switch RC` | 切到名为 RC 的 wrapper（不区分大小写） |
| `/switch wrapper-rc` | 用 id 精确切换 |

## 命令速查

| 命令 | 菜单 / 别名 | 说明 |
|------|-------------|------|
| `/snap` | 📸 截图 | 截取 Claude Code 窗口发飞书 |
| `/history` | 📜 历史 | 最近 5 轮对话摘要 |
| `/files` | 📂 文件 | 本次会话改动的文件列表，可选择上传 |
| `/pause` | ⏸ 暂停通知 | 静默工具调用推送 |
| `/resume` | ▶ 恢复通知 | 恢复工具调用推送 |
| `/clear` | 🗑️ 清屏 | 向 Claude 注入 `/clear` |
| `传 <路径>` | — | 上传指定文件到飞书（支持 Windows 绝对路径和相对路径） |

---

## 项目结构

```
CC-Relay-/
├── bridge/                  # FastAPI 服务（Windows Python）
│   ├── main.py              # 入口：启动 FastAPI + 飞书长连接
│   ├── server.py            # /hook/* 端点
│   ├── feishu.py            # 飞书 API 封装（发消息/卡片/文件/截图）
│   ├── long_conn.py         # 飞书长连接：接收消息、命令路由、卡片回调
│   ├── auth.py              # Bearer Token 生成与校验
│   ├── config.py            # 加载 .env 配置
│   ├── injector.py          # TCP → wrapper 注入文本
│   ├── echo_filter.py       # 抑制飞书 → inject → hook 的回声重复
│   ├── files_tracker.py     # 记录本次会话 Claude 修改的文件
│   ├── history.py           # 读取 transcript JSONL，生成对话摘要
│   ├── image_cache.py       # 飞书图片缓存（message_id → 本地路径）
│   ├── menu.py              # /files 交互式选择菜单
│   ├── push_state.py        # 暂停/恢复工具推送状态
│   ├── screenshot.py        # 调用 scripts/screenshot.ps1 截图
│   ├── sender.py            # "传 X" 命令：路径解析 + 安全校验 + 上传
│   ├── .env.example         # 环境变量模板
│   ├── requirements.txt     # Python 依赖
│   └── tests/               # 单元测试
├── hooks/
│   └── post_hook.py         # Claude Code hook 统一入口（所有事件）
├── wrapper/
│   └── wrapper.py           # ConPTY wrapper，托管 claude.exe，TCP 注入服务
├── scripts/
│   ├── launch_bridge.ps1    # 启动 bridge（Windows）
│   ├── launch_claude_wrapper.ps1  # 启动 wrapper
│   └── screenshot.ps1       # 截图辅助脚本（PrintWindow API）
├── .claude/
│   └── settings.json        # Claude Code hooks 注册配置
└── pyproject.toml           # 项目元数据
```

---

## License

MIT · 作者 jachel.lyu

# CC Relay

**Claude Code ↔ Feishu 实时双向中继桥**

CC Relay 将 Claude Code 终端与飞书手机端打通，让你在手机上实时接收 Claude 的回复、查看工具调用进度，并通过飞书消息直接向 Claude 发送指令。

```
手机飞书  ←→  飞书开放平台  ←→  bridge (FastAPI)  ←→  wrapper (ConPTY)  ←→  Claude Code
```

## 功能

- **实时推送**：用户输入、Claude 回复、工具调用、Bash 结果均以飞书卡片推送
- **双向控制**：手机发消息直接注入 Claude 上下文；支持 `/pause`、`/resume`、`/snap`、`/history` 等命令
- **交互卡片**：Claude 回复带「继续 / 📎 文件 / 打断」按钮，一键操作
- **文件收发**：手机发图片/文件，bridge 自动保存并注入路径给 Claude；Claude 写出的文件可一键回传飞书
- **截图推送**：`/snap` 命令截取当前 Claude Code 窗口并发送到飞书

## 系统要求

- Windows 10/11（wrapper 依赖 ConPTY）
- Python 3.11+
- Claude Code CLI（`claude` 可执行文件在 PATH）
- 飞书自建应用（见下方配置）

## 安装

```powershell
# 克隆仓库
git clone https://github.com/yourname/cc-relay.git
cd cc-relay

# 安装 bridge 依赖
cd bridge
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### Wrapper 依赖

```powershell
# wrapper 在系统 Python 下运行（不在 venv 内）
pip install pywinpty
```

## 飞书开放平台配置

> Bridge 使用**长连接（WebSocket）**接收消息，**不需要**公网 IP 或 Webhook 回调地址，纯内网运行即可。

### 步骤总览

| 步骤 | 内容 |
|------|------|
| ① | 创建企业自建应用，获取 App ID / App Secret |
| ② | 开启机器人功能，选择长连接接收模式 |
| ③ | 开通 API 权限：`im:message`、`im:resource` |
| ④ | 订阅事件：`im.message.receive_v1`、`card.action.trigger` |
| ⑤ | 配置自定义菜单（6 个菜单项） |
| ⑥ | 发布应用版本 |
| ⑦ | 获取用户 open_id |
| ⑧ | 填写本地 `bridge/.env` |

---

### ① 创建应用

1. 访问 [open.feishu.cn](https://open.feishu.cn/app)，进入「开发者后台」
2. 点击「创建企业自建应用」，填写应用名称（如 *CC Relay*），类型选「机器人」
3. 进入「凭证与基础信息」，复制 **App ID**（格式 `cli_xxx`）和 **App Secret**

---

### ② 开启机器人功能

路径：**应用详情 › 功能 › 机器人**

1. 点击开启机器人，确认状态为「已启用」
2. 消息接收方式选**长连接**，无需填写 Webhook 地址

---

### ③ API 权限

路径：**应用详情 › 权限管理 › 搜索并开通**

| 权限标识符 | 权限名称 | 用途 |
|------------|----------|------|
| `im:message` | 获取与发送消息 | 发送文本、交互卡片（Claude 回复、任务通知、Bash 结果等） |
| `im:resource` | 上传/下载资源 | 上传截图/文件、下载用户发来的图片和文件 |

> 权限申请后需**发布新版本**才能生效。

各 API 与权限对应关系：

| 代码调用 | 所需权限 | 消息类型 |
|----------|----------|----------|
| `im.v1.message.create` | `im:message` | text / interactive / image / file |
| `im.v1.image.create` | `im:resource` | 上传截图 |
| `im.v1.file.create` | `im:resource` | 上传 PDF / HTML 等文件 |
| `im.v1.message_resource.get` | `im:resource` | 下载用户发来的图片/文件 |

---

### ④ 事件订阅

路径：**应用详情 › 事件与回调 › 添加事件**

接收方式选**「长连接」**，无需填写回调 URL。

| 事件标识符 | 触发时机 | Bridge 处理 |
|------------|----------|-------------|
| `im.message.receive_v1` | 用户向机器人发送消息（文本/图片/文件/富文本） | 命令识别或注入到 Claude Code 终端 |
| `card.action.trigger` | 用户点击交互卡片按钮（继续 / 📎文件 / 打断） | 解析 `action.value`，执行对应操作 |

Bridge 可处理的消息类型：

| message_type | Bridge 动作 |
|--------------|-------------|
| `text` | 命令识别 or 注入 Claude |
| `post`（富文本） | 展开纯文本后注入 Claude |
| `image` | 下载 → 保存 → 让 Claude 读取 |
| `file` | 下载 → 保存 → 让 Claude 读取 |

---

### ⑤ 自定义菜单

路径：**应用详情 › 功能 › 机器人 › 自定义菜单**

每个菜单项类型选**「发送消息」**，发送内容填写菜单名本身（含 emoji），Bridge 收到后精确匹配。

| 层级 | 菜单名 | 发送内容（精确填写） |
|------|--------|---------------------|
| 顶级菜单 1 | 📸 截图 | `📸 截图` |
| 顶级菜单 2 | 📂 文件 | `📂 文件` |
| 顶级菜单 3 | 🛠️ 更多 | （父级，点击展开子菜单，不发送消息） |
| └ 子菜单 1 | 📜 历史 | `📜 历史` |
| └ 子菜单 2 | 🗑️ 清屏 | `🗑️ 清屏` |
| └ 子菜单 3 | ⏸ 暂停通知 | `⏸ 暂停通知` |
| └ 子菜单 4 | ▶ 恢复通知 | `▶ 恢复通知` |

> 「发送内容」必须与表格中的字符串完全一致（含 emoji 和空格）。飞书不同客户端可能附加 emoji 变体选择符（U+FE0F），Bridge 代码已做兼容处理。

各菜单项执行的动作：

| 菜单名 | Bridge 执行动作 |
|--------|----------------|
| 📸 截图 | 截取 cc-bridge-wrapper 窗口，发送至飞书 |
| 📂 文件 | 列出本次会话 Claude 修改/生成的文件，支持数字选择上传 |
| 📜 历史 | 读取 transcript JSONL，展示最近 5 轮对话摘要 |
| 🗑️ 清屏 | 向 Claude Code 注入 `/clear` 命令 |
| ⏸ 暂停通知 | 关闭工具调用推送 |
| ▶ 恢复通知 | 重新开启工具调用推送 |

---

### ⑥ 发布应用版本

路径：**应用详情 › 版本管理与发布 › 创建版本**

1. 点击「创建版本」，填写版本号（如 1.0.0）和更新说明
2. 点击「申请发布」。企业内部自建应用通常直接生效，无需管理员审批
3. 在飞书内搜索应用名称，发起与机器人的单聊

---

### ⑦ 获取用户 open_id

**方法（推荐）：从日志读取**

1. 先在飞书里给机器人发一条任意文字（如「你好」）
2. Bridge 控制台会打印：
   ```
   [long_conn] sender open_id=ou_xxxxxxxxxxxxxxxxxxxx type=text content=...
   ```
3. 复制其中的 `open_id` 值，填入 `.env` 文件

---

### ⑧ 本地 .env 配置

```bash
# bridge/.env  (从 bridge/.env.example 复制)
FEISHU_APP_ID=cli_xxxxxxxxxxxxxxxxxxxxxx
FEISHU_APP_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
FEISHU_USER_OPEN_ID=ou_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

| 配置项 | 来源 | 格式 |
|--------|------|------|
| `FEISHU_APP_ID` | 凭证与基础信息页面 | `cli_` 开头 |
| `FEISHU_APP_SECRET` | 凭证与基础信息页面（点击「查看」） | 32 位随机字符串 |
| `FEISHU_USER_OPEN_ID` | 步骤 ⑦ 获取 | `ou_` 开头 |

> `.env` 已在 `.gitignore` 中排除，**不要提交到 git 仓库**。

---

### Claude Code Hooks 配置

将 `.claude/settings.json` 中的 hooks 配置复制到你的项目 `.claude/settings.json`，或直接使用本仓库根目录作为 Claude Code 的工作目录。

### 启动

```powershell
# 终端 1：启动 wrapper（ConPTY 伪终端，托管 Claude Code）
powershell -File scripts\launch_claude_wrapper.ps1

# 终端 2：启动 bridge（FastAPI + 飞书长连接）
bash scripts/launch_bridge.sh
```

启动后飞书会收到一张「🚀 CC Relay 已连接」卡片，点击按钮即可开始使用。

## 命令速查

| 命令 | 别名 | 说明 |
|------|------|------|
| `/snap` | `📸 截图` | 截取当前 Claude 窗口发飞书 |
| `/history` | `📜 历史` | 显示当前会话摘要 |
| `/files` | `📂 文件` | 列出本次会话改动的文件 |
| `/pause` | `⏸ 暂停通知` | 暂停工具调用通知 |
| `/resume` | `▶ 恢复通知` | 恢复工具调用通知 |
| `/clear` | `🗑 清屏` | 清除 Claude 上下文 |

## 项目结构

```
cc-relay/
├── bridge/          # FastAPI 服务 + 飞书客户端
│   ├── main.py      # 入口
│   ├── server.py    # Hook 端点
│   ├── feishu.py    # 飞书 API 封装
│   ├── long_conn.py # 飞书长连接消息处理
│   └── ...
├── hooks/
│   └── post_hook.py # Claude Code hook 脚本（所有事件统一入口）
├── wrapper/
│   └── wrapper.py   # ConPTY wrapper，托管 claude.exe
├── scripts/         # 启动脚本
└── .claude/
    └── settings.json # Claude Code hooks 配置
```

## License

MIT · 作者 jachel.lyu

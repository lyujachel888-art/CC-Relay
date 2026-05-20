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

## 配置

### 1. 飞书应用

在[飞书开放平台](https://open.feishu.cn/app)创建自建应用，开通以下权限：

| 权限 | 用途 |
|------|------|
| `im:message` | 发送/接收消息 |
| `im:message:send_multi_msgs` | 批量发消息 |
| `im:resource` | 上传/下载图片文件 |

订阅事件：`im.message.receive_v1`、`card.action.trigger`

启用**长连接**（Websocket）接收模式。

### 2. 环境变量

```bash
# bridge/.env  (从 .env.example 复制)
FEISHU_APP_ID=cli_xxxxxxxxxxxxx
FEISHU_APP_SECRET=xxxxxxxxxxxxxxxxxxx
FEISHU_USER_OPEN_ID=ou_xxxxxxxxxxxxxxxxxxx   # 启动后给机器人发一条消息即可获取
```

### 3. Claude Code Hooks

将 `.claude/settings.json` 中的 hooks 配置复制到你的项目 `.claude/settings.json`，或直接使用本仓库根目录作为 Claude Code 的工作目录。

### 4. 启动

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

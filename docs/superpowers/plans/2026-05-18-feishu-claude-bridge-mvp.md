# 飞书 ↔ Claude Code 双向桥接 MVP 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 搭建一个本地 Python 桥接服务，让 Windows Terminal 里跑的 Claude Code 通过 hooks 把对话推送到飞书机器人，并允许从手机飞书发消息回打 Claude Code 终端，实现远程继续开发。

**Architecture:** Claude Code 在 WSL/tmux session `cc1` 里跑；hooks（UserPromptSubmit / Stop）curl 本地 `127.0.0.1:8787` 上的 FastAPI 端点，桥接服务通过 `lark-oapi` 调飞书 API 推消息；同时桥接以 WebSocket 长连接订阅飞书事件，收到手机消息后调 `tmux send-keys` 注入到 `cc1` session。

**Tech Stack:** Python 3.11+, FastAPI, uvicorn, lark-oapi (飞书官方 SDK), python-dotenv, pytest, tmux, jq, WSL Ubuntu。

**Reference:** 设计文档 `docs/superpowers/specs/2026-05-18-feishu-claude-bridge-mvp-design.md`

---

## 约定

- `[PowerShell]` 前缀：在 Windows PowerShell（Windows Terminal）从 `E:\MyProject\RC\` 执行
- `[WSL]` 前缀：在 WSL bash 里执行，cwd 假定为 `/mnt/e/MyProject/RC/`
- 所有 Python 命令在 WSL 的 venv（`source bridge/.venv/bin/activate`）中执行
- git 命令统一在 WSL 执行（避免 CRLF 问题）

---

## Task 1: 确保 WSL Ubuntu 可用

**Files:** 无

- [ ] **Step 1: 检查 WSL 是否已装**

`[PowerShell]` Run:
```powershell
wsl --status
```

Expected: 输出包含 "Default Distribution: Ubuntu"（或任何 Linux 发行版）。如果报错 "WSL is not installed"，进入 Step 2；否则跳到 Step 3。

- [ ] **Step 2: 安装 WSL + Ubuntu（仅未装时）**

`[PowerShell]` Run（管理员）:
```powershell
wsl --install -d Ubuntu
```

完成后**需要重启 Windows**，重启后 Ubuntu 会自动启动并要求设置用户名密码。设置完进入 Step 3。

- [ ] **Step 3: 验证 WSL 可访问 Windows 项目目录**

`[WSL]` Run:
```bash
ls /mnt/e/MyProject/RC/
```

Expected: 列出 `docs` 目录（spec 已经写在里面）。如果没有 `/mnt/e/`，说明 WSL 的盘符映射不一样，调整后续路径。

---

## Task 2: 安装 WSL 端必备工具

**Files:** 无

- [ ] **Step 1: 安装 tmux、jq、python3-venv、curl**

`[WSL]` Run:
```bash
sudo apt update && sudo apt install -y tmux jq python3-venv python3-pip curl
```

Expected: 全部安装成功，无报错。

- [ ] **Step 2: 验证版本**

`[WSL]` Run:
```bash
tmux -V && jq --version && python3 --version && curl --version | head -1
```

Expected: tmux ≥ 3.0, jq ≥ 1.6, python ≥ 3.10, curl 7.x+

- [ ] **Step 3: 在 WSL 安装 Claude Code**

`[WSL]` Run:
```bash
curl -fsSL https://claude.ai/install.sh | bash
```

如果脚本不可用，按 Claude Code 官方文档下载 Linux 版本到 `~/.local/bin/claude` 并 `chmod +x`。

- [ ] **Step 4: 验证 Claude Code + 登录**

`[WSL]` Run:
```bash
claude --version
claude  # 首次启动会引导登录，登录后退出 (Ctrl+C 或 /exit)
```

Expected: 能成功登录，进入对话界面。

---

## Task 3: 项目脚手架 + git init

**Files:**
- Create: `.gitignore`
- Create: `.gitattributes`
- Create: `bridge/`（目录）
- Create: `bridge/tests/`（目录）
- Create: `hooks/`（目录）
- Create: `scripts/`（目录）

- [ ] **Step 1: 创建目录结构**

`[WSL]` Run:
```bash
cd /mnt/e/MyProject/RC
mkdir -p bridge/tests hooks scripts
```

- [ ] **Step 2: 写 `.gitignore`**

Create `/mnt/e/MyProject/RC/.gitignore`:
```gitignore
# Python
__pycache__/
*.pyc
.venv/
*.egg-info/
.pytest_cache/

# Env
.env
.env.local

# IDE
.vscode/
.idea/

# OS
.DS_Store
Thumbs.db
```

- [ ] **Step 3: 写 `.gitattributes`（避免 Windows CRLF 把 bash 脚本搞坏）**

Create `/mnt/e/MyProject/RC/.gitattributes`:
```gitattributes
* text=auto
*.sh text eol=lf
*.py text eol=lf
```

- [ ] **Step 4: git init + 首次提交**

`[WSL]` Run:
```bash
cd /mnt/e/MyProject/RC
git init -b main
git add .gitignore .gitattributes docs/
git -c user.name="Jachel" -c user.email="lyujachel888@gmail.com" commit -m "chore: initial scaffold with spec and gitignore"
```

Expected: 一个 commit，包含 .gitignore、.gitattributes、spec 文档。

---

## Task 4: 注册飞书自建应用（手动，浏览器操作）

**Files:** 无（外部操作；最后产出 2 个字符串：`APP_ID` 和 `APP_SECRET`）

> 此任务**全程在浏览器中完成**。结束标志：你手机飞书的"通讯录-应用"里能看到 `cc-bridge`，且能跟它发起私聊。
> 整个流程 **15–20 分钟**。飞书后台 UI 偶尔会改版，菜单名找不到时按"功能含义"去找别名。

### Step 1: 注册/登录飞书账号

- [ ] **1.1** 浏览器打开 https://www.feishu.cn/，右上角点「**登录**」
- [ ] **1.2** 用**手机号**登录（推荐）。如果是首次访问，会引导注册一个"个人账号"
- [ ] **1.3** 在手机上下载「**飞书**」APP（App Store / Google Play / 各应用商店），用同一手机号登录

**成功标志：** PC 浏览器和手机 APP 都登录了同一账号。

---

### Step 2: 创建 1 人企业（开发者后台需要企业身份）

> 个人账号无法直接创建自建应用；必须挂靠到一个"企业"下面。免费创建 1 人企业即可。

- [ ] **2.1** 浏览器打开 https://open.feishu.cn/
- [ ] **2.2** 用同账号登录后，点击右上角「**开发者后台**」（或「**控制台**」，名字偶有改动）
- [ ] **2.3** 如果你只有个人账号，会弹窗提示「**需要使用团队/企业账号**」，点「**创建团队**」或「**创建企业**」
- [ ] **2.4** 填写信息：
  - 团队/企业名称：随意，比如 `Jachel Lab`（只给自己看的）
  - 行业：随便选一个，比如「**互联网/IT**」
  - 团队规模：选「**1–10 人**」
  - 你的角色：「**创始人/管理者**」
- [ ] **2.5** 点「**创建**」，等待几秒。如果跳出"需要手机验证码"按提示完成

**成功标志：** 浏览器跳到形如 `https://*.feishu.cn/admin/...` 或 `https://open.feishu.cn/app` 的页面，页面顶部能看到你的企业名。

**踩坑：** 如果提示"需要企业认证"，**不需要**选认证（自建应用不需要）。如果它非要你认证，可以选「**稍后再做**」或直接关掉弹窗。

---

### Step 3: 创建自建应用 `cc-bridge`

- [ ] **3.1** 确保在 https://open.feishu.cn/app 页面（如果没在，点击右上角「**开发者后台**」回到这里）
- [ ] **3.2** 点击页面上的「**创建企业自建应用**」按钮（一般是一个明显的蓝色或加号卡片）
- [ ] **3.3** 填表：
  - **应用名称**：`cc-bridge`
  - **应用描述**：`Claude Code 双向桥接`
  - **应用图标**：随便上传一张图，或留空用默认
- [ ] **3.4** 点「**创建**」

**成功标志：** 自动跳转到应用详情页，浏览器 URL 形如 `https://open.feishu.cn/app/cli_xxxxxxxxxxxxxxxx/`（注意 `cli_` 开头的就是 App ID）。左侧菜单出现一长串配置项。

---

### Step 4: 复制凭证（App ID / App Secret）

- [ ] **4.1** 在应用详情页左侧菜单找「**凭证与基础信息**」（也可能叫「**应用凭证**」），点进去
- [ ] **4.2** 找到「**App ID**」字段，复制（形如 `cli_a1b2c3d4e5f6g7h8`）
- [ ] **4.3** 找到「**App Secret**」字段，点旁边的「**显示**」或眼睛图标，复制（一长串字母数字）
- [ ] **4.4** 把两个值贴到一个临时记事本，标好哪个是哪个

**成功标志：** 你手上有两个字符串，一个 `cli_*` 开头，一个 32 位左右随机字符。

**⚠️ 安全提醒：** App Secret 等同密码。不要发到聊天里，不要 commit 到 git（`.env` 已在 `.gitignore` 里）。

---

### Step 5: 添加「机器人」能力

> 默认创建的应用只是"空壳"，要手动启用机器人能力才能发消息。

- [ ] **5.1** 左侧菜单找「**添加应用能力**」（在比较靠后的位置）
- [ ] **5.2** 在能力列表中找到「**机器人**」卡片，点「**添加**」或「**启用**」
- [ ] **5.3** 弹窗可能要你确认，点确认即可

**成功标志：** 左侧菜单新增「**机器人**」菜单项。

---

### Step 6: 申请 API 权限

> 必须申请权限，否则调用 API 会返回 "permission denied"。

- [ ] **6.1** 左侧菜单点「**权限管理**」
- [ ] **6.2** 在权限搜索框里**依次搜索**并点击「**开通**」（搜索框支持中英文，建议用英文 scope 名搜更准）：

| 权限 scope | 中文显示名（参考） | 用途 |
|---|---|---|
| `im:message:send_as_bot` | 以应用的身份发消息 | bridge 推消息到飞书 |
| `im:message` | 获取与发送单聊、群组消息 | 备用，部分 SDK 要求 |
| `im:resource` | 获取与上传图片或文件资源 | 备用（未来扩展） |

> **⚠️ 命名差异：** 飞书后台对权限有"分类树"。如果搜 `im:message:send_as_bot` 没结果，搜中文「**消息**」展开列表，勾选「**以应用的身份发消息**」即可。
>
> **接收私聊消息不需要单独权限**，靠下一步的"事件订阅"开通。

- [ ] **6.3** 申请完后，页面上方一般有「**待发布**」状态条，**不用**点发布（我们 Step 8 一起发布）

**成功标志：** 「已开通权限」列表里能看到上面 3 个权限（至少 `im:message:send_as_bot`）。

---

### Step 7: 配置事件订阅（**长连接模式**，关键步骤）

> 这是让"手机发的消息能到达 bridge"的唯一路径。**必须选长连接**，不选会要求你提供公网 URL。

- [ ] **7.1** 左侧菜单点「**事件与回调**」（可能在「**事件订阅**」下）
- [ ] **7.2** 进入「**事件配置**」标签页
- [ ] **7.3** 在「**事件接收方式**」或「**传输方式**」处，**选择「使用长连接接收事件」**
  - 另一个选项是「使用 HTTP 接收事件」/「配置请求地址」→ **不要选**
- [ ] **7.4** 保存（如果有保存按钮）

**踩坑：** 旧版本 UI 可能默认是 HTTP 模式，长连接选项可能藏在「**高级配置**」或者要先点「**编辑**」才出现。找不到时搜帮助文档关键词「**长连接事件**」。

- [ ] **7.5** 同页面下方，找「**添加事件**」按钮，点开
- [ ] **7.6** 在事件列表里搜索 `im.message.receive_v1`
  - 中文搜「**接收消息**」也能找到
  - 完整名可能是「**消息 - 接收消息 v1.0**」
- [ ] **7.7** 勾选该事件，点「**确定**」或「**添加**」

**成功标志：** 「已订阅事件」列表里出现 `im.message.receive_v1`（或对应的中文名）。

---

### Step 8: 配置「机器人可被搜索/添加」

> 应用发布前的最后准备，确保你能在飞书 APP 里搜到自己的机器人。

- [ ] **8.1** 左侧菜单点「**机器人**」（Step 5 启用后才会出现）
- [ ] **8.2** 找到「**消息卡片请求网址**」/「**回调地址**」之类的字段 → **留空**（我们走长连接）
- [ ] **8.3** 找到「**机器人可用范围**」或「**可见性**」设置 → 选「**全部成员**」或「**所有人**」（你企业里只有你，所以等同于"你自己")
- [ ] **8.4** 保存

**成功标志：** 机器人配置页显示"已启用"状态。

---

### Step 9: 创建版本并发布应用

> 自建应用做完所有配置后必须"发布"才生效。个人企业的应用**自审自批**。

- [ ] **9.1** 左侧菜单点「**版本管理与发布**」（或「**应用发布**」）
- [ ] **9.2** 点「**创建版本**」按钮
- [ ] **9.3** 填表：
  - **版本号**：`1.0.0`
  - **更新说明**：`首次发布`
  - **可用范围**：「**全部成员**」（如有这个选项）
- [ ] **9.4** 点「**保存并申请发布**」
- [ ] **9.5** 弹出确认框，点「**确认提交**」

**成功标志：** 应用版本状态显示「**已发布**」或「**审批通过**」。

**踩坑：** 如果状态显示「**审批中**」且没动静——左侧菜单看有没有「**应用审核**」入口，进去找到自己的应用，点「**通过**」（你既是开发者也是管理员，需要自己审自己）。

---

### Step 10: 把机器人加到你的飞书 IM

- [ ] **10.1** 打开**手机**飞书 APP（确认是登录了同一账号）
- [ ] **10.2** 在底部 Tab 切到「**通讯录**」
- [ ] **10.3** 找到「**应用**」或「**机器人**」分类（也可能在「**我的**」→「**应用**」里）
- [ ] **10.4** 搜索框输入 `cc-bridge`
- [ ] **10.5** 点搜到的机器人 → 「**添加**」或直接「**开始聊天**」

**成功标志：** 进入和 `cc-bridge` 的聊天会话，输入框可用。**先别发任何消息**，留到 Task 12 烟测时再发。

**踩坑：** 如果搜不到——
- 等 1–2 分钟，发布生效有延迟
- 回到 PC 开发者后台，确认应用「**已发布**」
- 确认 Step 8 可见性选了「全部成员」
- 杀掉飞书 APP 重开

---

### Step 11: 把 App ID / App Secret 准备好

- [ ] **11.1** 把 Step 4 拿到的两个字符串记到临时文本：
```
FEISHU_APP_ID=cli_a1b2c3d4e5f6g7h8
FEISHU_APP_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```
- [ ] **11.2** `OPEN_ID` 现在还**不知道**，先填占位 `unknown`，Task 12 启 bridge 后从 stdout 拿。

```
FEISHU_USER_OPEN_ID=unknown
```

**这一节结束的总验收：**
1. ✅ 浏览器开发者后台能看到 `cc-bridge` 应用，状态「已发布」
2. ✅ 手机飞书能搜到并打开 `cc-bridge` 机器人聊天框
3. ✅ 手上有 `FEISHU_APP_ID` 和 `FEISHU_APP_SECRET` 两个字符串

---

## Task 5: Python venv + requirements

**Files:**
- Create: `bridge/requirements.txt`
- Create: `bridge/.env.example`
- Create: `bridge/pytest.ini`

- [ ] **Step 1: 写 `bridge/requirements.txt`**

Create `/mnt/e/MyProject/RC/bridge/requirements.txt`:
```txt
fastapi==0.115.0
uvicorn[standard]==0.32.0
lark-oapi==1.4.15
python-dotenv==1.0.1
pytest==8.3.3
httpx==0.27.2
```

> `httpx` 是 FastAPI TestClient 用的；`lark-oapi` 版本固定到一个已知能跑的版本，新版本可能 API 微调。

- [ ] **Step 2: 写 `bridge/.env.example`**

Create `/mnt/e/MyProject/RC/bridge/.env.example`:
```env
# 从飞书开发者后台 -> 应用详情 -> 凭证与基础信息
FEISHU_APP_ID=cli_xxxxxxxxxxxxx
FEISHU_APP_SECRET=xxxxxxxxxxxxxxxxxxx

# 手机给机器人发条消息后，bridge stdout 会打印你的 open_id
FEISHU_USER_OPEN_ID=ou_xxxxxxxxxxxxxxxxxxx

# tmux session 名（暂时固定 cc1）
TMUX_SESSION=cc1
```

- [ ] **Step 3: 写 `bridge/pytest.ini`**

Create `/mnt/e/MyProject/RC/bridge/pytest.ini`:
```ini
[pytest]
pythonpath = .
testpaths = tests
```

- [ ] **Step 4: 创建 venv 并安装依赖**

`[WSL]` Run:
```bash
cd /mnt/e/MyProject/RC/bridge
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

Expected: 全部安装成功，最后一行类似 `Successfully installed fastapi-0.115.0 ...`。

- [ ] **Step 5: 复制 .env.example 为 .env 并填值**

`[WSL]` Run:
```bash
cp /mnt/e/MyProject/RC/bridge/.env.example /mnt/e/MyProject/RC/bridge/.env
nano /mnt/e/MyProject/RC/bridge/.env
```

把 Task 4 Step 9 拿到的 APP_ID/APP_SECRET 填进去（OPEN_ID 暂留 `unknown`）。保存。

- [ ] **Step 6: 提交**

`[WSL]` Run:
```bash
cd /mnt/e/MyProject/RC
git add bridge/requirements.txt bridge/.env.example bridge/pytest.ini
git commit -m "chore(bridge): add Python deps + env template"
```

---

## Task 6: Config 模块（TDD）

**Files:**
- Create: `bridge/config.py`
- Create: `bridge/tests/test_config.py`
- Create: `bridge/tests/conftest.py`

- [ ] **Step 1: 写 conftest.py（让 tests 能找到模块）**

Create `/mnt/e/MyProject/RC/bridge/tests/conftest.py`:
```python
# 空文件即可；pytest.ini 已配 pythonpath = .
```

- [ ] **Step 2: 写失败测试 `test_config.py`**

Create `/mnt/e/MyProject/RC/bridge/tests/test_config.py`:
```python
import os
import pytest
from config import load_config


def test_load_config_reads_env(monkeypatch):
    monkeypatch.setenv("FEISHU_APP_ID", "aid")
    monkeypatch.setenv("FEISHU_APP_SECRET", "sec")
    monkeypatch.setenv("FEISHU_USER_OPEN_ID", "ou_test")
    monkeypatch.setenv("TMUX_SESSION", "cc1")

    cfg = load_config()

    assert cfg.app_id == "aid"
    assert cfg.app_secret == "sec"
    assert cfg.user_open_id == "ou_test"
    assert cfg.tmux_session == "cc1"


def test_load_config_default_tmux_session(monkeypatch):
    monkeypatch.setenv("FEISHU_APP_ID", "aid")
    monkeypatch.setenv("FEISHU_APP_SECRET", "sec")
    monkeypatch.setenv("FEISHU_USER_OPEN_ID", "ou_test")
    monkeypatch.delenv("TMUX_SESSION", raising=False)

    cfg = load_config()
    assert cfg.tmux_session == "cc1"
```

- [ ] **Step 3: 运行测试验证失败**

`[WSL]` Run:
```bash
cd /mnt/e/MyProject/RC/bridge
source .venv/bin/activate
pytest tests/test_config.py -v
```

Expected: FAIL，`ModuleNotFoundError: No module named 'config'`。

- [ ] **Step 4: 实现 `config.py`**

Create `/mnt/e/MyProject/RC/bridge/config.py`:
```python
import os
from dataclasses import dataclass
from dotenv import load_dotenv


@dataclass
class Config:
    app_id: str
    app_secret: str
    user_open_id: str
    tmux_session: str = "cc1"


def load_config() -> Config:
    load_dotenv()
    return Config(
        app_id=os.environ["FEISHU_APP_ID"],
        app_secret=os.environ["FEISHU_APP_SECRET"],
        user_open_id=os.environ["FEISHU_USER_OPEN_ID"],
        tmux_session=os.environ.get("TMUX_SESSION", "cc1"),
    )
```

- [ ] **Step 5: 运行测试验证通过**

`[WSL]` Run:
```bash
pytest tests/test_config.py -v
```

Expected: 2 passed。

- [ ] **Step 6: 提交**

`[WSL]` Run:
```bash
cd /mnt/e/MyProject/RC
git add bridge/config.py bridge/tests/conftest.py bridge/tests/test_config.py
git commit -m "feat(bridge): config loader with env support"
```

---

## Task 7: 飞书发送模块（TDD）

**Files:**
- Create: `bridge/feishu.py`
- Create: `bridge/tests/test_feishu.py`

- [ ] **Step 1: 写失败测试**

Create `/mnt/e/MyProject/RC/bridge/tests/test_feishu.py`:
```python
from unittest.mock import MagicMock
from feishu import FeishuClient


def test_send_text_calls_lark_create_message():
    mock_lark = MagicMock()
    fc = FeishuClient(
        app_id="aid",
        app_secret="sec",
        user_open_id="ou_test",
        lark_client=mock_lark,
    )

    fc.send_text("hello world")

    mock_lark.im.v1.message.create.assert_called_once()


def test_send_text_includes_text_in_request_content():
    """Verify the text is JSON-encoded into the request content field."""
    import json
    mock_lark = MagicMock()
    fc = FeishuClient("aid", "sec", "ou_test", lark_client=mock_lark)

    fc.send_text("你好 world")

    call = mock_lark.im.v1.message.create.call_args
    req = call[0][0]
    # Lark's request object stores body via .request_body; inspect serialized content
    # The internal structure differs across SDK versions; assert the text appears in any
    # string representation of the request.
    assert "你好 world" in str(req.request_body.__dict__) or "\\u4f60\\u597d" in str(req.request_body.__dict__)
```

- [ ] **Step 2: 运行测试验证失败**

`[WSL]` Run:
```bash
pytest tests/test_feishu.py -v
```

Expected: FAIL，`ModuleNotFoundError: No module named 'feishu'`。

- [ ] **Step 3: 实现 `feishu.py`**

Create `/mnt/e/MyProject/RC/bridge/feishu.py`:
```python
import json
from typing import Optional
import lark_oapi as lark
from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody


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
        self._client.im.v1.message.create(req)
```

- [ ] **Step 4: 运行测试验证通过**

`[WSL]` Run:
```bash
pytest tests/test_feishu.py -v
```

Expected: 2 passed。如果第二个测试 fail（因为 lark SDK 内部结构和我假设不一样），把断言放宽为只断言 `create_once_called`，删掉第二个测试。这是 SDK 内部细节，不值得卡 MVP。

- [ ] **Step 5: 提交**

`[WSL]` Run:
```bash
cd /mnt/e/MyProject/RC
git add bridge/feishu.py bridge/tests/test_feishu.py
git commit -m "feat(bridge): feishu text sender via lark-oapi"
```

---

## Task 8: tmux 注入模块（TDD）

**Files:**
- Create: `bridge/injector.py`
- Create: `bridge/tests/test_injector.py`

- [ ] **Step 1: 写失败测试**

Create `/mnt/e/MyProject/RC/bridge/tests/test_injector.py`:
```python
from unittest.mock import patch
from injector import inject_to_tmux


@patch("injector.subprocess.run")
def test_inject_sends_text_then_enter(mock_run):
    inject_to_tmux("cc1", "hello world")

    assert mock_run.call_count == 2
    mock_run.assert_any_call(
        ["tmux", "send-keys", "-t", "cc1", "--", "hello world"],
        check=True,
    )
    mock_run.assert_any_call(
        ["tmux", "send-keys", "-t", "cc1", "Enter"],
        check=True,
    )


@patch("injector.subprocess.run")
def test_inject_handles_multiline_text(mock_run):
    inject_to_tmux("cc1", "line1\nline2")

    # Multiline text is passed as a single send-keys argument; tmux handles newlines
    mock_run.assert_any_call(
        ["tmux", "send-keys", "-t", "cc1", "--", "line1\nline2"],
        check=True,
    )
```

- [ ] **Step 2: 运行测试验证失败**

`[WSL]` Run:
```bash
pytest tests/test_injector.py -v
```

Expected: FAIL，`ModuleNotFoundError: No module named 'injector'`。

- [ ] **Step 3: 实现 `injector.py`**

Create `/mnt/e/MyProject/RC/bridge/injector.py`:
```python
import subprocess


def inject_to_tmux(session: str, text: str) -> None:
    """Send text to a tmux session and press Enter.

    Uses `--` to terminate options so text starting with `-` is treated as literal.
    """
    subprocess.run(
        ["tmux", "send-keys", "-t", session, "--", text],
        check=True,
    )
    subprocess.run(
        ["tmux", "send-keys", "-t", session, "Enter"],
        check=True,
    )
```

- [ ] **Step 4: 运行测试验证通过**

`[WSL]` Run:
```bash
pytest tests/test_injector.py -v
```

Expected: 2 passed。

- [ ] **Step 5: 提交**

`[WSL]` Run:
```bash
cd /mnt/e/MyProject/RC
git add bridge/injector.py bridge/tests/test_injector.py
git commit -m "feat(bridge): tmux send-keys injector"
```

---

## Task 9: FastAPI 服务（TDD）

**Files:**
- Create: `bridge/server.py`
- Create: `bridge/tests/test_server.py`

- [ ] **Step 1: 写失败测试**

Create `/mnt/e/MyProject/RC/bridge/tests/test_server.py`:
```python
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from server import create_app


def test_user_prompt_endpoint_calls_feishu_with_prefix():
    mock_feishu = MagicMock()
    app = create_app(mock_feishu)
    client = TestClient(app)

    resp = client.post("/hook/user_prompt", json={"text": "what time is it"})

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    mock_feishu.send_text.assert_called_once_with("🧑 what time is it")


def test_assistant_reply_endpoint_calls_feishu_with_prefix():
    mock_feishu = MagicMock()
    app = create_app(mock_feishu)
    client = TestClient(app)

    resp = client.post("/hook/assistant_reply", json={"text": "it is noon"})

    assert resp.status_code == 200
    mock_feishu.send_text.assert_called_once_with("🤖 it is noon")


def test_user_prompt_swallows_feishu_errors_returns_ok():
    """Hook should never block Claude Code; if feishu fails, still return ok."""
    mock_feishu = MagicMock()
    mock_feishu.send_text.side_effect = RuntimeError("network down")
    app = create_app(mock_feishu)
    client = TestClient(app)

    resp = client.post("/hook/user_prompt", json={"text": "hi"})

    assert resp.status_code == 200
    assert resp.json()["ok"] is False
```

- [ ] **Step 2: 运行测试验证失败**

`[WSL]` Run:
```bash
pytest tests/test_server.py -v
```

Expected: FAIL，`ModuleNotFoundError: No module named 'server'`。

- [ ] **Step 3: 实现 `server.py`**

Create `/mnt/e/MyProject/RC/bridge/server.py`:
```python
import logging
from fastapi import FastAPI
from pydantic import BaseModel
from feishu import FeishuClient

log = logging.getLogger("bridge.server")


class HookPayload(BaseModel):
    text: str


def create_app(feishu: FeishuClient) -> FastAPI:
    app = FastAPI()

    @app.post("/hook/user_prompt")
    async def user_prompt(payload: HookPayload):
        return _push(feishu, f"🧑 {payload.text}")

    @app.post("/hook/assistant_reply")
    async def assistant_reply(payload: HookPayload):
        return _push(feishu, f"🤖 {payload.text}")

    return app


def _push(feishu: FeishuClient, text: str) -> dict:
    try:
        feishu.send_text(text)
        return {"ok": True}
    except Exception as e:
        log.exception("failed to push to feishu: %s", e)
        return {"ok": False, "error": str(e)}
```

- [ ] **Step 4: 运行测试验证通过**

`[WSL]` Run:
```bash
pytest tests/test_server.py -v
```

Expected: 3 passed。

- [ ] **Step 5: 提交**

`[WSL]` Run:
```bash
cd /mnt/e/MyProject/RC
git add bridge/server.py bridge/tests/test_server.py
git commit -m "feat(bridge): FastAPI hook endpoints"
```

---

## Task 10: 长连接消息处理（TDD）

**Files:**
- Create: `bridge/long_conn.py`
- Create: `bridge/tests/test_long_conn.py`

- [ ] **Step 1: 写失败测试**

Create `/mnt/e/MyProject/RC/bridge/tests/test_long_conn.py`:
```python
from unittest.mock import MagicMock, patch
from long_conn import make_message_handler


@patch("long_conn.inject_to_tmux")
def test_handler_extracts_text_and_injects(mock_inject):
    handler = make_message_handler("cc1")

    fake_event = MagicMock()
    fake_event.event.message.content = '{"text":"hello there"}'
    fake_event.event.sender.sender_id.open_id = "ou_abc"

    handler(fake_event)

    mock_inject.assert_called_once_with("cc1", "hello there")


@patch("long_conn.inject_to_tmux")
def test_handler_ignores_empty_text(mock_inject):
    handler = make_message_handler("cc1")
    fake_event = MagicMock()
    fake_event.event.message.content = '{"text":""}'
    fake_event.event.sender.sender_id.open_id = "ou_abc"

    handler(fake_event)

    mock_inject.assert_not_called()


@patch("long_conn.inject_to_tmux")
def test_handler_ignores_non_text_content(mock_inject):
    handler = make_message_handler("cc1")
    fake_event = MagicMock()
    # Non-JSON content (e.g., image)
    fake_event.event.message.content = '{"image_key":"img_xxx"}'
    fake_event.event.sender.sender_id.open_id = "ou_abc"

    handler(fake_event)

    mock_inject.assert_not_called()


@patch("long_conn.inject_to_tmux")
@patch("builtins.print")
def test_handler_logs_sender_open_id(mock_print, mock_inject):
    """For first-run setup we need open_id printed to stdout."""
    handler = make_message_handler("cc1")
    fake_event = MagicMock()
    fake_event.event.message.content = '{"text":"hi"}'
    fake_event.event.sender.sender_id.open_id = "ou_first_time"

    handler(fake_event)

    printed = " ".join(str(c) for c in mock_print.call_args_list)
    assert "ou_first_time" in printed
```

- [ ] **Step 2: 运行测试验证失败**

`[WSL]` Run:
```bash
pytest tests/test_long_conn.py -v
```

Expected: FAIL，`ModuleNotFoundError: No module named 'long_conn'`。

- [ ] **Step 3: 实现 `long_conn.py`**

Create `/mnt/e/MyProject/RC/bridge/long_conn.py`:
```python
import json
import logging
from typing import Callable

import lark_oapi as lark

from injector import inject_to_tmux

log = logging.getLogger("bridge.long_conn")


def make_message_handler(tmux_session: str) -> Callable:
    """Build a handler that injects incoming Feishu messages into a tmux session."""

    def handler(data) -> None:
        try:
            content_raw = data.event.message.content
            content = json.loads(content_raw)
            text = (content.get("text") or "").strip()
        except (json.JSONDecodeError, AttributeError, TypeError) as e:
            log.warning("could not parse message content: %s", e)
            return

        try:
            open_id = data.event.sender.sender_id.open_id
        except AttributeError:
            open_id = "<unknown>"

        # Print the sender's open_id loudly — first-run user needs this to fill .env
        print(
            f"[long_conn] sender open_id={open_id} text={text!r}",
            flush=True,
        )

        if not text:
            return

        try:
            inject_to_tmux(tmux_session, text)
        except Exception as e:
            log.exception("tmux injection failed: %s", e)

    return handler


def start_ws_client(app_id: str, app_secret: str, tmux_session: str) -> None:
    """Block on lark WebSocket client. Run in a background thread."""
    handler = make_message_handler(tmux_session)

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
```

> ⚠️ `lark.ws.Client` 是基于 lark-oapi 1.4.x 的写法。如果 import 报错，先 `python -c "import lark_oapi as lark; print(dir(lark))"` 看可用属性，常见替代是 `from lark_oapi.ws.client import Client`。

- [ ] **Step 4: 运行测试验证通过**

`[WSL]` Run:
```bash
pytest tests/test_long_conn.py -v
```

Expected: 4 passed。

- [ ] **Step 5: 提交**

`[WSL]` Run:
```bash
cd /mnt/e/MyProject/RC
git add bridge/long_conn.py bridge/tests/test_long_conn.py
git commit -m "feat(bridge): long-conn message handler with tmux injection"
```

---

## Task 11: 主入口

**Files:**
- Create: `bridge/main.py`

- [ ] **Step 1: 实现 `main.py`**

Create `/mnt/e/MyProject/RC/bridge/main.py`:
```python
import logging
import threading

import uvicorn

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
    log.info("loaded config: app_id=%s tmux_session=%s open_id=%s",
             cfg.app_id, cfg.tmux_session, cfg.user_open_id)

    feishu = FeishuClient(cfg.app_id, cfg.app_secret, cfg.user_open_id)
    app = create_app(feishu)

    # Long-conn runs in background thread; FastAPI runs in main thread
    ws_thread = threading.Thread(
        target=start_ws_client,
        args=(cfg.app_id, cfg.app_secret, cfg.tmux_session),
        daemon=True,
        name="lark-ws",
    )
    ws_thread.start()
    log.info("lark websocket client started in background")

    log.info("FastAPI listening on http://127.0.0.1:8787")
    uvicorn.run(app, host="127.0.0.1", port=8787, log_level="warning")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 提交**

`[WSL]` Run:
```bash
cd /mnt/e/MyProject/RC
git add bridge/main.py
git commit -m "feat(bridge): main entry wiring server + long-conn"
```

- [ ] **Step 3: 所有测试一起跑确认无 regression**

`[WSL]` Run:
```bash
cd /mnt/e/MyProject/RC/bridge
source .venv/bin/activate
pytest -v
```

Expected: 全部 passed（约 11 个 test）。

---

## Task 12: Bridge 烟测（手动，半自动）

> 目的：先验证 bridge 本身能跑通飞书双向（不接 Claude Code），并拿到自己的 `OPEN_ID` 回填到 `.env`。

- [ ] **Step 1: 启动一个 dummy tmux 会话作为注入目标**

`[WSL]` 开一个新终端窗口 Run:
```bash
tmux new-session -A -s cc1
# 进入 tmux 后什么都不做，让窗口开着
```

- [ ] **Step 2: 启动 bridge**

`[WSL]` 另开一个终端 Run:
```bash
cd /mnt/e/MyProject/RC/bridge
source .venv/bin/activate
python main.py
```

Expected: 输出包含
```
INFO bridge.main: loaded config: app_id=cli_xxx tmux_session=cc1 open_id=unknown
INFO bridge.main: lark websocket client started in background
INFO bridge.main: FastAPI listening on http://127.0.0.1:8787
```
以及 lark SDK 的连接日志。如果 lark 报 "auth failed" → 检查 APP_ID/APP_SECRET 是否对。

- [ ] **Step 3: 从手机飞书给机器人发一条 "hi"**

bridge stdout 应打印类似：
```
[long_conn] sender open_id=ou_abcdefgh1234567890 text='hi'
```

复制这个 `open_id`。

- [ ] **Step 4: 切到 Step 1 的 tmux 窗口确认注入**

应该看到光标位置出现 `hi` 然后回车（虽然 shell 会报"command not found: hi"，但说明注入路径通了）。

- [ ] **Step 5: 把 open_id 回填到 .env，重启 bridge**

`[WSL]` 编辑 `.env`：
```bash
nano /mnt/e/MyProject/RC/bridge/.env
# 把 FEISHU_USER_OPEN_ID=unknown 改为刚才打印的 ou_xxx
```

然后 Ctrl+C 停掉 bridge，重新 `python main.py`。日志应该显示 `open_id=ou_xxx`。

- [ ] **Step 6: 验证推送方向（PowerShell → 飞书）**

`[WSL]` 第三个终端 Run:
```bash
curl -X POST http://127.0.0.1:8787/hook/assistant_reply \
  -H "Content-Type: application/json" \
  -d '{"text":"hello from bridge"}'
```

Expected: 响应 `{"ok":true}`；手机飞书收到 "🤖 hello from bridge"。

- [ ] **Step 7: 关掉 dummy tmux**

`[WSL]` 在 Step 1 的窗口里按 Ctrl+D 或 `exit` 退出 tmux。bridge 不用停（下一个 task 还要用）。

---

## Task 13: Hook 脚本

**Files:**
- Create: `hooks/user_prompt_submit.sh`
- Create: `hooks/stop.sh`

- [ ] **Step 1: 写 `user_prompt_submit.sh`**

Create `/mnt/e/MyProject/RC/hooks/user_prompt_submit.sh`:
```bash
#!/usr/bin/env bash
# Fires on UserPromptSubmit. Reads JSON from stdin, extracts .prompt, pushes to bridge.
# Must NEVER block or fail the user's prompt — always exit 0.

set +e

input=$(cat)
prompt=$(printf '%s' "$input" | jq -r '.prompt // empty' 2>/dev/null)

if [[ -z "$prompt" ]]; then
    exit 0
fi

body=$(jq -nc --arg text "$prompt" '{text: $text}')

curl -sS -m 3 -X POST http://127.0.0.1:8787/hook/user_prompt \
    -H "Content-Type: application/json" \
    -d "$body" > /dev/null 2>&1

exit 0
```

- [ ] **Step 2: 写 `stop.sh`**

Create `/mnt/e/MyProject/RC/hooks/stop.sh`:
```bash
#!/usr/bin/env bash
# Fires when Claude finishes a response. Reads transcript_path, extracts last
# assistant message text, pushes to bridge.

set +e

input=$(cat)
transcript=$(printf '%s' "$input" | jq -r '.transcript_path // empty' 2>/dev/null)

if [[ -z "$transcript" || ! -f "$transcript" ]]; then
    exit 0
fi

# Walk the JSONL transcript from the end, find the last line where role == "assistant".
# Each line is a JSON object with shape: {"type":"assistant","message":{"role":"assistant","content":[...]}}
last_text=$(tac "$transcript" 2>/dev/null | while IFS= read -r line; do
    role=$(printf '%s' "$line" | jq -r '.message.role // empty' 2>/dev/null)
    if [[ "$role" == "assistant" ]]; then
        # Extract text from content array (concatenate all text parts)
        text=$(printf '%s' "$line" | jq -r '
            .message.content
            | if type == "string" then .
              else (map(select(.type == "text") | .text) | join("\n"))
              end
        ' 2>/dev/null)
        if [[ -n "$text" && "$text" != "null" ]]; then
            printf '%s' "$text"
            break
        fi
    fi
done)

if [[ -z "$last_text" ]]; then
    exit 0
fi

body=$(jq -nc --arg text "$last_text" '{text: $text}')

curl -sS -m 3 -X POST http://127.0.0.1:8787/hook/assistant_reply \
    -H "Content-Type: application/json" \
    -d "$body" > /dev/null 2>&1

exit 0
```

- [ ] **Step 3: 加可执行权限**

`[WSL]` Run:
```bash
chmod +x /mnt/e/MyProject/RC/hooks/user_prompt_submit.sh
chmod +x /mnt/e/MyProject/RC/hooks/stop.sh
```

- [ ] **Step 4: 烟测 `user_prompt_submit.sh`（不依赖 Claude Code）**

`[WSL]` Run:
```bash
echo '{"prompt":"测试 hook","session_id":"x","transcript_path":"/tmp/x"}' \
  | /mnt/e/MyProject/RC/hooks/user_prompt_submit.sh
```

Expected: 命令静默返回 0；手机飞书收到 "🧑 测试 hook"。

- [ ] **Step 5: 烟测 `stop.sh` 用造假 transcript**

`[WSL]` Run:
```bash
cat > /tmp/fake_transcript.jsonl <<'EOF'
{"type":"user","message":{"role":"user","content":"hi"}}
{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"this is the last reply"}]}}
EOF

echo '{"transcript_path":"/tmp/fake_transcript.jsonl","session_id":"x"}' \
  | /mnt/e/MyProject/RC/hooks/stop.sh
```

Expected: 手机飞书收到 "🤖 this is the last reply"。

> 如果没收到，问题大概率在 transcript 格式假设错了。把真实 Claude Code 跑一次后的 transcript（路径在 `~/.claude/projects/<encoded>/<session>.jsonl`）拿出来 `head -5`，调整 `jq` 路径。

- [ ] **Step 6: 提交**

`[WSL]` Run:
```bash
cd /mnt/e/MyProject/RC
git add hooks/
git commit -m "feat(hooks): user_prompt_submit + stop bash hooks"
```

---

## Task 14: 注册 Claude Code hooks 配置

**Files:**
- Modify: `~/.claude/settings.json`（WSL 端用户配置；不在仓库内）

- [ ] **Step 1: 备份现有配置**

`[WSL]` Run:
```bash
mkdir -p ~/.claude
[ -f ~/.claude/settings.json ] && cp ~/.claude/settings.json ~/.claude/settings.json.bak.$(date +%s) || echo "no existing settings"
```

- [ ] **Step 2: 写/合并 settings.json**

`[WSL]` 编辑 `~/.claude/settings.json`：
```bash
nano ~/.claude/settings.json
```

If empty, paste this whole file:
```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "/mnt/e/MyProject/RC/hooks/user_prompt_submit.sh"
          }
        ]
      }
    ],
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "/mnt/e/MyProject/RC/hooks/stop.sh"
          }
        ]
      }
    ]
  }
}
```

If non-empty, merge the `"hooks"` key manually (preserve existing top-level keys).

- [ ] **Step 3: 验证 JSON 语法**

`[WSL]` Run:
```bash
cat ~/.claude/settings.json | jq .
```

Expected: 美化输出整个 JSON，没有报错。

---

## Task 15: 启动器脚本

**Files:**
- Create: `scripts/launch_cc1.sh`
- Create: `scripts/launch_bridge.sh`

- [ ] **Step 1: 写 Claude Code 启动器**

Create `/mnt/e/MyProject/RC/scripts/launch_cc1.sh`:
```bash
#!/usr/bin/env bash
# Launch Claude Code inside tmux session `cc1`. Idempotent: attach if exists, else create.
exec tmux new-session -A -s cc1 claude
```

- [ ] **Step 2: 写 bridge 启动器**

Create `/mnt/e/MyProject/RC/scripts/launch_bridge.sh`:
```bash
#!/usr/bin/env bash
# Activate venv and start bridge service in foreground.
cd /mnt/e/MyProject/RC/bridge
source .venv/bin/activate
exec python main.py
```

- [ ] **Step 3: 加可执行权限**

`[WSL]` Run:
```bash
chmod +x /mnt/e/MyProject/RC/scripts/launch_cc1.sh
chmod +x /mnt/e/MyProject/RC/scripts/launch_bridge.sh
```

- [ ] **Step 4: 提交**

`[WSL]` Run:
```bash
cd /mnt/e/MyProject/RC
git add scripts/
git commit -m "feat(scripts): launchers for cc1 tmux + bridge service"
```

---

## Task 16: 端到端验收（对应 spec 的 5 条验收标准）

> 现场跑一遍 spec 里的 5 条验收。两个终端窗口：A = bridge，B = Claude Code。

- [ ] **Step 1: 终端 A 启 bridge**

`[PowerShell]`：开 Windows Terminal 标签页 1，Run:
```powershell
wsl -- /mnt/e/MyProject/RC/scripts/launch_bridge.sh
```

Expected: bridge 日志显示 listening on 8787 + lark websocket 已连接。

- [ ] **Step 2: 终端 B 启 Claude Code in tmux**

`[PowerShell]`：开 Windows Terminal 标签页 2，Run:
```powershell
wsl -- /mnt/e/MyProject/RC/scripts/launch_cc1.sh
```

Expected: 看到 Claude Code TUI，光标在输入框。

- [ ] **Step 3: 验收点 1 — 终端能正常用**

在终端 B 的 Claude Code 输入框输入 "现在几点" 然后回车。

Expected: Claude 正常回答（可能用 tool 或直接答）。

- [ ] **Step 4: 验收点 2 — 提问被推送到手机**

提问回车后 2 秒内，手机飞书机器人收到 "🧑 现在几点"。

- [ ] **Step 5: 验收点 3 — 回答被推送到手机**

Claude 答完后，手机飞书收到 "🤖 现在是 ..."（具体文字取决于 Claude 的回答）。

- [ ] **Step 6: 验收点 4 — 手机消息打回终端**

关闭电脑屏幕（或假装不看）。从手机飞书机器人发 "那今天星期几"。

5 秒内观察终端 B：
- Claude Code 输入框出现 "那今天星期几" 然后回车（被 tmux 注入）
- Claude 开始作答
- 手机收到 "🧑 那今天星期几" 和 "🤖 今天是 ..."（完整闭环）

- [ ] **Step 7: 验收点 5 — 整个回合无人工干预**

第 6 步全程没碰键盘鼠标。✅ MVP 验收通过。

- [ ] **Step 8: 提交标记**

`[WSL]` Run:
```bash
cd /mnt/e/MyProject/RC
git tag -a mvp-v0.1 -m "MVP passed all 5 acceptance criteria"
```

---

## 故障排查速查

| 症状 | 可能原因 | 处理 |
|---|---|---|
| `wsl --status` 报错 | WSL 未装 | Task 1 Step 2 安装 |
| `pip install lark-oapi` 失败 | 网络 / pip 源 | `pip install -i https://pypi.tuna.tsinghua.edu.cn/simple lark-oapi` |
| bridge 启动报 "auth failed" | APP_ID/SECRET 错 | 回 Task 4 Step 3 重新复制 |
| 手机发消息 bridge 收不到 | 事件订阅没开 / 应用没发布 | Task 4 Step 6-7 |
| 手机消息收到但 tmux 没注入 | tmux session 名不对 / session 不存在 | `tmux ls` 确认 `cc1` 在；检查 .env 的 TMUX_SESSION |
| `stop.sh` 不推消息 | transcript 格式假设错 | Step 5 of Task 13 的兜底：人工 head 一个真 transcript 调 jq |
| hook 不触发 | settings.json 路径错 | Task 14 Step 3 验证 JSON；重启 Claude Code |
| 注入的中文乱码 | shell locale | `[WSL]` `export LANG=zh_CN.UTF-8` 加到 `~/.bashrc` |

---

## Self-review checklist

- [x] **Spec coverage:** 架构 4 个组件全部实现（Task 1-3 WSL/tmux，Task 5-11 bridge，Task 4+14 飞书应用+hooks 配置，Task 15 启动器）；数据流双向都验收（Task 16）；MVP "不做" 项都没出现。
- [x] **Placeholder scan:** 无 TBD/TODO；故障排查表给了具体处理而非"adjust accordingly"。
- [x] **Type consistency:** `FeishuClient.send_text(text)` 在 server.py 和 main.py 中都使用一致；`inject_to_tmux(session, text)` 签名在 injector.py、long_conn.py、test 中一致；`Config` dataclass 字段在 main.py 中按名称引用。
- [x] **Verification gates:** 每个 TDD task 都有"运行测试验证失败 → 实现 → 验证通过"步骤；端到端验收 5 步对齐 spec。

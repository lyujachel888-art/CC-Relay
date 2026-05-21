# 动态岛 HUD — 多 CC Session 桌面状态浮窗设计

**状态**: 设计完成，待实施
**日期**: 2026-05-21
**作者**: Jachel + Claude
**前置文档**:
- [2026-05-18 飞书 ↔ Claude Code MVP](./2026-05-18-feishu-claude-bridge-mvp-design.md)
- [2026-05-21 Bridge 多租户路由架构](./2026-05-21-bridge-multi-tenant-design.md)

---

## 1. 摘要

在 Windows 桌面上做一个**类苹果灵动岛风格的浮窗 HUD**，实时展示当前所有 Claude Code session 的运行状态。每个 session 一行，行内显示一只对应状态的拟物小猫（焦点猫 + 历史轨迹），点击行可直接聚焦该 CC 终端窗口。

技术栈选定 **Tauri + React + TypeScript**：WebView2 引擎下 CSS 动画顺滑，资源占用极低（~15MB RAM），与现有 Python bridge 完全解耦。

---

## 2. 目标与非目标

### 2.1 目标

- 一个浮窗同时观察 N 个 CC session 的运行状态，扫一眼可读
- 即使没盯着终端也能感知"哪个 session 在工作 / 出错 / 完成 / 空闲"
- 任务完成后能点开看 recap 摘要，点击行能跳回对应终端
- 界面有趣（拟物动态小猫），但不抢占工作注意力

### 2.2 非目标

- 不是消息中心：不接收/回复消息（飞书 bridge 已经做了）
- 不是日志查看器：不展示完整 tool output
- 不取代终端：只是状态指示器，不能在 HUD 里输入

---

## 3. 整体架构

```
                     CC hooks (UserPrompt / Stop / PreToolUse / PostToolUse / Notification)
                                       │
                                       ▼
                            ┌──────────────────────┐
                            │  hooks/post_hook.py  │
                            └──────────┬───────────┘
                                       │  POST /hook/{type}  (UTF-8 JSON)
                                       ▼
                  ┌──────────────────────────────────────────┐
                  │            bridge/server.py              │
                  │                                          │
                  │   现有 /hook/* 路由  ─────►  飞书推送      │
                  │                                          │
                  │   ★ 新增 GET /events  ──── SSE 广播       │
                  └──────────────────────────────────────────┘
                                       │
                              text/event-stream
                                       │
                                       ▼
                  ┌──────────────────────────────────────────┐
                  │   Tauri 进程 (frameless transparent)     │
                  │                                          │
                  │   React + TS                             │
                  │     • useSSE() hook 订阅事件              │
                  │     • Zustand store 维护 Session Map      │
                  │     • SessionRow / FocusCat / Trail 组件  │
                  │                                          │
                  │   Rust side                              │
                  │     • 窗口管理 (always-on-top / drag)     │
                  │     • focus_terminal(project_name)       │
                  │       → FindWindowW + SetForegroundWindow│
                  │     • 位置持久化 (tauri-plugin-store)     │
                  └──────────────────────────────────────────┘
                                       │
                                  点击行时
                                       ▼
                  Windows Terminal: "cc-bridge-wrapper-{project}"
```

**核心数据流**：CC 触发 hook → post_hook.py POST 给 bridge → bridge SSE 广播 → Tauri 前端实时更新对应 session 行的状态。

---

## 4. 视觉设计

### 4.1 整体形态

- **形状**：圆角矩形浮窗，毛玻璃背景（`rgba(12,12,22,.93)` + `backdrop-filter: blur(20px)`）
- **位置**：可拖动，记住上次位置（用户首次启动落在屏幕右上角）
- **行数**：每个活跃 session 一行，N 行纵向堆叠，宽度固定 460px

### 4.2 单行布局

```
┌─[●] [RC]  🐱(焦点猫)  · · ▪ ▪ ▪  12s ─┐
   │   │      │           │           │
   │   │      │           │           └─ 时间标签（自最近事件起的相对时间）
   │   │      │           └────────── 历史轨迹（5 个圆点，左小右大，最右=当前）
   │   │      └────────────────────── 焦点猫（当前状态的动态拟物图）
   │   └───────────────────────────── 项目标签（CWD basename）
   └───────────────────────────────── 状态圆点（脉冲 = 活跃，静止 = 完成/空闲）
```

### 4.3 状态系统

简化为 **4 个核心状态**，避免认知过载：

| 状态 | 触发事件 | 焦点猫 | 动画 | 颜色 |
|---|---|---|---|---|
| **working** | `tool_use` / `user_prompt` | 奔跑/工作猫 | stroll 漫步（2-4px 微起伏） | 按子类型：Bash=靛 / 文件=紫 / 搜索=青 |
| **done** | `assistant_reply` / `task_completed` | 满足举爪猫 | 仅呼吸（4s 周期） | 绿 / 金 |
| **error** | `bash_result fail` | 炸毛惊恐猫 | 炸毛脉冲（fur-pulse） | **红 + 整行红色背景脉冲** |
| **idle** | 无事件 >30s | 打盹猫 | 仅呼吸（4s 周期）+ z 飘散 | 灰（半透明） |

### 4.4 优先级颜色（CSS 变量）

```css
.p1 { --cm:#EF4444; }  /* CRITICAL · 报错 */
.p2 { --cm:#F97316; }  /* HIGH · 通知 */
.p3 { --cm:#EAB308; }  /* CELEBRATE · 任务完成 */
.p4 { --cm:#10B981; }  /* DONE · 回复完成 */
.p5 { --cm:#6366F1; }  /* ACTIVE · Bash 执行 */
.p6 { --cm:#8B5CF6; }  /* WORKING · 文件操作 */
.p7 { --cm:#06B6D4; }  /* INPUT · 用户输入 */
.p8 { --cm:#6B7280; }  /* IDLE · 空闲 */
```

每个状态用 `--cm` / `--cl`(亮) / `--cd`(暗) / `--cg`(光晕) 4 个变量统一着色，切换状态时 CSS `transition: fill .6s` 平滑渐变。

### 4.5 历史轨迹

5 个圆点按时间从左到右排列，**最右是当前**，越左越小越淡：

```
.tiny(4px,opacity .35) · .small(5px,.55) · .med(6px,.75) · .big(7px,.9) · .now(8px,1.0 + 脉冲)
```

每个圆点用对应事件的颜色变量。idle 状态轨迹用虚线 `─ ─ ─ ─ ─` 替代，明确"什么都没发生"。

### 4.6 动画分级原则

**动画是为传达信息服务的，不是装饰。** 重要状态用强动画，次要状态尽量静止。

| 状态 | 动画强度 | 说明 |
|---|---|---|
| error | ★★★★ | 整行红色脉冲背景 + 炸毛抖动 + 圆点脉冲 |
| working | ★★ | 焦点猫 stroll 漫步（位移 2-4px，scale 1-2%）|
| done | ★ | 仅呼吸（4s 慢周期） |
| idle | ★ | 仅呼吸 + z 飘散 |

漫步动画的缓动统一用 `cubic-bezier(0.37, 0, 0.63, 1)` sine 曲线，**无弹性 overshoot**。

### 4.7 仿生小动作（次要）

- **耳朵延迟摆动**：ear-lag 跟随身体动作慢半拍（Follow-through 原则）
- **尾巴慢摇**：2.2s 周期独立 sway（次要动作 Secondary Action）
- **眨眼**：3.5s 周期，rare 但增加生命感
- **阴影呼吸**：地面阴影宽度/模糊度与身体起伏同步

---

## 5. 数据流与状态管理

### 5.1 SSE 事件格式

bridge 新增的 `/events` 端点广播每个 hook 事件：

```json
{
  "type": "tool_use" | "assistant_reply" | "user_prompt" | "bash_result" | "notification" | "task_created" | "task_completed",
  "project": "RC",
  "text": "Bash: npm run build",
  "meta": "8.2s · 1137tok",
  "ts": 1716278400
}
```

`project` 字段从 hook payload 的 `[project]` 前缀解析（已有逻辑）。

### 5.2 前端 Session 状态

```ts
type CatState = "working" | "done" | "error" | "idle"

interface SessionState {
  project: string             // "RC"
  color: Priority             // p1-p8 之一，决定 CSS 变量
  state: CatState             // 决定显示哪只焦点猫
  history: HistoryDot[]       // 最近 5 个事件的 {color, ts}
  recap: string | null        // 最后一次 assistant_reply 的全文（recap 展开用）
  recapOpen: boolean
  lastEventAt: number         // 用于计算时间标签和 idle 检测
}

// 全局: Map<project, SessionState>
```

事件 → 状态的映射规则：

| event.type | event.meta | → state | → color |
|---|---|---|---|
| `tool_use`（text 以 `Bash:` 开头）| - | working | p5 |
| `tool_use`（text 以 `Read/Write/Edit` 开头）| - | working | p6 |
| `tool_use`（text 以 `Glob/Grep/WebSearch/WebFetch` 开头）| - | working | p7 |
| `assistant_reply` | - | done | p4 |
| `task_completed` | - | done | p3 |
| `user_prompt` | - | working | p7 |
| `bash_result` | `meta=="fail"` | **error** | p1 |
| `bash_result` | `meta=="ok"` | working | p5 |
| `notification` | - | error | p2 |

每收到一个事件：
1. 更新对应 session 的 `state` + `color`
2. `history.push({color, ts: now})`，超过 5 个截断头部
3. `lastEventAt = now`
4. 若是 `assistant_reply`，存到 `recap`

### 5.3 idle 检测

前端 setInterval 每 1s 检查所有 session，若 `now - lastEventAt > 30000` 则切到 `idle` 状态。

### 5.4 时间标签格式

```ts
function timeAgo(ts: number): string {
  const sec = (Date.now() - ts) / 1000
  if (sec < 60)  return `${Math.floor(sec)}s`
  if (sec < 3600) return `${Math.floor(sec / 60)}m`
  return `${Math.floor(sec / 3600)}h`
}
```

每 1s 刷新一次时间标签。

---

## 6. 与现有项目的集成点

### 6.1 bridge/server.py 改动

**新增**：`GET /events` SSE 端点

```python
from asyncio import Queue
from typing import List

_subscribers: List[Queue] = []

async def _broadcast(event: dict) -> None:
    for q in _subscribers:
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass  # 慢消费者不影响其他

@app.get("/events")
async def sse_stream():
    q: Queue = Queue(maxsize=100)
    _subscribers.append(q)
    async def gen():
        try:
            while True:
                event = await q.get()
                yield f"data: {json.dumps(event)}\n\n"
        finally:
            _subscribers.remove(q)
    return StreamingResponse(gen(), media_type="text/event-stream")
```

**改动**：每个 `/hook/*` 路由在处理完后调用 `_broadcast({...})` 把事件推到 SSE 队列。

### 6.2 wrapper/wrapper.py 改动

**仅 1 行**：把固定标题改成带项目后缀。

```python
# wrapper.py:57 原: CONSOLE_TITLE = "cc-bridge-wrapper"
_project = os.environ.get("CC_SESSION") or Path(os.getcwd()).name
CONSOLE_TITLE = f"cc-bridge-wrapper-{_project}" if _project else "cc-bridge-wrapper"
```

CWD 自动推导与 `post_hook.py:64` 已有的 `project_prefix` 完全一致，保证 HUD 看到的 `[RC]` 和窗口标题 `cc-bridge-wrapper-RC` 名字对得上。

### 6.3 hooks/post_hook.py

**无需改动**。现有的 `[project]` 前缀机制已经满足 HUD 识别 session 的需求。

---

## 7. Tauri 项目结构

```
island/
├── src-tauri/
│   ├── Cargo.toml
│   ├── tauri.conf.json          # 窗口: frameless + transparent + alwaysOnTop
│   └── src/
│       ├── main.rs              # tauri::Builder, 注册 commands
│       └── focus.rs             # focus_terminal(project) → Win32 API
├── src/
│   ├── main.tsx
│   ├── App.tsx                  # 根: drag handler + session list rendering
│   ├── components/
│   │   ├── SessionRow.tsx       # 单行: dot + tag + cat + trail + time
│   │   ├── FocusCat.tsx         # 焦点猫 (按 state 选 SVG + 动画)
│   │   ├── HistoryTrail.tsx     # 5 圆点轨迹
│   │   ├── RecapPanel.tsx       # 展开的 recap 面板
│   │   └── cats/                # 各状态的 SVG 子组件
│   │       ├── CatWorking.tsx
│   │       ├── CatDone.tsx
│   │       ├── CatError.tsx
│   │       └── CatIdle.tsx
│   ├── hooks/
│   │   ├── useSSE.ts            # 订阅 bridge /events
│   │   └── useDrag.ts           # 窗口拖动
│   ├── store/
│   │   └── sessions.ts          # Zustand store
│   ├── lib/
│   │   ├── event-mapper.ts      # event → SessionState 更新逻辑
│   │   └── colors.ts            # p1-p8 颜色映射
│   └── styles/
│       └── animations.css       # @keyframes 集合（stroll, shadow, fur-pulse...）
└── package.json
```

### 7.1 Rust 端 focus_terminal command

```rust
#[tauri::command]
fn focus_terminal(project: String) -> Result<(), String> {
    use windows::Win32::UI::WindowsAndMessaging::{FindWindowW, SetForegroundWindow};
    use windows::core::PCWSTR;

    let title = format!("cc-bridge-wrapper-{}", project);
    let wide: Vec<u16> = title.encode_utf16().chain(Some(0)).collect();
    unsafe {
        let hwnd = FindWindowW(PCWSTR::null(), PCWSTR(wide.as_ptr()));
        if hwnd.0 == 0 {
            return Err(format!("Window not found: {}", title));
        }
        SetForegroundWindow(hwnd);
    }
    Ok(())
}
```

### 7.2 tauri.conf.json 关键配置

```json
{
  "tauri": {
    "windows": [{
      "decorations": false,
      "transparent": true,
      "alwaysOnTop": true,
      "skipTaskbar": true,
      "width": 460,
      "height": 200,
      "resizable": false,
      "fileDropEnabled": false
    }],
    "allowlist": {
      "window": { "all": true },
      "http": { "all": true, "scope": ["http://127.0.0.1:8787/*"] }
    }
  }
}
```

---

## 8. 交互细节

| 操作 | 行为 |
|---|---|
| 拖动浮窗任意位置 | 移动窗口，松开时持久化位置（tauri-plugin-store） |
| 鼠标悬停某行 | 行背景轻微高亮（rgba(255,255,255,.04)） |
| **单击行** | 调用 Rust `focus_terminal(project)`，激活对应 Windows Terminal |
| **右键行 / 长按** | 展开 RecapPanel，显示最后一次 assistant_reply 的 markdown 摘要 |
| 浮窗右键空白处 | 系统菜单：退出 / 设置 / 关于 |
| 系统托盘图标 | 单击切换显示/隐藏 |

---

## 9. 实施分阶段

**Phase 1 — 数据通路（最小可见）**
1. bridge/server.py 加 `/events` SSE 端点
2. wrapper.py 的 1 行 title 改动
3. 一个最简单的 HTML 页面订阅 SSE 验证事件流通

**Phase 2 — Tauri 骨架**
1. `npm create tauri-app@latest island` 生成项目
2. 配置 frameless transparent window
3. 拖动逻辑 + 位置持久化
4. focus_terminal Rust command

**Phase 3 — UI 实现**
1. 4 个状态的猫 SVG 组件（working / done / error / idle）
2. SessionRow 组件 + 状态映射
3. HistoryTrail + time tag
4. error 状态的整行脉冲

**Phase 4 — 打磨**
1. 漫步动画 + 仿生小动作
2. RecapPanel 展开
3. 系统托盘 + 开机自启

---

## 10. 风险与未决项

| 风险 | 影响 | 缓解 |
|---|---|---|
| WebView2 透明窗口在某些 Win11 版本有渲染 bug | 视觉异常 | 提供 fallback 不透明背景模式 |
| SSE 在 bridge 重启时断连 | HUD 显示陈旧数据 | 前端 EventSource 自动重连 + 重连后请求一次 `/state` 全量 |
| 多 wrapper 同名（CWD 同名）冲突 | 点击聚焦到错的窗口 | 用 `CC_SESSION` env var 强制区分 |
| 长时间运行 history 内存增长 | 慢慢吃内存 | 每 session 限制 5 个历史点，无限增长不存在 |

**未决项**：
- 是否需要把 HUD 也对接现有 `push_state.is_tool_use_paused()` 的暂停开关？
- 多显示器时记忆位置的策略（绝对坐标还是相对显示器）？

---

## 11. 验收标准

- [ ] 在同一台 Windows 同时启动 3 个 CC session（不同项目目录），HUD 浮窗能正确显示 3 行
- [ ] 任一 session 触发 hook 后，对应行在 1s 内更新焦点猫和历史轨迹
- [ ] 点击 RC 行能聚焦 RC 的 Windows Terminal 窗口
- [ ] 模拟 bash 报错（exit code 1）时，对应行**整行红色脉冲**生效
- [ ] 30 秒无事件时自动切到 idle 灰色虚线轨迹
- [ ] HUD 拖动后位置在重启后恢复
- [ ] CPU 占用 < 1%（idle）/ < 3%（多个 session 活跃时）
- [ ] 内存占用 < 30MB

---

**下一步**：进入 writing-plans 阶段，把上述 4 个 Phase 拆成可执行任务。

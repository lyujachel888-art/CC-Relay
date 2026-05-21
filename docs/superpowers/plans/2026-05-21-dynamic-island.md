# Dynamic Island HUD Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Windows desktop floating HUD that visualizes the runtime status of every active Claude Code session as an animated "focus cat + history trail" row.

**Architecture:**
- **Backend:** add an SSE `/events` endpoint to the existing FastAPI bridge that fan-outs every hook event to subscribed clients; tweak `wrapper.py` to give each Windows Terminal a CWD-derived title.
- **Frontend:** a brand-new Tauri 2 app (`island/`) renders a frameless transparent always-on-top window using React + TypeScript. A Zustand store reduces incoming SSE events into a `Map<project, SessionState>`; the UI shows one row per session with an animated SVG cat and a 5-dot color history.
- **Cross-process click:** clicking a row calls a Rust `focus_terminal(project)` command that resolves `cc-bridge-wrapper-{project}` via `FindWindowW` + `SetForegroundWindow`.

**Tech Stack:** FastAPI · sse-starlette · pytest · Tauri 2 · React 18 · TypeScript · Zustand · Vitest · windows-rs

**Spec:** [`docs/superpowers/specs/2026-05-21-dynamic-island-design.md`](../specs/2026-05-21-dynamic-island-design.md)

---

## File Structure

**Backend changes (existing repo)**
- Modify: `bridge/server.py` — add `EventBroadcaster`, `GET /events`, wire `_broadcast()` into every hook route
- Modify: `bridge/requirements.txt` — add `sse-starlette`
- Modify: `bridge/tests/test_server.py` — extend existing TestClient suite with SSE tests
- Modify: `wrapper/wrapper.py:57` — derive `CONSOLE_TITLE` from CWD

**Tauri project (new at repo root)**
- `island/package.json`, `island/vite.config.ts`, `island/tsconfig.json` — scaffolded by `create-tauri-app`
- `island/src-tauri/Cargo.toml`, `island/src-tauri/tauri.conf.json` — window config
- `island/src-tauri/src/main.rs` — Tauri app entry, command registration
- `island/src-tauri/src/focus.rs` — Win32 `focus_terminal` command
- `island/src/main.tsx` — React root
- `island/src/App.tsx` — root component, draggable container, session list
- `island/src/components/SessionRow.tsx` — single row layout
- `island/src/components/FocusCat.tsx` — cat dispatcher (state → SVG)
- `island/src/components/HistoryTrail.tsx` — 5-dot trail
- `island/src/components/RecapPanel.tsx` — expandable recap panel
- `island/src/components/cats/{Working,Done,Error,Idle}.tsx` — 4 animated SVG cats
- `island/src/hooks/useSSE.ts` — EventSource subscription
- `island/src/store/sessions.ts` — Zustand store
- `island/src/store/sessions.test.ts` — unit tests for reducer
- `island/src/lib/event-mapper.ts` — pure mapping `event → SessionState` delta
- `island/src/lib/event-mapper.test.ts` — unit tests for mapper
- `island/src/lib/colors.ts` — p1-p8 priority → color variable name
- `island/src/styles/animations.css` — `@keyframes stroll, fur-pulse, breathe, row-error-pulse, ...`

---

## Phase 1 — Backend Data Pipeline

### Task 1: Add `EventBroadcaster` core (test-driven)

**Files:**
- Create: `bridge/event_broadcast.py`
- Create: `bridge/tests/test_event_broadcast.py`

- [ ] **Step 1: Write failing tests**

`bridge/tests/test_event_broadcast.py`:
```python
import asyncio
import pytest
from event_broadcast import EventBroadcaster


@pytest.mark.asyncio
async def test_subscribe_returns_queue_that_receives_published_events():
    bc = EventBroadcaster()
    q = bc.subscribe()

    await bc.publish({"type": "tool_use", "project": "RC", "text": "Bash: ls"})
    event = await asyncio.wait_for(q.get(), timeout=0.5)

    assert event == {"type": "tool_use", "project": "RC", "text": "Bash: ls"}


@pytest.mark.asyncio
async def test_publish_fanouts_to_all_subscribers():
    bc = EventBroadcaster()
    q1, q2 = bc.subscribe(), bc.subscribe()

    await bc.publish({"type": "stop", "project": "Bot"})

    assert (await asyncio.wait_for(q1.get(), timeout=0.5))["project"] == "Bot"
    assert (await asyncio.wait_for(q2.get(), timeout=0.5))["project"] == "Bot"


@pytest.mark.asyncio
async def test_unsubscribe_stops_delivery_to_that_queue():
    bc = EventBroadcaster()
    q1, q2 = bc.subscribe(), bc.subscribe()
    bc.unsubscribe(q1)

    await bc.publish({"type": "stop"})

    assert q1.empty()
    assert not q2.empty()


@pytest.mark.asyncio
async def test_slow_subscriber_drops_events_instead_of_blocking_publisher():
    """A subscriber that never reads must not block publish() for others."""
    bc = EventBroadcaster(maxsize=2)
    slow = bc.subscribe()
    fast = bc.subscribe()

    for i in range(10):
        await bc.publish({"i": i})

    # fast subscriber gets first 2 events, then drops kick in
    assert fast.qsize() == 2
    # slow subscriber: full queue, dropped excess
    assert slow.qsize() == 2
```

- [ ] **Step 2: Run tests — expect ImportError**

```bash
cd bridge && pytest tests/test_event_broadcast.py -v
```
Expected: `ModuleNotFoundError: No module named 'event_broadcast'`

- [ ] **Step 3: Implement minimal `EventBroadcaster`**

`bridge/event_broadcast.py`:
```python
"""Async fan-out of hook events to SSE subscribers.

Slow subscribers drop events (bounded queue) rather than blocking the
publisher. This keeps a stuck HUD client from stalling the bridge.
"""
import asyncio
import logging
from typing import Any, Dict, List

log = logging.getLogger("bridge.event_broadcast")


class EventBroadcaster:
    def __init__(self, maxsize: int = 100) -> None:
        self._maxsize = maxsize
        self._subscribers: List[asyncio.Queue] = []

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=self._maxsize)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        try:
            self._subscribers.remove(q)
        except ValueError:
            pass

    async def publish(self, event: Dict[str, Any]) -> None:
        for q in list(self._subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                log.debug("dropped event for slow subscriber: %s", event.get("type"))
```

- [ ] **Step 4: Install pytest-asyncio if missing**

```bash
cd bridge && pip show pytest-asyncio || pip install pytest-asyncio
```

Add `asyncio_mode = auto` under `[pytest]` in `bridge/pytest.ini` if not already present (verify by reading the file first).

- [ ] **Step 5: Re-run tests — expect PASS**

```bash
cd bridge && pytest tests/test_event_broadcast.py -v
```
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add bridge/event_broadcast.py bridge/tests/test_event_broadcast.py bridge/pytest.ini
git commit -m "feat(bridge): EventBroadcaster — async fan-out with slow-subscriber drop"
```

---

### Task 2: Add `GET /events` SSE endpoint

**Files:**
- Modify: `bridge/server.py`
- Modify: `bridge/tests/test_server.py`
- Modify: `bridge/requirements.txt`

- [ ] **Step 1: Add dependency**

Append to `bridge/requirements.txt`:
```
sse-starlette
```

Install:
```bash
cd bridge && pip install sse-starlette
```

- [ ] **Step 2: Write failing test**

Append to `bridge/tests/test_server.py`:
```python
def test_events_endpoint_streams_published_events():
    from event_broadcast import EventBroadcaster

    mock_feishu = MagicMock()
    bc = EventBroadcaster()
    app = create_app(mock_feishu, expected_token="TOKEN", broadcaster=bc)
    client = TestClient(app)

    # publish one event before connecting; SSE only emits future events,
    # so we connect first then publish via a thread
    import threading, time, asyncio

    def publish_later():
        time.sleep(0.1)
        loop = asyncio.new_event_loop()
        loop.run_until_complete(bc.publish({"type": "tool_use", "project": "RC", "text": "ls"}))
        loop.close()

    threading.Thread(target=publish_later, daemon=True).start()

    with client.stream("GET", "/events") as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        # read first non-empty SSE frame
        for chunk in resp.iter_lines():
            if chunk.startswith("data: "):
                import json
                payload = json.loads(chunk[len("data: "):])
                assert payload == {"type": "tool_use", "project": "RC", "text": "ls"}
                break
```

- [ ] **Step 3: Run — expect FAIL**

```bash
cd bridge && pytest tests/test_server.py::test_events_endpoint_streams_published_events -v
```
Expected: `TypeError: create_app() got an unexpected keyword argument 'broadcaster'`

- [ ] **Step 4: Modify `create_app` to accept broadcaster + add `/events` route**

In `bridge/server.py`:

Add imports at top:
```python
import json
from sse_starlette.sse import EventSourceResponse
from event_broadcast import EventBroadcaster
```

Change signature (line 29):
```python
def create_app(feishu: FeishuClient, expected_token: str, broadcaster: EventBroadcaster | None = None) -> FastAPI:
    app = FastAPI()
    if broadcaster is None:
        broadcaster = EventBroadcaster()
    app.state.broadcaster = broadcaster
```

Before `return app`, add the route:
```python
    @app.get("/events")
    async def events_stream():
        q = broadcaster.subscribe()
        async def gen():
            try:
                while True:
                    event = await q.get()
                    yield {"data": json.dumps(event, ensure_ascii=False)}
            finally:
                broadcaster.unsubscribe(q)
        return EventSourceResponse(gen())
```

- [ ] **Step 5: Re-run — expect PASS**

```bash
cd bridge && pytest tests/test_server.py::test_events_endpoint_streams_published_events -v
```
Expected: 1 passed

- [ ] **Step 6: Commit**

```bash
git add bridge/server.py bridge/tests/test_server.py bridge/requirements.txt
git commit -m "feat(bridge): GET /events SSE endpoint"
```

---

### Task 3: Wire `_broadcast` into every hook route

**Files:**
- Modify: `bridge/server.py`
- Modify: `bridge/tests/test_server.py`

- [ ] **Step 1: Write failing test**

Append to `bridge/tests/test_server.py`:
```python
def test_user_prompt_publishes_to_broadcaster():
    from event_broadcast import EventBroadcaster
    import asyncio

    bc = EventBroadcaster()
    q = bc.subscribe()
    app = create_app(MagicMock(), expected_token="T", broadcaster=bc)
    client = TestClient(app)

    client.post(
        "/hook/user_prompt",
        json={"text": "[RC] do something"},
        headers={"Authorization": "Bearer T"},
    )

    event = asyncio.get_event_loop().run_until_complete(
        asyncio.wait_for(q.get(), timeout=0.5)
    )
    assert event["type"] == "user_prompt"
    assert event["project"] == "RC"
    assert event["text"] == "do something"


def test_bash_result_publishes_with_fail_meta():
    from event_broadcast import EventBroadcaster
    import asyncio

    bc = EventBroadcaster()
    q = bc.subscribe()
    app = create_app(MagicMock(), expected_token="T", broadcaster=bc)
    client = TestClient(app)

    client.post(
        "/hook/bash_result",
        json={"text": "[RC] $ ls\n\nError: not found", "meta": "fail"},
        headers={"Authorization": "Bearer T"},
    )

    event = asyncio.get_event_loop().run_until_complete(
        asyncio.wait_for(q.get(), timeout=0.5)
    )
    assert event["type"] == "bash_result"
    assert event["meta"] == "fail"
```

- [ ] **Step 2: Run — expect FAIL**

```bash
cd bridge && pytest tests/test_server.py -k publishes -v
```

- [ ] **Step 3: Add `_broadcast_event` helper + wire into routes**

In `bridge/server.py`, add this helper near the top of `create_app`:

```python
    async def _broadcast_event(event_type: str, payload: HookPayload) -> None:
        chip, body = _split_prefix(payload.text)
        project = chip.strip("[] ") if chip else ""
        await broadcaster.publish({
            "type": event_type,
            "project": project,
            "text": body,
            "meta": payload.meta,
        })
```

Then in EVERY existing `@app.post("/hook/...")` handler, add `await _broadcast_event("<type>", payload)` as the first line AFTER `_check_auth(authorization)`. The types to use:

| route | event_type |
|---|---|
| `/hook/user_prompt` | `"user_prompt"` |
| `/hook/assistant_reply` | `"assistant_reply"` |
| `/hook/tool_use` | `"tool_use"` |
| `/hook/task` | `"task_created"` if `payload.task_type == "created"` else `"task_completed"` |
| `/hook/notification` | `"notification"` |
| `/hook/bash_result` | `"bash_result"` |
| `/hook/file_touched` | (skip — internal bookkeeping only) |

Example for `user_prompt`:
```python
    @app.post("/hook/user_prompt")
    async def user_prompt(payload: HookPayload, authorization: str = Header(default="")):
        _check_auth(authorization)
        await _broadcast_event("user_prompt", payload)
        # ... existing body unchanged
```

- [ ] **Step 4: Re-run — expect PASS, plus ensure no regression in existing tests**

```bash
cd bridge && pytest -v
```
Expected: all tests pass (existing + 2 new)

- [ ] **Step 5: Commit**

```bash
git add bridge/server.py bridge/tests/test_server.py
git commit -m "feat(bridge): broadcast every hook to /events subscribers"
```

---

### Task 4: Wrapper title carries project name

**Files:**
- Modify: `wrapper/wrapper.py:57`

- [ ] **Step 1: Edit `wrapper/wrapper.py` lines 56-57**

Replace:
```python
# Fixed window title so bridge/screenshot.py can find this console by title.
CONSOLE_TITLE = "cc-bridge-wrapper"
```

With:
```python
# Fixed window title so bridge/screenshot.py and the HUD can find this console.
# Derived from CWD basename to match the [project] prefix that post_hook.py
# adds, so HUD's row `RC` maps directly to window `cc-bridge-wrapper-RC`.
# Override with CC_SESSION env var when CWD basename is ambiguous.
_project = os.environ.get("CC_SESSION") or Path(os.getcwd()).name
CONSOLE_TITLE = f"cc-bridge-wrapper-{_project}" if _project else "cc-bridge-wrapper"
```

- [ ] **Step 2: Manually verify**

```bash
cd "E:/MyProject/RC" && python wrapper/wrapper.py
```
(Don't actually launch Claude — just observe the title via Task Manager → Details → look for `cmd.exe`'s window title, or run `(Get-Process | Where-Object MainWindowTitle -like 'cc-bridge-wrapper-*').MainWindowTitle` in another PowerShell.)

Expected: title is `cc-bridge-wrapper-RC` (since CWD basename is `RC`).

Ctrl+C to exit.

- [ ] **Step 3: Commit**

```bash
git add wrapper/wrapper.py
git commit -m "feat(wrapper): suffix console title with CWD project name"
```

---

## Phase 2 — Tauri Skeleton

### Task 5: Scaffold Tauri project

**Files:**
- Create: `island/` (entire directory tree via scaffolder)

- [ ] **Step 1: Install tauri-cli globally**

```bash
npm install -g @tauri-apps/cli@latest
```

- [ ] **Step 2: Scaffold project**

```bash
cd "E:/MyProject/RC" && npm create tauri-app@latest island -- --template react-ts --manager npm --identifier com.jachel.cc-island
```

Choose:
- App name: `island`
- Window title: `CC Island`
- Frontend: `React - TypeScript`
- Package manager: `npm`

- [ ] **Step 3: Install + initial dev run**

```bash
cd island && npm install && npm run tauri dev
```

Expected: a default Tauri window opens showing the React boilerplate. Close it.

- [ ] **Step 4: Add additional deps**

```bash
cd island && npm install zustand
npm install -D vitest @vitest/ui jsdom @testing-library/react @testing-library/jest-dom
```

- [ ] **Step 5: Configure Vitest**

Create `island/vitest.config.ts`:
```typescript
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: { environment: "jsdom", globals: true, setupFiles: [] },
});
```

Add to `island/package.json` scripts:
```json
"test": "vitest run",
"test:watch": "vitest"
```

- [ ] **Step 6: Commit**

```bash
git add -f island/
git commit -m "feat(island): scaffold Tauri 2 + React + TS project"
```

---

### Task 6: Configure transparent frameless always-on-top window

**Files:**
- Modify: `island/src-tauri/tauri.conf.json`
- Modify: `island/src-tauri/Cargo.toml`
- Create: `island/src/App.tsx` (replace boilerplate)
- Modify: `island/src/main.tsx`
- Create: `island/src/App.css`

- [ ] **Step 1: Edit window config**

In `island/src-tauri/tauri.conf.json`, replace the `windows` array entry with:
```json
{
  "label": "main",
  "title": "CC Island",
  "width": 460,
  "height": 200,
  "decorations": false,
  "transparent": true,
  "alwaysOnTop": true,
  "skipTaskbar": true,
  "resizable": false,
  "shadow": false,
  "fileDropEnabled": false
}
```

- [ ] **Step 2: Replace `island/src/App.tsx`**

```tsx
import "./App.css";

export default function App() {
  return (
    <div className="hud">
      <div className="hud-placeholder">CC Island — frameless transparent skeleton</div>
    </div>
  );
}
```

- [ ] **Step 3: Replace `island/src/App.css`** (delete any existing content)

```css
:root, html, body, #root { background: transparent; margin: 0; padding: 0; }
* { box-sizing: border-box; }

.hud {
  font-family: -apple-system, "Segoe UI", sans-serif;
  background: rgba(12, 12, 22, 0.93);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 16px;
  padding: 7px;
  margin: 8px;
  backdrop-filter: blur(20px);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.7);
  color: #e2e8f0;
}

.hud-placeholder {
  padding: 12px;
  font-size: 12px;
  color: #64748b;
  text-align: center;
}
```

- [ ] **Step 4: Run + verify visually**

```bash
cd island && npm run tauri dev
```

Expected: a small frameless dark pill with the placeholder text, no Windows title bar, always on top of other apps. Close window when verified.

- [ ] **Step 5: Commit**

```bash
git add island/src-tauri/tauri.conf.json island/src/App.tsx island/src/App.css island/src/main.tsx
git commit -m "feat(island): frameless transparent always-on-top window"
```

---

### Task 7: Window drag + position persistence

**Files:**
- Modify: `island/src-tauri/tauri.conf.json` — enable required plugins
- Modify: `island/src-tauri/Cargo.toml` — add tauri-plugin-store
- Modify: `island/src-tauri/src/main.rs`
- Modify: `island/src/App.tsx`
- Create: `island/src/hooks/useDrag.ts`

- [ ] **Step 1: Add tauri-plugin-store dependency**

In `island/src-tauri/Cargo.toml` under `[dependencies]`:
```toml
tauri-plugin-store = "2"
```

In `island/src-tauri/src/main.rs`, register the plugin:
```rust
fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_store::Builder::new().build())
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
```

- [ ] **Step 2: Install JS-side store plugin**

```bash
cd island && npm install @tauri-apps/plugin-store
```

- [ ] **Step 3: Implement drag hook**

`island/src/hooks/useDrag.ts`:
```typescript
import { getCurrentWindow } from "@tauri-apps/api/window";
import { LazyStore } from "@tauri-apps/plugin-store";
import { useEffect } from "react";

const store = new LazyStore("island-state.json");
const KEY = "window_pos";

interface Pos { x: number; y: number; }

export function useDrag(ref: React.RefObject<HTMLElement>) {
  // restore on mount
  useEffect(() => {
    (async () => {
      const pos = await store.get<Pos>(KEY);
      if (pos) await getCurrentWindow().setPosition(new (await import("@tauri-apps/api/dpi")).PhysicalPosition(pos.x, pos.y));
    })();
  }, []);

  // drag listener
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const onDown = async (e: MouseEvent) => {
      if (e.button !== 0) return;
      await getCurrentWindow().startDragging();
    };
    el.addEventListener("mousedown", onDown);
    return () => el.removeEventListener("mousedown", onDown);
  }, [ref]);

  // save on move-end (poll every 500ms, save if changed)
  useEffect(() => {
    let last: Pos | null = null;
    const id = setInterval(async () => {
      const pp = await getCurrentWindow().outerPosition();
      const cur = { x: pp.x, y: pp.y };
      if (!last || last.x !== cur.x || last.y !== cur.y) {
        await store.set(KEY, cur);
        await store.save();
        last = cur;
      }
    }, 500);
    return () => clearInterval(id);
  }, []);
}
```

- [ ] **Step 4: Wire in `App.tsx`**

```tsx
import { useRef } from "react";
import "./App.css";
import { useDrag } from "./hooks/useDrag";

export default function App() {
  const hudRef = useRef<HTMLDivElement>(null);
  useDrag(hudRef);
  return (
    <div className="hud" ref={hudRef}>
      <div className="hud-placeholder">drag me</div>
    </div>
  );
}
```

- [ ] **Step 5: Verify**

```bash
cd island && npm run tauri dev
```

- Drag the window by clicking and holding anywhere on the dark pill, then move the mouse.
- Close the window and reopen with `npm run tauri dev` — expected: it reappears at the last position.

- [ ] **Step 6: Commit**

```bash
git add island/src-tauri/ island/src/ island/package.json island/package-lock.json
git commit -m "feat(island): draggable window with persisted position"
```

---

### Task 8: Rust `focus_terminal` command

**Files:**
- Modify: `island/src-tauri/Cargo.toml` — add `windows` crate
- Create: `island/src-tauri/src/focus.rs`
- Modify: `island/src-tauri/src/main.rs` — register command

- [ ] **Step 1: Add windows-rs dep**

In `island/src-tauri/Cargo.toml`:
```toml
[target.'cfg(windows)'.dependencies]
windows = { version = "0.58", features = ["Win32_Foundation", "Win32_UI_WindowsAndMessaging"] }
```

- [ ] **Step 2: Implement command**

`island/src-tauri/src/focus.rs`:
```rust
use windows::core::PCWSTR;
use windows::Win32::Foundation::HWND;
use windows::Win32::UI::WindowsAndMessaging::{FindWindowW, SetForegroundWindow, ShowWindow, IsIconic, SW_RESTORE};

#[tauri::command]
pub fn focus_terminal(project: String) -> Result<(), String> {
    let title = format!("cc-bridge-wrapper-{}", project);
    let wide: Vec<u16> = title.encode_utf16().chain(Some(0)).collect();

    unsafe {
        let hwnd: HWND = FindWindowW(PCWSTR::null(), PCWSTR(wide.as_ptr()))
            .map_err(|e| format!("FindWindowW failed: {e}"))?;
        if hwnd.0.is_null() {
            return Err(format!("Window not found: {}", title));
        }
        if IsIconic(hwnd).as_bool() {
            let _ = ShowWindow(hwnd, SW_RESTORE);
        }
        if !SetForegroundWindow(hwnd).as_bool() {
            return Err(format!("SetForegroundWindow failed for {}", title));
        }
    }
    Ok(())
}
```

- [ ] **Step 3: Register in `main.rs`**

```rust
mod focus;

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_store::Builder::new().build())
        .invoke_handler(tauri::generate_handler![focus::focus_terminal])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
```

- [ ] **Step 4: Verify from devtools console**

```bash
cd island && npm run tauri dev
```

Open the devtools (Ctrl+Shift+I), in console run:
```javascript
const { invoke } = await import("@tauri-apps/api/core");
await invoke("focus_terminal", { project: "RC" });
```

Expected:
- If a Windows Terminal with title `cc-bridge-wrapper-RC` exists → it pops to foreground.
- Otherwise → the call rejects with `Window not found: cc-bridge-wrapper-RC`.

- [ ] **Step 5: Commit**

```bash
git add island/src-tauri/
git commit -m "feat(island): focus_terminal Rust command via FindWindowW"
```

---

## Phase 3 — Frontend State + Components

### Task 9: Animations + color palette

**Files:**
- Create: `island/src/styles/animations.css`
- Create: `island/src/lib/colors.ts`
- Modify: `island/src/main.tsx` — import animations.css

- [ ] **Step 1: Color palette module**

`island/src/lib/colors.ts`:
```typescript
export type Priority = "p1" | "p2" | "p3" | "p4" | "p5" | "p6" | "p7" | "p8";

/** Maps a Priority to the hex value of its main color (used for trail dots). */
export const COLOR_MAIN: Record<Priority, string> = {
  p1: "#EF4444",  // CRITICAL · error
  p2: "#F97316",  // HIGH · notification
  p3: "#EAB308",  // CELEBRATE · task complete
  p4: "#10B981",  // DONE · assistant reply
  p5: "#6366F1",  // ACTIVE · Bash
  p6: "#8B5CF6",  // WORKING · file ops
  p7: "#06B6D4",  // INPUT · user prompt
  p8: "#6B7280",  // IDLE · no activity
};
```

- [ ] **Step 2: Animations stylesheet**

`island/src/styles/animations.css`:
```css
/* Priority color variables — applied to a cat container via class .p{N} */
.p1 { --cm: #EF4444; --cl: #FCA5A5; --cd: #B91C1C; --cg: #EF4444; }
.p2 { --cm: #F97316; --cl: #FED7AA; --cd: #C2410C; --cg: #F97316; }
.p3 { --cm: #EAB308; --cl: #FEF08A; --cd: #A16207; --cg: #EAB308; }
.p4 { --cm: #10B981; --cl: #6EE7B7; --cd: #065F46; --cg: #10B981; }
.p5 { --cm: #6366F1; --cl: #A5B4FC; --cd: #3730A3; --cg: #6366F1; }
.p6 { --cm: #8B5CF6; --cl: #C4B5FD; --cd: #5B21B6; --cg: #8B5CF6; }
.p7 { --cm: #06B6D4; --cl: #A5F3FC; --cd: #0E7490; --cg: #06B6D4; }
.p8 { --cm: #6B7280; --cl: #9CA3AF; --cd: #374151; --cg: #6B7280; }

/* Inside-SVG class hooks */
.cat-svg .bm { fill: var(--cm); transition: fill .6s; }
.cat-svg .bl { fill: var(--cl); transition: fill .6s; }
.cat-svg .bd { fill: var(--cd); transition: fill .6s; }
.cat-svg .gl { stroke: var(--cg); transition: stroke .6s; }
.cat-svg .gf { fill: var(--cg); transition: fill .6s; }

/* Cat motion ── strolling (soft sine) */
@keyframes stroll {
  0%, 100% { transform: translateY(0) scaleY(1); }
  50%      { transform: translateY(-3px) scaleY(1.02); }
}
.stroll { animation: stroll 1.8s cubic-bezier(0.37, 0, 0.63, 1) infinite; transform-origin: bottom; }

/* Cat parts — secondary motion */
@keyframes breathe   { 0%,100% { transform: scaleY(1); } 50% { transform: scaleY(1.04); } }
@keyframes blink     { 0%,90%,100% { transform: scaleY(1); } 95% { transform: scaleY(.05); } }
@keyframes tail-sway { 0%,100% { transform: rotate(-2deg); } 50% { transform: rotate(6deg); } }
@keyframes ear-soft  { 0%,100% { transform: rotate(0); } 50% { transform: rotate(-2deg); } }
@keyframes zzz       { 0% { transform: translate(0,0); opacity: 1; } 100% { transform: translate(4px,-9px); opacity: 0; } }
@keyframes paw-l     { 0%,40%,100% { transform: translateY(0); } 20% { transform: translateY(-2px); } }
@keyframes paw-r     { 0%,20%,60%,100% { transform: translateY(0); } 40% { transform: translateY(-2px); } }
@keyframes leg-fl    { 0% { transform: rotate(0); } 25% { transform: rotate(28deg); } 50% { transform: rotate(0); } 75% { transform: rotate(-20deg); } 100% { transform: rotate(0); } }
@keyframes leg-fr    { 0% { transform: rotate(0); } 25% { transform: rotate(-20deg); } 50% { transform: rotate(0); } 75% { transform: rotate(28deg); } 100% { transform: rotate(0); } }
@keyframes wave-l    { 0%,100% { transform: rotate(0); } 50% { transform: rotate(-15deg); } }
@keyframes wave-r    { 0%,100% { transform: rotate(0); } 50% { transform: rotate(15deg); } }
@keyframes fur-pulse { 0%,100% { opacity: .7; transform: scaleY(1); } 50% { opacity: 1; transform: scaleY(1.15); } }
@keyframes shiver    { 0%,100% { transform: translateX(0); } 25% { transform: translateX(-1px); } 50% { transform: translateX(0); } 75% { transform: translateX(1px); } }
@keyframes dot-pulse { 0%,100% { opacity: 1; } 50% { opacity: .4; } }

/* Error row whole-background pulse */
@keyframes row-error-pulse {
  0%,100% { background: rgba(239,68,68,0.06); border-color: rgba(239,68,68,0.18); }
  50%      { background: rgba(239,68,68,0.16); border-color: rgba(239,68,68,0.45); }
}
```

- [ ] **Step 3: Import in main.tsx**

`island/src/main.tsx`:
```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./styles/animations.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode><App /></React.StrictMode>
);
```

- [ ] **Step 4: Commit**

```bash
git add island/src/styles/ island/src/lib/colors.ts island/src/main.tsx
git commit -m "feat(island): priority color palette + cat animation keyframes"
```

---

### Task 10: Idle cat SVG component

**Files:**
- Create: `island/src/components/cats/Idle.tsx`

- [ ] **Step 1: Implement**

```tsx
export default function CatIdle({ size = 38 }: { size?: number }) {
  return (
    <svg
      className="cat-svg p8"
      width={size}
      height={size * 0.74}
      viewBox="0 0 54 48"
      style={{ opacity: 0.65 }}
    >
      <g style={{ animation: "breathe 4s ease-in-out infinite", transformOrigin: "27px 34px" }}>
        <ellipse cx="27" cy="36" rx="20" ry="11" className="bd" />
        <ellipse cx="27" cy="35" rx="18" ry="9.5" className="bm" />
        <circle cx="37" cy="22" r="10" className="bm" />
        <polygon points="29,15 32,7 36,15" className="bm" />
        <polygon points="38,14 41,6 45,13" className="bm" />
        <polygon points="30,15 32,9 35,15" className="bl" />
        <polygon points="39,14 41,8 44,14" className="bl" />
        <path d="M32 22 Q34 24.5 36 22" stroke="#374151" strokeWidth="1.5" strokeLinecap="round" fill="none" />
        <path d="M37 22 Q39 24.5 41 22" stroke="#374151" strokeWidth="1.5" strokeLinecap="round" fill="none" />
      </g>
      <g style={{ animation: "tail-sway 2.4s ease-in-out infinite", transformOrigin: "8px 30px" }}>
        <path d="M8 36 Q3 30 7 24 Q11 18 9 30" className="gl" strokeWidth="3.5" strokeLinecap="round" fill="none" />
      </g>
      <text x="5" y="16" fontSize="9" className="gf" fontFamily="sans-serif" fontWeight="bold"
        style={{ animation: "zzz 2.5s ease-in infinite" }}>z</text>
    </svg>
  );
}
```

- [ ] **Step 2: Smoke-render verification (no commit yet)**

Temporarily edit `island/src/App.tsx` to render the cat:
```tsx
import CatIdle from "./components/cats/Idle";
// ...
<div className="hud" ref={hudRef}><CatIdle /></div>
```

Run `npm run tauri dev`. Expected: a small gray sleeping cat with a slowly drifting `z`.

- [ ] **Step 3: Commit (revert App.tsx demo if needed; the cat module stays)**

```bash
git add island/src/components/cats/Idle.tsx
git commit -m "feat(island): CatIdle SVG component (P8 gray, breathe + zzz)"
```

---

### Task 11: Working cat SVG component

**Files:**
- Create: `island/src/components/cats/Working.tsx`

- [ ] **Step 1: Implement**

```tsx
import type { Priority } from "../../lib/colors";

export default function CatWorking({ priority = "p5", size = 38 }: { priority?: Priority; size?: number }) {
  return (
    <svg className={`cat-svg ${priority}`} width={size} height={size * 0.74} viewBox="0 0 58 46">
      <g style={{ animation: "stroll 1.8s cubic-bezier(0.37,0,0.63,1) infinite", transformOrigin: "bottom" }}>
        <ellipse cx="30" cy="28" rx="16" ry="9" className="bm" transform="rotate(-12 30 28)" />
        <circle cx="43" cy="17" r="10" className="bm" />
        <polygon points="36,10 39,2 43,10" className="bm" />
        <polygon points="43,9 46,1 50,9" className="bm" />
        <polygon points="37,10 39,4 42,10" className="bl" />
        <polygon points="44,9 46,3 49,9" className="bl" />
        <circle cx="40" cy="18" r="3" fill="#1F2937" />
        <circle cx="47" cy="17" r="3" fill="#1F2937" />
        <circle cx="41" cy="17" r="1.2" fill="white" />
        <circle cx="48" cy="16" r="1.2" fill="white" />
        <g style={{ animation: "leg-fl .8s ease-in-out infinite", transformOrigin: "22px 28px" }}>
          <line x1="22" y1="28" x2="14" y2="40" className="gl" strokeWidth="4" strokeLinecap="round" />
        </g>
        <g style={{ animation: "leg-fr .8s ease-in-out infinite", transformOrigin: "36px 32px" }}>
          <line x1="36" y1="32" x2="44" y2="42" className="gl" strokeWidth="4" strokeLinecap="round" />
        </g>
        <path d="M15 26 Q5 18 9 8" className="gl" strokeWidth="3.5" strokeLinecap="round" fill="none" />
      </g>
    </svg>
  );
}
```

- [ ] **Step 2: Smoke render** — temporarily swap `<CatIdle />` for `<CatWorking priority="p5" />` in App.tsx and run `npm run tauri dev`. Expected: indigo running cat with bouncing legs. Then revert.

- [ ] **Step 3: Commit**

```bash
git add island/src/components/cats/Working.tsx
git commit -m "feat(island): CatWorking SVG (running pose, color via priority prop)"
```

---

### Task 12: Done cat SVG component

**Files:**
- Create: `island/src/components/cats/Done.tsx`

- [ ] **Step 1: Implement**

```tsx
import type { Priority } from "../../lib/colors";

export default function CatDone({ priority = "p4", size = 36 }: { priority?: Priority; size?: number }) {
  return (
    <svg className={`cat-svg ${priority}`} width={size} height={size * 0.89} viewBox="0 0 52 54">
      <g style={{ animation: "breathe 3.5s ease-in-out infinite", transformOrigin: "26px 40px" }}>
        <ellipse cx="26" cy="44" rx="12" ry="7" className="bd" />
        <ellipse cx="26" cy="41" rx="11" ry="11" className="bm" />
        <circle cx="26" cy="20" r="13" className="bm" />
        <polygon points="14,12 17,4 21,12" className="bm" />
        <polygon points="31,11 35,3 38,11" className="bm" />
        <polygon points="15,12 17,6 20,12" className="bl" />
        <polygon points="32,11 35,5 37,11" className="bl" />
        <path d="M19 22 Q21 19 23 22" stroke="#065F46" strokeWidth="2" strokeLinecap="round" fill="none" />
        <path d="M29 22 Q31 19 33 22" stroke="#065F46" strokeWidth="2" strokeLinecap="round" fill="none" />
      </g>
      <g style={{ animation: "wave-l 1.5s ease-in-out infinite", transformOrigin: "14px 36px" }}>
        <line x1="14" y1="36" x2="5" y2="24" className="gl" strokeWidth="4.5" strokeLinecap="round" />
      </g>
      <g style={{ animation: "wave-r 1.5s ease-in-out infinite", transformOrigin: "38px 36px" }}>
        <line x1="38" y1="36" x2="47" y2="24" className="gl" strokeWidth="4.5" strokeLinecap="round" />
      </g>
    </svg>
  );
}
```

- [ ] **Step 2: Smoke render** — swap in `<CatDone />`, verify green satisfied cat with waving paws.

- [ ] **Step 3: Commit**

```bash
git add island/src/components/cats/Done.tsx
git commit -m "feat(island): CatDone SVG (satisfied pose, waving paws)"
```

---

### Task 13: Error cat SVG component

**Files:**
- Create: `island/src/components/cats/Error.tsx`

- [ ] **Step 1: Implement**

```tsx
export default function CatError({ size = 34 }: { size?: number }) {
  return (
    <svg
      className="cat-svg p1"
      width={size}
      height={size * 0.94}
      viewBox="0 0 52 48"
      style={{ animation: "shiver .4s ease-in-out infinite" }}
    >
      <path d="M10 42 Q18 22 26 20 Q34 22 42 42 Z" className="bm" />
      <path d="M10 42 Q24 32 42 42" className="bd" />
      <g style={{ animation: "fur-pulse .7s ease-in-out infinite" }}>
        <line x1="16" y1="22" x2="11" y2="12" className="gl" strokeWidth="2" strokeLinecap="round" />
        <line x1="20" y1="19" x2="17" y2="9"  className="gl" strokeWidth="2" strokeLinecap="round" />
        <line x1="26" y1="18" x2="26" y2="8"  className="gl" strokeWidth="2" strokeLinecap="round" />
        <line x1="32" y1="19" x2="35" y2="9"  className="gl" strokeWidth="2" strokeLinecap="round" />
        <line x1="36" y1="22" x2="41" y2="12" className="gl" strokeWidth="2" strokeLinecap="round" />
      </g>
      <circle cx="26" cy="30" r="10" className="bm" />
      <polygon points="18,24 20,17 24,24" className="bm" />
      <polygon points="28,23 31,16 35,23" className="bm" />
      <circle cx="22" cy="31" r="4.5" fill="white" />
      <circle cx="30" cy="31" r="4.5" fill="white" />
      <circle cx="22" cy="31" r="2.5" fill="#1F2937" />
      <circle cx="30" cy="31" r="2.5" fill="#1F2937" />
      <circle cx="22" cy="30" r="1" fill="white" />
      <circle cx="30" cy="30" r="1" fill="white" />
    </svg>
  );
}
```

- [ ] **Step 2: Smoke render** — verify red bristled cat trembling with bulging eyes.

- [ ] **Step 3: Commit**

```bash
git add island/src/components/cats/Error.tsx
git commit -m "feat(island): CatError SVG (bristled fur, shivering, bulging eyes)"
```

---

### Task 14: FocusCat dispatcher + HistoryTrail

**Files:**
- Create: `island/src/components/FocusCat.tsx`
- Create: `island/src/components/HistoryTrail.tsx`

- [ ] **Step 1: FocusCat dispatcher**

`island/src/components/FocusCat.tsx`:
```tsx
import type { Priority } from "../lib/colors";
import CatIdle from "./cats/Idle";
import CatWorking from "./cats/Working";
import CatDone from "./cats/Done";
import CatError from "./cats/Error";

export type CatState = "working" | "done" | "error" | "idle";

interface Props { state: CatState; priority: Priority; }

export default function FocusCat({ state, priority }: Props) {
  switch (state) {
    case "working": return <CatWorking priority={priority} />;
    case "done":    return <CatDone priority={priority} />;
    case "error":   return <CatError />;
    case "idle":    return <CatIdle />;
  }
}
```

- [ ] **Step 2: HistoryTrail**

`island/src/components/HistoryTrail.tsx`:
```tsx
import { COLOR_MAIN, type Priority } from "../lib/colors";

export interface HistoryDot { color: Priority; ts: number; }

interface Props { history: HistoryDot[]; }

const SIZE_BY_INDEX = [4, 5, 6, 7, 8]; // tiny → big, rightmost current
const OPACITY_BY_INDEX = [0.35, 0.55, 0.75, 0.9, 1.0];

export default function HistoryTrail({ history }: Props) {
  if (history.length === 0) {
    return (
      <div className="history-trail empty">
        <span style={{ color: "#1e293b", fontSize: 10, letterSpacing: 2 }}>─ ─ ─ ─ ─</span>
      </div>
    );
  }
  // pad left with placeholders if < 5
  const padded: (HistoryDot | null)[] = Array(Math.max(0, 5 - history.length)).fill(null).concat(history);
  return (
    <div className="history-trail" style={{ display: "flex", alignItems: "center", gap: 4 }}>
      {padded.map((d, i) =>
        d ? (
          <div
            key={i}
            style={{
              width: SIZE_BY_INDEX[i],
              height: SIZE_BY_INDEX[i],
              borderRadius: "50%",
              background: COLOR_MAIN[d.color],
              opacity: i === 4 ? OPACITY_BY_INDEX[4] : OPACITY_BY_INDEX[i],
              boxShadow: i === 4 ? `0 0 6px ${COLOR_MAIN[d.color]}` : "none",
              flexShrink: 0,
            }}
          />
        ) : (
          <div key={i} style={{ width: SIZE_BY_INDEX[i], height: SIZE_BY_INDEX[i] }} />
        )
      )}
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add island/src/components/FocusCat.tsx island/src/components/HistoryTrail.tsx
git commit -m "feat(island): FocusCat dispatcher + HistoryTrail component"
```

---

### Task 15: Session store + event-mapper (with tests)

**Files:**
- Create: `island/src/lib/event-mapper.ts`
- Create: `island/src/lib/event-mapper.test.ts`
- Create: `island/src/store/sessions.ts`
- Create: `island/src/store/sessions.test.ts`

- [ ] **Step 1: Write event-mapper tests**

`island/src/lib/event-mapper.test.ts`:
```typescript
import { describe, it, expect } from "vitest";
import { mapEvent } from "./event-mapper";

describe("mapEvent", () => {
  it("maps tool_use Bash:* → working/p5", () => {
    expect(mapEvent({ type: "tool_use", project: "RC", text: "Bash: ls", meta: "" }))
      .toEqual({ state: "working", color: "p5" });
  });

  it("maps tool_use Read/Write/Edit → working/p6", () => {
    expect(mapEvent({ type: "tool_use", project: "RC", text: "Read: foo.py", meta: "" }))
      .toEqual({ state: "working", color: "p6" });
    expect(mapEvent({ type: "tool_use", project: "RC", text: "Write: bar.ts", meta: "" }))
      .toEqual({ state: "working", color: "p6" });
  });

  it("maps tool_use Glob/Grep/WebSearch/WebFetch → working/p7", () => {
    expect(mapEvent({ type: "tool_use", project: "RC", text: "Glob: **/*.py", meta: "" }))
      .toEqual({ state: "working", color: "p7" });
    expect(mapEvent({ type: "tool_use", project: "RC", text: "WebFetch: example.com", meta: "" }))
      .toEqual({ state: "working", color: "p7" });
  });

  it("maps assistant_reply → done/p4", () => {
    expect(mapEvent({ type: "assistant_reply", project: "RC", text: "ok", meta: "" }))
      .toEqual({ state: "done", color: "p4" });
  });

  it("maps task_completed → done/p3", () => {
    expect(mapEvent({ type: "task_completed", project: "RC", text: "", meta: "" }))
      .toEqual({ state: "done", color: "p3" });
  });

  it("maps user_prompt → working/p7", () => {
    expect(mapEvent({ type: "user_prompt", project: "RC", text: "hi", meta: "" }))
      .toEqual({ state: "working", color: "p7" });
  });

  it("maps bash_result fail → error/p1", () => {
    expect(mapEvent({ type: "bash_result", project: "RC", text: "$ ls", meta: "fail" }))
      .toEqual({ state: "error", color: "p1" });
  });

  it("maps bash_result ok → working/p5", () => {
    expect(mapEvent({ type: "bash_result", project: "RC", text: "$ ls", meta: "ok" }))
      .toEqual({ state: "working", color: "p5" });
  });

  it("maps notification → error/p2", () => {
    expect(mapEvent({ type: "notification", project: "RC", text: "Hey", meta: "" }))
      .toEqual({ state: "error", color: "p2" });
  });
});
```

- [ ] **Step 2: Run — expect FAIL**

```bash
cd island && npm test
```
Expected: import error for `event-mapper`.

- [ ] **Step 3: Implement mapper**

`island/src/lib/event-mapper.ts`:
```typescript
import type { Priority } from "./colors";
import type { CatState } from "../components/FocusCat";

export interface RawEvent {
  type: "tool_use" | "assistant_reply" | "user_prompt" | "bash_result" | "notification" | "task_created" | "task_completed";
  project: string;
  text: string;
  meta: string;
}

export interface MappedState { state: CatState; color: Priority; }

export function mapEvent(e: RawEvent): MappedState {
  switch (e.type) {
    case "tool_use": {
      if (/^Bash:/i.test(e.text))                  return { state: "working", color: "p5" };
      if (/^(Read|Write|Edit|MultiEdit|NotebookEdit):/i.test(e.text)) return { state: "working", color: "p6" };
      if (/^(Glob|Grep|WebSearch|WebFetch):/i.test(e.text))           return { state: "working", color: "p7" };
      return { state: "working", color: "p5" };  // unknown tool — default active
    }
    case "user_prompt":     return { state: "working", color: "p7" };
    case "assistant_reply": return { state: "done",    color: "p4" };
    case "task_created":    return { state: "working", color: "p3" };
    case "task_completed":  return { state: "done",    color: "p3" };
    case "bash_result":     return e.meta === "fail"
                              ? { state: "error",   color: "p1" }
                              : { state: "working", color: "p5" };
    case "notification":    return { state: "error",   color: "p2" };
  }
}
```

- [ ] **Step 4: Re-run — expect PASS**

```bash
cd island && npm test
```

- [ ] **Step 5: Write store test**

`island/src/store/sessions.test.ts`:
```typescript
import { describe, it, expect, beforeEach } from "vitest";
import { useSessions } from "./sessions";

describe("sessions store", () => {
  beforeEach(() => { useSessions.setState({ map: new Map() }); });

  it("creates a session on first event for a project", () => {
    useSessions.getState().ingest({ type: "tool_use", project: "RC", text: "Bash: ls", meta: "" });
    const s = useSessions.getState().map.get("RC")!;
    expect(s.state).toBe("working");
    expect(s.color).toBe("p5");
    expect(s.history).toHaveLength(1);
  });

  it("appends history dots up to 5, then trims oldest", () => {
    const ing = useSessions.getState().ingest;
    for (let i = 0; i < 7; i++) ing({ type: "tool_use", project: "RC", text: "Bash: x", meta: "" });
    expect(useSessions.getState().map.get("RC")!.history).toHaveLength(5);
  });

  it("stores assistant_reply text as recap", () => {
    useSessions.getState().ingest({ type: "assistant_reply", project: "RC", text: "all done", meta: "" });
    expect(useSessions.getState().map.get("RC")!.recap).toBe("all done");
  });

  it("toggleRecap flips recapOpen", () => {
    useSessions.getState().ingest({ type: "assistant_reply", project: "RC", text: "x", meta: "" });
    useSessions.getState().toggleRecap("RC");
    expect(useSessions.getState().map.get("RC")!.recapOpen).toBe(true);
    useSessions.getState().toggleRecap("RC");
    expect(useSessions.getState().map.get("RC")!.recapOpen).toBe(false);
  });

  it("markIdle flips a stale session to idle", () => {
    useSessions.getState().ingest({ type: "tool_use", project: "RC", text: "Bash: x", meta: "" });
    useSessions.getState().markIdle("RC");
    expect(useSessions.getState().map.get("RC")!.state).toBe("idle");
    expect(useSessions.getState().map.get("RC")!.color).toBe("p8");
  });
});
```

- [ ] **Step 6: Run — expect FAIL**

```bash
cd island && npm test
```

- [ ] **Step 7: Implement store**

`island/src/store/sessions.ts`:
```typescript
import { create } from "zustand";
import { mapEvent, type RawEvent } from "../lib/event-mapper";
import type { CatState } from "../components/FocusCat";
import type { Priority } from "../lib/colors";
import type { HistoryDot } from "../components/HistoryTrail";

export interface SessionState {
  project: string;
  state: CatState;
  color: Priority;
  history: HistoryDot[];
  recap: string | null;
  recapOpen: boolean;
  lastEventAt: number;
}

interface Store {
  map: Map<string, SessionState>;
  ingest: (e: RawEvent) => void;
  toggleRecap: (project: string) => void;
  markIdle: (project: string) => void;
}

export const useSessions = create<Store>((set) => ({
  map: new Map(),

  ingest: (e) => set((s) => {
    if (!e.project) return s;
    const mapped = mapEvent(e);
    const prev: SessionState = s.map.get(e.project) ?? {
      project: e.project, state: "idle", color: "p8",
      history: [], recap: null, recapOpen: false, lastEventAt: Date.now(),
    };
    const history = [...prev.history, { color: mapped.color, ts: Date.now() }].slice(-5);
    const next: SessionState = {
      ...prev,
      state: mapped.state,
      color: mapped.color,
      history,
      recap: e.type === "assistant_reply" ? e.text : prev.recap,
      lastEventAt: Date.now(),
    };
    const m = new Map(s.map); m.set(e.project, next);
    return { map: m };
  }),

  toggleRecap: (project) => set((s) => {
    const sess = s.map.get(project); if (!sess) return s;
    const m = new Map(s.map);
    m.set(project, { ...sess, recapOpen: !sess.recapOpen });
    return { map: m };
  }),

  markIdle: (project) => set((s) => {
    const sess = s.map.get(project); if (!sess) return s;
    const m = new Map(s.map);
    m.set(project, { ...sess, state: "idle", color: "p8" });
    return { map: m };
  }),
}));
```

- [ ] **Step 8: Re-run — expect all PASS**

```bash
cd island && npm test
```
Expected: 9 + 5 = 14 tests passing.

- [ ] **Step 9: Commit**

```bash
git add island/src/lib/ island/src/store/
git commit -m "feat(island): event-mapper + Zustand session store (TDD)"
```

---

### Task 16: useSSE hook + SessionRow + App wiring

**Files:**
- Create: `island/src/hooks/useSSE.ts`
- Create: `island/src/components/SessionRow.tsx`
- Modify: `island/src/App.tsx`
- Modify: `island/src/App.css`

- [ ] **Step 1: useSSE hook**

`island/src/hooks/useSSE.ts`:
```typescript
import { useEffect } from "react";
import { useSessions } from "../store/sessions";
import type { RawEvent } from "../lib/event-mapper";

const BRIDGE_URL = "http://127.0.0.1:8787/events";

export function useSSE() {
  const ingest = useSessions((s) => s.ingest);
  useEffect(() => {
    const src = new EventSource(BRIDGE_URL);
    src.onmessage = (msg) => {
      try {
        const event = JSON.parse(msg.data) as RawEvent;
        ingest(event);
      } catch (e) {
        console.warn("bad SSE payload", e);
      }
    };
    src.onerror = () => {
      // EventSource auto-reconnects after a delay; just log
      console.warn("SSE error; will auto-reconnect");
    };
    return () => src.close();
  }, [ingest]);
}
```

- [ ] **Step 2: SessionRow**

`island/src/components/SessionRow.tsx`:
```tsx
import { invoke } from "@tauri-apps/api/core";
import FocusCat from "./FocusCat";
import HistoryTrail from "./HistoryTrail";
import { COLOR_MAIN } from "../lib/colors";
import { useSessions, type SessionState } from "../store/sessions";

interface Props { session: SessionState; }

export default function SessionRow({ session }: Props) {
  const toggleRecap = useSessions((s) => s.toggleRecap);
  const isError = session.state === "error";

  const onClick = async () => {
    try { await invoke("focus_terminal", { project: session.project }); }
    catch (e) { console.warn("focus_terminal failed", e); }
  };
  const onRightClick = (e: React.MouseEvent) => {
    e.preventDefault();
    toggleRecap(session.project);
  };

  return (
    <div
      className={`hud-row ${isError ? "err-row" : ""}`}
      onClick={onClick}
      onContextMenu={onRightClick}
    >
      <div className="row-left">
        <div
          className="dot"
          style={{
            background: COLOR_MAIN[session.color],
            boxShadow: `0 0 5px ${COLOR_MAIN[session.color]}`,
            animation: session.state === "working" || isError ? "dot-pulse 1.6s ease-in-out infinite" : "none",
          }}
        />
        <span
          className="tag"
          style={{
            background: `${COLOR_MAIN[session.color]}2E`,
            color: COLOR_MAIN[session.color],
            border: `1px solid ${COLOR_MAIN[session.color]}4D`,
          }}
        >{session.project}</span>
      </div>
      <div className="focus-area">
        <div className="focus-cat"><FocusCat state={session.state} priority={session.color} /></div>
      </div>
      <HistoryTrail history={session.history} />
    </div>
  );
}
```

- [ ] **Step 3: App.tsx**

```tsx
import { useRef } from "react";
import "./App.css";
import { useDrag } from "./hooks/useDrag";
import { useSSE } from "./hooks/useSSE";
import { useSessions } from "./store/sessions";
import SessionRow from "./components/SessionRow";

export default function App() {
  const hudRef = useRef<HTMLDivElement>(null);
  useDrag(hudRef);
  useSSE();

  const sessions = useSessions((s) => Array.from(s.map.values()));

  return (
    <div className="hud" ref={hudRef}>
      {sessions.length === 0 ? (
        <div className="hud-placeholder">waiting for events…</div>
      ) : (
        sessions.map((s, i) => (
          <div key={s.project}>
            <SessionRow session={s} />
            {i < sessions.length - 1 && <div className="sep" />}
          </div>
        ))
      )}
    </div>
  );
}
```

- [ ] **Step 4: Add row styles to App.css** (append)

```css
.hud-row {
  display: flex; align-items: center; gap: 9px;
  padding: 6px 10px; border-radius: 10px;
  border: 1px solid transparent;
  cursor: pointer; transition: background .15s;
}
.hud-row:hover { background: rgba(255,255,255,.04); }
.hud-row.err-row { animation: row-error-pulse 1.6s ease-in-out infinite; }

.row-left { display: flex; align-items: center; gap: 7px; flex-shrink: 0; }
.dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.tag {
  font-size: 9.5px; font-weight: 700;
  padding: 1px 7px; border-radius: 999px; flex-shrink: 0;
  min-width: 40px; text-align: center;
}
.focus-area { display: flex; align-items: center; gap: 10px; flex-shrink: 0; min-width: 70px; }
.focus-cat { width: 38px; height: 32px; display: flex; align-items: flex-end; justify-content: center; }
.history-trail { flex: 1; display: flex; align-items: center; gap: 4px; min-width: 0; justify-content: flex-end; padding-right: 6px; }
.sep { height: 1px; background: rgba(255,255,255,.05); margin: 1px 8px; }
```

- [ ] **Step 5: End-to-end verification**

In one terminal:
```bash
cd bridge && python main.py
```

In another:
```bash
cd island && npm run tauri dev
```

In a third, simulate a hook event:
```bash
curl -X POST http://127.0.0.1:8787/hook/tool_use `
  -H "Authorization: Bearer $(cat hooks/.bridge_token)" `
  -H "Content-Type: application/json" `
  -d "{\"text\": \"[RC] Bash: npm run build\"}"
```

Expected: HUD shows one row labeled `RC` with an indigo running cat and one dot in the history trail.

Send 4 more events to see the trail fill up, then send `bash_result` with `meta: "fail"` to see the error pulse:
```bash
curl -X POST http://127.0.0.1:8787/hook/bash_result `
  -H "Authorization: Bearer $(cat hooks/.bridge_token)" `
  -H "Content-Type: application/json" `
  -d "{\"text\": \"[RC] $ pytest\", \"meta\": \"fail\"}"
```

Expected: row glows red with bristled cat, whole row background pulses.

- [ ] **Step 6: Commit**

```bash
git add island/src/
git commit -m "feat(island): SSE hook + SessionRow + App wiring (end-to-end MVP)"
```

---

## Phase 4 — Polish

### Task 17: Time tag + idle detector

**Files:**
- Create: `island/src/components/TimeTag.tsx`
- Modify: `island/src/components/SessionRow.tsx`
- Modify: `island/src/App.tsx`

- [ ] **Step 1: TimeTag component**

`island/src/components/TimeTag.tsx`:
```tsx
import { useEffect, useState } from "react";

function fmt(ts: number): string {
  const sec = (Date.now() - ts) / 1000;
  if (sec < 60)   return `${Math.floor(sec)}s`;
  if (sec < 3600) return `${Math.floor(sec / 60)}m`;
  return `${Math.floor(sec / 3600)}h`;
}

interface Props { ts: number; isError?: boolean; }

export default function TimeTag({ ts, isError }: Props) {
  const [_, force] = useState(0);
  useEffect(() => {
    const id = setInterval(() => force((n) => n + 1), 1000);
    return () => clearInterval(id);
  }, []);
  return (
    <span
      className="time-tag"
      style={{
        fontSize: 9.5,
        color: isError ? "#FCA5A5" : "#475569",
        fontVariantNumeric: "tabular-nums",
        minWidth: 32,
        textAlign: "right",
        fontWeight: isError ? 700 : 400,
        flexShrink: 0,
      }}
    >{fmt(ts)}</span>
  );
}
```

- [ ] **Step 2: Mount in SessionRow** (append after `<HistoryTrail>` line)

```tsx
import TimeTag from "./TimeTag";
// ... at the end of the row JSX:
      <TimeTag ts={session.lastEventAt} isError={isError} />
    </div>
  );
}
```

- [ ] **Step 3: Idle detector**

Append to `island/src/App.tsx` (inside the component body):
```tsx
import { useEffect } from "react";
// ...
useEffect(() => {
  const id = setInterval(() => {
    const { map, markIdle } = useSessions.getState();
    const now = Date.now();
    map.forEach((s, project) => {
      if (s.state !== "idle" && s.state !== "done" && now - s.lastEventAt > 30_000) {
        markIdle(project);
      }
    });
  }, 1000);
  return () => clearInterval(id);
}, []);
```

- [ ] **Step 4: Verify**

Run bridge + HUD as before. Send one event, wait 30s. Expected: cat transitions to gray sleeping (idle) and time tag shows `30s`, then `1m`, `2m`...

- [ ] **Step 5: Commit**

```bash
git add island/src/components/TimeTag.tsx island/src/components/SessionRow.tsx island/src/App.tsx
git commit -m "feat(island): time tag + 30s idle detector"
```

---

### Task 18: Recap panel expand on right-click

**Files:**
- Create: `island/src/components/RecapPanel.tsx`
- Modify: `island/src/App.tsx` — render below row when open

- [ ] **Step 1: RecapPanel**

`island/src/components/RecapPanel.tsx`:
```tsx
import { invoke } from "@tauri-apps/api/core";
import type { SessionState } from "../store/sessions";

interface Props { session: SessionState; }

export default function RecapPanel({ session }: Props) {
  if (!session.recapOpen || !session.recap) return null;
  return (
    <div style={{
      margin: "0 12px 4px 36px",
      background: "rgba(99,102,241,.06)",
      border: "1px solid rgba(99,102,241,.2)",
      borderRadius: 8,
      padding: "8px 12px",
      maxHeight: 200, overflowY: "auto",
    }}>
      <div style={{ fontSize: 9, color: "#475569", textTransform: "uppercase", letterSpacing: ".07em", marginBottom: 6 }}>
        Recap
      </div>
      <div style={{ fontSize: 11, color: "#94A3B8", lineHeight: 1.5, whiteSpace: "pre-wrap" }}>
        {session.recap}
      </div>
      <div
        onClick={() => invoke("focus_terminal", { project: session.project }).catch(() => {})}
        style={{
          marginTop: 6, paddingTop: 6,
          borderTop: "1px solid rgba(255,255,255,.05)",
          fontSize: 10, color: "#334155", cursor: "pointer",
        }}
      >⌖ focus {session.project} terminal</div>
    </div>
  );
}
```

- [ ] **Step 2: Render in App.tsx** — modify map block:

```tsx
{sessions.map((s, i) => (
  <div key={s.project}>
    <SessionRow session={s} />
    <RecapPanel session={s} />
    {i < sessions.length - 1 && <div className="sep" />}
  </div>
))}
```

Add `import RecapPanel from "./components/RecapPanel";` at the top.

- [ ] **Step 3: Verify**

Send an `assistant_reply` event:
```powershell
curl -X POST http://127.0.0.1:8787/hook/assistant_reply `
  -H "Authorization: Bearer $(cat hooks/.bridge_token)" `
  -H "Content-Type: application/json" `
  -d "{\"text\": \"[RC] All done — refactored 3 files\", \"meta\": \"2.3s · 420tok\"}"
```

Right-click the RC row. Expected: panel expands below showing the reply text + "focus RC terminal" link.

- [ ] **Step 4: Commit**

```bash
git add island/src/components/RecapPanel.tsx island/src/App.tsx
git commit -m "feat(island): right-click row to toggle recap panel"
```

---

### Task 19: System tray + autostart

**Files:**
- Modify: `island/src-tauri/Cargo.toml` — add `tauri-plugin-autostart`
- Modify: `island/src-tauri/tauri.conf.json` — declare tray icon
- Modify: `island/src-tauri/src/main.rs`

- [ ] **Step 1: Add plugins**

`island/src-tauri/Cargo.toml`:
```toml
tauri-plugin-autostart = "2"
```

```bash
cd island && npm install @tauri-apps/plugin-autostart
```

- [ ] **Step 2: Update tauri.conf.json**

Add under `tauri.bundle` (or wherever bundle config lives in the Tauri v2 schema):
```json
"trayIcon": {
  "iconPath": "icons/icon.png",
  "iconAsTemplate": true,
  "tooltip": "CC Island"
}
```

- [ ] **Step 3: Wire tray + autostart in `main.rs`**

```rust
use tauri::Manager;
use tauri::tray::{TrayIconBuilder, MouseButton, MouseButtonState, TrayIconEvent};
use tauri_plugin_autostart::{MacosLauncher, ManagerExt};

mod focus;

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_store::Builder::new().build())
        .plugin(tauri_plugin_autostart::init(MacosLauncher::LaunchAgent, None))
        .setup(|app| {
            // enable autostart on first run
            let _ = app.autolaunch().enable();

            let tray = TrayIconBuilder::new()
                .tooltip("CC Island")
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click { button: MouseButton::Left, button_state: MouseButtonState::Up, .. } = event {
                        if let Some(window) = tray.app_handle().get_webview_window("main") {
                            let visible = window.is_visible().unwrap_or(false);
                            if visible { let _ = window.hide(); } else { let _ = window.show(); let _ = window.set_focus(); }
                        }
                    }
                })
                .build(app)?;
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![focus::focus_terminal])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
```

- [ ] **Step 4: Verify**

```bash
cd island && npm run tauri dev
```

- Tray icon appears near clock. Click toggles HUD visibility.
- Verify autostart entry via `shell:startup` or Task Manager → Startup apps → `island` should be listed.

- [ ] **Step 5: Commit**

```bash
git add island/
git commit -m "feat(island): system tray toggle + Windows autostart"
```

---

### Task 20: Acceptance verification against design spec

**Files:**
- None (verification only). Optionally update spec checklist.

- [ ] **Step 1: Run end-to-end multi-session test**

Open 3 PowerShell windows. In each:
```powershell
cd "E:/MyProject/RC/<some-project-dir>"
python "E:/MyProject/RC/wrapper/wrapper.py"
```

Verify titles via:
```powershell
Get-Process | Where-Object MainWindowTitle -like 'cc-bridge-wrapper-*' | Select-Object MainWindowTitle
```

Expected: 3 distinct titles like `cc-bridge-wrapper-RC`, `cc-bridge-wrapper-X`, `cc-bridge-wrapper-Y`.

- [ ] **Step 2: Trigger events for each project**

For each project, in a fourth shell:
```powershell
$tok = Get-Content hooks/.bridge_token
@("RC","X","Y") | ForEach-Object {
  curl -X POST http://127.0.0.1:8787/hook/tool_use `
    -H "Authorization: Bearer $tok" -H "Content-Type: application/json" `
    -d "{`"text`": `"[$_] Bash: ls`"}"
}
```

Expected: HUD shows 3 rows in <1s, each with a running cat.

- [ ] **Step 3: Click each row → verify terminal focus**

Click RC row → RC's Windows Terminal pops to foreground. Repeat for X, Y.

- [ ] **Step 4: Trigger failure**

```powershell
curl -X POST http://127.0.0.1:8787/hook/bash_result `
  -H "Authorization: Bearer $tok" -H "Content-Type: application/json" `
  -d "{`"text`": `"[RC] $ pytest`", `"meta`": `"fail`"}"
```

Expected: RC row → entire row background pulses red, cat bristles.

- [ ] **Step 5: Wait 30s idle**

Stop sending events; observe RC transition to gray sleeping cat after 30s.

- [ ] **Step 6: Drag + restart persistence**

Drag HUD to new position. Close window (`Ctrl+C` in dev). Re-run `npm run tauri dev`. Expected: HUD reappears at the dragged position.

- [ ] **Step 7: Measure resource usage**

In Task Manager → Details, find `island.exe`:
- Expected: < 30 MB private working set, < 1% CPU idle, < 3% CPU during burst events.

- [ ] **Step 8: Mark spec section 11 acceptance criteria**

Open `docs/superpowers/specs/2026-05-21-dynamic-island-design.md`, change every `- [ ]` in §11 to `- [x]` after each criterion is observed.

- [ ] **Step 9: Final commit**

```bash
git add docs/superpowers/specs/2026-05-21-dynamic-island-design.md
git commit -m "docs(spec): mark dynamic island acceptance criteria verified"
```

---

## Done

All 20 tasks complete. The dynamic island HUD is functional, draggable, persistent, multi-session-aware, and integrated with the existing bridge.

**Suggested next steps (out of scope for this plan):**
- Settings panel (right-click tray): toggle autostart, change SSE URL, choose theme
- macOS / Linux support (replace `FindWindowW` with platform-specific window-focus mechanism)
- HUD-side pause toggle that PUTs to bridge's `push_state` to silence noisy events

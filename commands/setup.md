---
description: Initialize CC Relay - install pywinpty, configure Feishu credentials, install PowerShell shim, and smoke-test bridge
allowed-tools: Bash, Read, Write, Edit, AskUserQuestion
---

You are running the CC Relay setup flow. Follow these 7 steps **in order**. After each step, briefly report status to the user. Stop and surface the error if any step fails — do not silently skip.

## Step 1: Platform check (Windows-only)

CC Relay depends on Windows ConPTY. Bail out on non-Windows.

Run:
```bash
python -c "import os, sys; sys.exit(0 if os.name == 'nt' else 2)"
```

If exit code is 2: tell the user "CC Relay only supports Windows (ConPTY dependency). Aborting." and stop.

## Step 2: Python version check (>= 3.11)

Run:
```bash
python --version
```

Parse the output. If the version is below 3.11, tell the user: "CC Relay needs Python 3.11+ (current: <version>). Install from https://www.python.org/ and re-run /cc-relay:setup." Then stop.

## Step 3: Install Python dependencies (wrapper + bridge)

Install all the runtime dependencies the wrapper and bridge need. (`pip install` is idempotent — already-installed packages are no-ops.)

```bash
python -m pip install pywinpty fastapi "uvicorn[standard]" lark-oapi python-dotenv
```

Verify each was installed:

```bash
python -m pip show pywinpty fastapi uvicorn lark-oapi python-dotenv
```

If any package is missing in the output: install was incomplete. If install failed with a permission error, tell the user: "Dependency install failed (likely permissions). Run this in PowerShell manually: `python -m pip install --user pywinpty fastapi 'uvicorn[standard]' lark-oapi python-dotenv`, then re-run /cc-relay:setup." Then stop.

## Step 4: Locate claude.exe

Try these in order, stop at first hit. **Note:** PowerShell commands are wrapped in single-quoted bash strings so $env:VAR reaches PowerShell unexpanded.

1. $env:CLAUDE_EXE (PowerShell-side check):
```bash
powershell -NoProfile -Command 'if ($env:CLAUDE_EXE -and (Test-Path $env:CLAUDE_EXE)) { $env:CLAUDE_EXE }'
```

2. PATH lookup:
```bash
powershell -NoProfile -Command '(Get-Command claude.exe -ErrorAction SilentlyContinue).Source'
```

3. Default install:
```bash
powershell -NoProfile -Command '$p = Join-Path $env:LOCALAPPDATA "AnthropicClaude\claude.exe"; if (Test-Path $p) { $p }'
```

If all three return empty: tell user "claude.exe not found. Install Claude Code from https://claude.com/code first, then re-run /cc-relay:setup." Then stop.

Otherwise, report the discovered path. No need to persist — the shim's Resolve-ClaudeExe re-runs the same lookup at every invocation.

## Step 5: Feishu credentials in ~/.claude/plugins/cc-relay/.env

Determine the target path:
```bash
powershell -NoProfile -Command 'Join-Path $HOME ".claude\plugins\cc-relay\.env"'
```

The expected path is `C:\Users\<you>\.claude\plugins\cc-relay\.env`. Read it via the Read tool (handle non-existence — that means "no credentials yet").

If the file exists, parse each line KEY=VALUE and check all 3 keys (FEISHU_APP_ID, FEISHU_APP_SECRET, FEISHU_USER_OPEN_ID) are present and non-empty.

**If all 3 present:** use AskUserQuestion:
- Question: "Existing Feishu credentials found. Keep them or re-enter?"
- Options: "Keep existing (default)" / "Re-enter all 3 values"

If user chose Keep, skip to Step 6.

**If any key missing OR user chose Re-enter:** use AskUserQuestion **3 times sequentially** (one per credential), each as a single-answer free-text input via the "Other" option. Question headers:
- "FEISHU_APP_ID" — "Paste your Feishu App ID (starts with cli_):"
- "FEISHU_APP_SECRET" — "Paste your Feishu App Secret (32-char hex):"
- "FEISHU_USER_OPEN_ID" — "Paste your user open_id (starts with ou_):"

Ensure the parent directory exists, then use the Write tool to create the .env file. (Use Write tool rather than shell heredoc — avoids cross-shell quoting issues.)

Step 5a: ensure directory exists:
```bash
powershell -NoProfile -Command 'New-Item -ItemType Directory -Path (Join-Path $HOME ".claude\plugins\cc-relay") -Force | Out-Null'
```

Step 5b: use the Write tool to write the file at the absolute path you computed in Step 5 first line. File content (substitute the user's actual values):

```
FEISHU_APP_ID=<user-provided APP_ID>
FEISHU_APP_SECRET=<user-provided APP_SECRET>
FEISHU_USER_OPEN_ID=<user-provided OPEN_ID>
```

No trailing whitespace, one key per line, UTF-8 encoded (Write tool default).

## Step 6: Install shim block into PowerShell $PROFILE

Find the user's $PROFILE path:
```bash
powershell -NoProfile -Command '$PROFILE'
```

The shim block uses a **dynamic-version-lookup** pattern so plugin upgrades don't break it:

```powershell
# >>> claude-bridge shim >>>
$ccRelayDir = (Get-ChildItem (Join-Path $HOME ".claude\plugins\cache\cc-relay\cc-relay") -Directory -EA SilentlyContinue |
                Where-Object { $_.Name -match '^\d+(\.\d+)+$' } |
                Sort-Object { [version]$_.Name } -Descending |
                Select-Object -First 1).FullName
if ($ccRelayDir) { . (Join-Path $ccRelayDir "scripts\claude-shim.ps1") }
# <<< claude-bridge shim <<<
```

Read the existing $PROFILE (create empty file if missing) and search for the marker # >>> claude-bridge shim >>>:

- **No marker present:** append the full block above (with a leading blank line) to $PROFILE.
- **Marker present:** replace the entire block from # >>> claude-bridge shim >>> through # <<< claude-bridge shim <<< (inclusive) with the new block. This ensures users on older plugin versions get the latest shim logic when they re-run /cc-relay:setup.

Use the Read tool to read the existing $PROFILE content (handle non-existence — empty string then). Then use Write (full file rewrite) or Edit (targeted block replace) to apply the change. If $PROFILE doesn't exist yet, create it first:
```bash
powershell -NoProfile -Command 'if (-not (Test-Path $PROFILE)) { New-Item -ItemType File -Path $PROFILE -Force | Out-Null }'
```

If the write fails (e.g. profile path read-only): tell user the $PROFILE path and the exact block to paste manually, then stop.

## Step 7: Smoke-test bridge (TCP-port probe, not HTTP)

Bridge has no /health endpoint — probe port 8787 instead. The entire smoke test runs in **one** PowerShell process so the PID variable survives across launch/probe/cleanup (Claude's Bash tool starts a fresh shell per command block, so we can't split this across multiple bash blocks).

```bash
powershell -NoProfile -Command '
$latestDir = (Get-ChildItem (Join-Path $HOME ".claude\plugins\cache\cc-relay\cc-relay") -Directory | Where-Object { $_.Name -match "^\d+(\.\d+)+$" } | Sort-Object { [version]$_.Name } -Descending | Select-Object -First 1).FullName
$ps1 = Join-Path $latestDir "scripts\launch_bridge.ps1"
$proc = Start-Process powershell -ArgumentList "-ExecutionPolicy","Bypass","-NoProfile","-File",$ps1 -WindowStyle Hidden -PassThru
Start-Sleep -Seconds 3
$result = "FAIL"
try {
    $c = New-Object System.Net.Sockets.TcpClient
    $c.Connect("127.0.0.1", 8787)
    $c.Close()
    $result = "OK"
} catch { }
Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
Write-Host "smoke=$result pid=$($proc.Id)"
'
```

Parse the output line `smoke=OK pid=NNNN` or `smoke=FAIL pid=NNNN`.

If `smoke=OK`: report success and move to Final report.

If `smoke=FAIL`: diagnose what's holding port 8787:

```bash
powershell -NoProfile -Command 'Get-NetTCPConnection -LocalPort 8787 -State Listen -ErrorAction SilentlyContinue | Format-Table OwningProcess, State'
```

- If output shows a process holding 8787, tell the user the PID and suggest killing it. Then stop.
- If output is empty (port not held by anyone), the bridge crashed at launch. Tell the user: "Bridge failed to start. Re-run `/cc-relay:setup` (Step 3 reinstalls dependencies), or check that `python -c \"import fastapi, uvicorn, lark_oapi\"` succeeds." Then stop.

## Final report

If all 7 steps pass, tell the user verbatim:

> ✅ CC Relay setup complete.
>
> **Next steps:**
> 1. **Close this Claude session and open a fresh PowerShell window** — the $PROFILE shim only loads at PowerShell startup.
> 2. Start the bridge once per session (in a separate window):
>    powershell -ExecutionPolicy Bypass -File <plugin>\scripts\launch_bridge.ps1
> 3. In your project window:
>
>    ```powershell
>    Enable-ClaudeBridge
>    cd E:\YourProject
>    claude
>    ```
>
> 4. Anytime, check status with /cc-relay:status.

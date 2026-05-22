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

## Step 6: Install shim block into PowerShell profiles (both PS 5.1 and PS 7)

CC Relay supports both Windows PowerShell 5.1 (`powershell.exe`) and PowerShell 7+ (`pwsh.exe`). Each edition has its own `$PROFILE` path — both should receive the shim so users on either edition get the `claude` / `Enable-ClaudeBridge` functions on shell start. (Earlier setup runs wrote only to the 5.1 profile because `powershell -NoProfile -Command '$PROFILE'` always resolves to the 5.1 path, leaving PS 7 users without the shim.)

The two target paths are:
- PS 5.1: `~/Documents/WindowsPowerShell/Microsoft.PowerShell_profile.ps1`
- PS 7+:  `~/Documents/PowerShell/Microsoft.PowerShell_profile.ps1`

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

Compute both paths and ensure parent dirs / files exist:

```bash
powershell -NoProfile -Command '
$paths = @(
    (Join-Path $HOME "Documents\WindowsPowerShell\Microsoft.PowerShell_profile.ps1"),
    (Join-Path $HOME "Documents\PowerShell\Microsoft.PowerShell_profile.ps1")
)
foreach ($p in $paths) {
    $dir = Split-Path -Parent $p
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    if (-not (Test-Path $p))   { New-Item -ItemType File -Path $p -Force | Out-Null }
    Write-Output "PROFILE:$p"
}
'
```

This prints two `PROFILE:<path>` lines. For **each** path independently:

1. Read the file content via the Read tool.
2. Search for the marker `# >>> claude-bridge shim >>>`.
3. **Marker present:** replace the entire block from `# >>> claude-bridge shim >>>` through `# <<< claude-bridge shim <<<` (inclusive) with the new block above. Idempotent — ensures users on older plugin versions get the latest shim logic on re-run.
4. **Marker absent:** append the full shim block above. Prepend a single blank line as separator if the existing file is non-empty.
5. Use the Write tool (full file rewrite) or Edit tool (targeted block replace) to persist.

If a write fails for one path (e.g. read-only), report the failing path and the exact block for the user to paste manually, then continue with the other path. Do not abort the whole setup on a single profile failure — partial success is still useful.

After both writes, report: "Shim installed to N of 2 profiles" (N = 0, 1, or 2).

## Step 7: Smoke-test bridge (TCP-port probe, not HTTP)

Bridge has no /health endpoint — probe port 8787 instead. The entire smoke test runs in **one** PowerShell process so PID variables survive across launch/probe/cleanup (Claude's Bash tool starts a fresh shell per command block, so we can't split this across multiple bash blocks).

Bridge cold-start can take 15-60s (the `lark_oapi` SDK import chain is slow), so probe in a poll loop up to 75s rather than a single fixed sleep. After probing, kill **both** the PowerShell wrapper AND its `python.exe` child — `Stop-Process` on the wrapper does not cascade, leaving an orphaned bridge holding port 8787.

```bash
powershell -NoProfile -Command '
$latestDir = (Get-ChildItem (Join-Path $HOME ".claude\plugins\cache\cc-relay\cc-relay") -Directory | Where-Object { $_.Name -match "^\d+(\.\d+)+$" } | Sort-Object { [version]$_.Name } -Descending | Select-Object -First 1).FullName
$ps1 = Join-Path $latestDir "scripts\launch_bridge.ps1"
$proc = Start-Process powershell -ArgumentList "-ExecutionPolicy","Bypass","-NoProfile","-File",$ps1 -WindowStyle Hidden -PassThru
$result = "FAIL"
$elapsed = 0
for ($i = 1; $i -le 75; $i++) {
    Start-Sleep -Seconds 1
    try {
        $c = New-Object System.Net.Sockets.TcpClient
        $c.Connect("127.0.0.1", 8787)
        $c.Close()
        $result = "OK"
        $elapsed = $i
        break
    } catch { }
}
Get-CimInstance Win32_Process -Filter "name=''python.exe''" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*main.py*" -and $_.ParentProcessId -eq $proc.Id } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
Write-Host "smoke=$result pid=$($proc.Id) elapsed=${elapsed}s"
'
```

Parse the output line `smoke=OK pid=NNNN elapsed=NNs` or `smoke=FAIL pid=NNNN elapsed=0s`.

If `smoke=OK`: report success and move to Final report.

If `smoke=FAIL`: diagnose what's holding port 8787:

```bash
powershell -NoProfile -Command 'Get-NetTCPConnection -LocalPort 8787 -State Listen -ErrorAction SilentlyContinue | Format-Table OwningProcess, State'
```

- If output shows a process holding 8787, tell the user the PID and suggest killing it. Then stop.
- If output is empty (port not held by anyone), the bridge crashed at launch. Tell the user: "Bridge failed to start. Re-run `/cc-relay:setup` (Step 3 reinstalls dependencies), or check that `python -c \"import fastapi, uvicorn, lark_oapi\"` succeeds." Then stop.

## Final report

If all 7 steps pass, first resolve the absolute path of `launch_bridge.ps1` in the latest installed plugin version (so the Next-steps block prints a real path, not a placeholder):

```bash
powershell -NoProfile -Command '
$dir = (Get-ChildItem (Join-Path $HOME ".claude\plugins\cache\cc-relay\cc-relay") -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match "^\d+(\.\d+)+$" } |
        Sort-Object { [version]$_.Name } -Descending |
        Select-Object -First 1).FullName
if ($dir) { Write-Output "LAUNCH_BRIDGE:$dir\scripts\launch_bridge.ps1" }
else      { Write-Output "LAUNCH_BRIDGE:(no plugin install found)" }
'
```

Strip the `LAUNCH_BRIDGE:` prefix and substitute the captured path for `<launch-bridge-path>` below.

Then tell the user verbatim (with the path substituted):

> ✅ CC Relay setup complete.
>
> **Next steps:**
> 1. **Close this Claude session and open a fresh PowerShell window** — the $PROFILE shim only loads at PowerShell startup.
> 2. Start the bridge once per session (in a separate window):
>    powershell -ExecutionPolicy Bypass -File <launch-bridge-path>
> 3. In your project window:
>
>    ```powershell
>    Enable-ClaudeBridge
>    cd E:\YourProject
>    claude
>    ```
>
> 4. Anytime, check status with /cc-relay:status.

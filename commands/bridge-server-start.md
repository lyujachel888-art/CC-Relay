---
description: Start the CC Relay bridge (FastAPI :8787) in a detached PowerShell window
allowed-tools: Bash
---

You are starting the CC Relay bridge — the long-running FastAPI server + Feishu WebSocket client that listens on `127.0.0.1:8787`.

## Step 1: Pre-check (skip if already running)

```bash
powershell -NoProfile -Command '$p = (Get-NetTCPConnection -LocalPort 8787 -State Listen -EA SilentlyContinue).OwningProcess; if ($p) { Write-Output "ALREADY_RUNNING:$p" } else { Write-Output "NOT_RUNNING" }'
```

If output starts with `ALREADY_RUNNING:`, report to the user verbatim:

> Bridge is already running (PID: \<pid>). Use `/cc-relay:bridge-server-stop` if you want to restart.

…then stop. Do not launch a second instance.

## Step 2: Resolve + launch + poll

Otherwise launch the bridge in a detached PowerShell window and poll TCP 8787 for up to 75s (cold-start can take 15-60s due to `lark_oapi` import chain). Kill nothing in this script — bridge should stay alive after this command returns.

```bash
powershell -NoProfile -Command '
$dir = (Get-ChildItem (Join-Path $HOME ".claude\plugins\cache\cc-relay\cc-relay") -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match "^\d+(\.\d+)+$" } |
        Sort-Object { [version]$_.Name } -Descending |
        Select-Object -First 1).FullName
if (-not $dir) { Write-Output "result=NO_PLUGIN"; exit }
$ps1 = Join-Path $dir "scripts\launch_bridge.ps1"
$proc = Start-Process powershell -ArgumentList "-NoProfile","-ExecutionPolicy","Bypass","-File",$ps1 -PassThru
$result = "TIMEOUT"
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
Write-Output "result=$result pid=$($proc.Id) elapsed=${elapsed}s path=$ps1"
'
```

## Step 3: Report

Parse the output line `result=... pid=... elapsed=...s path=...`:

| `result` | Report |
|---|---|
| `OK` | ✅ Bridge started (PID \<pid>, bound port 8787 in \<elapsed>s). Tail log at `<path-dir>\bridge\bridge.log` if you want to watch activity. |
| `TIMEOUT` | ⚠️ Bridge process launched (PID \<pid>) but didn't bind port 8787 within 75s. Either still loading or crashed. Check `<path>` for errors or run `/cc-relay:status` in a few seconds. |
| `NO_PLUGIN` | ❌ No `cc-relay` plugin install found under `~/.claude/plugins/cache/cc-relay/cc-relay/`. Run `/cc-relay:setup` first. |

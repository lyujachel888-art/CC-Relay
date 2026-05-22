---
description: Stop the CC Relay bridge — kills python child and clears port 8787
allowed-tools: Bash
---

You are stopping the CC Relay bridge. The bridge is a `python.exe main.py` process (often spawned inside a `powershell.exe` wrapper that started it). `Stop-Process` on the powershell wrapper does NOT cascade to the python child, so this command must explicitly enumerate and kill both.

## Step 1: Kill bridge processes

```bash
powershell -NoProfile -Command '
$killed = 0
Get-CimInstance Win32_Process -Filter "name=''python.exe''" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*main.py*" } |
    ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        $killed++
    }
Get-NetTCPConnection -LocalPort 8787 -State Listen -ErrorAction SilentlyContinue |
    ForEach-Object {
        Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
        $killed++
    }
Write-Output "killed=$killed"
'
```

## Step 2: Report

Parse `killed=N`:

| `N` | Report |
|---|---|
| `0` | Bridge was not running — nothing to stop. |
| `>0` | ✅ Stopped \<N> process(es). Port 8787 should be free now. |

Do NOT also kill any `wrapper.py` processes — those belong to active `claude` sessions and the user manages their lifecycle separately (Ctrl+C in the claude window, or `Disable-ClaudeBridge` + restart claude).

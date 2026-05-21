---
description: Check CC Relay installation and runtime health (read-only)
allowed-tools: Bash, Read
---

You are running the CC Relay status check. Perform all checks **read-only** — never modify files, never start/stop processes. Output a single status table at the end.

## Checks to perform

Collect results into 4 groups; for each group, run the listed commands and tally ✅ / ❌ per row.

All PowerShell snippets are wrapped in single-quoted bash strings so `$env:VAR`, `$HOME`, `$PROFILE` reach PowerShell unexpanded.

### Environment

| Check | Command | Pass criteria |
|---|---|---|
| Platform | `python -c "import os, sys; sys.exit(0 if os.name == 'nt' else 1)"` | exit 0 |
| Python version | `python --version` | output contains `3.11` or higher |
| pywinpty installed | `python -m pip show pywinpty` | exit 0; capture Version field |
| claude.exe found | `powershell -NoProfile -Command '(Get-Command claude.exe -EA SilentlyContinue).Source'` | non-empty output (also check `$env:CLAUDE_EXE` and `$env:LOCALAPPDATA\AnthropicClaude\claude.exe` as fallbacks via separate PS commands) |

### Configuration

| Check | Command | Pass criteria |
|---|---|---|
| Plugin .env exists | `powershell -NoProfile -Command 'Test-Path (Join-Path $HOME ".claude\plugins\cc-relay\.env")'` | `True` |
| FEISHU_APP_ID set | Read the .env file with Read tool; grep `^FEISHU_APP_ID=.+` | match |
| FEISHU_APP_SECRET set | grep `^FEISHU_APP_SECRET=.+` | match |
| FEISHU_USER_OPEN_ID set | grep `^FEISHU_USER_OPEN_ID=.+` | match |

### Shim

| Check | Command | Pass criteria |
|---|---|---|
| `$PROFILE` has shim block | `powershell -NoProfile -Command 'if (Test-Path $PROFILE) { Select-String -Path $PROFILE -Pattern "claude-bridge shim" -Quiet }'` | `True` |
| `$env:CLAUDE_BRIDGE` value | `powershell -NoProfile -Command '$env:CLAUDE_BRIDGE'` | report value (`1`, `0`, or empty) |

### Runtime

| Check | Command | Pass criteria |
|---|---|---|
| Bridge port 8787 listen | `powershell -NoProfile -Command '(Get-NetTCPConnection -LocalPort 8787 -State Listen -EA SilentlyContinue).OwningProcess'` | non-empty PID = LISTENING |
| Wrapper port 8788 listen | `powershell -NoProfile -Command '(Get-NetTCPConnection -LocalPort 8788 -State Listen -EA SilentlyContinue).OwningProcess'` | non-empty PID = LISTENING |
| Wrapper console window | `powershell -NoProfile -Command '(Get-Process \| Where-Object MainWindowTitle -like "云匣-*").Count'` | `>= 1` |

## Output format

After collecting all results, print **exactly** this layout (substitute actual values; show ✅ for pass, ❌ for fail, with the captured value next to it):

```
CC Relay Status

Environment
  Platform:                 Windows  ✅
  Python:                   3.11.5   ✅
  pywinpty:                 2.0.13   ✅
  claude.exe:               C:\Users\Jachel\.local\bin\claude.exe  ✅

Configuration
  ~/.claude/plugins/cc-relay/.env exists:   ✅
  FEISHU_APP_ID set:                        ✅
  FEISHU_APP_SECRET set:                    ✅
  FEISHU_USER_OPEN_ID set:                  ✅

Shim
  $PROFILE has cc-relay block:              ✅
  $env:CLAUDE_BRIDGE current value:         "1"

Runtime
  Port 8787 (bridge HTTP):                  LISTENING (pid 12345)
  Port 8788 (wrapper inject):               LISTENING (pid 67890)
  Console window "云匣-*":                  FOUND

Suggestions
  ✅ Everything looks good.
```

## Suggestions section

For each ❌ row, add a one-line suggestion under "Suggestions":

| Failed check | Suggestion |
|---|---|
| Platform != Windows | "Not Windows. CC Relay does not support this OS." |
| Python < 3.11 | "Upgrade Python to 3.11+ from python.org" |
| pywinpty missing | "Run /cc-relay:setup to install pywinpty" |
| claude.exe missing | "Install Claude Code (https://claude.com/code), then re-run /cc-relay:setup" |
| .env missing or incomplete | "Run /cc-relay:setup to configure Feishu credentials" |
| $PROFILE missing shim | "Run /cc-relay:setup to install the shim into your PowerShell profile" |
| Port 8787 not listening | "Bridge not running. Start with: powershell -ExecutionPolicy Bypass -File <plugin>/scripts/launch_bridge.ps1" |
| Port 8788 not listening | "Wrapper not running. Open a PowerShell, Enable-ClaudeBridge, then claude" |
| Console window absent | "No wrapper window with title '云匣-*' found — same as port 8788 case" |

If all rows pass, write `✅ Everything looks good.` under Suggestions.

**Important:** Do NOT take any corrective action. This command is observation-only. Users decide what to fix.

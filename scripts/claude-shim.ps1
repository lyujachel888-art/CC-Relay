# PowerShell function that overrides `claude` to optionally route through
# the feishu-bridge wrapper. Toggle per-window with $env:CLAUDE_BRIDGE.
#
# Dot-source this file from your $PROFILE to enable:
#     . "E:\MyProject\RC\scripts\claude-shim.ps1"
#
# Or run scripts\install-claude-shim.ps1 once to wire it into $PROFILE.

$global:ClaudeBridgeWrapperScript = "E:\MyProject\RC\scripts\launch_claude_wrapper.ps1"
$global:ClaudeBridgeExe           = "C:\Users\Jachel\.local\bin\claude.exe"

function global:claude {
    [CmdletBinding()]
    param([Parameter(ValueFromRemainingArguments = $true)] $ArgsForClaude)

    $on = $env:CLAUDE_BRIDGE
    if ($on -eq '1' -or $on -eq 'on' -or $on -eq 'true') {
        # Wrapper path. The wrapper currently ignores extra args — surface a
        # one-line warning if any were passed so the user notices.
        if ($ArgsForClaude -and $ArgsForClaude.Count -gt 0) {
            Write-Host "[bridge] note: wrapper does not forward args ($ArgsForClaude) yet" -ForegroundColor Yellow
        }
        & $global:ClaudeBridgeWrapperScript
    }
    else {
        & $global:ClaudeBridgeExe @ArgsForClaude
    }
}

function global:Enable-ClaudeBridge {
    $env:CLAUDE_BRIDGE = '1'
    Write-Host "[bridge] CLAUDE_BRIDGE=1 — next `claude` will route through wrapper" -ForegroundColor Green
}

function global:Disable-ClaudeBridge {
    $env:CLAUDE_BRIDGE = '0'
    Write-Host "[bridge] CLAUDE_BRIDGE=0 — next `claude` will be native claude.exe" -ForegroundColor Green
}

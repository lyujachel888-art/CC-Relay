# PowerShell function that overrides `claude` to optionally route through
# the cc-relay wrapper. Toggle per-window with $env:CLAUDE_BRIDGE.
#
# Dot-source this file from your $PROFILE to enable. The cc-relay plugin's
# /cc-relay:setup command writes a dynamic-version-lookup snippet into your
# $PROFILE that dot-sources whichever version is currently installed.

# wrapper launcher path: derived from this script's own location so the shim
# survives if the CC-Relay repo (or plugin cache version) moves.
$global:ClaudeBridgeWrapperScript = Join-Path $PSScriptRoot 'launch_claude_wrapper.ps1'

# claude.exe discovery, matching wrapper.py:_find_claude() priority:
#   1. $env:CLAUDE_EXE (user override)
#   2. PATH (Get-Command claude.exe)
#   3. %LOCALAPPDATA%\AnthropicClaude\claude.exe (default install)
function global:Resolve-ClaudeExe {
    if ($env:CLAUDE_EXE -and (Test-Path $env:CLAUDE_EXE)) {
        return $env:CLAUDE_EXE
    }
    $cmd = Get-Command claude.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    if ($env:LOCALAPPDATA) {
        $localCandidate = Join-Path $env:LOCALAPPDATA 'AnthropicClaude\claude.exe'
        if (Test-Path $localCandidate) { return $localCandidate }
    }
    return $null
}

function global:Get-CCBridgeMode {
    <#
    .SYNOPSIS
    Resolves which bridge mode applies to the current project.

    .DESCRIPTION
    Returns one of:
      - 'env-on'  : $env:CLAUDE_BRIDGE is set to a truthy value, overriding marker
      - 'env-off' : $env:CLAUDE_BRIDGE is set to a falsy value, overriding marker
      - 'on'      : no env var; marker file present at project root
      - 'off'     : no env var; no marker file

    Project root is `git rev-parse --show-toplevel` of current directory,
    falling back to (Get-Location).Path if not in a git repo or git unavailable.
    #>
    $envVal = $env:CLAUDE_BRIDGE
    if ($envVal -in '1','on','true')  { return 'env-on'  }
    if ($envVal -in '0','off','false') { return 'env-off' }

    $root = $null
    try { $root = (git rev-parse --show-toplevel 2>$null) } catch { }
    if (-not $root) { $root = (Get-Location).Path }

    $marker = Join-Path $root '.cc-relay-mode'
    if (Test-Path $marker) { return 'on' } else { return 'off' }
}

function global:claude {
    [CmdletBinding()]
    param([Parameter(ValueFromRemainingArguments = $true)] $ArgsForClaude)

    $on = $env:CLAUDE_BRIDGE
    if ($on -eq '1' -or $on -eq 'on' -or $on -eq 'true') {
        # Bridge mode: hand off to wrapper. Set CLAUDE_CWD explicitly so the
        # wrapper spawns claude in the user's current directory.
        $env:CLAUDE_CWD = (Get-Location).Path
        if ($ArgsForClaude -and $ArgsForClaude.Count -gt 0) {
            Write-Host "[bridge] note: wrapper does not forward args ($ArgsForClaude) yet" -ForegroundColor Yellow
        }
        & $global:ClaudeBridgeWrapperScript
    }
    else {
        # Native mode: discover claude.exe and run it directly.
        $exe = Resolve-ClaudeExe
        if (-not $exe) {
            Write-Host "[bridge] claude.exe not found. Set `$env:CLAUDE_EXE or add claude to PATH." -ForegroundColor Red
            return
        }
        & $exe @ArgsForClaude
    }
}

function global:Enable-ClaudeBridge {
    $env:CLAUDE_BRIDGE = '1'
    Write-Host "[bridge] CLAUDE_BRIDGE=1 — next claude will route through wrapper" -ForegroundColor Green
}

function global:Disable-ClaudeBridge {
    $env:CLAUDE_BRIDGE = '0'
    Write-Host "[bridge] CLAUDE_BRIDGE=0 — next claude will be native claude.exe" -ForegroundColor Green
}

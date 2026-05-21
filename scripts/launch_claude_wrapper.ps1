# Launch Claude Code wrapped in a ConPTY so the bridge can inject input.
# Usage: double-click, or run from PowerShell: .\scripts\launch_claude_wrapper.ps1
$ErrorActionPreference = "Stop"

# Capture the caller's PWD BEFORE chdir; only set if upstream (shim) didn't set it.
# Wrapper.py reads $env:CLAUDE_CWD; this is the "user double-clicks the ps1" path.
if (-not $env:CLAUDE_CWD) {
    $env:CLAUDE_CWD = (Get-Location).Path
}

$WrapperDir = Join-Path (Split-Path -Parent $PSScriptRoot) "wrapper"
Set-Location $WrapperDir
python wrapper.py

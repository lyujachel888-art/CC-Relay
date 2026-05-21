param(
    [string]$Id,
    [string]$Name
)
$ErrorActionPreference = "Stop"

# scripts/launch_claude_wrapper.ps1
# Launch the Claude Code wrapper. ConPTY-based; bridge can inject input.
# Usage:
#   .\scripts\launch_claude_wrapper.ps1                          # auto-derive id from cwd
#   .\scripts\launch_claude_wrapper.ps1 -Id wrapper-rc -Name RC  # explicit id/name

# Capture the caller's PWD BEFORE chdir; only set if upstream (shim) didn't set it.
# Wrapper.py reads $env:CLAUDE_CWD; this is the "user double-clicks the ps1" path.
if (-not $env:CLAUDE_CWD) {
    $env:CLAUDE_CWD = (Get-Location).Path
}

$WrapperDir = Join-Path (Split-Path -Parent $PSScriptRoot) "wrapper"
Set-Location $WrapperDir

$ArgList = @()
if ($Id)   { $ArgList += @("--id", $Id) }
if ($Name) { $ArgList += @("--name", $Name) }

python wrapper.py @ArgList

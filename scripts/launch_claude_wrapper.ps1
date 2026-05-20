# Launch Claude Code wrapped in a ConPTY so the bridge can inject input.
# Usage: double-click, or run from Windows Terminal: .\scripts\launch_claude_wrapper.ps1
$ErrorActionPreference = "Stop"

$WrapperDir = Join-Path (Split-Path -Parent $PSScriptRoot) "wrapper"
Set-Location $WrapperDir
python wrapper.py

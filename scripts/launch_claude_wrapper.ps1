# Launch Claude Code wrapped in a ConPTY so the bridge can inject input.
# Usage: double-click, or run from Windows Terminal: .\scripts\launch_claude_wrapper.ps1
$ErrorActionPreference = "Stop"

$WrapperDir = "E:\MyProject\RC\wrapper"
$ClaudeExe = "C:\Users\Jachel\.local\bin\claude.exe"

if (-not (Test-Path $ClaudeExe)) {
    Write-Host "ERROR: claude.exe not found at $ClaudeExe" -ForegroundColor Red
    exit 2
}

# Run wrapper in the current console — it takes over stdin/stdout
Set-Location $WrapperDir
python wrapper.py

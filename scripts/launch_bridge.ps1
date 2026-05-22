# Launch cc-relay bridge (FastAPI + Feishu long-conn) on Windows.
# Usage: powershell -ExecutionPolicy Bypass -File scripts\launch_bridge.ps1
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$BridgeDir = Join-Path $RepoRoot "bridge"
$Python = Join-Path $BridgeDir ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    # No venv — fall back to system Python (plugin install path; handoff §5.6).
    $sys = Get-Command python -ErrorAction SilentlyContinue
    if ($sys) {
        $Python = $sys.Source
    } else {
        Write-Host "ERROR: neither bridge/.venv nor 'python' on PATH" -ForegroundColor Red
        Write-Host "  dev clone:      cd bridge; python -m venv .venv; .venv\Scripts\pip install -r requirements.txt" -ForegroundColor Yellow
        Write-Host "  plugin install: ensure python is on PATH (/cc-relay:setup Step 3 handles deps)" -ForegroundColor Yellow
        exit 1
    }
}

Set-Location $BridgeDir
& $Python -u main.py

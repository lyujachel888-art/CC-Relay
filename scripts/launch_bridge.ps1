# Launch cc-relay bridge (FastAPI + Feishu long-conn) on Windows.
# Usage: powershell -ExecutionPolicy Bypass -File scripts\launch_bridge.ps1
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$BridgeDir = Join-Path $RepoRoot "bridge"
$Python = Join-Path $BridgeDir ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    Write-Host "ERROR: venv not found at $Python" -ForegroundColor Red
    Write-Host "Run once to set up:" -ForegroundColor Yellow
    Write-Host "  cd bridge" -ForegroundColor Yellow
    Write-Host "  python -m venv .venv" -ForegroundColor Yellow
    Write-Host "  .venv\Scripts\pip install -r requirements.txt" -ForegroundColor Yellow
    exit 1
}

Set-Location $BridgeDir
& $Python -u main.py

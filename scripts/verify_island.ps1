# Dynamic Island Acceptance Test
#
# Manual end-to-end check after implementation. Requires:
#   - bridge running (`python bridge/main.py`)
#   - One or more wrapper instances running in their own Windows Terminal windows
#   - Tauri dev mode running (`cd island; npm run tauri dev`)
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts/verify_island.ps1

$ErrorActionPreference = "Stop"
$BridgeUrl = "http://127.0.0.1:8787"
$TokenPath = "hooks/.bridge_token"

if (-not (Test-Path $TokenPath)) {
    Write-Host "[FAIL] Token file not found: $TokenPath. Run bridge once to generate it." -ForegroundColor Red
    exit 1
}
$tok = (Get-Content $TokenPath).Trim()
Write-Host "[OK] Token loaded ($($tok.Length) chars)" -ForegroundColor Green

# ---------- 1. Bridge reachable ----------
Write-Host ""
Write-Host "[1/6] Bridge health check..." -ForegroundColor Cyan
try {
    $r = Invoke-WebRequest -Uri "$BridgeUrl/" -UseBasicParsing -TimeoutSec 2 -ErrorAction SilentlyContinue
} catch {
    # Bridge has no GET / — any response (including 404) means it's up
}
$listening = (Get-NetTCPConnection -LocalPort 8787 -ErrorAction SilentlyContinue) -ne $null
if ($listening) {
    Write-Host "  [OK] Bridge listening on :8787" -ForegroundColor Green
} else {
    Write-Host "  [FAIL] Bridge not listening on :8787. Run: python bridge/main.py" -ForegroundColor Red
    exit 1
}

# ---------- 2. SSE endpoint ----------
Write-Host ""
Write-Host "[2/6] SSE endpoint /events..." -ForegroundColor Cyan
$sseTest = Invoke-WebRequest -Uri "$BridgeUrl/events" -Method GET -TimeoutSec 1 -UseBasicParsing -ErrorAction SilentlyContinue
if ($sseTest.Headers["Content-Type"] -like "text/event-stream*" -or $sseTest.StatusCode -eq 200) {
    Write-Host "  [OK] /events responds with SSE content-type" -ForegroundColor Green
} else {
    Write-Host "  [WARN] /events response shape unexpected (status=$($sseTest.StatusCode))" -ForegroundColor Yellow
}

# ---------- 3. Inject events to multiple projects ----------
Write-Host ""
Write-Host "[3/6] Sending tool_use events to RC, X, Y..." -ForegroundColor Cyan
foreach ($p in @("RC","X","Y")) {
    $body = @{ text = "[$p] Bash: ls -la" } | ConvertTo-Json -Compress
    try {
        Invoke-RestMethod -Uri "$BridgeUrl/hook/tool_use" `
            -Method POST `
            -Headers @{ "Authorization" = "Bearer $tok"; "Content-Type" = "application/json" } `
            -Body $body -TimeoutSec 2 | Out-Null
        Write-Host "  [OK] sent tool_use for $p" -ForegroundColor Green
    } catch {
        Write-Host "  [FAIL] sending event for $p: $_" -ForegroundColor Red
    }
}
Write-Host "  -> HUD should now show 3 rows (RC, X, Y) with running cats" -ForegroundColor Gray

Start-Sleep -Seconds 2

# ---------- 4. Trigger bash failure ----------
Write-Host ""
Write-Host "[4/6] Triggering bash failure on RC..." -ForegroundColor Cyan
$body = @{ text = "[RC] `$ pytest"; meta = "fail" } | ConvertTo-Json -Compress
Invoke-RestMethod -Uri "$BridgeUrl/hook/bash_result" `
    -Method POST `
    -Headers @{ "Authorization" = "Bearer $tok"; "Content-Type" = "application/json" } `
    -Body $body -TimeoutSec 2 | Out-Null
Write-Host "  [OK] sent bash_result fail" -ForegroundColor Green
Write-Host "  -> RC row should now pulse red (whole row background)" -ForegroundColor Gray

Start-Sleep -Seconds 2

# ---------- 5. Trigger assistant_reply for recap ----------
Write-Host ""
Write-Host "[5/6] Triggering assistant_reply on X (sets recap)..." -ForegroundColor Cyan
$reply = @"
[X] Done — refactored 3 files:
  - bridge/server.py
  - bridge/event_broadcast.py
  - tests/test_server.py
"@
$body = @{ text = $reply; meta = "8.2s · 1137tok" } | ConvertTo-Json -Compress
Invoke-RestMethod -Uri "$BridgeUrl/hook/assistant_reply" `
    -Method POST `
    -Headers @{ "Authorization" = "Bearer $tok"; "Content-Type" = "application/json" } `
    -Body $body -TimeoutSec 2 | Out-Null
Write-Host "  [OK] X now has recap stored" -ForegroundColor Green
Write-Host "  -> Right-click X row to expand the recap panel" -ForegroundColor Gray

# ---------- 6. Wrapper title check ----------
Write-Host ""
Write-Host "[6/6] Wrapper title presence..." -ForegroundColor Cyan
$titles = Get-Process | Where-Object MainWindowTitle -Like 'cc-bridge-wrapper-*' | Select-Object -ExpandProperty MainWindowTitle -Unique
if ($titles) {
    Write-Host "  [OK] Found wrapper windows:" -ForegroundColor Green
    $titles | ForEach-Object { Write-Host "    - $_" -ForegroundColor Gray }
    Write-Host "  -> Click any row in the HUD to focus the matching window" -ForegroundColor Gray
} else {
    Write-Host "  [WARN] No cc-bridge-wrapper-* windows found." -ForegroundColor Yellow
    Write-Host "         Start one with: cd <project>; python E:/MyProject/RC/wrapper/wrapper.py" -ForegroundColor Gray
}

# ---------- Summary ----------
Write-Host ""
Write-Host "======================================" -ForegroundColor Cyan
Write-Host "  Manual checks remaining:" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host "  [ ] Drag the HUD to a new position, close it, reopen — position persists" -ForegroundColor Gray
Write-Host "  [ ] Wait 30s without sending events — RC/X/Y rows go gray (idle)" -ForegroundColor Gray
Write-Host "  [ ] Click a row — corresponding Windows Terminal pops to foreground" -ForegroundColor Gray
Write-Host "  [ ] Right-click X row — RecapPanel expands below" -ForegroundColor Gray
Write-Host "  [ ] Tray icon (near clock) toggles HUD visibility on click" -ForegroundColor Gray
Write-Host "  [ ] Task Manager: island.exe < 30 MB private working set, < 3% CPU" -ForegroundColor Gray
Write-Host ""

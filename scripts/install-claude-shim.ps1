# Adds a dot-source line for claude-shim.ps1 to your PowerShell $PROFILE,
# so the `claude` function (and Enable-ClaudeBridge / Disable-ClaudeBridge)
# are available in every new PowerShell window.
#
# Idempotent — running this multiple times only adds the line once.

$ErrorActionPreference = "Stop"

$shimPath = "E:\MyProject\RC\scripts\claude-shim.ps1"
if (-not (Test-Path $shimPath)) {
    Write-Host "ERROR: shim not found at $shimPath" -ForegroundColor Red
    exit 1
}

$marker = "# >>> claude-bridge shim >>>"
$line   = ". `"$shimPath`""

# Make sure $PROFILE file exists
if (-not (Test-Path $PROFILE)) {
    New-Item -ItemType File -Path $PROFILE -Force | Out-Null
    Write-Host "[install] created profile at $PROFILE"
}

$profileText = Get-Content -Raw -Path $PROFILE -ErrorAction SilentlyContinue
if ($null -eq $profileText) { $profileText = "" }

if ($profileText -match [regex]::Escape($marker)) {
    Write-Host "[install] already installed in $PROFILE — nothing to do" -ForegroundColor Yellow
} else {
    $block = @"

$marker
$line
# <<< claude-bridge shim <<<
"@
    Add-Content -Path $PROFILE -Value $block -Encoding UTF8
    Write-Host "[install] added shim hook to $PROFILE" -ForegroundColor Green
}

Write-Host ""
Write-Host "Usage in any new PowerShell window:" -ForegroundColor Cyan
Write-Host '    Enable-ClaudeBridge     # this window uses wrapper'
Write-Host '    claude                  # → routed through wrapper'
Write-Host '    Disable-ClaudeBridge    # back to native'
Write-Host ""
Write-Host "Activate now in THIS window without restarting:" -ForegroundColor Cyan
Write-Host "    . `"$shimPath`""

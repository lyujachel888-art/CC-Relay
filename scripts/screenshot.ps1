# Windows-side screenshot helper. Called by bridge (running in WSL) via
# powershell.exe to capture either a specific window (by partial title match)
# or, if no match, the whole primary screen.
#
# Usage: powershell.exe -NoProfile -ExecutionPolicy Bypass -File screenshot.ps1
#                       -OutPath "E:\path\out.png" [-TitleSubstring "Claude Code"]
# Author: jachel.lyu

param(
    [Parameter(Mandatory=$true)][string]$OutPath,
    [string]$TitleSubstring = ""
)

$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Text;

public class WinAPI {
    [StructLayout(LayoutKind.Sequential)]
    public struct RECT { public int Left, Top, Right, Bottom; }

    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);

    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetWindowTextW(IntPtr hWnd, StringBuilder lpString, int nMaxCount);
    [DllImport("user32.dll")] public static extern int GetWindowTextLengthW(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr hWnd, IntPtr hdcBlt, uint nFlags);
    [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
}
"@

function Find-WindowByTitle([string]$needle) {
    $script:found = [IntPtr]::Zero
    $cb = [WinAPI+EnumWindowsProc]{
        param($hWnd, $lParam)
        if (-not [WinAPI]::IsWindowVisible($hWnd)) { return $true }
        $len = [WinAPI]::GetWindowTextLengthW($hWnd)
        if ($len -le 0) { return $true }
        $sb = New-Object System.Text.StringBuilder ($len + 1)
        [WinAPI]::GetWindowTextW($hWnd, $sb, $sb.Capacity) | Out-Null
        if ($sb.ToString() -like "*$needle*") {
            $script:found = $hWnd
            return $false   # stop enumerating
        }
        return $true
    }
    [WinAPI]::EnumWindows($cb, [IntPtr]::Zero) | Out-Null
    return $script:found
}

# Pick target.
$hwndInt = 0
$rect = New-Object 'WinAPI+RECT'
if ($TitleSubstring -ne "") {
    $hwnd = Find-WindowByTitle $TitleSubstring
    try { $hwndInt = [int64]$hwnd.ToInt64() } catch { try { $hwndInt = [int64]$hwnd } catch { $hwndInt = 0 } }
    if ($hwndInt -ne 0) {
        [WinAPI]::GetWindowRect([IntPtr]$hwndInt, [ref]$rect) | Out-Null
    }
}

if ($hwndInt -eq 0) {
    # Full-screen fallback.
    $b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
    $rect.Left = $b.Left; $rect.Top = $b.Top
    $rect.Right = $b.Right; $rect.Bottom = $b.Bottom
}

# Temporarily restore minimized window so PrintWindow has content to capture.
$wasMinimized = $false
if ($hwndInt -ne 0) {
    $wasMinimized = [WinAPI]::IsIconic([IntPtr]$hwndInt)
    if ($wasMinimized) {
        [WinAPI]::ShowWindow([IntPtr]$hwndInt, 9) | Out-Null   # SW_RESTORE
        Start-Sleep -Milliseconds 350
        [WinAPI]::GetWindowRect([IntPtr]$hwndInt, [ref]$rect) | Out-Null
    }
}

$w = $rect.Right - $rect.Left
$h = $rect.Bottom - $rect.Top
if ($w -le 0 -or $h -le 0) {
    Write-Error "invalid rect: $w x $h"
    exit 2
}

$bmp = New-Object System.Drawing.Bitmap $w, $h
$g   = [System.Drawing.Graphics]::FromImage($bmp)

$ok = $false
if ($hwndInt -ne 0) {
    # PrintWindow with PW_RENDERFULLCONTENT (0x2) — draws the actual window
    # contents even if it's hidden / covered by other windows. Available on
    # Win 8.1+. Falls back to a screen-region copy if it fails.
    $hdc = $g.GetHdc()
    try {
        $ok = [WinAPI]::PrintWindow([IntPtr]$hwndInt, $hdc, 2)
    } finally {
        $g.ReleaseHdc($hdc)
    }
}
if (-not $ok) {
    $g.CopyFromScreen($rect.Left, $rect.Top, 0, 0, [System.Drawing.Size]::new($w, $h))
}

$bmp.Save($OutPath, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose()
$bmp.Dispose()

if ($wasMinimized) {
    [WinAPI]::ShowWindow([IntPtr]$hwndInt, 6) | Out-Null   # SW_MINIMIZE
}

$method = if ($ok) { "printwindow" } else { "screencopy" }
Write-Output ("ok " + $w + "x" + $h + " " + $method + " -> " + $OutPath)

---
description: Disable bridge mode for the current project (removes .cc-relay-mode marker at project root)
allowed-tools: Bash
---

You are disabling bridge mode for the current project. This removes the `.cc-relay-mode` marker file at the project root so future `claude` launches from this project run native (not routed through the bridge wrapper).

The "project root" is `git rev-parse --show-toplevel` of the current working directory, falling back to the current working directory itself if git is unavailable or the cwd is not inside a git repository.

## Step 1: Resolve project root, delete marker

```bash
powershell -NoProfile -Command '
# standalone — shim not loaded in Bash subshell, so resolve root inline
$root = $null
try { $root = (git rev-parse --show-toplevel 2>$null) } catch { }
if (-not $root) { $root = (Get-Location).Path }
$marker = Join-Path $root ".cc-relay-mode"
if (Test-Path $marker) {
    Remove-Item $marker -Force
    Write-Output "REMOVED MARKER:$marker ROOT:$root"
} else {
    Write-Output "NOT_PRESENT MARKER:$marker ROOT:$root"
}
'
```

## Step 2: Report

Parse the output:
- `REMOVED MARKER:<path> ROOT:<path>` → tell the user:
  > ✅ Bridge mode disabled for project `<root>`. Marker removed: `<marker>`. The next `claude` launched from this project will run native.
- `NOT_PRESENT MARKER:<path> ROOT:<path>` → tell the user:
  > Bridge mode was not enabled for project `<root>` (no marker at `<marker>` to remove). Nothing changed.

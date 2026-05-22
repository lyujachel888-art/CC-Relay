---
description: Enable bridge mode for the current project (creates .cc-relay-mode marker at project root)
allowed-tools: Bash
---

You are enabling bridge mode for the current project. This creates a `.cc-relay-mode` marker file at the project root so that future `claude` launches from this project automatically route through the bridge wrapper.

The "project root" is `git rev-parse --show-toplevel` of the current working directory, falling back to the current working directory itself if git is unavailable or the cwd is not inside a git repository.

## Step 1: Resolve project root, write marker

```bash
powershell -NoProfile -Command '
# standalone — shim not loaded in Bash subshell, so resolve root inline
$root = $null
try { $root = (git rev-parse --show-toplevel 2>$null) } catch { }
if (-not $root) { $root = (Get-Location).Path }
$marker = Join-Path $root ".cc-relay-mode"
$stamp = (Get-Date).ToString("yyyy-MM-ddTHH:mm:ssK")
try {
    [System.IO.File]::WriteAllLines(
        $marker,
        @(
            "# cc-relay: bridge mode enabled for this project"
            "# written by /cc-relay:bridge-enable at $stamp"
        ),
        [System.Text.UTF8Encoding]::new($false)
    )
    Write-Output "OK MARKER:$marker ROOT:$root"
} catch {
    Write-Output "FAIL_WRITE MARKER:$marker ROOT:$root ERR:$_"
}
'
```

## Step 2: Report

Parse the output:
- `OK MARKER:<path> ROOT:<path>` → tell the user:
  > ✅ Bridge mode enabled for project `<root>`. Marker file: `<marker>`. The next `claude` launched from any directory inside this project will route through the wrapper (bridge mode).
- `FAIL_WRITE ...` → tell the user the write failed (permissions?), surface the path, and stop.

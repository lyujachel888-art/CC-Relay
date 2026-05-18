#!/usr/bin/env bash
# Fires on UserPromptSubmit. Reads JSON from stdin, extracts .prompt, pushes to bridge.
# Must NEVER block or fail the user's prompt — always exit 0.

set +e

input=$(cat)
prompt=$(printf '%s' "$input" | jq -r '.prompt // empty' 2>/dev/null)

if [[ -z "$prompt" ]]; then
    exit 0
fi

body=$(jq -nc --arg text "$prompt" '{text: $text}')

curl -sS -m 3 -X POST http://127.0.0.1:8787/hook/user_prompt \
    -H "Content-Type: application/json" \
    -d "$body" > /dev/null 2>&1

exit 0

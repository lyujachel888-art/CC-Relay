#!/usr/bin/env bash
# Fires when Claude finishes a response. Reads transcript_path, extracts last
# assistant message text, pushes to bridge.

set +e

input=$(cat)
transcript=$(printf '%s' "$input" | jq -r '.transcript_path // empty' 2>/dev/null)

if [[ -z "$transcript" || ! -f "$transcript" ]]; then
    exit 0
fi

# Walk the JSONL transcript from the end, find the last line where role == "assistant".
# Each line is a JSON object with shape: {"type":"assistant","message":{"role":"assistant","content":[...]}}
last_text=$(tac "$transcript" 2>/dev/null | while IFS= read -r line; do
    role=$(printf '%s' "$line" | jq -r '.message.role // empty' 2>/dev/null)
    if [[ "$role" == "assistant" ]]; then
        # Extract text from content array (concatenate all text parts)
        text=$(printf '%s' "$line" | jq -r '
            .message.content
            | if type == "string" then .
              else (map(select(.type == "text") | .text) | join("\n"))
              end
        ' 2>/dev/null)
        if [[ -n "$text" && "$text" != "null" ]]; then
            printf '%s' "$text"
            break
        fi
    fi
done)

if [[ -z "$last_text" ]]; then
    exit 0
fi

body=$(jq -nc --arg text "$last_text" '{text: $text}')

curl -sS -m 3 -X POST http://127.0.0.1:8787/hook/assistant_reply \
    -H "Content-Type: application/json" \
    -d "$body" > /dev/null 2>&1

exit 0

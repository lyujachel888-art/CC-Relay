#!/usr/bin/env bash
# Launch Claude Code inside tmux session `cc1`. Idempotent: attach if exists, else create.
exec tmux new-session -A -s cc1 claude

#!/usr/bin/env bash
# Activate venv and start bridge service in foreground.
# Venv lives on WSL home filesystem (NOT /mnt/e) — /mnt/e WSL1 IO is too slow
# for lark_oapi imports (>3 min). One-time setup:
#   python3 -m venv ~/.venvs/feishu-bridge
#   ~/.venvs/feishu-bridge/bin/pip install -r /mnt/e/MyProject/RC/bridge/requirements.txt
source ~/.venvs/feishu-bridge/bin/activate
cd /mnt/e/MyProject/RC/bridge
exec python -u main.py

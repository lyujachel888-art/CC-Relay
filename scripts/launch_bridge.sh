#!/usr/bin/env bash
# Activate venv and start bridge service in foreground.
cd /mnt/e/MyProject/RC/bridge
source .venv/bin/activate
exec python main.py

"""Shared-secret bootstrap so only our hook script can POST to /hook/*.

The bridge generates a random token on first run and writes it to a known
location inside hooks/. post_hook.py reads the same file and sends it as
`Authorization: Bearer <token>`. server.py enforces presence on every
/hook/* endpoint."""

import secrets
from pathlib import Path

# auth.py lives in bridge/; hooks/ is one level up at the repo root.
TOKEN_PATH = Path(__file__).resolve().parent.parent / "hooks" / ".bridge_token"

HEADER_NAME = "Authorization"
HEADER_PREFIX = "Bearer "


def ensure_token() -> str:
    """Read the persistent token, or generate-and-write one if missing."""
    if TOKEN_PATH.exists():
        existing = TOKEN_PATH.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    token = secrets.token_urlsafe(32)
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(token, encoding="utf-8")
    # 0600 — best-effort; ignored on filesystems that don't support it.
    try:
        TOKEN_PATH.chmod(0o600)
    except Exception:
        pass
    return token

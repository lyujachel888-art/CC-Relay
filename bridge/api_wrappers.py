# bridge/api_wrappers.py
"""FastAPI routes for wrapper lifecycle: register / heartbeat / deregister.

Wrapper-side flow:
  1. POST /api/wrappers/register  → receive token + heartbeat_interval_sec
  2. Every heartbeat_interval_sec: POST /api/wrappers/heartbeat with Bearer token
  3. On clean shutdown: POST /api/wrappers/deregister
"""

import logging

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from auth import HEADER_PREFIX
from config_store import ConfigStore
from errors import BadToken, WrapperConflict, WrapperUnknown
from wrapper_registry import WrapperRegistry

log = logging.getLogger("bridge.api_wrappers")

HEARTBEAT_INTERVAL_SEC = 15


class RegisterPayload(BaseModel):
    id: str
    name: str
    cwd: str
    port: int
    pid: int


class HeartbeatPayload(BaseModel):
    id: str


def _extract_token(authorization: str) -> str:
    if not authorization or not authorization.startswith(HEADER_PREFIX):
        raise HTTPException(status_code=401, detail="missing token")
    return authorization[len(HEADER_PREFIX):].strip()


def attach_wrapper_routes(app: FastAPI, *, registry: WrapperRegistry, store: ConfigStore) -> None:

    @app.post("/api/wrappers/register")
    async def register(p: RegisterPayload):
        try:
            info = registry.register(id=p.id, name=p.name, cwd=p.cwd, port=p.port, pid=p.pid)
        except WrapperConflict as e:
            raise HTTPException(status_code=409, detail=str(e))
        # Persist wrapper metadata (id/name/expected_cwd) — port/pid stay in registry only.
        store.upsert_wrapper(id=p.id, name=p.name, expected_cwd=p.cwd)
        log.info("云匣已注册 id=%s port=%d pid=%d", p.id, p.port, p.pid)
        return {
            "wrapper_id": info.id,
            "token": info.token,
            "heartbeat_interval_sec": HEARTBEAT_INTERVAL_SEC,
        }

    @app.post("/api/wrappers/heartbeat")
    async def heartbeat(p: HeartbeatPayload, authorization: str = Header(default="")):
        token = _extract_token(authorization)
        try:
            registry.heartbeat(p.id, token)
        except WrapperUnknown:
            raise HTTPException(status_code=404, detail="unknown wrapper")
        except BadToken:
            raise HTTPException(status_code=403, detail="bad token")
        return {"ok": True}

    @app.post("/api/wrappers/deregister")
    async def deregister(p: HeartbeatPayload, authorization: str = Header(default="")):
        token = _extract_token(authorization)
        try:
            registry.deregister(p.id, token)
        except WrapperUnknown:
            raise HTTPException(status_code=404, detail="unknown wrapper")
        except BadToken:
            raise HTTPException(status_code=403, detail="bad token")
        log.info("云匣已注销 id=%s", p.id)
        return {"ok": True}

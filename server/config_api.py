"""Dashboard config override APIs."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import runtime_config
from storage import db

router = APIRouter(prefix="/api/config", tags=["config"])


class ConfigPatch(BaseModel):
    key: str
    value: Any


@router.get("")
def get_config():
    return runtime_config.list_config()


@router.patch("")
def patch_config(payload: ConfigPatch):
    try:
        item = runtime_config.set_override(payload.key, payload.value)
        runtime_config.apply_overrides_to_config()
        return item
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="unknown config key") from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/{key}")
def reset_config(key: str):
    if key not in runtime_config.CONFIG_SCHEMA:
        raise HTTPException(status_code=404, detail="unknown config key")
    ok = db.reset_config_override(key)
    runtime_config.apply_overrides_to_config()
    return {"ok": ok}


@router.post("/validate")
def validate_config(payload: ConfigPatch):
    if payload.key not in runtime_config.CONFIG_SCHEMA:
        raise HTTPException(status_code=404, detail="unknown config key")
    try:
        value = runtime_config._coerce(  # type: ignore[attr-defined]
            payload.value,
            runtime_config.CONFIG_SCHEMA[payload.key]["type"],
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "value": value}

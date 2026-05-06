"""Runtime config resolver for dashboard overrides."""
from __future__ import annotations

import copy
import os
from typing import Any, Dict

import config
from storage import db


CONFIG_SCHEMA: Dict[str, Dict[str, Any]] = {
    "DAYS_BACK": {"group": "抓取", "type": "int", "env": "DAYS_BACK"},
    "FETCH_CATEGORIES": {"group": "抓取", "type": "list"},
    "ARXIV_PAGE_SIZE": {"group": "抓取", "type": "int", "env": "ARXIV_PAGE_SIZE"},
    "ARXIV_MAX_RESULTS": {"group": "抓取", "type": "int", "env": "ARXIV_MAX_RESULTS"},
    "PREFILTER_KEYWORDS": {"group": "筛选", "type": "list"},
    "BLACKLIST_KEYWORDS": {"group": "筛选", "type": "list"},
    "BLACKLIST_SUBJECTS": {"group": "筛选", "type": "list"},
    "TOPICS_OF_INTEREST": {"group": "筛选", "type": "str"},
    "STAGE1_KEEP": {"group": "排序展示", "type": "int", "env": "STAGE1_KEEP"},
    "TOP_DISPLAY_MIN_SCORE": {"group": "排序展示", "type": "int", "env": "TOP_DISPLAY_MIN_SCORE"},
    "TOP_DISPLAY_MIN_COUNT": {"group": "排序展示", "type": "int", "env": "TOP_DISPLAY_MIN_COUNT"},
    "FEATURED_AUTHORS": {"group": "作者/机构/会议", "type": "dict"},
    "FEATURED_VENUES": {"group": "作者/机构/会议", "type": "list"},
    "AUTHOR_BONUS_PER_HIT": {"group": "作者/机构/会议", "type": "int", "env": "AUTHOR_BONUS_PER_HIT"},
    "VENUE_BONUS": {"group": "作者/机构/会议", "type": "int", "env": "VENUE_BONUS"},
    "LLM_PROVIDER": {"group": "模型", "type": "str", "env": "LLM_PROVIDER"},
    "FAST_MODEL": {"group": "模型", "type": "str", "env": "FAST_MODEL"},
    "STRONG_MODEL": {"group": "模型", "type": "str", "env": "STRONG_MODEL"},
    "INSTITUTION_INFERENCE_CONCURRENCY": {
        "group": "模型",
        "type": "int",
        "env": "INSTITUTION_INFERENCE_CONCURRENCY",
    },
}


def _coerce(value: Any, value_type: str) -> Any:
    if value_type == "int":
        return int(value)
    if value_type == "list":
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return list(value or [])
    if value_type == "dict":
        return dict(value or {})
    return str(value)


def default_value(key: str) -> Any:
    return copy.deepcopy(getattr(config, key))


def resolved_value(key: str) -> Any:
    meta = CONFIG_SCHEMA[key]
    env_name = meta.get("env")
    if env_name and env_name in os.environ:
        return _coerce(os.environ[env_name], meta["type"])
    overrides = db.get_config_overrides()
    if key in overrides:
        return _coerce(overrides[key], meta["type"])
    return default_value(key)


def list_config() -> Dict[str, Any]:
    overrides = db.get_config_overrides()
    items = []
    for key, meta in CONFIG_SCHEMA.items():
        env_name = meta.get("env")
        source = "default"
        if key in overrides:
            source = "override"
        if env_name and env_name in os.environ:
            source = "env"
        items.append(
            {
                "key": key,
                "group": meta["group"],
                "type": meta["type"],
                "default": default_value(key),
                "override": overrides.get(key),
                "value": resolved_value(key),
                "source": source,
                "editable": source != "env",
            }
        )
    return {"items": items}


def set_override(key: str, value: Any, *, source: str = "manual") -> Dict[str, Any]:
    if key not in CONFIG_SCHEMA:
        raise KeyError(key)
    value = _coerce(value, CONFIG_SCHEMA[key]["type"])
    return db.set_config_override(key, value, source=source)


def apply_overrides_to_config() -> None:
    for key in CONFIG_SCHEMA:
        setattr(config, key, resolved_value(key))

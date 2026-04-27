"""
LLM 后端抽象层
支持：anthropic | kimi | zhipu | deepseek（以及任意 OpenAI 兼容接口）

通过 config.py 中的 LLM_PROVIDER 和 LLM_API_KEY 切换。
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any, Iterable, List, Optional

logger = logging.getLogger(__name__)

# ── Provider 注册表 ────────────────────────────────────────────────────────────
# name -> (base_url, fast_default_model, strong_default_model)
# fast 档：标题粗筛 / 机构推断这类轻语义任务，要便宜快
# strong 档：摘要精排 / 深度精读，需要更强的判断力
PROVIDERS = {
    "anthropic": (None,                                     "claude-haiku-4-5",     "claude-opus-4-6"),
    "kimi":      ("https://api.moonshot.cn/v1",             "moonshot-v1-32k",      "kimi-k2.6"),
    "zhipu":     ("https://open.bigmodel.cn/api/paas/v4/",  "glm-4-flash",          "glm-4-plus"),
    "deepseek":  ("https://api.deepseek.com/v1",            "deepseek-v4-flash",    "deepseek-v4-pro"),
    # 兼容任意 OpenAI endpoint：在 config 里设 LLM_PROVIDER="custom"
    # 并设 LLM_BASE_URL + FAST_MODEL / STRONG_MODEL
    "custom":    (os.getenv("LLM_BASE_URL", ""),            os.getenv("FAST_MODEL", "gpt-4o-mini"),
                                                            os.getenv("STRONG_MODEL", "gpt-4o")),
}

VALID_TIERS = ("fast", "strong")


def _get_settings(tier: str = "strong"):
    """从 config 读取 provider / api_key / model，按档位选择实际模型。"""
    if tier not in VALID_TIERS:
        raise ValueError(f"未知 tier: {tier!r}，可选：{VALID_TIERS}")

    import config
    provider = getattr(config, "LLM_PROVIDER", "anthropic").lower()
    if provider not in PROVIDERS:
        raise ValueError(f"未知 LLM_PROVIDER: {provider}，可选：{list(PROVIDERS)}")

    base_url, fast_default, strong_default = PROVIDERS[provider]
    overrides = {
        "fast":   getattr(config, "FAST_MODEL", "") or "",
        "strong": getattr(config, "STRONG_MODEL", "") or "",
    }
    defaults = {"fast": fast_default, "strong": strong_default}
    model = overrides[tier] or defaults[tier]

    key_env = {
        "anthropic": "ANTHROPIC_API_KEY",
        "kimi":      "MOONSHOT_API_KEY",
        "zhipu":     "ZHIPU_API_KEY",
        "deepseek":  "DEEPSEEK_API_KEY",
        "custom":    "LLM_API_KEY",
    }
    api_key = os.getenv(key_env.get(provider, "LLM_API_KEY"), "")

    return provider, api_key, base_url, model


def get_active_model(tier: str = "strong") -> str:
    """返回指定档位实际会用的模型名（供展示 / 报告用）。"""
    _, _, _, model = _get_settings(tier)
    return model


def chat(
    messages: list,
    max_tokens: int = 4000,
    thinking: bool = False,         # 仅 anthropic 支持
    stream_to_stdout: bool = False,  # 调试用
    *,
    tier: str = "strong",
    label: str = "llm.chat",
) -> str:
    """
    统一的文本生成接口，返回模型回复字符串。

    messages 格式（OpenAI 风格）：
        [{"role": "user", "content": "..."}, ...]

    ``tier`` 选择模型档位：
    - ``"fast"``：标题粗筛 / 机构推断这类简单任务
    - ``"strong"``（默认）：摘要精排 / 深度精读这类复杂任务

    ``label`` 只用于日志里的追踪标识（例如 "stage1_title_filter"），
    不影响请求本身。
    """
    provider, api_key, base_url, model = _get_settings(tier)
    prompt_chars = sum(len(str(m.get("content", ""))) for m in messages)
    logger.info(
        "%s [%s] → %s/%s (prompt %d chars, max_tokens=%d)",
        label, tier, provider, model, prompt_chars, max_tokens,
    )
    start = time.monotonic()

    if provider == "anthropic":
        content = _anthropic_chat(messages, model, api_key, max_tokens, thinking)
    else:
        content = _openai_compat_chat(messages, model, api_key, base_url, max_tokens)

    elapsed_ms = int((time.monotonic() - start) * 1000)
    logger.info(
        "%s [%s] ← %s/%s (response %d chars, %d ms)",
        label, tier, provider, model, len(content or ""), elapsed_ms,
    )
    return content


# ── JSON 解析 / 校验 ─────────────────────────────────────────────────────────


def extract_json(
    text: str,
    *,
    required_keys: Iterable[str] = (),
    list_roots: Iterable[str] = (),
) -> dict:
    """从 LLM 输出中抠出 JSON 对象，并做基本结构校验。

    - 剥掉 ``` / ```json 等 code fence；先整段 ``json.loads``，失败再退而"找首个 {"。
    - 如果顶层是 array，自动包装成 ``{"items": [...]}``，方便调用方统一访问。
    - ``required_keys``：给出期望的键名列表，缺失时抛 ``ValueError``。
    - ``list_roots``：把其中第一个存在且为 list 的键"提升"到 ``items``，
      这样调用方既能走 ``data["relevant_ids"]`` 也能走 ``data["items"]``。
    """
    if not text:
        raise ValueError("空响应")

    cleaned = re.sub(r"```(?:json)?\s*", "", text).replace("```", "").strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        data = None

    if data is None:
        start = cleaned.find("{")
        end = cleaned.rfind("}") + 1
        if start == -1 or end == 0:
            arr_start = cleaned.find("[")
            arr_end = cleaned.rfind("]") + 1
            if arr_start != -1 and arr_end > arr_start:
                try:
                    arr = json.loads(cleaned[arr_start:arr_end])
                except json.JSONDecodeError as exc:
                    raise ValueError(f"无法解析 JSON：{exc}") from exc
                data = {"items": arr} if isinstance(arr, list) else {}
            else:
                raise ValueError("找不到 JSON 对象")
        else:
            try:
                data = json.loads(cleaned[start:end])
            except json.JSONDecodeError as exc:
                raise ValueError(f"JSON 解析失败：{exc}") from exc

    if isinstance(data, list):
        data = {"items": data}
    if not isinstance(data, dict):
        raise ValueError(f"期望 JSON object，实际得到 {type(data).__name__}")

    # 把第一个命中 list_roots 的键同步到 items，调用方写法更统一
    if list_roots and "items" not in data:
        for key in list_roots:
            value = data.get(key)
            if isinstance(value, list):
                data.setdefault("items", value)
                break

    if required_keys:
        missing = [key for key in required_keys if key not in data]
        if missing:
            raise ValueError(f"LLM JSON 缺少必填字段：{missing}")

    return data


# ── Anthropic 后端 ─────────────────────────────────────────────────────────────

def _anthropic_chat(messages, model, api_key, max_tokens, thinking) -> str:
    import anthropic as _anthropic

    client = _anthropic.Anthropic(api_key=api_key or None)  # None → 读环境变量

    kwargs = dict(
        model=model,
        max_tokens=max_tokens,
        messages=messages,
    )
    if thinking:
        kwargs["thinking"] = {"type": "adaptive"}

    with client.messages.stream(**kwargs) as stream:
        return stream.get_final_message().content[0].text


# ── OpenAI 兼容后端（Kimi / 智谱 / DeepSeek / custom）────────────────────────

def _openai_compat_chat(messages, model, api_key, base_url, max_tokens) -> str:
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError("请安装 openai：pip install openai")

    client = OpenAI(api_key=api_key, base_url=base_url)

    for attempt in range(1, 4):
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
        )
        choice = resp.choices[0]
        content = choice.message.content
        finish = choice.finish_reason

        if finish == "engine_overloaded":
            wait = 15 * attempt
            logger.warning("模型服务过载，%ds 后重试（第 %d 次）...", wait, attempt)
            time.sleep(wait)
            continue

        if finish == "length" and not content:
            raise ValueError(
                f"max_tokens={max_tokens} 不足（reasoning 模型需要更多 token）"
            )

        return content or ""

    raise RuntimeError("模型服务持续过载，请稍后重试")

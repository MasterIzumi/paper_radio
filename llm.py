"""
LLM 后端抽象层
支持：anthropic | kimi | zhipu | deepseek（以及任意 OpenAI 兼容接口）

通过 config.py 中的 LLM_PROVIDER 和 LLM_API_KEY 切换。
"""
import os
from typing import Optional

# ── Provider 注册表 ────────────────────────────────────────────────────────────
# name -> (base_url, default_model)
PROVIDERS = {
    "anthropic": (None,                                     "claude-opus-4-6"),
    "kimi":      ("https://api.moonshot.cn/v1",             "kimi-k2.5"),
    "zhipu":     ("https://open.bigmodel.cn/api/paas/v4/",  "glm-4-air"),
    "deepseek":  ("https://api.deepseek.com/v1",            "deepseek-chat"),
    # 兼容任意 OpenAI endpoint：在 config 里设 LLM_PROVIDER="custom"
    # 并设 LLM_BASE_URL 和 LLM_MODEL
    "custom":    (os.getenv("LLM_BASE_URL", ""),            os.getenv("LLM_MODEL", "gpt-4o")),
}


def _get_settings():
    """从 config 读取 provider / api_key / model，避免循环导入。"""
    import config
    provider = getattr(config, "LLM_PROVIDER", "anthropic").lower()
    model    = getattr(config, "MODEL", None)

    if provider not in PROVIDERS:
        raise ValueError(f"未知 LLM_PROVIDER: {provider}，可选：{list(PROVIDERS)}")

    base_url, default_model = PROVIDERS[provider]
    if not model:
        model = default_model

    # 根据 provider 读对应的环境变量，避免串 key
    key_env = {
        "anthropic": "ANTHROPIC_API_KEY",
        "kimi":      "MOONSHOT_API_KEY",
        "zhipu":     "ZHIPU_API_KEY",
        "deepseek":  "DEEPSEEK_API_KEY",
        "custom":    "LLM_API_KEY",
    }
    api_key = os.getenv(key_env.get(provider, "LLM_API_KEY"), "")

    return provider, api_key, base_url, model


def chat(
    messages: list,
    max_tokens: int = 4000,
    thinking: bool = False,        # 仅 anthropic 支持
    stream_to_stdout: bool = False, # 调试用
) -> str:
    """
    统一的文本生成接口，返回模型回复字符串。

    messages 格式（OpenAI 风格）：
        [{"role": "user", "content": "..."}, ...]
    """
    provider, api_key, base_url, model = _get_settings()

    if provider == "anthropic":
        return _anthropic_chat(messages, model, api_key, max_tokens, thinking)
    else:
        return _openai_compat_chat(messages, model, api_key, base_url, max_tokens)


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
    import time as _time
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
            print(f"  ⚠️  模型服务过载，{wait}s 后重试（第 {attempt} 次）...")
            _time.sleep(wait)
            continue

        if finish == "length" and not content:
            raise ValueError(
                f"max_tokens={max_tokens} 不足（reasoning 模型需要更多 token）"
            )

        return content or ""

    raise RuntimeError("模型服务持续过载，请稍后重试")

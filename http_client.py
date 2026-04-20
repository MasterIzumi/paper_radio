"""统一 HTTP 请求层。

设计目标：
- 所有模块共享同一个 ``requests.Session``（复用连接 / cookie）
- User-Agent、timeout、重试策略统一走 config
- 指数退避 + 抖动，限制 429/5xx/超时类错误的雪崩
- 提供 ``get_text`` / ``get_bytes`` 两种便捷接口，供 crawler / fulltext / pdf 复用
"""
from __future__ import annotations

import logging
import random
import time
from typing import Mapping, Optional

import requests

from config import (
    REQUEST_RETRIES,
    REQUEST_RETRY_BASE_SLEEP,
    REQUEST_TIMEOUT,
)

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT = "paper-radio/1.0 (+https://github.com/paper-radio; research tool)"

# 触发重试的 HTTP 状态码：限流 + 常见服务端错误
_RETRYABLE_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}

_session: Optional[requests.Session] = None


def get_session() -> requests.Session:
    """返回进程内复用的 ``requests.Session``。"""
    global _session
    if _session is None:
        session = requests.Session()
        session.headers.update({"User-Agent": DEFAULT_USER_AGENT})
        _session = session
    return _session


def _sleep_with_backoff(attempt: int, base: float) -> None:
    """指数退避 + 抖动。attempt 从 1 开始。"""
    wait = base * (2 ** (attempt - 1))
    jitter = random.uniform(0, base)
    time.sleep(wait + jitter)


def request(
    method: str,
    url: str,
    *,
    params: Optional[Mapping[str, object]] = None,
    headers: Optional[Mapping[str, str]] = None,
    timeout: Optional[float] = None,
    retries: Optional[int] = None,
    retry_base_sleep: Optional[float] = None,
    allow_redirects: bool = True,
) -> requests.Response:
    """带重试的通用请求。

    - 对连接异常、超时、以及 ``_RETRYABLE_STATUS_CODES`` 内的状态码重试。
    - 其它 4xx 直接抛 ``HTTPError``，避免把业务 bug 当网络抖动处理。
    """
    timeout = timeout if timeout is not None else REQUEST_TIMEOUT
    retries = retries if retries is not None else REQUEST_RETRIES
    retry_base_sleep = (
        retry_base_sleep if retry_base_sleep is not None else REQUEST_RETRY_BASE_SLEEP
    )
    session = get_session()

    last_exc: Optional[BaseException] = None
    for attempt in range(1, retries + 1):
        try:
            response = session.request(
                method,
                url,
                params=params,
                headers=headers,
                timeout=timeout,
                allow_redirects=allow_redirects,
            )
        except requests.RequestException as exc:
            last_exc = exc
            if attempt >= retries:
                raise RuntimeError(f"HTTP {method} {url} 失败：{exc}") from exc
            logger.warning(
                "HTTP %s %s 第 %d/%d 次失败：%s，准备重试",
                method, url, attempt, retries, exc,
            )
            _sleep_with_backoff(attempt, retry_base_sleep)
            continue

        if response.status_code in _RETRYABLE_STATUS_CODES and attempt < retries:
            logger.warning(
                "HTTP %s %s 返回 %d（第 %d/%d 次），准备重试",
                method, url, response.status_code, attempt, retries,
            )
            _sleep_with_backoff(attempt, retry_base_sleep)
            continue

        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(
                f"HTTP {method} {url} 返回 {response.status_code}：{exc}"
            ) from exc
        return response

    raise RuntimeError(f"HTTP {method} {url} 重试 {retries} 次后仍失败：{last_exc}")


def get_text(
    url: str,
    *,
    params: Optional[Mapping[str, object]] = None,
    headers: Optional[Mapping[str, str]] = None,
    timeout: Optional[float] = None,
) -> str:
    """GET 文本内容（供 HTML / Atom XML 场景使用）。"""
    response = request(
        "GET", url, params=params, headers=headers, timeout=timeout
    )
    return response.text


def get_bytes(
    url: str,
    *,
    params: Optional[Mapping[str, object]] = None,
    headers: Optional[Mapping[str, str]] = None,
    timeout: Optional[float] = None,
) -> bytes:
    """GET 二进制内容（供 PDF / Atom 原始字节场景使用）。"""
    response = request(
        "GET", url, params=params, headers=headers, timeout=timeout
    )
    return response.content

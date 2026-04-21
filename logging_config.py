"""日志初始化。

CLI / 测试脚本启动时调一次 ``setup_logging()``，之后各模块用
``logger = logging.getLogger(__name__)`` 就能拿到一致的格式与级别。

设计取舍：
- 默认 INFO，``PAPER_RADIO_LOG_LEVEL`` 环境变量可改（DEBUG / INFO / WARNING）。
- 只在 stderr 输出；``root`` 上加 handler，避免重复初始化。
- 第三方库（urllib3 / requests 等）的日志抑制到 WARNING，减少噪音。
"""
from __future__ import annotations

import logging
import os
from typing import Optional

_CONFIGURED = False

_DEFAULT_FORMAT = "%(asctime)s %(levelname)-7s %(name)s | %(message)s"
_DEFAULT_DATEFMT = "%H:%M:%S"


def setup_logging(level: Optional[str] = None) -> None:
    """幂等地配置 root logger。"""
    global _CONFIGURED
    if _CONFIGURED:
        return

    level_name = (level or os.getenv("PAPER_RADIO_LOG_LEVEL", "INFO")).upper()
    numeric_level = getattr(logging, level_name, logging.INFO)

    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(_DEFAULT_FORMAT, _DEFAULT_DATEFMT))

    root = logging.getLogger()
    root.setLevel(numeric_level)
    # 清掉一些 libs 可能留下的 handler，保证只有一个 stream handler
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)

    # 压低高频第三方库噪音
    for noisy in ("urllib3", "httpx", "httpcore", "openai", "anthropic"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _CONFIGURED = True


__all__ = ["setup_logging"]

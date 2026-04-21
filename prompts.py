"""Prompt 模板加载与渲染。

把 `${var}` 形式的模板从 ``prompt_templates/*.txt`` 读出来，进程内缓存，
避免和业务代码混在一起。小巧到不用装 Jinja2。

设计取舍：
- 模板用 ``string.Template`` 的 ``$var`` / ``${var}`` 语法——Python 内建，零依赖。
- ``safe_substitute`` 允许模板里真的写 ``$100`` 之类的字面量不挂掉；
  真的漏传字段时会在渲染后报 ``MissingPromptVariableError``。
- 读一次缓存一次，模板文件修改后需要重启进程；反正是静态资产。
"""
from __future__ import annotations

import logging
from pathlib import Path
from string import Template
from typing import Any, Dict

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).resolve().parent / "prompt_templates"
_cache: Dict[str, Template] = {}


class PromptNotFoundError(FileNotFoundError):
    """模板文件不存在。"""


class MissingPromptVariableError(KeyError):
    """渲染时某些 ``${var}`` 没拿到值。"""


def _load(name: str) -> Template:
    cached = _cache.get(name)
    if cached is not None:
        return cached

    path = _TEMPLATE_DIR / f"{name}.txt"
    if not path.exists():
        raise PromptNotFoundError(f"找不到 prompt 模板：{path}")

    template = Template(path.read_text(encoding="utf-8"))
    _cache[name] = template
    logger.debug("加载 prompt 模板 %s (%d chars)", name, len(template.template))
    return template


def render(name: str, /, **variables: Any) -> str:
    """根据模板名 + 变量渲染出最终 prompt 字符串。

    ``safe_substitute`` 只处理"模板"里的占位符，不会碰注入进来的值，所以
    arXiv 标题 / 摘要里的 LaTeX 数学公式（``$T$`` / ``$\\pi_{0.7}$`` 等）会
    原样进入最终 prompt。副作用是：漏传的 ``$var`` 形式占位符也会原样留下，
    因此项目约定模板里只用 ``${var}`` 形式，``_find_unfilled`` 也只扫这种
    形式，避免把用户内容里的 ``$T`` 误判成"缺变量"。
    """
    template = _load(name)
    rendered = template.safe_substitute(variables)

    leftover = _find_unfilled(rendered)
    if leftover:
        raise MissingPromptVariableError(
            f"prompt 模板 {name!r} 缺少变量：{sorted(leftover)}"
        )
    return rendered


def _find_unfilled(text: str) -> set[str]:
    """扫描渲染结果里残留的 ``${name}`` 占位符。

    只看 ``${...}`` 形式，不再扫 ``$name``——否则用户内容里的 LaTeX 宏
    （``$T$``、``$X_2$``）会被误判为占位符。模板内部都用 ``${var}``，漏字段
    一样能被这里发现。
    """
    import re

    pattern = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
    return {match.group(1) for match in pattern.finditer(text) if match.group(1)}


__all__ = [
    "PromptNotFoundError",
    "MissingPromptVariableError",
    "render",
]

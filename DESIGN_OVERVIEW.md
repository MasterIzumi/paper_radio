# Paper Radio 设计总览

## 1. 文档目的

这份文档说明 `paper_radio` 当前的核心设计理念、模块分工、筛选与分析链路，以及继续演进时需要遵守的约束。

目标读者：

- 新 session 中继续协作的模型
- 被压缩上下文后接手的人
- 后续维护这套工具的开发者

如果只看一段，记住这几个关键词：

- **recent 页面优先**
- **先抓全量，再逐层筛选**
- **规则预筛 + LLM 标题粗筛 + LLM 摘要精排**
- **抓取快照 / 入选快照 / 最终日报** 三层 Markdown 输出，外加前端消费用 JSON
- **机构推断覆盖 selected 集，深度精读只做少量高分论文**
- **数据用 dataclass，prompts 外部化，调用走统一 HTTP/日志层**

---

## 2. 项目目标

`paper_radio` 不是通用论文爬虫，而是一个围绕用户研究偏好的**每日 arXiv 论文筛选与摘要工具**。

主要功能：

1. 抓取 arXiv 最近几天的新论文
2. 按用户兴趣方向做规则 + LLM 双重筛选并打分
3. 输出抓取快照、入选快照、最终日报三层 Markdown，并同步导出前端 JSON
4. 对总分达到阈值的少量论文做深度简报（方法介绍 / 贡献锐评 / 影响力预测）
5. 对 selected 集论文，用 PDF 首页文本驱动 LLM 做机构归一

用户当前关注方向集中在 [`config.py`](config.py) 的 `TOPICS_OF_INTEREST`：

- 端到端自动驾驶
- 世界模型
- VLA 模型
- 空间智能
- 自动驾驶大模型

---

## 3. 核心设计理念

### 3.1 recent 页面优先，不依赖搜索 API 做"最近论文"查询

- "最近 N 天论文" 优先走 `https://arxiv.org/list/<category>/recent`
- 不用搜索 API 做时间过滤

原因：

- recent 页面就是 arXiv 官方面向人类展示"最近提交"的入口，已按 announce 日期分组，更贴合"最近 N 个自然日"语义
- 搜索 API 容易遇到限流、时间过滤不直观、语法变化等问题
- arXiv API 仍然有用，但只用作 recent 抓取后的元数据补全（摘要、affiliation、真实 published 时间）

### 3.2 "最近 N 天"按本地自然日理解

- `--days 3` = "今天往回数 3 个自然日"，不是滚动 72 小时
- 时间窗口在 [`crawler._calendar_day_range`](crawler.py) 用 `datetime.now()`（本地时间）算
- 这样和 recent 页面 heading 上不带时区的 `Tue, 21 Apr 2026` 字符串保持一致，避免"抓到了但统计表对不上"的错位

### 3.3 先抓全量，再逐层收缩

整个 pipeline 是一个不断缩小的漏斗：

1. recent 页面抓全量候选
2. 本地关键词规则**预筛**（不调 LLM）
3. LLM **标题粗筛**（只发标题，省 token）
4. 对 selected 集做 **PDF 首页驱动的机构归一**
5. LLM **摘要精排**（发摘要，给评分 + 一句话总结）
6. 仅对总分达到阈值的少量论文做 **深度简报**

总原则：**轻操作前置，重操作只留给少数高价值论文。**

### 3.4 不把所有判断都交给 LLM

- LLM 用于"语义判断"和"复杂关系推断"
- 规则 / 代码用于"结构化筛选"、"兜底"、"标准化"、"排序"

理由：LLM 有波动 + 贵，规则便宜稳定。所以是**规则 + LLM 混合**路线，不追求纯 LLM。

### 3.5 输出分层，不只输出最终一份报告

三层 Markdown 输出 + 两层 JSON 输出，每层独立保存、可单独排查：

| 目录 | 文件 | 内容 |
|---|---|---|
| `reports/recent_crawls/` | `recent_crawl_YYYY-MM-DD.md` | 抓取快照（全量原始清单 + 每日统计） |
| `reports/selected_papers/` | `selected_papers_YYYY-MM-DD.md` | 入选快照（selected 集全量评分明细 + 方向） |
| `reports/` | `daily_report_YYYY-MM-DD.md` | 最终日报（动态重点论文 + 机构 + 深度简报） |
| `reports_json/selected/` | `selected_papers_YYYY-MM-DD.json` | selected 集的结构化明细，供静态前端展示 |
| `reports_json/daily/` | `daily_report_YYYY-MM-DD.json` | 日报结构化数据（重点论文 + 深度简报） |
| `reports_json/` | `index.json` | 前端入口索引（可用日期、路径、默认日期） |

意义：抓取出问题查 recent_crawls，筛选出问题查 selected_papers，最终阅读看 daily_report；前端展示直接读 `reports_json/`，不再反向解析 Markdown。

### 3.6 数据用 dataclass，少在 dict 里 `.get()`

整条管线统一用 [`models.py`](models.py) 里的两个 dataclass 承载论文：

- `Paper`：从 arXiv 抓回来的基础元信息（含 `announced_date`）
- `RankedPaper`：在 `Paper` 基础上多评分、机构归一字段

这样下游不用到处写 `paper.get("xxx", "")`，并且 `merge_non_empty` / `with_scores` / `with_institutions` 这些"返回新对象"的方法集中维护合并语义。

---

## 4. 当前目录与模块职责

### 4.1 入口

- [`main.py`](main.py)：主流程入口，串联抓取 → 粗筛 → 机构推断 → 摘要精排 → 写日报。`setup_logging()` 在最早一步初始化日志。

### 4.2 数据层

- [`models.py`](models.py)：`Paper` / `RankedPaper` 两个 dataclass，以及类型转换工具（`_parse_atom_datetime` / `_normalize_arxiv_id` / `_coerce_int`）。
- [`config.py`](config.py)：所有可调参数集中点，所有运行时配置都通过环境变量 override。

### 4.3 抓取层

- [`crawler.py`](crawler.py)：
  - `fetch_papers()`：主流程入口，先抓 recent，再用 arXiv API 补元数据
  - `fetch_recent_papers(enrich_metadata=False)`：测试脚本用的轻量版，不调 API
  - `fetch_paper_by_id()`：按 ID 单篇抓取（测试 / 调试用）
  - `get_recent_coverage()`：探测 recent 页面能覆盖到的最早日期
- [`pdf_context.py`](pdf_context.py)：下载 PDF 并提取**标题区 / 机构候选 / 页底候选**这类高价值片段给机构推断用。
- [`fulltext.py`](fulltext.py)：抓 arXiv HTML 版本的 Introduction / Method 段落，给深度简报用。

### 4.4 排序与机构推断

- [`ranker.py`](ranker.py)：三个公开入口 + 内部实现
  - `run_stage1_filter(papers)`：规则预筛 + LLM 标题粗筛，返回进入机构推理 / 摘要精排的 selected 集
  - `enrich_papers_with_institutions(papers)`：对 selected 集并行拉 PDF + LLM 推断机构
  - `run_stage2_rank(papers)`：LLM 摘要精排，对全量候选**逐篇打分**（不截断），返回排序后的 `RankedPaper` 列表
  - `infer_paper_institutions`：单篇机构推断（测试脚本用）
- [`score_adjust.py`](score_adjust.py)：stage2 之后的规则型评分叠加层，纯正则 + 字典匹配，不碰 LLM
  - `apply_score_adjustments(papers)`：整批算 `author_bonus` / `venue_bonus`、按 `BONUS_BUDGET` 封顶、按新 `total_score` 重排 `rank`（`penalty` 字段保留为扩展点，目前恒为 0）
  - `_match_featured_authors`：姓名 + 机构双命中识别重点作者（防止同名误伤）
  - `_match_venues`：顶会 `accepted / to appear` 或 `会议名 + 年份` 识别，带 `submitted / rejected / under review` 否定上下文过滤

### 4.5 LLM 抽象层

- [`llm.py`](llm.py)：
  - `chat(label=...)`：统一的 LLM 调用入口，前后打日志（provider / model / prompt 字符数 / 响应字符数 / 耗时 ms）
  - `extract_json(required_keys=, list_roots=)`：从 LLM 回复中抠 JSON，支持必填字段校验和 list 根节点提升
  - `get_active_model()`：给 reporter 展示当前模型用
  - 多 provider 支持：anthropic 原生 + OpenAI 兼容（kimi / zhipu / deepseek / custom）

### 4.6 Prompt 模板

- [`prompts.py`](prompts.py)：基于 `string.Template` 的轻量渲染器，缓存模板对象，缺变量时显式抛 `MissingPromptVariableError`。
- [`prompt_templates/*.txt`](prompt_templates/)：四个 LLM prompt
  - `stage1_title_filter.txt`
  - `stage2_abstract_rank.txt`
  - `institution_inference.txt`
  - `deep_analysis.txt`

### 4.7 渲染层

- [`recent_report.py`](recent_report.py)：抓取快照（全量论文表 + 每日 announce 统计）
- [`selected_report.py`](selected_report.py)：入选快照（selected 集的全量评分明细、机构、加分扣分占位列、方向汇总）
- [`reporter.py`](reporter.py)：最终日报（按阈值 + 最小数动态挑选"重点论文"展示，外加深度简报）
- [`serializers.py`](serializers.py)：前端 JSON 导出（daily / selected / index）
- [`webapp/`](webapp/)：静态前端（`Highlight` / `Longlist` 两个标签页），直接读取 JSON

### 4.8 基础设施

- [`http_client.py`](http_client.py)：进程内共享 `requests.Session`、统一 User-Agent、超时、重试 + 指数退避 + 抖动。所有抓取都走它（crawler / pdf_context / fulltext）。
- [`logging_config.py`](logging_config.py)：`setup_logging()` 幂等初始化，默认 INFO，`PAPER_RADIO_LOG_LEVEL` 可改；urllib3 / openai / anthropic 等高频库压到 WARNING。
- [`formatting.py`](formatting.py)：`fmt_authors` / `fmt_affiliations` / `escape_md_cell` / `clip` / `weekday_cn` / `arxiv_sort_key` 等展示层共用工具。

---

## 5. 抓取层设计

### 5.1 recent 页面是第一来源

[`_scrape_recent_category`](crawler.py)：

1. 访问 `https://arxiv.org/list/{category}/recent?show=2000`
2. 解析 `h3` 日期标题（如 `Tue, 21 Apr 2026 (showing 100 of 100 entries)`）
3. 在最近 N 个自然日范围内收集 `dt/dd` 条目
4. 每条得到：`arxiv_id` / `title` / `authors` / `categories` / `announced_at`
5. `announced_at.date()` 写入 `Paper.announced_date`，用于每日统计

### 5.2 arXiv API 只做元数据补全

[`_enrich_papers_with_api_metadata`](crawler.py)：

- 把 recent 抓到的 ID 列表分批（默认 50/批）发给 arXiv API
- 解析 Atom feed，补全：`abstract` / 完整 `authors` / `affiliations` / 真实 `published` 时间
- 用 `Paper.merge_non_empty(other)` 做"非空字段覆盖"合并，**不会用空值擦掉 recent 阶段已有的 `announced_date`**

这是个有意为之的合并语义——任何阶段抓到的非空字段都视为更可信，不允许后续阶段用空值倒灌覆盖。

### 5.3 Affiliation 抓取分阶段

| 阶段 | 来源 | 范围 | 说明 |
|---|---|---|---|
| 全量抓取 | arXiv API 的 `<arxiv:affiliation>` | 所有候选 | 轻量、稳定，但很多论文 API 里没填 |
| selected 集增强 | PDF 首页文本 + LLM 归一 | 粗筛通过的 selected 全量候选 | 比 recent 全量轻，且能让 selected 快照 / 日报都复用统一机构结果 |

明确不做：

- 全量阶段抓 HTML 兜底 affiliation
- 全量阶段解析 PDF
- 第一阶段做作者顺序 / 校企合作判断

### 5.4 PDF 首页文本提取

[`pdf_context.py`](pdf_context.py)：

- 用 `pypdf` 抽第一页文本
- 做行级清洗与噪声过滤（watermark / 页码 / 常见版权语句）
- 从第一页里提取三类高价值片段：
  - 标题 / 作者块
  - 机构 / 邮箱 / 脚注候选
  - 页底候选文本
- 字符数封顶 8000，给 LLM 做机构推断用

相比早期的"整页全文直接输入"，现在的策略更偏向把最可能含机构信息的片段显式标出来，减少正文噪声干扰。

---

## 6. 筛选与排序设计

### 6.1 三层筛选漏斗

```
全量候选
  ↓ 规则预筛（本地关键词命中，零成本，不截断）
  ↓ LLM 标题粗筛（仅 title + arxiv_id）
  ↓ 机构推理（对 selected 集并行 PDF + LLM）
  ↓ LLM 摘要精排（标题 + 作者 + 摘要 → 逐篇评分 + 一句话总结）
完整打分列表（按 total_score 降序）
  ↓ 按阈值 + 最小数挑出"重点论文"用于日报展示
```

**关键决策**：粗筛之后的候选集即 **selected papers**。它们会同时进入机构推理、摘要精排，并以评分明细写入 `selected_papers` 快照；日报展示层再按阈值动态挑出"重点论文"。

### 6.2 规则预筛

[`_rule_prefilter`](ranker.py) 三步纯字符串/正则规则，零成本：

1. **subject 黑名单硬剔除**：论文任一 arXiv 分类命中 `BLACKLIST_SUBJECTS`（默认：`eess.SY` / `cs.MA` / `cs.SE` / `cs.HC` / `cs.OS`）即直接丢弃，不进入后续任何 LLM 环节。比对大小写不敏感。OR 语义——只要有一个分区命中就算命中，哪怕同时挂了 `cs.CV`。
2. **关键词白名单命中**：拼接 `title + abstract + categories`，小写匹配 `PREFILTER_KEYWORDS`。命中即保留；全量未命中时 fallback 取前 `STAGE1_KEEP * 2 = 60` 篇兜底（已剔除 subject 黑名单）。
3. **关键词黑名单硬剔除**：对保留下来的候选扫 `title + abstract`，命中 `BLACKLIST_KEYWORDS`（默认：`Drone Racing` / `V2V` / `V2X` / `Remote Sensing` / `UAV` / `Quadrotor` / `Underwater`）即丢弃。匹配规则见 [`_build_blacklist_keyword_pattern`](ranker.py)：
   - case-insensitive + **word boundary**，避免 `UAVNet` / `V2XNet` 误伤
   - 尾部允许 `s?`：`UAV` / `UAVs` 都算命中，`Quadrotor` / `Quadrotors` 都算
   - 词组内部空格用 `\s+`：`Drone Racing` 命中 `Drone  Racing`（双空格 / 换行）

注意：

- **不应用 `MAX_PAPERS_TO_RANK` 截断**——这是零成本的纯字符串/正则匹配，LLM 限额只在下一步生效
- 目的：第一刀去掉明显不相关（主题偏 / 领域偏），降低 LLM 输入量
- **两层黑名单分工**：`BLACKLIST_SUBJECTS` 面向"整篇分区不对口"（`cs.SE` 全丢），`BLACKLIST_KEYWORDS` 面向"分区沾边但主题明确跑偏"（`cs.RO` 里的 `Drone Racing` / `UAV`）

### 6.3 第一阶段：LLM 标题粗筛（`run_stage1_filter`）

[`_stage1_filter`](ranker.py)：

- 输入：候选论文的 `arxiv_id + title`（最多 `MAX_PAPERS_TO_RANK` 篇）
- prompt：[`stage1_title_filter.txt`](prompt_templates/stage1_title_filter.txt)
- 调用档位：**fast**（更便宜快速的模型，任务简单）
- 输出 JSON：`{"relevant_ids": [...]}`
- 失败兜底：直接返回前 `STAGE1_KEEP = 30` 篇

`run_stage1_filter` 是公开入口，返回的是 `List[RankedPaper]`（分数还都是 0），下游在同一批对象上累加机构 / 评分 / 加分扣分字段。

### 6.4 中间阶段：机构推理（`enrich_papers_with_institutions`）

见 §7。对**整个 selected 集合**并行补机构信息，完成后再进入摘要精排。

> 为什么放在精排前？这样机构信息会出现在 `selected_papers` 快照里，也能在未来用作评分输入（比如"校企联合 +1"），而不仅仅是日报展示。

### 6.5 第二阶段：LLM 摘要精排（`run_stage2_rank`）

[`_stage2_rank`](ranker.py)：

- 输入：标题 + 作者 + 摘要前 500 字
- prompt：[`stage2_abstract_rank.txt`](prompt_templates/stage2_abstract_rank.txt)
- 调用档位：**strong**（reasoning 模型，任务复杂）
- 评分维度：`relevance_score` (0-10) + `novelty_score` (0-10) → `total_score` (0-20 原始分)
- **对全量候选逐篇打分**，不在此处做固定数量截断
- 输出字段：`rank` / `arxiv_id` / `relevance_score` / `novelty_score` / `total_score` / `topic_category` / `one_line_summary`
- LLM 漏评字段时由 [`_normalize_ranked_papers`](ranker.py) 做兜底（默认值 + 重排 rank）
- LLM 漏评某篇时以 0 分兜底补入（保证 `selected_papers` 快照完整）
- 失败兜底：返回原候选列表（0 分），不再做"前 N 篇"的截断

**为什么全量评分**：`selected_papers` 快照承担"候选集回放 + 评分审计 + 未来重排"三个职责，必须包含所有评分明细；日报中的重点论文交给 reporter 层按阈值动态挑。

**重要决策**：排序阶段不再有"机构分"维度。机构信息只是辅助阅读信号，不参与排名。

### 6.6 评分体系与分数叠加

[`config.py`](config.py) 定义的分数范围：

- `RAW_SCORE_MAX = 20`：LLM 直接产出的原始分上限（`relevance_score` + `novelty_score`）
- `TOTAL_SCORE_MAX = 30`：**最终总分上限**，预留 +10 的加分项 budget
- `BONUS_BUDGET = 10`：`author_bonus + venue_bonus` 之和硬封顶
- `DEEP_ANALYSIS_MIN_TOTAL_SCORE = 21`：深度精读阈值，对应新总分的 70%
- `TOP_DISPLAY_MIN_SCORE = 18`、`TOP_DISPLAY_MIN_COUNT = 5`：日报"重点论文"展示阈值 + 保底数

叠加规则在 [`score_adjust.py`](score_adjust.py) 里实现，在 `run_stage2_rank` 之后、`save_selected_report` 之前执行一次：

```
total_score = clamp(
    relevance + novelty
    + min(author_bonus + venue_bonus, BONUS_BUDGET),
    0, TOTAL_SCORE_MAX
)
```

注：`RankedPaper.penalty` 字段保留为未来扩展点（比如新增其他降权场景），目前恒为 0——"主题黑名单关键词"已在 §6.2 规则预筛阶段硬剔除。

#### 重点作者加分

- 配置：`FEATURED_AUTHORS = {"Hongyang Li": ["HKU", ...], "Hao Zhao": ["Tsinghua", ...], ...}`
- 规则：**"姓名命中 AND 机构关键词命中"** 才加。姓名匹配 case-insensitive + 去标点；机构关键词对 `normalized_institutions + affiliations + institution_summary` 做 substring 检查。单纯同名不加分（防止 Hongyang Li @ Stanford 这种同名冲突）。
- 每位命中 `+AUTHOR_BONUS_PER_HIT = 3`，同篇 `author_bonus` 累计封顶 `AUTHOR_BONUS_CAP = 6`（防止多位 featured author 同台直接刷满）。
- 依赖顺序：必须在**机构推理之后**才能做这一步，所以安排在 stage2 之后。

#### 顶会录用加分

- 配置：`FEATURED_VENUES = ["CVPR", "ICCV", "NeurIPS", "ICLR", "ECCV", "ICML", "CoRL", "RSS"]`
- 数据源：`Paper.comments`（从 arXiv API 的 `<arxiv:comment>` 抓出），`crawler._parse_feed` 里填入。
- 识别策略（两条正则 + 一条否定过滤）：
  - **A. 录用表述**：`accepted / to appear / appearing in / to be published / in proceedings` + 会议名（允许中间夹 40-60 字符内的介词/冠词，但不跨句号）
  - **B. 会议名 + 年份**：`<VENUE>\s*(20\d\d|'\d\d)`（典型如 `CVPR 2024`）
  - **否定过滤**：`submitted / rejected / under review / not accepted / declined` 上下文里的会议名不算命中。混合场景（`Accepted to CVPR 2024. Rejected from NeurIPS 2023`）只剔除落在否定上下文里的会议。
- 单篇命中多个顶会只加一次 `VENUE_BONUS = 4`（不叠加）。

#### 封顶策略

1. `author_bonus` 先各自封顶到 `AUTHOR_BONUS_CAP`
2. `author_bonus + venue_bonus` 超出 `BONUS_BUDGET = 10` 时，**先压 venue，再压 author**（保护"重点作者"信号优先级）
3. `total_score` 最后再按 `[0, TOTAL_SCORE_MAX = 30]` 硬截断

#### 展示

- `selected_papers` 快照有 `作者加分 / 顶会加分` 两列，0 显示为 `-`
- 日报"重点论文详细卡片"里：
  - 评分行按需追加 `作者 +N / 顶会 +N`
  - 有加分时新增一行 `- **加分原因**: featured author: Hongyang Li@HKU +3; venue accepted: CVPR +4`

### 6.7 LLM 输出标准化

[`_normalize_ranked_papers`](ranker.py)：

- `one_line_summary` 缺失时用摘要首句或标题兜底
- `rank == 0` 时按出现顺序补 `rank`
- 按 `(total_score, arxiv_id)` 重排，重写 `rank`

理由：LLM 有时漏字段、给的 `rank` 乱、`total_score` 缺失，代码层必须有兜底。

---

## 7. 机构归一设计

### 7.1 设计目标

- 用户日报上要展示"哪些机构合作了这篇"
- arXiv API 的 `<arxiv:affiliation>` 经常空缺
- 批量 prompt 受上下文限制，单篇失败会连累全批

所以机构推断的单位是：**覆盖整个 selected 集合（粗筛通过的全部候选），每篇独立 + 并行**。

### 7.2 流程

[`enrich_papers_with_institutions(papers)`](ranker.py)：

1. 用 `ThreadPoolExecutor`（默认并发 `INSTITUTION_INFERENCE_CONCURRENCY = 4`）跑 N 个 worker
2. 每个 worker 处理一篇论文：
   - `fetch_pdf_first_page_context` 抽 PDF 首页文本
   - 用 [`institution_inference.txt`](prompt_templates/institution_inference.txt) 渲染**单论文 prompt**
   - 用 **fast 档** LLM 调一次 `chat()`，输出**单个 JSON 对象**
3. 输出字段：
   - `normalized_institutions`：归一后的机构列表
   - `institution_types`：`university | company | research_lab | mixed | unknown`
   - `institution_summary`：一句中文简述
   - `evidence_source`：`api | pdf | api+pdf | unknown`
4. 单篇失败（PDF 抓不到 / LLM 报错）只影响那一篇，其它论文照常完成

刻意选择"逐篇 + 并行"而不是"打包成一个大 prompt 一次调用"：

- 单 prompt 体积可控，避免 N × 8000 字符 PDF 文本超长上下文
- 单篇失败不连累其它
- 调用并发受同一上限保护，对 arxiv PDF 和 LLM provider 都比较礼貌
- 跨篇归一一致性的损失在可接受范围（机构名都是常见缩写，单论文也能归对）

### 7.3 粒度约束

机构识别到 **学校 / 公司 / 研究机构** 层级，不分析到学院 / 系 / 实验室。

### 7.4 输出位置

- `selected_papers` 快照：新增 `机构` 列展示 `normalized_institutions`
- 日报"重点论文速览表"：`机构` 列展示 `normalized_institutions`
- 日报"重点论文详细卡片"：同上
- 深度简报：同上

---

## 8. 深度简报设计

### 8.1 阈值 + 上限

配置在 [`config.py`](config.py)：

- `DEEP_ANALYSIS_MAX_PAPERS = 3`
- `DEEP_ANALYSIS_MIN_TOTAL_SCORE = 21`（总分上限 30，相当于 70%）

逻辑：

- 总分 < 阈值的论文不做精读（哪怕进入日报"重点论文"展示）
- 达到阈值的论文最多分析 `DEEP_ANALYSIS_MAX_PAPERS` 篇
- 当天没有达标论文时，报告里明确写"今日没有达到精读阈值的论文，因此不生成深度分析"

### 8.2 日报"重点论文"的动态展示

[`_select_top_display_papers`](reporter.py)：

- 取 `total_score >= TOP_DISPLAY_MIN_SCORE = 18` 的**全部**论文进入速览表与详细卡片
- 若数量少于 `TOP_DISPLAY_MIN_COUNT = 5`，从排名靠前顺位补齐到 5 篇作为保底
- 低分日也不会空表，高分日不会被 10 篇硬上限截住

### 8.3 深度精读输入

[`_deep_analysis`](reporter.py)：

- 优先用 [`fulltext.fetch_sections`](fulltext.py) 抓 arXiv HTML 版本的 Introduction / Method 章节
- 失败时降级到摘要
- prompt：[`deep_analysis.txt`](prompt_templates/deep_analysis.txt)

### 8.4 深度精读输出三段式

LLM 直接输出 Markdown，三段：

- **方法介绍**：3-4 句，强调具体模块 / 架构设计
- **贡献锐评**：2-3 句，犀利点出潜在局限
- **影响力预测**：1 句

Anthropic 后端会启用 `thinking=adaptive`，其它 provider 直接生成。

---

## 9. LLM 抽象层

### 9.1 模型分两档：fast / strong

不同 LLM 任务的难度差很多，所以系统按 tier 选模型：

| tier | 用途 | 调用点 |
|---|---|---|
| `fast` | 标题粗筛、机构归一（结构化任务） | `_stage1_filter` / `_infer_one_paper_institution` |
| `strong` | 摘要精排、深度精读（需要语义判断 + 评分） | `_stage2_rank` / `_deep_analysis` |

调用方写 `chat(..., tier="fast")` 或 `chat(..., tier="strong")`（默认 strong），底层 `_get_settings(tier)` 把档位翻译成具体模型名。

### 9.2 多 provider × 两档默认

[`config.LLM_PROVIDER_REGISTRY`](config.py) 注册表（每个 provider 同时定义 fast / strong 两档默认模型）：

| provider | base_url | fast 默认 | strong 默认 | API key 环境变量 |
|---|---|---|---|---|
| anthropic | （SDK 默认）| `claude-haiku-4-5` | `claude-opus-4-6` | `ANTHROPIC_API_KEY` |
| kimi | `https://api.moonshot.cn/v1` | `moonshot-v1-32k` | `kimi-k2.6` | `MOONSHOT_API_KEY` |
| zhipu | `https://open.bigmodel.cn/api/paas/v4/` | `glm-4-flash` | `glm-4-plus` | `ZHIPU_API_KEY` |
| deepseek | `https://api.deepseek.com/v1` | `deepseek-v4-flash` | `deepseek-v4-pro` | `DEEPSEEK_API_KEY` |
| custom | `LLM_BASE_URL` | `FAST_MODEL` env | `STRONG_MODEL` env | `LLM_API_KEY` |

环境变量覆盖优先级（每档独立）：

```
config.FAST_MODEL   > LLM_PROVIDER_REGISTRY[provider]["fast_model"]    # fast 档
config.STRONG_MODEL > LLM_PROVIDER_REGISTRY[provider]["strong_model"]  # strong 档
```

旧的 `LLM_MODEL` 环境变量被当作 `STRONG_MODEL` 兼容值，不影响 fast 档默认。

### 9.3 调用可观测性

`chat(messages, tier=, label=...)` 在每次调用前后打结构化日志，把档位也带上：

```
HH:MM:SS INFO    llm | stage1_title_filter [fast]   → kimi/moonshot-v1-32k (prompt 12345 chars, max_tokens=16000)
HH:MM:SS INFO    llm | stage1_title_filter [fast]   ← kimi/moonshot-v1-32k (response 1234 chars, 3456 ms)
HH:MM:SS INFO    llm | stage2_abstract_rank [strong] → kimi/kimi-k2.6 (prompt 23456 chars, max_tokens=8000)
HH:MM:SS INFO    llm | stage2_abstract_rank [strong] ← kimi/kimi-k2.6 (response 4567 chars, 18234 ms)
```

每个 LLM 调用点都传了独立的 `label`，方便聚合统计哪步耗时长 / 失败率高。

### 9.4 OpenAI 兼容后端的过载重试

[`_openai_compat_chat`](llm.py) 处理 `engine_overloaded` finish_reason，重试 3 次，间隔 `15 * attempt` 秒，超过抛 `RuntimeError`。

### 9.5 JSON 抽取

`extract_json(required_keys=, list_roots=)`：

1. 剥 ``` / ```json code fence
2. 整段 `json.loads`，失败则定位最外层 `{...}` / `[...]` 重试
3. 顶层 array 自动包装成 `{"items": [...]}`
4. `list_roots=("relevant_ids",)` 等：把第一个命中的 list 字段同步到 `items`，调用方既能写 `data["relevant_ids"]` 也能写 `data["items"]`
5. `required_keys=(...)` 缺失时抛 `ValueError`

---

## 10. Prompt 模板系统

### 10.1 为什么外移

之前 prompt 散在 `ranker.py` / `reporter.py` 的 f-string 里，存在的问题：

- prompt 长度变大后影响代码可读性
- 改 prompt 必须改代码
- 多 prompt 共用变量没法集中维护
- 没有"模板缺变量"的兜底

现在统一放在 `prompt_templates/*.txt`，业务代码只剩调用：

```python
prompt = prompts.render(
    "stage2_abstract_rank",
    topics_of_interest=TOPICS_OF_INTEREST,
    paper_blocks=blocks,
    total_score_max=TOTAL_SCORE_MAX,
    top_n=TOP_N,
)
```

### 10.2 模板语法

用 Python 内建的 `string.Template`：

- 占位符**统一用 `${var}` 形式**（不用 `$var`）
- `safe_substitute` 让漏变量不直接挂掉，渲染后再统一兜底

### 10.3 LaTeX 兼容

arXiv 论文标题 / 摘要里经常出现 `$T$` / `$\pi_{0.7}$` / `$X_2$` 这类 LaTeX 数学。`string.Template` 默认会把 `$T` 也当占位符。

处理方式：

- `safe_substitute` 只处理"模板"侧的占位符，**不会碰注入进来的值**，所以 LaTeX 公式自动原样保留
- `_find_unfilled` 只扫 `${var}` 形式的残留，**不扫 `$var`**，避免把用户内容里的 `$T` 误判成"缺变量"
- 项目硬约定：模板里只用 `${var}`，不用 `$var`

漏变量真出现时，`render()` 会抛 `MissingPromptVariableError`，提示 `prompt 模板 'xxx' 缺少变量：[...]`。

### 10.4 缓存

模板按 `name` 进程内缓存（`_cache: Dict[str, Template]`），改完模板需要重启进程。这是静态资产，可以接受。

---

## 11. 输出层设计

### 11.1 文件命名约定

- `recent_crawl_YYYY-MM-DD.md`：抓取快照
- `selected_papers_YYYY-MM-DD.md`：入选快照
- `daily_report_YYYY-MM-DD.md`：最终日报
- `reports_json/index.json`：前端日期索引
- `reports_json/daily/daily_report_YYYY-MM-DD.json`：日报结构化数据
- `reports_json/selected/selected_papers_YYYY-MM-DD.json`：selected 结构化数据

约定：

- 按天命名，同一天重复运行覆盖
- 不在文件名里塞 category，保持稳定路径
- 三层目录平级（`reports/recent_crawls/` / `reports/selected_papers/` / `reports/`）

### 11.2 日期口径

当前实现里有两个时间字段：

- `announced_date`：recent 页面 heading 对应的公告日期
- `published` / `published_day`：arXiv API 返回的真实提交时间

设计原则上，**系统的主统计口径应当以 `announced_date` 为准**。

原因：

- 我们的抓取入口就是 `recent` 页面
- 用户关心的是"arXiv 今天放出来了哪些论文"
- 即使出现漏跑 / 补跑 / 重跑，按 `announced_date` 组织也更稳定

因此：

- 抓取快照的每日统计按 `Paper.announced_date` 分桶
- 前端按日期查看某天结果时，语义上也应理解为"这天 announced 的论文"
- `published_day` 只作为辅助元信息展示；仅在 `announced_date` 缺失时，才允许 fallback

### 11.3 表格样式

- 所有表格走 [`render_table`](recent_report.py)，对齐 + 转义 `|` / 换行
- 重点论文速览表分数显示为 `{score}/{TOTAL_SCORE_MAX}`，跟随配置动态变化
- `selected_papers` 表格不截断"一句话总结"

---

## 12. 基础设施层

### 12.1 HTTP 层

[`http_client.py`](http_client.py)：

- 进程内单例 `requests.Session`（连接复用 + cookie 复用）
- 统一 User-Agent：`paper-radio/1.0 (+...; research tool)`
- 超时 / 重试次数 / 退避基数全走 `config`（环境变量可调）
- 重试触发：连接异常 / 超时 / 状态码 ∈ `{408, 425, 429, 500, 502, 503, 504}`
- 4xx（除上面几个）直接抛错，不当抖动重试
- 指数退避 + 抖动：`base * 2^(attempt-1) + uniform(0, base)`

`get_text` / `get_bytes` 是上层 helpers，crawler / fulltext / pdf_context 全部统一走这里。

### 12.2 日志

[`logging_config.py`](logging_config.py)：

- `setup_logging()` 幂等初始化，CLI 和测试脚本入口处调一次
- 默认 INFO，`PAPER_RADIO_LOG_LEVEL=DEBUG` 可放大
- 格式：`HH:MM:SS LEVEL  module | message`
- 第三方库（urllib3 / httpx / openai / anthropic）压到 WARNING

业务代码统一 `logger = logging.getLogger(__name__)`，**禁止在内部模块用 `print`**。`main.py` 里的 `print` 是用户面 banner / 进度，可以保留。

### 12.3 配置

[`config.py`](config.py) 是唯一的配置入口：

- 抓取相关：`FETCH_CATEGORIES` / `DAYS_BACK` / `ARXIV_PAGE_SIZE` / `REQUEST_*`
- 两阶段筛选：`MAX_PAPERS_TO_RANK` / `STAGE1_KEEP`
- 规则预筛：`BLACKLIST_SUBJECTS` / `PREFILTER_KEYWORDS` / `BLACKLIST_KEYWORDS`
- 排序相关：`TOPICS_OF_INTEREST` / `RAW_SCORE_MAX` / `TOTAL_SCORE_MAX` / `BONUS_BUDGET`
- 分数叠加：`FEATURED_AUTHORS` / `AUTHOR_BONUS_PER_HIT` / `AUTHOR_BONUS_CAP` / `FEATURED_VENUES` / `VENUE_BONUS`
- 日报展示：`TOP_DISPLAY_MIN_SCORE` / `TOP_DISPLAY_MIN_COUNT`
- LLM 相关：`LLM_PROVIDER` / `FAST_MODEL` / `STRONG_MODEL`
- 深度分析：`DEEP_ANALYSIS_MAX_PAPERS` / `DEEP_ANALYSIS_MIN_TOTAL_SCORE`
- 并发：`INSTITUTION_INFERENCE_CONCURRENCY`
- 输出目录：`OUTPUT_DIR` / `CRAWL_OUTPUT_DIR` / `SELECTED_OUTPUT_DIR` / `REPORTS_JSON_DIR`

所有运行时参数都通过环境变量 override（`os.getenv(..., default)`）。`.env` 文件在 `main.py` 最开头由 `python-dotenv` 加载。

---

## 13. 端到端调用链

```
main.py
  └─ setup_logging()
  └─ calendar_day_range(args.days)
  └─ fetch_papers(days, categories)             # crawler
        ├─ _scrape_recent_category(...)         # http_client.get_text
        ├─ _dedupe_papers (merge_non_empty)
        └─ _enrich_papers_with_api_metadata     # http_client.get_bytes
  └─ summarize_daily_counts(papers)             # recent_report
  └─ save_recent_crawl_report(...)              # recent_report
  └─ run_stage1_filter(papers)                  # ranker
        ├─ _rule_prefilter                      # 本地关键词，不截断
        └─ _stage1_filter                       # llm.chat(tier="fast") + extract_json
  └─ enrich_papers_with_institutions(selected)  # ranker，对 selected 集全量并行
        ├─ fetch_pdf_first_page_context (×N)    # pdf_context + http_client
        └─ _infer_one_paper_institution (×N)    # llm.chat(tier="fast") + extract_json
  └─ run_stage2_rank(enriched)                  # ranker
        ├─ _stage2_rank                         # llm.chat(tier="strong") + extract_json（全量逐篇打分）
        └─ _normalize_ranked_papers
  └─ apply_score_adjustments(ranked)            # score_adjust
        ├─ _match_featured_authors              # 姓名 + 机构双命中
        ├─ _match_venues                        # accepted / 会议+年份 + 否定过滤
        └─ _rerank_by_total                     # 按新 total_score 重排 rank
  └─ save_selected_report(...)                  # selected_report，含机构列 + 评分明细
  └─ generate_report_bundle(ranked, categories) # reporter，一次产 markdown + daily JSON
        ├─ _select_top_display_papers           # 阈值 + 最小数
        └─ _deep_analysis (×K, K ≤ DEEP_ANALYSIS_MAX_PAPERS)
              ├─ fulltext.fetch_sections        # http_client
              └─ llm.chat(tier="strong")        # deep_analysis
  └─ build_selected_json_payload(...)           # serializers
  └─ write_json(...)                            # serializers
  └─ refresh_reports_index(...)                 # serializers
```

---

## 14. 维护原则

后续继续改这套工具时尽量遵守：

1. **recent 页面仍是"最近论文"的第一来源**，arXiv API 只做补全
2. **重操作里要区分层次**：机构推理覆盖整个 selected 集，深度精读只对少量高分论文做
3. **规则用于降本和稳定，LLM 用于复杂语义判断**
4. **中间快照（recent_crawls / selected_papers）不要删**，是可观察性的关键；`selected_papers` 要包含全量评分明细，为未来重排服务
5. **对 LLM 输出要有代码兜底**——`_normalize_ranked_papers` / `extract_json` 的 list_roots / required_keys、stage2 漏评 0 分补入等都是这层兜底
6. **数据结构改动统一在 `models.py`**，不要在调用层私自加字段
7. **新增 LLM 调用必须传 `label=` 和 `tier=`**，便宜任务用 `tier="fast"`，复杂任务用 `tier="strong"`
8. **新增 prompt 必须落到 `prompt_templates/*.txt`**，业务代码不写裸 prompt 字符串
9. **HTTP 抓取统一走 `http_client`**，不要在新模块里 `requests.get`
10. **机构信息是辅助信号**，不要重新引入它作为排名维度
11. **推测类信息（机构、作者关系）必须明确是"判断"而非"事实"**
12. **日报"重点论文"展示不固定篇数**——按分数阈值动态选择，仅保留最小数作为低分日保底
13. **新增的评分叠加（作者 / 顶会）放在 `score_adjust.py`**，不要改 LLM 输出维度；规则需要配合 `BONUS_BUDGET` 封顶，保证"加分不会盖过内容质量"
14. **featured author 匹配必须"姓名 + 机构"双命中**，避免同名误判；新增 featured author 时给出至少 2 个机构关键词变体
15. **两层黑名单都在规则预筛阶段硬剔除**：`BLACKLIST_SUBJECTS` 看 arXiv 分区，`BLACKLIST_KEYWORDS` 看 title + abstract。黑名单不做"降权"——要么不感兴趣直接剔掉，要么让 LLM 去打分；中间状态只会让展示和审计变复杂

---

## 15. 已知未决与后续方向

### 15.1 PDF 首页机构抽取仍可继续提升

- 拆"标题区"和"页底脚注候选"分别送 LLM
- 加邮箱 / 版权声明 / 基金信息的清洗规则
- 视效果决定是否引入带坐标信息的 PDF 解析库（pdfplumber 等）

### 15.2 `crawler.py` 仍可继续拆

当前 `crawler.py` 同时承担：recent HTML 抓取 + API XML 解析 + 元数据补全 + 单篇查询 + coverage 探测。后续可以拆成：

- `recent_fetcher`
- `api_metadata_enricher`
- `paper_lookup`

### 15.2A `reports_json` 已收敛到单一目录

前端现在只读取根目录下的：

- `reports_json/`

`webapp/` 只保留静态页面本身，不再存放一份 JSON 镜像。这样目录职责更清晰，也减少了生成产物双写带来的维护成本。

### 15.3 作者关系 / 校企合作判断

旧版有过"作者顺序 / 合作类型"的 LLM 分析，目前主流程已不做。如果后续要重启，建议放在最终 TOP K 这一层，并输出半结构化字段（首作角色 / 末作角色 / 合作类型 / 主要机构 / 不确定点）而非自由文本。

### 15.4 测试与单测

当前只有 `test_author_affiliation_inference.py` / `test_crawler_recent.py` 两个端到端脚本。后续可以补：

- `prompts.render` 的单测（LaTeX / 缺变量 / 缓存）
- `extract_json` 的单测（容错路径）
- `models.Paper.merge_non_empty` 的单测（合并语义）
- `_normalize_ranked_papers` 的单测（兜底逻辑）

### 15.5 前端展示（Highlight + Longlist）

当前已经有一个首版静态前端：[`webapp/index.html`](webapp/index.html)。
前端不解析 Markdown，而是直接消费 `reports_json/` 下的结构化数据：

- `reports_json/index.json`
- `reports_json/daily/daily_report_YYYY-MM-DD.json`
- `reports_json/selected/selected_papers_YYYY-MM-DD.json`

页面当前提供两个标签页：

- `Highlight`：展示重点论文速览、重点论文列表、深度简报
- `Longlist`：展示 selected 全量评分表、方向汇总、排序/筛选/搜索

可能的形态：

- 每日首页卡片流继续增强：更好的深度分析排版、按方向聚类
- 历史归档页：按分数 / 机构 / 关键词筛选跨日期的论文
- 后续可以新增 `Recent` 标签页，展示抓取层全量统计和原始清单

当前的真实导出入口是：

- [`models.py`](models.py) 中 `Paper.to_dict()` / `RankedPaper.to_dict()`
- [`serializers.py`](serializers.py) 中 `build_selected_json_payload()` / `build_daily_json_payload()`
- [`main.py`](main.py) 负责落盘和刷新 `reports_json/index.json`

这条路线仍然保持"无后端服务"：主流程产 JSON，静态前端渲染。

### 15.6 外网访问 + 每日定时运行

希望脚本不再依赖本地开机，能定时跑、且前端可以在外网访问。

关键考量：

- **定时调度**：GitHub Actions 的 `schedule`（cron）完全能胜任，`main.py` 本来就是一次性脚本，跑完写文件即可。
- **结果托管**：Action 里把 `reports/` 与 `reports_json/` 产物 commit 回仓库（或推到一个 `reports` 分支），GitHub Pages 直接托管 `webapp/` 前端。
  这样"每日一跑 → 自动发版"形成闭环，无需独立服务器。
- **前端数据源**：GitHub Pages 上的 `webapp/` 直接相对路径读取 `reports_json/`，Markdown 继续保留给人工阅读和调试。
- **API key 保护**：**绝对不要**把 key 写进仓库或 `.env` 提交。应通过 GitHub Actions Secrets 注入
  （`secrets.LLM_API_KEY` 等），workflow 里 `env:` 段写成 `${{ secrets.* }}`。`.env` 保持在 `.gitignore` 里。
  如果担心 Action 日志误泄露，可以在脚本里裁掉 LLM 请求日志里可能带 key 的字段。
- **成本与频率**：默认 Action runner 跑一次就退出，不存在长驻进程，token 成本只和 LLM 调用挂钩。
- **备选**：如果后续想带后端（搜索 / 筛选交互），再考虑上 Vercel / Cloudflare Pages + Functions，
  把 LLM 调用 proxy 到服务端，前端拿不到 key。

### 15.7 统一时间轴到 `announced_date`

这项改动已经落地，当前系统按 **`announced_date` 维度** 组织核心产物：

- 抓取快照的每日统计按 `announced_date` 聚合
- `selected_papers_YYYY-MM-DD.*` / `daily_report_YYYY-MM-DD.*` 的日期语义按当天 announced 的论文理解
- 前端侧边栏按日期浏览时，查看的是当天 announced 的结果
- `published_day` 保留为辅助字段，只用于详情展示，或在 `announced_date` 缺失时 fallback

这次调整涉及的主要模块包括：

- [`recent_report.py`](recent_report.py)
- [`selected_report.py`](selected_report.py)
- [`reporter.py`](reporter.py)
- [`serializers.py`](serializers.py)
- [`webapp/app.js`](webapp/app.js)

---

## 16. 一句话总结

`paper_radio` 当前不是"一个爬虫脚本"，而是：

**一个以 arXiv recent 页面为输入、以用户研究偏好为核心、通过"规则预筛 + LLM 标题粗筛 + selected 集机构归一 + LLM 摘要精排 + 阈值过滤的深度精读"逐层收缩的论文筛选与摘要系统；数据用 dataclass 串联，prompt 模板外部化，HTTP / 日志 / LLM 调用走统一基础设施层，并同步产出 Markdown + JSON 供静态前端消费。**

# Paper Radio 设计总览

## 1. 文档目的

这份文档用于快速说明 `paper_radio` 当前的核心设计理念、关键模块分工、筛选与分析链路、已达成的设计决策，以及接下来继续演进时应遵守的原则。

目标读者：

- 新 session 中的模型
- 被压缩上下文后的继续协作者
- 后续维护这套工具的人

如果只看一页，需要记住这几个关键词：

- `recent 页面优先`
- `先抓全量，再逐层筛选`
- `规则预筛 + LLM 粗筛 + LLM 精排`
- `抓取快照 / 入选快照 / 最终日报` 三层输出
- `重点论文才做重分析`

---

## 2. 项目目标

`paper_radio` 不是一个通用论文爬虫，而是一个围绕用户研究偏好的“每日论文筛选与总结工具”。

当前主要目标：

1. 从 arXiv 最近几天的新论文里抓取候选
2. 按用户兴趣方向进行筛选、分类、排序
3. 生成抓取快照、入选快照和最终摘要报告
4. 对重点论文做更深层的分析，包括：
   - 方法分析
   - 贡献评价
   - 影响力判断
   - 作者顺序 / 机构合作关系判断

用户偏好重点领域当前包括：

- 端到端自动驾驶
- 世界模型
- VLA 模型
- 空间智能
- 自动驾驶大模型

这些定义集中在 [config.py](/Users/louis.zhang/Projects/paper_radio/config.py:26) 的 `TOPICS_OF_INTEREST`。

---

## 3. 核心设计理念

### 3.1 recent 页面优先，而不是全依赖 arXiv API

关键决策：

- “最近几天论文”这个需求，优先使用 arXiv 的 `recent` 页面
- 不优先依赖搜索 API 做 recent 查询

原因：

- `https://arxiv.org/list/<category>/recent` 本身就是 arXiv 官方面向用户展示“最近提交”的页面
- 页面上已经按天分组，更符合“最近 N 个自然日”的产品语义
- 搜索 API 更容易遇到限流、语法不稳定、时间过滤不直观等问题

当前实现：

- recent 页面抓取在 [crawler.py](/Users/louis.zhang/Projects/paper_radio/crawler.py:144)
- 覆盖范围探测在 [crawler.py](/Users/louis.zhang/Projects/paper_radio/crawler.py:176)

### 3.2 “最近 N 天”按自然日理解

关键决策：

- `--days 3` 表示“今天往回数 3 个自然日”
- 不是“滚动过去 72 小时”

原因：

- 与 `recent` 页面按日期段展示的方式一致
- 更符合日报和人工浏览习惯
- 周六、周日没有论文时，应该明确显示为 0

### 3.3 先抓全量，再逐层筛选

当前思路不是一开始就强约束，而是分层收缩：

1. 先抓 recent 页面上的全量候选
2. 再用规则预筛缩小范围
3. 再用 LLM 做标题粗筛
4. 再用 LLM 做摘要精排
5. 只对高价值论文做更重的分析

这是整套系统最重要的设计思想之一：

- 轻操作尽量前置
- 重操作只留给少数重点论文

### 3.4 不把所有判断都交给 LLM

关键决策：

- LLM 用在“语义判断”和“复杂关系推断”
- 规则和代码用在“结构化筛选”“兜底”“标准化”“排序”

原因：

- LLM 有波动
- 纯 LLM 成本更高
- 规则更便宜、更稳定

所以当前系统采用“规则 + LLM 混合”路线。

### 3.5 输出分层，而不是只有一份最终报告

当前有三类输出：

1. `recent_crawls`
   原始抓取快照，偏事实清单
2. `selected_papers`
   入选论文快照，偏筛选结果与中间产物
3. `daily_report`
   最终摘要报告，偏用户阅读体验

这样做的意义：

- 抓取层出问题时可单独排查
- 筛选层结果可以单独审阅
- 最终日报可以专注“值得读什么”和“为什么”

---

## 4. 当前目录与模块职责

### 4.1 主流程模块

- [main.py](/Users/louis.zhang/Projects/paper_radio/main.py:1)
  主入口。串联抓取、筛选、作者机构分析、快照保存、最终报告生成。

### 4.2 数据抓取模块

- [crawler.py](/Users/louis.zhang/Projects/paper_radio/crawler.py:1)
  负责：
  - 抓 arXiv recent 页面
  - 用 arXiv API 补摘要 / 作者 / affiliation
  - 仅为后续重点论文分析提供 HTML 作者/机构上下文抓取能力

### 4.3 排序模块

- [ranker.py](/Users/louis.zhang/Projects/paper_radio/ranker.py:1)
  负责：
  - 规则预筛
  - LLM 标题粗筛
  - LLM 摘要精排
  - 排名结果标准化

### 4.4 抓取快照渲染模块

- [recent_report.py](/Users/louis.zhang/Projects/paper_radio/recent_report.py:1)
  负责：
  - recent crawl 表格渲染
  - 每日统计表
  - Markdown 生成与保存

### 4.5 入选快照渲染模块

- [selected_report.py](/Users/louis.zhang/Projects/paper_radio/selected_report.py:1)
  负责：
  - 入选论文表格
  - 方向汇总

### 4.6 最终日报模块

- [reporter.py](/Users/louis.zhang/Projects/paper_radio/reporter.py:1)
  负责：
  - TOP 10 速览
  - TOP 10 详细卡片
  - 对最终 TOP 10 补充机构展示
  - 仅对达到阈值的论文做深度简报

### 4.7 LLM 抽象层

- [llm.py](/Users/louis.zhang/Projects/paper_radio/llm.py:1)
  统一封装 provider 切换。

### 4.8 配置层

- [config.py](/Users/louis.zhang/Projects/paper_radio/config.py:1)
  集中管理：
  - 抓取配置
  - 研究偏好
  - 输出目录
  - 深度分析阈值

---

## 5. 抓取层设计

### 5.1 recent 页面抓取是第一来源

抓取流程：

1. 对每个 category 访问 `https://arxiv.org/list/{category}/recent`
2. 解析页面上的 `h3` 日期分组
3. 在最近 N 个自然日范围内收集 `dt/dd` 条目
4. 得到：
   - `arxiv_id`
   - `title`
   - `authors`
   - `categories`
   - 基于日期段推断的 `published`

### 5.2 arXiv API 只做元数据补全

API 不是 recent 查询主入口，而是 recent 抓取后的补全层。

主要补：

- `abstract`
- 更完整的 `authors`
- `affiliations`
- 更稳定的 `published`

### 5.3 affiliation 获取策略

当前设计是分阶段处理机构信息：

1. 第一阶段全量抓取时，只使用 API 的 `<arxiv:affiliation>`
2. 第二阶段只对少量高价值论文抓取 HTML 标题附近的作者/机构段落，交给 LLM 做关系判断

这样设计的原因：

- 第一阶段目标是轻、快、稳定
- 不希望在全量候选上过早访问 HTML，增加请求成本
- 机构评分可以在第二步精排时结合 API 结果完成
- 更重的作者顺序 / 校企合作判断，只值得放在重点论文上做

明确不做：

- 第一阶段的 HTML affiliation 兜底
- PDF 首页解析

### 5.4 HTML 作者机构上下文的边界

当前 HTML 抓取不是为了给全量论文补结构化 affiliation，而是为了给重点论文提供额外语境。

定位：

- 用于辅助 LLM 判断作者顺序与合作关系
- 用于补充 API 未显式表达的上下文线索
- 不用于严格的作者-单位一一映射事实判定

---

## 6. 筛选与排序设计

### 6.1 三层筛选结构

当前筛选结构：

1. 本地规则预筛
2. LLM 标题粗筛
3. LLM 摘要精排

### 6.2 本地规则预筛

位置：

- [ranker.py](/Users/louis.zhang/Projects/paper_radio/ranker.py:82)

原理：

- 拼接 `title + abstract + categories`
- 用本地关键词表 `PREFILTER_KEYWORDS` 做低成本命中
- 目的是先过滤掉明显不相关论文

设计目标：

- 降低第一轮 LLM 输入量
- 提高稳定性
- 节省 token

注意：

- 它不是最终判断
- 只是“便宜地先缩小候选集合”

### 6.3 第一阶段：LLM 标题粗筛

位置：

- [ranker.py](/Users/louis.zhang/Projects/paper_radio/ranker.py:84)

策略：

- 只发 `title + arxiv_id`
- 让 LLM 根据用户兴趣方向挑相关论文

不做的事：

- 不在第一步做机构评分
- 不在第一步做作者合作分析

这是刻意设计的，因为第一步要轻、快、便宜。

### 6.4 第二阶段：LLM 摘要精排

位置：

- [ranker.py](/Users/louis.zhang/Projects/paper_radio/ranker.py:121)

输入：

- 标题
- 作者
- 摘要

输出字段：

- `relevance_score`
- `novelty_score`
- `total_score`
- `topic_category`
- `one_line_summary`

关键设计点：

- 排序阶段不再引入机构评分
- 机构推断只在最终 TOP 10 展示时补充

### 6.5 排序结果标准化

位置：

- [ranker.py](/Users/louis.zhang/Projects/paper_radio/ranker.py:46)

为什么需要：

- LLM 有时会漏字段
- 分数格式可能不统一
- rank 可能乱

当前标准化做的事：

- 分数字段转整数
- `total_score` 缺失时自动补
- `topic_category` 缺失时补 `未分类`
- `one_line_summary` 缺失时用摘要首句或标题兜底
- 最后按分数重新排序并重写 rank

---

## 7. 作者/机构关系分析设计

### 7.1 为什么要引入 LLM

用户关心的不只是“有哪些机构”，还关心：

- 第一作者是否像主要执行者
- 末位作者是否像 PI / 老板
- 校企合作更像实习合作还是毕业后入职
- 是否存在多机构联合

这些判断不适合纯规则硬推。

### 7.2 为什么不在抓取阶段做

关键决策：

- 不对所有抓取论文都做作者/机构关系分析
- 只对最终少量高价值论文做

原因：

- HTML 抓取有网络成本
- LLM 分析有调用成本
- 大多数候选论文不值得做这层重分析

### 7.3 当前做法

当前版本已经不再在主流程里做作者顺序 / 合作关系判断。

机构相关的重分析被收缩为：

1. 排序阶段不做机构评分
2. `selected_papers` 不展示机构字段
3. 仅在最终日报前，对 TOP 10 论文做一次 PDF 首页驱动的机构推断

### 7.4 粒度要求

当前机构推断要求 LLM：

- 机构识别到学校 / 公司 / 研究机构层级
- 不分析到学院、系、实验室层级

### 7.5 输出位置

这部分结果目前写在：

- `selected_papers_YYYY-MM-DD.md` 的 `作者/机构关系判断` 章节

原因：

- 比放进表格更易读
- 这类判断带推测性，不宜伪装成硬字段

---

## 8. 深度简报设计

### 8.1 不再固定分析前 3 篇

关键决策：

- 不再写死 `TOP 3`
- 改成“达到阈值的论文，最多分析 K 篇”

原因：

- 有些天可能没有真正值得精读的论文
- 固定分析 3 篇会显得机械

### 8.2 当前策略

配置在 [config.py](/Users/louis.zhang/Projects/paper_radio/config.py:59)：

- `DEEP_ANALYSIS_MAX_PAPERS = 5`
- `DEEP_ANALYSIS_MIN_TOTAL_SCORE = 20`

也就是：

- 总分低于阈值，不做精读
- 达到阈值的论文，最多精读 5 篇

### 8.3 当天没有论文达标时

报告里会明确写：

- 今日没有达到精读阈值的论文，因此不生成深度分析

---

## 9. 输出文档设计

### 9.1 输出目录分层

当前输出目录：

- `reports/`
  - 最终日报
- `reports/recent_crawls/`
  - 抓取快照
- `reports/selected_papers/`
  - 入选论文快照

### 9.2 文件命名原则

抓取快照：

- `recent_crawl_YYYY-MM-DD.md`

入选快照：

- `selected_papers_YYYY-MM-DD.md`

最终日报：

- `daily_report_YYYY-MM-DD.md`

设计原则：

- 按天命名
- 同一天重复运行覆盖
- 不在文件名里塞 category，保持稳定路径

### 9.3 为什么要保留中间快照

原因：

- 便于排查“抓到了什么”
- 便于核对“为什么选了这些”
- 便于把“抓取问题”和“排序问题”分开调试

---

## 10. 当前已实现的重要体验细节

这些是已经确认过的设计要求：

- recent crawl 的论文表格按 `arXiv ID` 排序
- recent crawl 表格展示：
  - 完整标题
  - 作者
  - 机构
  - Subjects（缩写）
  - URL
  - 发布时间
- 每日统计显示：
  - 自然日
  - 总量
  - 各分类数量
- 当查询天数超出 `recent` 页最早覆盖日期时，明确提示用户
- `selected_papers` 的“一句话总结”不做截断
- 机构信息仅在最终日报的 TOP 10 中展示

---

## 11. 关键未决与后续建议

### 11.1 PDF 首页机构抽取仍可继续增强

当前机构推断已经收缩到仅对 TOP 10 做，但 PDF 首页证据仍然有进一步提升空间。

建议后续做法：

- 将 PDF 首页拆成标题区块与页底脚注候选分别输入
- 增加邮箱、版权声明、基金信息的清洗规则
- 强化 footnote / affiliation 模式识别
- 视效果决定是否引入带坐标信息的 PDF 解析库

### 11.2 规则预筛关键词应迁移到配置

当前 `PREFILTER_KEYWORDS` 还在代码里。

后续可迁移到：

- `config.py`

好处：

- 调整偏好无需改代码
- 更适合长期维护

### 11.3 增加“降权黑名单关键词”

除了正向兴趣关键词，还应增加一组“降权关键词”。

设计意图：

- 命中这些方向时，不直接过滤论文
- 但如果论文的方法或贡献点明显围绕这些方向，应降低排序权重

当前已记录的候选关键词：

- `V2X`
- `V2V`
- `Drone Racing`
- `Remote Sensing`

建议实现方式：

- 放在摘要精排附近，而不是规则预筛阶段一刀切
- 区分“只是背景提及”与“核心方法/贡献相关”
- 通过 penalty score 影响最终排序，而不是直接丢弃

### 11.4 crawler 仍可继续拆分

当前 `crawler.py` 职责偏多，后续可以拆成：

- `recent_fetcher`
- `api_metadata_enricher`
- `paper_lookup`

### 11.5 作者关系分析可进一步结构化

当前是自由文本判断。

后续可改成半结构化字段：

- 第一作者角色判断
- 末位作者角色判断
- 合作类型判断
- 主要机构列表
- 不确定点

---

## 12. 维护时的硬原则

后续继续改这套工具时，尽量遵守这些原则：

1. recent 页面仍应是“最近论文”的第一来源  
2. 重分析只对少量重点论文做  
3. 规则用于降本和稳定，LLM 用于复杂语义判断  
4. 中间快照不要删，它们是可观察性的关键  
5. 对 LLM 输出要有代码兜底，不要直接信任  
6. 用户真正关心的是“方向相关性”，机构只是辅助信号  
7. 推测类信息必须明确是“判断”而不是“事实”  

---

## 13. 一句话总结

`paper_radio` 当前的正确理解方式不是“一个爬虫脚本”，而是：

一个以 arXiv recent 为输入、以用户研究偏好为核心、通过“规则预筛 + LLM 语义筛选 + 重点论文深度分析”逐层收缩的信息筛选系统。

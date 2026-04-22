import os
from pathlib import Path

# ── arXiv 爬取配置 ────────────────────────────────────────────────────────────

# 爬取的分区列表。默认聚焦视觉与机器人方向。
FETCH_CATEGORIES = [
    "cs.CV",
    "cs.RO",
]

# 向前追溯天数，主流程和测试脚本都会使用这个默认值。
DAYS_BACK = int(os.getenv("DAYS_BACK", "3"))

# arXiv API 批量抓取参数
ARXIV_PAGE_SIZE = int(os.getenv("ARXIV_PAGE_SIZE", "100"))
ARXIV_MAX_RESULTS = int(os.getenv("ARXIV_MAX_RESULTS", "500"))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "60"))
REQUEST_RETRIES = int(os.getenv("REQUEST_RETRIES", "3"))
REQUEST_RETRY_BASE_SLEEP = int(os.getenv("REQUEST_RETRY_BASE_SLEEP", "5"))

MAX_PAPERS_TO_RANK = 200  # 送给 LLM 的上限（两阶段筛选）

# ── 规则预筛黑名单 ────────────────────────────────────────────────────────────
# 只要论文的任一 arXiv subject 命中这个集合，就在规则预筛阶段直接剔除，
# 不再消耗 LLM。subject 比对 case-insensitive，但写法建议保留官方大小写。
BLACKLIST_SUBJECTS = [
    "eess.SY",  # Systems and Control
    "cs.MA",    # Multiagent Systems
    "cs.SE",    # Software Engineering
    "cs.HC",    # Human-Computer Interaction
    "cs.OS",    # Operating Systems
]

# ── 排名偏好 ──────────────────────────────────────────────────────────────────

TOPICS_OF_INTEREST = """
1. 端到端自动驾驶 (E2E Autonomous Driving)：端到端规划、感知-决策一体化、数据驱动驾驶、BEV感知
2. 世界模型 (World Models)：驾驶场景视频生成/预测、时空建模、4D生成、物理仿真
3. VLA模型 (Vision-Language-Action)：机器人操作、多模态指令跟随、语言条件策略
4. 空间智能 (Spatial Intelligence)：3D高斯、VGGT、深度估计、三维重建、空间推理
5. 自动驾驶大模型：多模态预训练、占据预测、场景理解大模型
"""

# ── LLM 后端配置 ──────────────────────────────────────────────────────────────
# 可选：anthropic | kimi | zhipu | deepseek | custom
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic")

# 模型分档：
# - fast 档用于标题粗筛 / 机构推断（任务简单，要便宜快）
# - strong 档用于摘要精排 / 深度精读（需要语义理解和打分判断）
# 留空则使用 llm.py 中各 provider 的默认模型；旧 LLM_MODEL 会被当作 STRONG_MODEL 兼容。
FAST_MODEL = os.getenv("FAST_MODEL", "")
STRONG_MODEL = os.getenv("STRONG_MODEL", os.getenv("LLM_MODEL", ""))

# ── 评分体系 ──────────────────────────────────────────────────────────────────
# LLM 直接产出的"原始分"：relevance (0-10) + novelty (0-10)
RAW_SCORE_MAX = 20
# 最终显示的总分上限 = 原始分上限 + 加分项预算（重点作者 / 顶会录用等）
# 留出 +10 的 bonus 余量，后续 PR 引入加分维度时不用再次扩表。
TOTAL_SCORE_MAX = 30

# ── 深度分析配置 ──────────────────────────────────────────────────────────────
DEEP_ANALYSIS_MAX_PAPERS = int(os.getenv("DEEP_ANALYSIS_MAX_PAPERS", "3"))
# 总分 ≥ 21 才做精读（约为新总分上限 30 的 70%）
DEEP_ANALYSIS_MIN_TOTAL_SCORE = int(os.getenv("DEEP_ANALYSIS_MIN_TOTAL_SCORE", "21"))

# ── 日报展示阈值 ──────────────────────────────────────────────────────────────
# 速览 / 卡片动态展示：分数 ≥ TOP_DISPLAY_MIN_SCORE 的全部显示，
# 同时保底至少 TOP_DISPLAY_MIN_COUNT 篇（防止低分日什么都没有）。
TOP_DISPLAY_MIN_SCORE = int(os.getenv("TOP_DISPLAY_MIN_SCORE", "18"))
TOP_DISPLAY_MIN_COUNT = int(os.getenv("TOP_DISPLAY_MIN_COUNT", "5"))

# ── 机构推断配置 ──────────────────────────────────────────────────────────────
# 每篇论文独立调用 LLM 推断机构，这里控制并发上限。LLM API 通常允许 4-8 并发，
# 同时也是 arXiv PDF 抓取的并发数；调高时注意 provider rate limit 与 arxiv 礼貌性。
INSTITUTION_INFERENCE_CONCURRENCY = int(os.getenv("INSTITUTION_INFERENCE_CONCURRENCY", "4"))

# ── 输出配置 ──────────────────────────────────────────────────────────────────
OUTPUT_DIR = Path("reports")
CRAWL_OUTPUT_DIR = OUTPUT_DIR / "recent_crawls"
SELECTED_OUTPUT_DIR = OUTPUT_DIR / "selected_papers"
 
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

# ── 两阶段筛选参数 ────────────────────────────────────────────────────────────
# MAX_PAPERS_TO_RANK：stage1 标题粗筛发给 LLM 的最大论文数（LLM 输入上限）。
# STAGE1_KEEP：stage1 粗筛后希望保留进入摘要精排的目标数量，也是 LLM 失败时的兜底 top-K。
MAX_PAPERS_TO_RANK = int(os.getenv("MAX_PAPERS_TO_RANK", "200"))
STAGE1_KEEP = int(os.getenv("STAGE1_KEEP", "30"))

# ── 规则预筛 ──────────────────────────────────────────────────────────────────
# 三步流程（顺序与 ``ranker._rule_prefilter`` 对应）：
#   1) BLACKLIST_SUBJECTS 硬剔除  →  2) PREFILTER_KEYWORDS 白名单命中保留
#   →  3) BLACKLIST_KEYWORDS 硬剔除

# subject 黑名单：论文任一 arXiv subject 命中即直接剔除，不消耗后续 LLM。
# subject 比对 case-insensitive，但写法建议保留官方大小写。
BLACKLIST_SUBJECTS = [
    "eess.SY",  # Systems and Control
    "cs.MA",    # Multiagent Systems
    "cs.SE",    # Software Engineering
    "cs.HC",    # Human-Computer Interaction
    "cs.OS",    # Operating Systems
    "cs.DB",    # Databases
    "cs.NE",    # Neural and Evolutionary Computing
    "cs.CL",    # Computation and Language
    "cs.ET",    # Emerging Technologies
]

# 关键词白名单：对 title + abstract + categories 拼接后小写匹配（substring）。
# 命中任一即保留，否则剔除。全量未命中时会 fallback 取前 STAGE1_KEEP*2 篇兜底。
PREFILTER_KEYWORDS = [
    "autonomous driving", "driving", "driverless", "end-to-end", "e2e",
    "world model", "world models", "video prediction", "occupancy",
    "bev", "4d", "spatial", "3d", "gaussian", "reconstruction",
    "depth estimation", "slam", "localization", "navigation",
    "robot", "robotics", "manipulation", "locomotion",
    "vision-language-action", "vla", "foundation model",
    "multimodal foundation model", "scene understanding", "embodied ai",
]

# 关键词黑名单：扫描 title + abstract，任一关键词命中即剔除。
# 与 BLACKLIST_SUBJECTS 的分工——subject 是整篇分区不对口；关键词是分区沾边但主题
# 明确跑偏（例如 cs.RO 里的 Drone Racing / UAV）。
# 匹配规则：case-insensitive + word boundary + 可选复数 ``s?``；词组内部的空格用
# ``\s+`` 匹配，避免 "Drone  Racing"（双空格）漏检。
BLACKLIST_KEYWORDS = [
    "Drone Racing",
    "V2V",
    "V2X",
    "Remote Sensing",
    "UAV",
    "Quadrotor",
    "Underwater",
    "MAV",
    "Bio-Inspired",
    "Bio-Inspiration",
    "Tactile",
    "Tactile Sensing",
    "Peg-in-Hole",
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

# ── 加分规则（在 stage2 LLM 打分之后叠加，受 BONUS_BUDGET 硬封顶）────────────
# 重点关注作者：姓名 → 机构关键词列表（姓名 / 关键词都 case-insensitive）
# 需要"姓名命中 AND 机构关键词命中"才算，避免同名误伤。
# 机构关键词会对 normalized_institutions + affiliations + institution_summary 做 substring 匹配，
# 所以写几个变体即可（英文缩写 + 全称 + 中文名都可）。
FEATURED_AUTHORS = {
    "Hongyang Li": ["HKU", "University of Hong Kong", "香港大学"],
    "Hao Zhao":    ["Tsinghua", "THU", "清华"],
    "Hang Zhao":   ["Tsinghua", "THU", "清华"],
}
# 每命中一位 featured author 加多少分
AUTHOR_BONUS_PER_HIT = int(os.getenv("AUTHOR_BONUS_PER_HIT", "3"))
# 同一篇 author_bonus 累计封顶（防止"四位 featured author 同台"直接冲顶）
AUTHOR_BONUS_CAP = int(os.getenv("AUTHOR_BONUS_CAP", "6"))

# 顶级会议列表（命中 arXiv comments 即视为录用）。命名按学术社区习惯。
FEATURED_VENUES = ["CVPR", "ICCV", "NeurIPS", "ICLR", "ECCV", "ICML", "CoRL", "RSS"]
# 单篇命中顶会加多少分（不叠加，同一篇命中多个也只加一次）
VENUE_BONUS = int(os.getenv("VENUE_BONUS", "4"))

# 总 bonus 硬封顶 = TOTAL_SCORE_MAX - RAW_SCORE_MAX
# 超过预算的 bonus 会被截断。
BONUS_BUDGET = TOTAL_SCORE_MAX - RAW_SCORE_MAX

# ── 机构推断配置 ──────────────────────────────────────────────────────────────
# 每篇论文独立调用 LLM 推断机构，这里控制并发上限。LLM API 通常允许 4-8 并发，
# 同时也是 arXiv PDF 抓取的并发数；调高时注意 provider rate limit 与 arxiv 礼貌性。
INSTITUTION_INFERENCE_CONCURRENCY = int(os.getenv("INSTITUTION_INFERENCE_CONCURRENCY", "4"))

# ── 输出配置 ──────────────────────────────────────────────────────────────────
OUTPUT_DIR = Path("reports")
CRAWL_OUTPUT_DIR = OUTPUT_DIR / "recent_crawls"
SELECTED_OUTPUT_DIR = OUTPUT_DIR / "selected_papers"
REPORTS_JSON_DIR = Path("reports_json")
DAILY_JSON_OUTPUT_DIR = REPORTS_JSON_DIR / "daily"
SELECTED_JSON_OUTPUT_DIR = REPORTS_JSON_DIR / "selected"
 

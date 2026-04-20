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

# 留空则使用 llm.py 中各 provider 的默认模型
MODEL = os.getenv("LLM_MODEL", "")

# ── 深度分析配置 ──────────────────────────────────────────────────────────────
# 排名只用 relevance + novelty 两个 0-10 维度，总分上限 20。阈值 14 相当于 70%。
DEEP_ANALYSIS_MAX_PAPERS = int(os.getenv("DEEP_ANALYSIS_MAX_PAPERS", "3"))
DEEP_ANALYSIS_MIN_TOTAL_SCORE = int(os.getenv("DEEP_ANALYSIS_MIN_TOTAL_SCORE", "14"))
# 评分显示用的总分上限（相关性 0-10 + 新颖性 0-10）。
TOTAL_SCORE_MAX = 20

# ── 输出配置 ──────────────────────────────────────────────────────────────────
OUTPUT_DIR = Path("reports")
CRAWL_OUTPUT_DIR = OUTPUT_DIR / "recent_crawls"
SELECTED_OUTPUT_DIR = OUTPUT_DIR / "selected_papers"
 
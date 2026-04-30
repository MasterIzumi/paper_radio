function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

async function apiJson(url) {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `请求失败：${response.status} ${response.statusText}`);
  }
  return response.json();
}

function showError(message) {
  const banner = document.getElementById("error-banner");
  banner.textContent = message;
  banner.classList.remove("hidden");
}

async function init() {
  const params = new URLSearchParams(window.location.search);
  const arxivId = params.get("arxiv_id");
  const date = params.get("date") || "";
  if (!arxivId) {
    throw new Error("缺少 arxiv_id 参数。");
  }

  const query = date ? `?date=${encodeURIComponent(date)}` : "";
  const report = await apiJson(`/api/deep-analysis/${encodeURIComponent(arxivId)}/report${query}`);

  document.getElementById("report-title").textContent = report.title || report.arxiv_id;
  document.getElementById("report-meta").innerHTML = `
    <span class="tag">${escapeHtml(report.arxiv_id)}</span>
    <span class="tag">公布 ${escapeHtml(report.announced_day || report.date || "-")}</span>
    <span class="tag">${escapeHtml(report.topic_category || "未分类")}</span>
    ${report.total_score !== "" ? `<span class="tag">总分 ${escapeHtml(report.total_score)}</span>` : ""}
    <a class="tag" href="${escapeHtml(report.primary_url || `https://arxiv.org/abs/${report.arxiv_id}`)}" target="_blank" rel="noreferrer">arXiv</a>
  `;
  document.getElementById("report-body").textContent =
    report.report_markdown || report.analysis_markdown || "暂无AI解读正文。";
}

init().catch((error) => {
  showError(`AI解读报告加载失败：${error.message}`);
});

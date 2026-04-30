const DATA_INDEX_URL = "../reports_json/index.json";
const API_INDEX_URL = "/api/reports/index";

const state = {
  index: null,
  apiAvailable: false,
  currentDate: "",
  currentTab: window.location.hash === "#daily"
    ? "daily"
    : window.location.hash === "#deep"
      ? "deep"
      : window.location.hash === "#favorites"
        ? "favorites"
        : "selected",
  daily: null,
  selected: null,
  selectedSort: "total",
  selectedTopic: "",
  selectedSearch: "",
  activeDailyId: "",
  favorites: [],
  deepReads: [],
  deepReadsError: "",
  deepAnalysis: {},
  currentJobId: "",
  jobPollTimer: null,
  miningExpanded: false,
  miningRunning: false,
};

const el = {
  dateRail: document.getElementById("date-rail"),
  metaDate: document.getElementById("meta-date"),
  metaGeneratedAt: document.getElementById("meta-generated-at"),
  metaCategories: document.getElementById("meta-categories"),
  metaModels: document.getElementById("meta-models"),
  protocolWarning: document.getElementById("protocol-warning"),
  errorBanner: document.getElementById("error-banner"),
  dailySummaryCards: document.getElementById("daily-summary-cards"),
  dailyThresholdNote: document.getElementById("daily-threshold-note"),
  dailyTopGrid: document.getElementById("daily-top-grid"),
  dailyDetail: document.getElementById("daily-detail"),
  deepAnalysisList: document.getElementById("deep-analysis-list"),
  topicSummary: document.getElementById("topic-summary"),
  selectedSort: document.getElementById("selected-sort"),
  selectedTopicFilter: document.getElementById("selected-topic-filter"),
  selectedSearch: document.getElementById("selected-search"),
  selectedTableBody: document.getElementById("selected-table-body"),
  miningWidget: document.getElementById("mining-widget"),
  miningToggle: document.getElementById("mining-toggle"),
  miningForm: document.getElementById("mining-form"),
  miningSubmit: document.querySelector("#mining-form button[type='submit']"),
  miningDays: document.getElementById("mining-days"),
  miningCategories: document.getElementById("mining-categories"),
  jobCancelButton: document.getElementById("job-cancel-button"),
  jobResetButton: document.getElementById("job-reset-button"),
  jobStatus: document.getElementById("job-status"),
  jobLog: document.getElementById("job-log"),
  favoritesList: document.getElementById("favorites-list"),
  deepReadList: document.getElementById("deep-read-list"),
  tabButtons: [...document.querySelectorAll(".tab-button")],
  tabPanels: [...document.querySelectorAll(".tab-panel")],
};

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function prettyTime(value) {
  if (!value) return "-";
  return value.replace("T", " ");
}

function formatDateLabel(date) {
  const [year, month, day] = date.split("-");
  return `${month}/${day}`;
}

function formatWeekdayShort(dateString) {
  const date = new Date(`${dateString}T00:00:00`);
  return date.toLocaleDateString("en-US", { weekday: "short" });
}

function formatMonthLabel(monthKey) {
  const [year, month] = monthKey.split("-");
  return `${year}.${month}`;
}

function pad2(value) {
  return String(value).padStart(2, "0");
}

function formatLocalDate(date) {
  return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`;
}

function getWeekKey(dateString) {
  const date = new Date(`${dateString}T00:00:00`);
  const day = date.getDay();
  const diffToMonday = day === 0 ? -6 : 1 - day;
  const monday = new Date(date);
  monday.setDate(date.getDate() + diffToMonday);
  const sunday = new Date(monday);
  sunday.setDate(monday.getDate() + 6);
  const start = formatLocalDate(monday);
  const end = formatLocalDate(sunday);
  return `${start}|${end}`;
}

function formatWeekLabel(weekKey) {
  const [start, end] = weekKey.split("|");
  return `${start.slice(5)} - ${end.slice(5)}`;
}

function joinOrDash(values) {
  if (!Array.isArray(values) || !values.length) return "—";
  return values.join("; ");
}

function institutionDisplay(paper) {
  return (
    paper.affiliations_display ||
    paper.institution_summary ||
    joinOrDash(paper.normalized_institutions) ||
    "—"
  );
}

function showError(message) {
  el.errorBanner.textContent = message;
  el.errorBanner.classList.remove("hidden");
}

function clearError() {
  el.errorBanner.textContent = "";
  el.errorBanner.classList.add("hidden");
}

async function fetchJson(url) {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`请求失败：${response.status} ${response.statusText}`);
  }
  return response.json();
}

async function apiJson(url, options = {}) {
  const response = await fetch(url, {
    cache: "no-store",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `请求失败：${response.status} ${response.statusText}`);
  }
  return response.json();
}

async function loadIndex() {
  try {
    const payload = await apiJson(API_INDEX_URL);
    state.apiAvailable = true;
    return payload;
  } catch (error) {
    state.apiAvailable = false;
    return fetchJson(DATA_INDEX_URL);
  }
}

async function loadFavorites() {
  if (!state.apiAvailable) {
    state.favorites = [];
    return;
  }
  try {
    const payload = await apiJson("/api/favorites");
    state.favorites = payload.favorites || [];
  } catch (error) {
    state.favorites = [];
  }
}

async function loadDeepReads() {
  if (!state.apiAvailable) {
    state.deepReads = [];
    state.deepReadsError = "";
    return;
  }
  try {
    const payload = await apiJson("/api/deep-analysis");
    state.deepReads = payload.items || [];
    state.deepReadsError = "";
  } catch (error) {
    state.deepReads = [];
    state.deepReadsError = error.message;
  }
}

async function resumeRunningJob() {
  if (!state.apiAvailable) return;
  try {
    const payload = await apiJson("/api/jobs");
    const running = (payload.jobs || []).find((job) =>
      job.type === "mining" &&
      (job.status === "queued" || job.status === "running" || job.status === "cancel_requested")
    );
    if (running) {
      setMiningRunning(true);
      setMiningExpanded(false);
      pollJob(running.id);
    }
  } catch (error) {
    setMiningRunning(false);
  }
}

function isFavorite(arxivId) {
  return state.favorites.some((item) => item.arxiv_id === arxivId);
}

function hasAiInsight(arxivId) {
  return (
    state.deepAnalysis[arxivId]?.status === "succeeded" ||
    state.deepReads.some((item) => item.arxiv_id === arxivId && item.status === "succeeded")
  );
}

function findPaper(arxivId) {
  const collections = [
    state.daily?.top_display_papers || [],
    state.selected?.papers || [],
  ];
  for (const collection of collections) {
    const paper = collection.find((item) => item.arxiv_id === arxivId);
    if (paper) return paper;
  }
  return null;
}

function getRequestedDate() {
  const params = new URLSearchParams(window.location.search);
  return params.get("date") || "";
}

function updateUrl() {
  const url = new URL(window.location.href);
  if (state.currentDate) {
    url.searchParams.set("date", state.currentDate);
  }
  url.hash = state.currentTab === "selected"
    ? "#selected"
    : state.currentTab === "daily"
      ? "#daily"
    : state.currentTab === "deep"
      ? "#deep"
      : state.currentTab === "favorites"
        ? "#favorites"
        : "#selected";
  window.history.replaceState({}, "", url);
}

function switchTab(tab) {
  state.currentTab = tab;
  el.tabButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.tab === tab);
  });
  el.tabPanels.forEach((panel) => {
    panel.classList.toggle("active", panel.id === `${tab}-tab`);
  });
  updateUrl();
}

function renderMeta() {
  const entry = state.index?.entries?.find((item) => item.date === state.currentDate);
  const generatedAt = state.daily?.generated_at || state.selected?.generated_at || entry?.daily_generated_at || "-";
  const categories = state.daily?.categories || state.selected?.categories || entry?.categories || [];
  const models = state.daily?.models
    ? `${state.daily.models.fast} / ${state.daily.models.strong}`
    : "-";

  el.metaDate.textContent = state.currentDate || "-";
  el.metaGeneratedAt.textContent = prettyTime(generatedAt);
  el.metaCategories.textContent = categories.length ? categories.join(", ") : "-";
  el.metaModels.textContent = models;
  if (el.jobStatus && !state.apiAvailable) {
    el.jobStatus.textContent = "当前是静态浏览模式：可以看结果，不能启动任务、AI解读或收藏。";
  }
}

function setMiningExpanded(expanded) {
  state.miningExpanded = Boolean(expanded);
  el.miningWidget.classList.toggle("collapsed", !state.miningExpanded);
  el.miningWidget.classList.toggle("expanded", state.miningExpanded);
  el.miningToggle.setAttribute("aria-expanded", String(state.miningExpanded));
}

function setMiningRunning(running) {
  state.miningRunning = Boolean(running);
  el.miningWidget.classList.toggle("running", state.miningRunning);
}

function setMiningLogVisible(visible) {
  el.miningWidget.classList.toggle("with-log", Boolean(visible));
}

function buildSidebarGroups(entries) {
  return entries;
}

function renderDateRail() {
  const entries = buildSidebarGroups(state.index?.entries || []);
  el.dateRail.innerHTML = entries
    .map((entry) => `
      <button class="rail-date ${entry.date === state.currentDate ? "active" : ""}" data-rail-date="${escapeHtml(entry.date)}">
        <span class="rail-date-day">${escapeHtml(entry.date.slice(5))}</span>
        <span class="rail-date-weekday">${escapeHtml(formatWeekdayShort(entry.date))}</span>
      </button>
    `)
    .join("");

  document.querySelectorAll("[data-rail-date]").forEach((node) => {
    node.addEventListener("click", async () => {
      try {
        await loadDate(node.dataset.railDate);
      } catch (error) {
        showError(`切换日期失败：${error.message}`);
      }
    });
  });
}

function renderDailySummary() {
  const daily = state.daily;
  if (!daily) return;

  const cards = [
    {
      label: "Longlist 论文数",
      value: daily.selected_paper_count,
      note: "通过粗筛并完成精排的候选池规模",
    },
    {
      label: "重点展示数",
      value: daily.top_display_papers.length,
      note: `阈值 ${daily.display_policy.top_display_min_score}，至少展示 ${daily.display_policy.top_display_min_count} 篇`,
    },
    {
      label: "深度分析数",
      value: daily.deep_analysis_papers.length,
      note: `精读阈值 ${daily.deep_analysis_policy.min_total_score}，最多 ${daily.deep_analysis_policy.max_papers} 篇`,
    },
  ];

  el.dailySummaryCards.innerHTML = cards
    .map(
      (card) => `
        <article class="summary-card">
          <p class="eyebrow">${escapeHtml(card.label)}</p>
          <strong>${escapeHtml(card.value)}</strong>
          <p class="subtle">${escapeHtml(card.note)}</p>
        </article>
      `
    )
    .join("");

  el.dailyThresholdNote.textContent =
    `展示规则：总分 >= ${daily.display_policy.top_display_min_score}，若不足则保底显示 ${daily.display_policy.top_display_min_count} 篇`;
}

function setActiveDailyPaper(arxivId) {
  state.activeDailyId = arxivId;
  renderDailyCards();
  renderDailyDetail();
}

async function toggleFavorite(arxivId) {
  if (!state.apiAvailable) {
    showError("收藏需要通过本地 Dashboard 服务访问。");
    return;
  }
  const paper = findPaper(arxivId);
  try {
    if (isFavorite(arxivId)) {
      await apiJson(`/api/favorites/${encodeURIComponent(arxivId)}`, { method: "DELETE" });
    } else {
      await apiJson(`/api/favorites/${encodeURIComponent(arxivId)}`, {
        method: "POST",
        body: JSON.stringify({
          title: paper?.title || "",
          source_date: state.currentDate || paper?.announced_day || "",
          primary_url: paper?.primary_url || "",
          topic_category: paper?.topic_category || "",
          tags: [],
          note: "",
        }),
      });
    }
    await loadFavorites();
    renderDailyCards();
    renderDailyDetail();
    renderSelectedTable();
    renderFavorites();
  } catch (error) {
    showError(`收藏操作失败：${error.message}`);
  }
}

async function requestDeepAnalysis(arxivId) {
  if (!state.apiAvailable) {
    showError("按需 AI解读需要通过本地 Dashboard 服务访问。");
    return;
  }
  try {
    const query = state.currentDate ? `?date=${encodeURIComponent(state.currentDate)}` : "";
    const item = await apiJson(
      `/api/papers/${encodeURIComponent(arxivId)}/deep-analysis${query}`,
      { method: "POST" }
    );
    state.deepAnalysis[arxivId] = item;
    renderDailyDetail();
    renderSelectedTable();
    pollDeepAnalysis(arxivId);
  } catch (error) {
    showError(`AI解读任务启动失败：${error.message}`);
  }
}

async function pollDeepAnalysis(arxivId) {
  if (!state.apiAvailable) return;
  const query = state.currentDate ? `?date=${encodeURIComponent(state.currentDate)}` : "";
  for (let attempt = 0; attempt < 120; attempt += 1) {
    await new Promise((resolve) => setTimeout(resolve, 2000));
    try {
      const item = await apiJson(`/api/papers/${encodeURIComponent(arxivId)}/deep-analysis${query}`);
      state.deepAnalysis[arxivId] = item;
      renderDailyDetail();
      renderSelectedTable();
      if (item.status !== "running") {
        await loadDeepReads();
        renderDeepReads();
        return;
      }
    } catch (error) {
      return;
    }
  }
}

function renderDailyCards() {
  const papers = state.daily?.top_display_papers || [];
  if (!papers.length) {
    el.dailyTopGrid.innerHTML = '<div class="detail-empty">当日没有可展示的重点论文。</div>';
    return;
  }

  el.dailyTopGrid.innerHTML = papers
    .map((paper) => {
      const active = paper.arxiv_id === state.activeDailyId ? "active" : "";
      return `
        <article class="paper-card ${active}" data-daily-id="${escapeHtml(paper.arxiv_id)}">
          <p class="eyebrow">#${escapeHtml(paper.rank || "-")} · ${escapeHtml(paper.topic_category || "未分类")}</p>
          <h3>${escapeHtml(paper.title)}</h3>
          <div class="score-row">
            <span class="score-pill">总分 ${escapeHtml(paper.total_score)}</span>
            <span class="score-pill">相关性 ${escapeHtml(paper.relevance_score)}</span>
            <span class="score-pill">新颖性 ${escapeHtml(paper.novelty_score)}</span>
          </div>
          <p class="paper-meta">${escapeHtml(paper.authors_display || joinOrDash(paper.authors))}</p>
          <div class="card-institution">
            <p class="paper-meta institution-meta">${escapeHtml(institutionDisplay(paper))}</p>
          </div>
          <p>${escapeHtml(paper.one_line_summary || "暂无一句话总结")}</p>
          <div class="link-row">
            <a class="link-chip" href="${escapeHtml(paper.primary_url)}" target="_blank" rel="noreferrer">arXiv</a>
            <button class="chip-button favorite-button ${isFavorite(paper.arxiv_id) ? "active" : ""}" data-favorite-id="${escapeHtml(paper.arxiv_id)}" data-tooltip="${isFavorite(paper.arxiv_id) ? "从收藏列表移除" : "加入收藏列表"}">${isFavorite(paper.arxiv_id) ? "★ 已收藏" : "☆ 收藏"}</button>
            <button class="chip-button" data-deep-id="${escapeHtml(paper.arxiv_id)}" data-tooltip="生成这篇论文的 AI解读">${state.deepAnalysis[paper.arxiv_id]?.status === "running" ? "解读中" : "AI解读"}</button>
            <span class="subtle">${escapeHtml(paper.arxiv_id)}</span>
          </div>
        </article>
      `;
    })
    .join("");

  el.dailyTopGrid.querySelectorAll("[data-daily-id]").forEach((node) => {
    node.addEventListener("click", () => setActiveDailyPaper(node.dataset.dailyId));
  });
  el.dailyTopGrid.querySelectorAll("[data-favorite-id]").forEach((node) => {
    node.addEventListener("click", (event) => {
      event.stopPropagation();
      toggleFavorite(node.dataset.favoriteId);
    });
  });
  el.dailyTopGrid.querySelectorAll("[data-deep-id]").forEach((node) => {
    node.addEventListener("click", (event) => {
      event.stopPropagation();
      requestDeepAnalysis(node.dataset.deepId);
    });
  });
}

function renderDailyDetail() {
  const papers = state.daily?.top_display_papers || [];
  const paper = papers.find((item) => item.arxiv_id === state.activeDailyId) || papers[0];
  if (!paper) {
    el.dailyDetail.innerHTML = '<div class="detail-empty">暂无详情。</div>';
    return;
  }
  state.activeDailyId = paper.arxiv_id;
  const analysis = (state.daily?.deep_analysis_papers || []).find((item) => item.arxiv_id === paper.arxiv_id);
  const onDemandAnalysis = state.deepAnalysis[paper.arxiv_id];
  const bonuses = [
    paper.author_bonus ? `重点作者 +${paper.author_bonus}` : "",
    paper.venue_bonus ? `顶会录用 +${paper.venue_bonus}` : "",
    paper.penalty ? `惩罚 -${paper.penalty}` : "",
  ].filter(Boolean);

  el.dailyDetail.innerHTML = `
    <article class="detail-card">
      <p class="eyebrow">Highlight Detail</p>
      <h3>${escapeHtml(paper.title)}</h3>
      <p class="subtle">${escapeHtml(paper.authors_display || joinOrDash(paper.authors))}</p>
      <div class="detail-tags">
        <span class="tag">${escapeHtml(paper.topic_category || "未分类")}</span>
        <span class="tag">公布 ${escapeHtml(paper.announced_day || "N/A")}</span>
        ${paper.published_day ? `<span class="tag">提交 ${escapeHtml(paper.published_day)}</span>` : ""}
        <span class="tag">机构 ${escapeHtml(paper.affiliations_display || "—")}</span>
      </div>
      <div class="detail-grid">
        <div class="detail-block">
          <strong>一句话总结</strong>
          <span>${escapeHtml(paper.one_line_summary || "暂无")}</span>
        </div>
        <div class="detail-block">
          <strong>加分说明</strong>
          <span>${escapeHtml(bonuses.length ? bonuses.join(" · ") : "无额外加分")}</span>
        </div>
      </div>
      <div class="detail-grid">
        <div class="detail-block">
          <strong>时间信息</strong>
          <span>公布 ${escapeHtml(paper.announced_day || "N/A")}${paper.published_day ? ` · 提交 ${escapeHtml(paper.published_day)}` : ""}</span>
        </div>
        <div class="detail-block">
          <strong>评分拆解</strong>
          <span>总分 ${escapeHtml(paper.total_score)} · 相关性 ${escapeHtml(paper.relevance_score)} · 新颖性 ${escapeHtml(paper.novelty_score)}</span>
        </div>
        <div class="detail-block">
          <strong>链接</strong>
          <a href="${escapeHtml(paper.primary_url)}" target="_blank" rel="noreferrer">打开 arXiv 页面</a>
        </div>
      </div>
      <div class="action-row">
        <button class="primary-button small favorite-button ${isFavorite(paper.arxiv_id) ? "active" : ""}" data-favorite-id="${escapeHtml(paper.arxiv_id)}" data-tooltip="${isFavorite(paper.arxiv_id) ? "从收藏列表移除" : "加入收藏列表"}">${isFavorite(paper.arxiv_id) ? "★ 已收藏" : "☆ 收藏"}</button>
        <button class="primary-button small" data-deep-id="${escapeHtml(paper.arxiv_id)}" data-tooltip="生成这篇论文的 AI解读">${onDemandAnalysis?.status === "running" ? "解读中" : "生成AI解读"}</button>
      </div>
      ${
        analysis?.analysis_markdown
          ? `<div class="detail-block" style="margin-top: 16px;"><strong>已生成深度分析</strong><span>该论文同时进入了深度简报。</span></div>`
          : ""
      }
      ${
        onDemandAnalysis?.analysis_markdown
          ? `<div class="analysis-card on-demand-analysis"><p class="eyebrow">On-demand Deep Analysis</p><div class="analysis-text">${escapeHtml(onDemandAnalysis.analysis_markdown)}</div></div>`
          : onDemandAnalysis?.status === "running"
            ? `<div class="detail-block" style="margin-top: 16px;"><strong>解读中</strong><span>正在生成这篇论文的 AI解读。</span></div>`
            : onDemandAnalysis?.status === "failed"
              ? `<div class="detail-block" style="margin-top: 16px;"><strong>AI解读失败</strong><span>${escapeHtml(onDemandAnalysis.error || "未知错误")}</span></div>`
              : ""
      }
    </article>
  `;
  el.dailyDetail.querySelectorAll("[data-favorite-id]").forEach((node) => {
    node.addEventListener("click", (event) => {
      event.stopPropagation();
      toggleFavorite(node.dataset.favoriteId);
    });
  });
  el.dailyDetail.querySelectorAll("[data-deep-id]").forEach((node) => {
    node.addEventListener("click", (event) => {
      event.stopPropagation();
      requestDeepAnalysis(node.dataset.deepId);
    });
  });
}

function renderDeepAnalysis() {
  const items = state.daily?.deep_analysis_papers || [];
  if (!items.length) {
    el.deepAnalysisList.innerHTML = '<div class="detail-empty">当日没有达到 AI解读阈值的论文，因此没有深度简报。</div>';
    return;
  }

  el.deepAnalysisList.innerHTML = items
    .map(
      (paper, index) => `
        <article class="analysis-card">
          <p class="eyebrow">AI Insights #${index + 1}</p>
          <h3>${escapeHtml(paper.title)}</h3>
          <p class="subtle">${escapeHtml(paper.authors_display || joinOrDash(paper.authors))}</p>
          <div class="detail-tags">
            <span class="tag">${escapeHtml(paper.topic_category || "未分类")}</span>
            <span class="tag">总分 ${escapeHtml(paper.total_score)}</span>
            <a class="tag" href="${escapeHtml(paper.primary_url)}" target="_blank" rel="noreferrer">arXiv</a>
          </div>
          <div class="analysis-text">${escapeHtml(paper.analysis_markdown || "暂无深度分析正文")}</div>
        </article>
      `
    )
    .join("");
}

function renderTopicSummary() {
  const items = state.selected?.topic_summary || [];
  el.topicSummary.innerHTML = items.length
    ? items
        .map(
          (item) => `
            <div class="topic-chip">
              <strong>${escapeHtml(item.topic_category)}</strong>
              <span>${escapeHtml(item.count)} 篇</span>
            </div>
          `
        )
        .join("")
    : '<div class="detail-empty">暂无方向汇总。</div>';
}

function populateTopicFilter() {
  const topics = state.selected?.topic_summary || [];
  const current = state.selectedTopic;
  el.selectedTopicFilter.innerHTML = '<option value="">全部</option>' +
    topics
      .map((item) => `<option value="${escapeHtml(item.topic_category)}">${escapeHtml(item.topic_category)} (${escapeHtml(item.count)})</option>`)
      .join("");
  el.selectedTopicFilter.value = current;
}

function getFilteredSelectedPapers() {
  const papers = [...(state.selected?.papers || [])];
  const query = state.selectedSearch.trim().toLowerCase();
  let filtered = papers;

  if (state.selectedTopic) {
    filtered = filtered.filter((paper) => paper.topic_category === state.selectedTopic);
  }
  if (query) {
    filtered = filtered.filter((paper) => {
      const haystack = `${paper.title} ${paper.one_line_summary}`.toLowerCase();
      return haystack.includes(query);
    });
  }

  const sorters = {
    total: (paper) => [paper.total_score, paper.relevance_score, paper.novelty_score],
    relevance: (paper) => [paper.relevance_score, paper.total_score, paper.novelty_score],
    novelty: (paper) => [paper.novelty_score, paper.total_score, paper.relevance_score],
  };
  const sorter = sorters[state.selectedSort] || sorters.total;
  filtered.sort((a, b) => {
    const av = sorter(a);
    const bv = sorter(b);
    for (let index = 0; index < av.length; index += 1) {
      if (av[index] !== bv[index]) return bv[index] - av[index];
    }
    return String(a.arxiv_id).localeCompare(String(b.arxiv_id));
  });
  return filtered;
}

function setActiveSelectedPaper(arxivId) {
  return arxivId;
}

function renderSelectedTable() {
  const papers = getFilteredSelectedPapers();
  if (!papers.length) {
    el.selectedTableBody.innerHTML = '<tr><td colspan="10">没有匹配当前筛选条件的论文。</td></tr>';
    return;
  }

  el.selectedTableBody.innerHTML = papers
    .map(
      (paper, index) => {
        const insightRunning = state.deepAnalysis[paper.arxiv_id]?.status === "running";
        const insightDone = hasAiInsight(paper.arxiv_id);
        return `
        <tr>
          <td>${index + 1}</td>
          <td>
            <a class="arxiv-id-link" href="${escapeHtml(paper.primary_url)}" target="_blank" rel="noreferrer" title="打开 arXiv 页面">
              ${escapeHtml(paper.arxiv_id)}
              <span class="arxiv-link-hint">↗</span>
            </a>
          </td>
          <td>${escapeHtml(paper.title)}</td>
          <td>${escapeHtml(institutionDisplay(paper))}</td>
          <td>${escapeHtml(paper.topic_category || "未分类")}</td>
          <td>${escapeHtml(paper.total_score)}</td>
          <td>${escapeHtml(paper.relevance_score)}</td>
          <td>${escapeHtml(paper.novelty_score)}</td>
          <td>${escapeHtml(paper.one_line_summary || "—")}</td>
          <td>
            <div class="table-actions">
              <button class="icon-button favorite-button ${isFavorite(paper.arxiv_id) ? "active" : ""}" data-favorite-id="${escapeHtml(paper.arxiv_id)}" data-tooltip="${isFavorite(paper.arxiv_id) ? "取消收藏" : "收藏"}">${isFavorite(paper.arxiv_id) ? "★" : "☆"}</button>
              <button class="icon-button ai-insight-button ${insightDone ? "active" : ""}" data-deep-id="${escapeHtml(paper.arxiv_id)}" data-tooltip="${insightDone ? "已生成AI解读，点击可重新触发" : "AI解读"}">
                ${
                  insightRunning
                    ? "…"
                    : '<img src="./assets/icons/robot-svgrepo-com.svg" alt="" />'
                }
              </button>
            </div>
          </td>
        </tr>
      `;
      }
    )
    .join("");
  el.selectedTableBody.querySelectorAll(".arxiv-id-link").forEach((node) => {
    node.addEventListener("click", (event) => {
      event.stopPropagation();
    });
  });
  el.selectedTableBody.querySelectorAll("[data-favorite-id]").forEach((node) => {
    node.addEventListener("click", (event) => {
      event.stopPropagation();
      toggleFavorite(node.dataset.favoriteId);
    });
  });
  el.selectedTableBody.querySelectorAll("[data-deep-id]").forEach((node) => {
    node.addEventListener("click", (event) => {
      event.stopPropagation();
      requestDeepAnalysis(node.dataset.deepId);
    });
  });
}

function renderSelected() {
  renderTopicSummary();
  populateTopicFilter();
  renderSelectedTable();
}

function renderFavorites() {
  if (!el.favoritesList) return;
  if (!state.apiAvailable) {
    el.favoritesList.innerHTML = '<div class="detail-empty">收藏列表需要通过本地 Dashboard 服务访问。</div>';
    return;
  }
  if (!state.favorites.length) {
    el.favoritesList.innerHTML = '<div class="detail-empty">还没有收藏论文。</div>';
    return;
  }
  el.favoritesList.innerHTML = state.favorites
    .map((item) => `
      <article class="favorite-card">
        <div>
          <p class="eyebrow">${escapeHtml(item.source_date || "Saved")}</p>
          <h3>${escapeHtml(item.title || item.arxiv_id)}</h3>
          <p class="subtle">${escapeHtml(item.topic_category || "未分类")} · ${escapeHtml(item.arxiv_id)}</p>
        </div>
        <div class="link-row">
          <a class="link-chip" href="${escapeHtml(item.primary_url || `https://arxiv.org/abs/${item.arxiv_id}`)}" target="_blank" rel="noreferrer">arXiv</a>
          <button class="chip-button favorite-button active" data-favorite-id="${escapeHtml(item.arxiv_id)}" data-tooltip="从收藏列表移除">★ 已收藏</button>
        </div>
      </article>
    `)
    .join("");
  el.favoritesList.querySelectorAll("[data-favorite-id]").forEach((node) => {
    node.addEventListener("click", (event) => {
      event.stopPropagation();
      toggleFavorite(node.dataset.favoriteId);
    });
  });
}

function deepReportUrl(item) {
  const params = new URLSearchParams({ arxiv_id: item.arxiv_id });
  if (item.date) params.set("date", item.date);
  return `./deep_analysis.html?${params.toString()}`;
}

function renderDeepReads() {
  if (!el.deepReadList) return;
  if (!state.apiAvailable) {
    el.deepReadList.innerHTML = '<div class="detail-empty">AI解读列表需要通过本地 Dashboard 服务访问。</div>';
    return;
  }
  if (state.deepReadsError) {
    el.deepReadList.innerHTML = `<div class="detail-empty">AI解读列表加载失败：${escapeHtml(state.deepReadsError)}。如果刚更新了代码，请重启 Dashboard 服务。</div>`;
    return;
  }
  const items = state.deepReads.filter((item) => item.status === "succeeded");
  if (!items.length) {
    el.deepReadList.innerHTML = '<div class="detail-empty">还没有已完成的 AI解读。可以从 Highlight 卡片或 Longlist 表格里点击“AI解读”生成。</div>';
    return;
  }
  el.deepReadList.innerHTML = items
    .map((item) => `
      <a class="deep-read-card" href="${escapeHtml(deepReportUrl(item))}" target="_blank" rel="noreferrer">
        <div>
          <p class="eyebrow">${escapeHtml(item.date || item.announced_day || "AI Insights")}</p>
          <h3>${escapeHtml(item.title || item.arxiv_id)}</h3>
          <p class="subtle">${escapeHtml(item.authors_display || joinOrDash(item.authors))}</p>
          <p>${escapeHtml(item.one_line_summary || "暂无一句话总结")}</p>
        </div>
        <div class="deep-read-meta">
          <span class="tag">${escapeHtml(item.arxiv_id)}</span>
          <span class="tag">${escapeHtml(item.topic_category || "未分类")}</span>
          ${item.total_score !== "" ? `<span class="tag">总分 ${escapeHtml(item.total_score)}</span>` : ""}
          <span class="link-chip">查看报告 ↗</span>
        </div>
      </a>
    `)
    .join("");
}

async function loadDate(date) {
  clearError();
  const entry = state.index?.entries?.find((item) => item.date === date);
  if (!entry) {
    throw new Error(`未找到 ${date} 对应的数据入口`);
  }

  const [daily, selected] = await Promise.all([
    entry.daily_path
      ? (state.apiAvailable ? apiJson(`/api/reports/daily/${date}`) : fetchJson(`../reports_json/${entry.daily_path}`))
      : Promise.resolve(null),
    entry.selected_path
      ? (state.apiAvailable ? apiJson(`/api/reports/selected/${date}`) : fetchJson(`../reports_json/${entry.selected_path}`))
      : Promise.resolve(null),
  ]);

  state.currentDate = date;
  state.daily = daily;
  state.selected = selected;
  state.activeDailyId = daily?.top_display_papers?.[0]?.arxiv_id || "";

  renderDateRail();
  renderMeta();
  renderDailySummary();
  renderDailyCards();
  renderDailyDetail();
  renderDeepAnalysis();
  renderSelected();
  renderDeepReads();
  renderFavorites();
  updateUrl();
}

function renderJobStatus(job, logs = []) {
  if (!el.jobStatus) return;
  if (!job) {
    setMiningRunning(false);
    setMiningLogVisible(false);
    el.jobStatus.textContent = state.apiAvailable
      ? "服务已连接，可启动挖掘"
      : "当前是静态浏览模式：可以看结果，不能启动任务、AI解读或收藏。";
    el.miningSubmit.disabled = !state.apiAvailable;
    el.jobLog.classList.add("hidden");
    el.jobCancelButton.classList.add("hidden");
    el.jobResetButton.classList.add("hidden");
    return;
  }
  const statusText = {
    queued: "排队中",
    running: "运行中",
    cancel_requested: "正在停止",
    canceled: "已取消",
    succeeded: "已完成",
    failed: "失败",
  }[job.status] || job.status;
  const active = job.status === "queued" || job.status === "running" || job.status === "cancel_requested";
  const showLog = active || logs.length > 0;
  setMiningRunning(active);
  setMiningLogVisible(showLog);
  el.miningSubmit.disabled = active || !state.apiAvailable;
  el.jobCancelButton.classList.toggle("hidden", !active);
  el.jobResetButton.classList.toggle("hidden", !active);
  el.jobStatus.textContent = `${statusText} · ${job.progress || 0}%`;
  el.jobLog.classList.toggle("hidden", !showLog);
  el.jobLog.innerHTML = logs
    .slice(-12)
    .map((item) => `<div><span>${escapeHtml(prettyTime(item.created_at))}</span> ${escapeHtml(item.message)}</div>`)
    .join("");
}

async function refreshIndexAndCurrentDate() {
  state.index = await loadIndex();
  const dates = (state.index.entries || []).map((entry) => entry.date);
  const nextDate = dates.includes(state.currentDate)
    ? state.currentDate
    : state.index.default_date || dates[0] || "";
  renderDateRail();
  if (nextDate) {
    await loadDate(nextDate);
  }
}

async function pollJob(jobId) {
  state.currentJobId = jobId;
  if (state.jobPollTimer) clearInterval(state.jobPollTimer);
  const tick = async () => {
    try {
      const [job, logPayload] = await Promise.all([
        apiJson(`/api/jobs/${jobId}`),
        apiJson(`/api/jobs/${jobId}/logs`),
      ]);
      renderJobStatus(job, logPayload.logs || []);
      if (job.status === "succeeded" || job.status === "failed" || job.status === "canceled") {
        clearInterval(state.jobPollTimer);
        state.jobPollTimer = null;
        if (job.status === "succeeded") {
          await refreshIndexAndCurrentDate();
        }
      }
    } catch (error) {
      showError(`任务状态刷新失败：${error.message}`);
      clearInterval(state.jobPollTimer);
      state.jobPollTimer = null;
    }
  };
  await tick();
  state.jobPollTimer = setInterval(tick, 2000);
}

async function startMiningJob(event) {
  event.preventDefault();
  if (!state.apiAvailable) {
    showError("启动任务需要通过本地 Dashboard 服务访问。");
    return;
  }
  clearError();
  try {
    setMiningExpanded(true);
    setMiningRunning(true);
    const payload = await apiJson("/api/jobs/mining", {
      method: "POST",
      body: JSON.stringify({
        days: Number(el.miningDays.value || 1),
        categories: el.miningCategories.value || "cs.CV,cs.RO",
      }),
    });
    renderJobStatus({ status: "queued", progress: 0 }, []);
    await pollJob(payload.job_id);
  } catch (error) {
    setMiningRunning(false);
    showError(`任务启动失败：${error.message}`);
  }
}

async function resetActiveMiningJobs() {
  if (!state.apiAvailable) return;
  try {
    const payload = await apiJson("/api/jobs/mining/reset-active", { method: "POST" });
    if (state.jobPollTimer) {
      clearInterval(state.jobPollTimer);
      state.jobPollTimer = null;
    }
    state.currentJobId = "";
    renderJobStatus(null);
    setMiningRunning(false);
    el.jobStatus.textContent = `已重置 ${payload.reset_count || 0} 个卡住的任务。`;
  } catch (error) {
    showError(`重置任务状态失败：${error.message}`);
  }
}

async function cancelMiningJob() {
  if (!state.apiAvailable || !state.currentJobId) return;
  try {
    const job = await apiJson(`/api/jobs/${state.currentJobId}/cancel`, { method: "POST" });
    renderJobStatus(job, []);
  } catch (error) {
    showError(`停止任务失败：${error.message}`);
  }
}

async function init() {
  if (window.location.protocol === "file:") {
    el.protocolWarning.classList.remove("hidden");
    el.protocolWarning.textContent =
      "当前是 file:// 打开方式，很多浏览器会拦截本地 JSON 读取。建议在仓库根目录运行 `python3 -m http.server 8000`，然后访问 http://localhost:8000/webapp/index.html";
  }
  clearError();

  state.index = await loadIndex();
  await loadFavorites();
  await loadDeepReads();
  await resumeRunningJob();
  const requestedDate = getRequestedDate();
  const availableDates = (state.index.entries || []).map((entry) => entry.date);
  if (!availableDates.length) {
    showError("当前还没有可展示的前端 JSON 数据。请先运行主流程，在仓库根目录生成 reports_json/。");
    return;
  }
  const defaultDate = availableDates.includes(requestedDate)
    ? requestedDate
    : state.index.default_date || availableDates[0];

  el.tabButtons.forEach((button) => {
    button.addEventListener("click", () => switchTab(button.dataset.tab));
  });
  window.addEventListener("hashchange", () => {
    switchTab(window.location.hash === "#daily"
      ? "daily"
      : window.location.hash === "#deep"
        ? "deep"
        : window.location.hash === "#favorites"
          ? "favorites"
          : "selected");
  });

  el.selectedSort.addEventListener("change", (event) => {
    state.selectedSort = event.target.value;
    renderSelectedTable();
  });
  el.selectedTopicFilter.addEventListener("change", (event) => {
    state.selectedTopic = event.target.value;
    renderSelectedTable();
  });
  el.selectedSearch.addEventListener("input", (event) => {
    state.selectedSearch = event.target.value;
    renderSelectedTable();
  });
  el.miningForm.addEventListener("submit", startMiningJob);
  el.miningToggle.addEventListener("click", () => {
    setMiningExpanded(!state.miningExpanded);
  });
  el.jobCancelButton.addEventListener("click", cancelMiningJob);
  el.jobResetButton.addEventListener("click", resetActiveMiningJobs);
  document.addEventListener("click", (event) => {
    if (!state.miningExpanded) return;
    if (el.miningWidget.contains(event.target)) return;
    setMiningExpanded(false);
  });
  el.miningWidget.addEventListener("click", (event) => {
    event.stopPropagation();
  });

  switchTab(state.currentTab);
  setMiningExpanded(false);
  renderJobStatus(null);
  state.currentDate = defaultDate;
  renderDateRail();
  await loadDate(defaultDate);
}

init().catch((error) => {
  showError(`页面初始化失败：${error.message}`);
  console.error(error);
});

const DATA_INDEX_URL_CANDIDATES = [
  "./reports_json/index.json",
  "../reports_json/index.json",
];

const state = {
  index: null,
  currentDate: "",
  currentTab: window.location.hash === "#selected" ? "selected" : "daily",
  daily: null,
  selected: null,
  selectedSort: "total",
  selectedTopic: "",
  selectedSearch: "",
  activeDailyId: "",
  activeSelectedId: "",
};

const el = {
  dateSidebar: document.getElementById("date-sidebar"),
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
  selectedDetail: document.getElementById("selected-detail"),
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

async function fetchJsonFromCandidates(urls) {
  let lastError = null;
  for (const url of urls) {
    try {
      return await fetchJson(url);
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError || new Error("未找到可用的数据文件");
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
  url.hash = state.currentTab === "selected" ? "#selected" : "#daily";
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
}

function buildSidebarGroups(entries) {
  const monthMap = new Map();
  entries.forEach((entry) => {
    const monthKey = entry.date.slice(0, 7);
    const weekKey = getWeekKey(entry.date);
    if (!monthMap.has(monthKey)) monthMap.set(monthKey, new Map());
    const weekMap = monthMap.get(monthKey);
    if (!weekMap.has(weekKey)) weekMap.set(weekKey, []);
    weekMap.get(weekKey).push(entry);
  });
  return monthMap;
}

function renderDateSidebar() {
  const entries = state.index?.entries || [];
  const groups = buildSidebarGroups(entries);
  el.dateSidebar.innerHTML = [...groups.entries()]
    .map(([monthKey, weekMap]) => `
      <section class="month-block">
        <h3 class="month-title">${escapeHtml(formatMonthLabel(monthKey))}</h3>
        ${[...weekMap.entries()]
          .map(([weekKey, items]) => `
            <section class="week-block">
              <p class="week-title">Week ${escapeHtml(formatWeekLabel(weekKey))}</p>
              <div class="date-list">
                ${items
                  .map((entry) => `
                    <button class="date-item ${entry.date === state.currentDate ? "active" : ""}" data-date-value="${escapeHtml(entry.date)}">
                      <span class="date-label">
                        <span class="date-main">${escapeHtml(formatDateLabel(entry.date))}</span>
                        <span class="date-sub">${escapeHtml(entry.date)}</span>
                      </span>
                      <span class="date-badge">${entry.date === state.index?.default_date ? "Latest" : "Open"}</span>
                    </button>
                  `)
                  .join("")}
              </div>
            </section>
          `)
          .join("")}
      </section>
    `)
    .join("");

  document.querySelectorAll("[data-date-value]").forEach((node) => {
    node.addEventListener("click", async () => {
      try {
        await loadDate(node.dataset.dateValue);
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
      label: "Selected 论文数",
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
          <p>${escapeHtml(paper.one_line_summary || "暂无一句话总结")}</p>
          <div class="link-row">
            <a class="link-chip" href="${escapeHtml(paper.primary_url)}" target="_blank" rel="noreferrer">arXiv</a>
            <span class="subtle">${escapeHtml(paper.arxiv_id)}</span>
          </div>
        </article>
      `;
    })
    .join("");

  document.querySelectorAll("[data-daily-id]").forEach((node) => {
    node.addEventListener("click", () => setActiveDailyPaper(node.dataset.dailyId));
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
  const bonuses = [
    paper.author_bonus ? `重点作者 +${paper.author_bonus}` : "",
    paper.venue_bonus ? `顶会录用 +${paper.venue_bonus}` : "",
    paper.penalty ? `惩罚 -${paper.penalty}` : "",
  ].filter(Boolean);

  el.dailyDetail.innerHTML = `
    <article class="detail-card">
      <p class="eyebrow">Daily Detail</p>
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
      ${
        analysis?.analysis_markdown
          ? `<div class="detail-block" style="margin-top: 16px;"><strong>已生成深度分析</strong><span>该论文同时进入了深度简报。</span></div>`
          : ""
      }
    </article>
  `;
}

function renderDeepAnalysis() {
  const items = state.daily?.deep_analysis_papers || [];
  if (!items.length) {
    el.deepAnalysisList.innerHTML = '<div class="detail-empty">当日没有达到精读阈值的论文，因此没有深度简报。</div>';
    return;
  }

  el.deepAnalysisList.innerHTML = items
    .map(
      (paper, index) => `
        <article class="analysis-card">
          <p class="eyebrow">Deep Dive #${index + 1}</p>
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
  state.activeSelectedId = arxivId;
  renderSelectedTable();
  renderSelectedDetail();
}

function renderSelectedTable() {
  const papers = getFilteredSelectedPapers();
  if (!papers.length) {
    el.selectedTableBody.innerHTML = '<tr><td colspan="8">没有匹配当前筛选条件的论文。</td></tr>';
    return;
  }

  if (!papers.some((paper) => paper.arxiv_id === state.activeSelectedId)) {
    state.activeSelectedId = papers[0].arxiv_id;
  }

  el.selectedTableBody.innerHTML = papers
    .map(
      (paper, index) => `
        <tr data-selected-id="${escapeHtml(paper.arxiv_id)}" class="${paper.arxiv_id === state.activeSelectedId ? "active" : ""}">
          <td>${index + 1}</td>
          <td>
            <a class="arxiv-id-link" href="${escapeHtml(paper.primary_url)}" target="_blank" rel="noreferrer" title="打开 arXiv 页面">
              ${escapeHtml(paper.arxiv_id)}
              <span class="arxiv-link-hint">↗</span>
            </a>
          </td>
          <td>${escapeHtml(paper.title)}</td>
          <td>${escapeHtml(paper.topic_category || "未分类")}</td>
          <td>${escapeHtml(paper.total_score)}</td>
          <td>${escapeHtml(paper.relevance_score)}</td>
          <td>${escapeHtml(paper.novelty_score)}</td>
          <td>${escapeHtml(paper.one_line_summary || "—")}</td>
        </tr>
      `
    )
    .join("");

  document.querySelectorAll("[data-selected-id]").forEach((node) => {
    node.addEventListener("click", () => setActiveSelectedPaper(node.dataset.selectedId));
  });
  document.querySelectorAll(".arxiv-id-link").forEach((node) => {
    node.addEventListener("click", (event) => {
      event.stopPropagation();
    });
  });
}

function renderSelectedDetail() {
  const papers = getFilteredSelectedPapers();
  const paper = papers.find((item) => item.arxiv_id === state.activeSelectedId) || papers[0];
  if (!paper) {
    el.selectedDetail.innerHTML = '<div class="detail-empty">暂无 selected 详情。</div>';
    return;
  }
  state.activeSelectedId = paper.arxiv_id;

  const reasons = paper.bonus_reasons?.length ? paper.bonus_reasons : ["无额外加分原因"];
  el.selectedDetail.innerHTML = `
    <article class="detail-card">
      <p class="eyebrow">Selected Detail</p>
      <h3>${escapeHtml(paper.title)}</h3>
      <p class="subtle">${escapeHtml(joinOrDash(paper.authors))}</p>
      <div class="detail-tags">
        <span class="tag">${escapeHtml(paper.topic_category || "未分类")}</span>
        <span class="tag">总分 ${escapeHtml(paper.total_score)}</span>
        <span class="tag">公布 ${escapeHtml(paper.announced_day || "N/A")}</span>
        <span class="tag">机构 ${escapeHtml(paper.affiliations_display || "—")}</span>
      </div>
      <div class="detail-grid">
        <div class="detail-block">
          <strong>一句话总结</strong>
          <span>${escapeHtml(paper.one_line_summary || "暂无")}</span>
        </div>
        <div class="detail-block">
          <strong>机构推断</strong>
          <span>${escapeHtml(paper.institution_summary || joinOrDash(paper.normalized_institutions) || "暂无")}</span>
        </div>
        <div class="detail-block">
          <strong>时间信息</strong>
          <span>公布 ${escapeHtml(paper.announced_day || "N/A")}${paper.published_day ? ` · 提交 ${escapeHtml(paper.published_day)}` : ""}</span>
        </div>
        <div class="detail-block">
          <strong>评分拆解</strong>
          <span>相关性 ${escapeHtml(paper.relevance_score)} · 新颖性 ${escapeHtml(paper.novelty_score)} · 作者加分 ${escapeHtml(paper.author_bonus)} · 顶会加分 ${escapeHtml(paper.venue_bonus)}</span>
        </div>
        <div class="detail-block">
          <strong>证据来源</strong>
          <span>${escapeHtml(paper.institution_evidence_source || "unknown")}</span>
        </div>
      </div>
      <div class="detail-block" style="margin-top: 16px;">
        <strong>加分原因</strong>
        <ul>${reasons.map((reason) => `<li>${escapeHtml(reason)}</li>`).join("")}</ul>
      </div>
      <div class="detail-block" style="margin-top: 16px;">
        <strong>摘要</strong>
        <span>${escapeHtml(paper.abstract || "暂无摘要")}</span>
      </div>
      <div class="detail-block" style="margin-top: 16px;">
        <strong>链接</strong>
        <a href="${escapeHtml(paper.primary_url)}" target="_blank" rel="noreferrer">打开 arXiv 页面</a>
      </div>
    </article>
  `;
}

function renderSelected() {
  renderTopicSummary();
  populateTopicFilter();
  renderSelectedTable();
  renderSelectedDetail();
}

async function loadDate(date) {
  clearError();
  const entry = state.index?.entries?.find((item) => item.date === date);
  if (!entry) {
    throw new Error(`未找到 ${date} 对应的数据入口`);
  }

  const [daily, selected] = await Promise.all([
    entry.daily_path
      ? fetchJsonFromCandidates([
          `./reports_json/${entry.daily_path}`,
          `../reports_json/${entry.daily_path}`,
        ])
      : Promise.resolve(null),
    entry.selected_path
      ? fetchJsonFromCandidates([
          `./reports_json/${entry.selected_path}`,
          `../reports_json/${entry.selected_path}`,
        ])
      : Promise.resolve(null),
  ]);

  state.currentDate = date;
  state.daily = daily;
  state.selected = selected;
  state.activeDailyId = daily?.top_display_papers?.[0]?.arxiv_id || "";
  state.activeSelectedId = selected?.papers?.[0]?.arxiv_id || "";

  renderDateSidebar();
  renderMeta();
  renderDailySummary();
  renderDailyCards();
  renderDailyDetail();
  renderDeepAnalysis();
  renderSelected();
  updateUrl();
}

async function init() {
  if (window.location.protocol === "file:") {
    el.protocolWarning.classList.remove("hidden");
    el.protocolWarning.textContent =
      "当前是 file:// 打开方式，很多浏览器会拦截本地 JSON 读取。建议在仓库根目录运行 `python3 -m http.server 8000`，然后访问 http://localhost:8000/webapp/index.html";
  }
  clearError();

  state.index = await fetchJsonFromCandidates(DATA_INDEX_URL_CANDIDATES);
  const requestedDate = getRequestedDate();
  const availableDates = (state.index.entries || []).map((entry) => entry.date);
  if (!availableDates.length) {
    showError("当前还没有可展示的前端 JSON 数据。请先运行主流程生成 reports_json/。");
    return;
  }
  const defaultDate = availableDates.includes(requestedDate)
    ? requestedDate
    : state.index.default_date || availableDates[0];

  el.tabButtons.forEach((button) => {
    button.addEventListener("click", () => switchTab(button.dataset.tab));
  });
  window.addEventListener("hashchange", () => {
    switchTab(window.location.hash === "#selected" ? "selected" : "daily");
  });

  el.selectedSort.addEventListener("change", (event) => {
    state.selectedSort = event.target.value;
    renderSelectedTable();
    renderSelectedDetail();
  });
  el.selectedTopicFilter.addEventListener("change", (event) => {
    state.selectedTopic = event.target.value;
    renderSelectedTable();
    renderSelectedDetail();
  });
  el.selectedSearch.addEventListener("input", (event) => {
    state.selectedSearch = event.target.value;
    renderSelectedTable();
    renderSelectedDetail();
  });

  switchTab(state.currentTab);
  state.currentDate = defaultDate;
  renderDateSidebar();
  await loadDate(defaultDate);
}

init().catch((error) => {
  showError(`页面初始化失败：${error.message}`);
  console.error(error);
});

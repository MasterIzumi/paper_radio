const DATA_INDEX_URL = "../reports_json/index.json";
const API_INDEX_URL = "/api/reports/index";

const state = {
  index: null,
  apiAvailable: false,
  currentDate: "",
  currentSection: (window.location.hash === "#deep" || window.location.hash === "#favorites")
    ? "workspace"
    : "daily-board",
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
  selectedUnreadOnly: false,
  activeDailyId: "",
  favorites: [],
  paperStates: {},
  deepReads: [],
  deepReadsError: "",
  deepAnalysis: {},
  tasks: [],
  schedules: [],
  configItems: [],
  activeConfigGroup: "",
  taskPollTimer: null,
  currentJobId: "",
  jobPollTimer: null,
  miningExpanded: false,
  miningRunning: false,
  miningTab: "manual",
  taskExpanded: false,
  configExpanded: false,
};

const el = {
  dateRail: document.getElementById("date-rail"),
  datePanel: document.getElementById("date-panel"),
  heroEyebrow: document.getElementById("hero-eyebrow"),
  heroTitle: document.getElementById("hero-title"),
  heroText: document.getElementById("hero-text"),
  metaDate: document.getElementById("meta-date"),
  metaDateLabel: document.getElementById("meta-date-label"),
  metaGeneratedAt: document.getElementById("meta-generated-at"),
  metaGeneratedAtLabel: document.getElementById("meta-generated-at-label"),
  metaCategories: document.getElementById("meta-categories"),
  metaCategoriesLabel: document.getElementById("meta-categories-label"),
  metaModels: document.getElementById("meta-models"),
  metaModelsLabel: document.getElementById("meta-models-label"),
  protocolWarning: document.getElementById("protocol-warning"),
  errorBanner: document.getElementById("error-banner"),
  workspaceBackdrop: document.getElementById("workspace-backdrop"),
  dailySummaryCards: document.getElementById("daily-summary-cards"),
  dailyThresholdNote: document.getElementById("daily-threshold-note"),
  dailyTopGrid: document.getElementById("daily-top-grid"),
  dailyDetail: document.getElementById("daily-detail"),
  deepAnalysisList: document.getElementById("deep-analysis-list"),
  topicSummary: document.getElementById("topic-summary"),
  selectedSort: document.getElementById("selected-sort"),
  selectedTopicFilter: document.getElementById("selected-topic-filter"),
  selectedSearch: document.getElementById("selected-search"),
  selectedUnreadOnly: document.getElementById("selected-unread-only"),
  selectedTableBody: document.getElementById("selected-table-body"),
  miningWidget: document.getElementById("mining-widget"),
  miningToggle: document.getElementById("mining-toggle"),
  miningTabButtons: [...document.querySelectorAll("[data-mining-tab]")],
  miningTabPanels: [...document.querySelectorAll("[data-mining-panel]")],
  scheduleIndicator: document.getElementById("schedule-indicator"),
  miningForm: document.getElementById("mining-form"),
  miningSubmit: document.querySelector("#mining-form button[type='submit']"),
  miningDays: document.getElementById("mining-days"),
  miningCategories: document.getElementById("mining-categories"),
  jobCancelButton: document.getElementById("job-cancel-button"),
  jobResetButton: document.getElementById("job-reset-button"),
  jobProgress: document.getElementById("job-progress"),
  jobStatus: document.getElementById("job-status"),
  jobLog: document.getElementById("job-log"),
  favoritesList: document.getElementById("favorites-list"),
  deepReadList: document.getElementById("deep-read-list"),
  taskWidget: document.getElementById("task-widget"),
  taskToggle: document.getElementById("task-toggle"),
  taskPopover: document.getElementById("task-popover"),
  taskList: document.getElementById("task-list"),
  tasksRefresh: document.getElementById("tasks-refresh"),
  configWidget: document.getElementById("config-widget"),
  configToggle: document.getElementById("config-toggle"),
  configPopover: document.getElementById("config-popover"),
  scheduleForm: document.getElementById("schedule-form"),
  scheduleEnabled: document.getElementById("schedule-enabled"),
  scheduleFields: document.getElementById("schedule-fields"),
  scheduleTime: document.getElementById("schedule-time"),
  scheduleDays: document.getElementById("schedule-days"),
  scheduleCategories: document.getElementById("schedule-categories"),
  scheduleRunNow: document.getElementById("schedule-run-now"),
  scheduleStatus: document.getElementById("schedule-status"),
  configTabs: document.getElementById("config-tabs"),
  configList: document.getElementById("config-list"),
  activeTaskCount: document.getElementById("active-task-count"),
  paperDetailModal: document.getElementById("paper-detail-modal"),
  paperDetailBackdrop: document.getElementById("paper-detail-backdrop"),
  paperDetailClose: document.getElementById("paper-detail-close"),
  paperDetailContent: document.getElementById("paper-detail-content"),
  dailySubtabs: document.getElementById("daily-subtabs"),
  workspaceSubtabs: document.getElementById("workspace-subtabs"),
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

function renderMath(root = document) {
  if (window.renderPaperMath) {
    window.renderPaperMath(root);
  }
}

function paperDate(paper) {
  return paper.announced_day || paper.date || state.currentDate || "";
}

function stateKey(arxivId, date = "") {
  return `${arxivId}::${date || ""}`;
}

function getPaperState(paper) {
  const date = paperDate(paper);
  return (
    state.paperStates[stateKey(paper.arxiv_id, date)] ||
    state.paperStates[stateKey(paper.arxiv_id, "")] ||
    paper.state ||
    {}
  );
}

function isPaperRead(paper) {
  return Boolean(getPaperState(paper).read);
}

function isPaperUpvoted(paper) {
  return Boolean(getPaperState(paper).upvoted);
}

function isPaperDownvoted(paper) {
  return Boolean(getPaperState(paper).downvoted);
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

async function loadPaperStates() {
  if (!state.apiAvailable) {
    state.paperStates = {};
    return;
  }
  try {
    const payload = await apiJson("/api/papers/state/list");
    state.paperStates = {};
    (payload.states || []).forEach((item) => {
      state.paperStates[stateKey(item.arxiv_id, item.date)] = item;
    });
  } catch (error) {
    state.paperStates = {};
  }
}

async function loadTasks() {
  if (!state.apiAvailable) {
    state.tasks = [];
    return;
  }
  try {
    const payload = await apiJson("/api/tasks");
    state.tasks = payload.tasks || [];
  } catch (error) {
    state.tasks = [];
  }
}

async function loadSchedules() {
  if (!state.apiAvailable) {
    state.schedules = [];
    return;
  }
  try {
    const payload = await apiJson("/api/schedules");
    state.schedules = payload.schedules || [];
  } catch (error) {
    state.schedules = [];
  }
}

async function loadConfig() {
  if (!state.apiAvailable) {
    state.configItems = [];
    return;
  }
  try {
    const payload = await apiJson("/api/config");
    state.configItems = payload.items || [];
  } catch (error) {
    state.configItems = [];
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

function sectionForTab(tab) {
  return tab === "deep" || tab === "favorites" ? "workspace" : "daily-board";
}

function switchSection(section) {
  state.currentSection = section === "workspace" ? "workspace" : "daily-board";
  el.datePanel?.classList.toggle("hidden", state.currentSection !== "daily-board");
  renderMeta();
}

function switchTab(tab) {
  state.currentTab = tab;
  switchSection(sectionForTab(tab));
  el.tabButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.tab === tab);
  });
  el.tabPanels.forEach((panel) => {
    panel.classList.toggle("active", panel.id === `${tab}-tab`);
  });
  updateUrl();
  renderMeta();
}

function renderMeta() {
  const entry = state.index?.entries?.find((item) => item.date === state.currentDate);
  const generatedAt = state.daily?.generated_at || state.selected?.generated_at || entry?.daily_generated_at || "-";
  const categories = state.daily?.categories || state.selected?.categories || entry?.categories || [];
  const models = state.daily?.models
    ? `${state.daily.models.fast} / ${state.daily.models.strong}`
    : "-";
  const metaModelsBlock = el.metaModelsLabel?.parentElement;
  if (state.currentSection === "daily-board") {
    el.heroEyebrow.textContent = "Paper Radio Dashboard";
    el.heroTitle.textContent = "每日论文挖掘看板";
    el.heroText.textContent = "用一个静态页面同时查看 Highlights 和 Longlist，适合快速扫当日亮点，也方便回看筛选链路。";
    el.metaDateLabel.textContent = "公布日期";
    el.metaGeneratedAtLabel.textContent = "数据更新时间";
    el.metaCategoriesLabel.textContent = "分区";
    el.metaModelsLabel.textContent = "分析模型";
    el.metaDate.textContent = state.currentDate || "-";
    el.metaGeneratedAt.textContent = prettyTime(generatedAt);
    el.metaCategories.textContent = categories.length ? categories.join(", ") : "-";
    el.metaModels.textContent = models;
    metaModelsBlock?.classList.remove("hidden");
  } else {
    el.heroEyebrow.textContent = "Paper Radio Workspace";
    el.heroTitle.textContent = "研究工作台";
    el.heroText.textContent = "这里保存跨日期累积的 AI解读和收藏论文，更适合回看、沉淀与个人研究管理。";
    el.metaDateLabel.textContent = "AI解读数";
    el.metaGeneratedAtLabel.textContent = "收藏数";
    el.metaCategoriesLabel.textContent = "最近更新";
    el.metaDate.textContent = String(state.deepReads.length || 0);
    el.metaGeneratedAt.textContent = String(state.favorites.length || 0);
    el.metaCategories.textContent = prettyTime(generatedAt);
    metaModelsBlock?.classList.add("hidden");
  }
  if (el.jobStatus && !state.apiAvailable) {
    el.jobStatus.textContent = "当前是静态浏览模式：可以看结果，不能启动任务、AI解读或收藏。";
  }
}

function renderTasks() {
  if (!el.taskList) return;
  const activeCount = state.tasks.filter((task) =>
    ["queued", "running", "cancel_requested"].includes(task.status)
  ).length;
  if (el.activeTaskCount) {
    el.activeTaskCount.textContent = String(activeCount);
    el.activeTaskCount.classList.toggle("active", activeCount > 0);
  }
  if (!state.apiAvailable) {
    el.taskList.innerHTML = '<div class="detail-empty compact-empty">本地服务未连接。</div>';
    return;
  }
  const tasks = state.tasks.slice(0, 8);
  if (!tasks.length) {
    el.taskList.innerHTML = '<div class="detail-empty compact-empty">暂无任务。</div>';
    return;
  }
  const labels = {
    queued: "排队",
    running: "运行",
    cancel_requested: "停止中",
    canceled: "已取消",
    succeeded: "完成",
    failed: "失败",
  };
  const rows = tasks.map((task) => {
    const active = ["queued", "running", "cancel_requested"].includes(task.status);
    const source = task.params?.source === "scheduled" ? "定时" : "手动";
    const params = task.params || {};
    const categoryText = Array.isArray(params.categories)
      ? params.categories.join(", ")
      : params.categories || "";
    const result = task.result || {};
    const resultText = [
      result.date_count ? `日期 ${result.date_count}` : "",
      result.total_papers ? `论文 ${result.total_papers}` : "",
      result.selected_count ? `入选 ${result.selected_count}` : "",
    ].filter(Boolean).join(" · ");
    const summaryBits = [
      params.days ? `${params.days}天` : "",
      categoryText || "",
      resultText || "",
    ].filter(Boolean).join(" · ");
    return `
      <article class="task-row ${active ? "active" : ""}">
        <div class="task-col task-col-name">
          <strong>${escapeHtml(task.type)}</strong>
          <span>${escapeHtml(source)}</span>
        </div>
        <div class="task-col task-col-state">
          <strong>${escapeHtml(labels[task.status] || task.status)}</strong>
          <span>${escapeHtml(task.progress || 0)}%</span>
        </div>
        <div class="task-col task-col-summary">
          <span>${escapeHtml(summaryBits || "—")}</span>
        </div>
        <div class="task-col task-col-time">
          <span><em>创建</em>${escapeHtml(task.created_at ? prettyTime(task.created_at) : "—")}</span>
          <span><em>开始</em>${escapeHtml(task.started_at ? prettyTime(task.started_at) : "—")}</span>
          <span><em>结束</em>${escapeHtml(task.finished_at ? prettyTime(task.finished_at) : "—")}</span>
        </div>
        <div class="task-col task-col-progress">
          <progress value="${escapeHtml(task.progress || 0)}" max="100"></progress>
        </div>
        ${task.error ? `<p class="subtle task-error">${escapeHtml(task.error)}</p>` : ""}
      </article>
    `;
  }).join("");
  el.taskList.innerHTML = `
    <div class="task-table-head">
      <span>任务</span>
      <span>状态</span>
      <span>摘要</span>
      <span>时间</span>
      <span>进度</span>
    </div>
    ${rows}
  `;
}

function setTaskExpanded(expanded) {
  state.taskExpanded = Boolean(expanded);
  el.taskWidget?.classList.toggle("collapsed", !state.taskExpanded);
  el.taskWidget?.classList.toggle("expanded", state.taskExpanded);
  el.taskToggle?.setAttribute("aria-expanded", String(state.taskExpanded));
  updateWorkspaceBackdrop();
}

function setConfigExpanded(expanded) {
  state.configExpanded = Boolean(expanded);
  el.configWidget?.classList.toggle("collapsed", !state.configExpanded);
  el.configWidget?.classList.toggle("expanded", state.configExpanded);
  el.configToggle?.setAttribute("aria-expanded", String(state.configExpanded));
  updateWorkspaceBackdrop();
}

function switchMiningTab(tab) {
  state.miningTab = tab === "schedule" ? "schedule" : "manual";
  el.miningTabButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.miningTab === state.miningTab);
  });
  el.miningTabPanels.forEach((panel) => {
    panel.classList.toggle("active", panel.dataset.miningPanel === state.miningTab);
  });
}

function updateWorkspaceBackdrop() {
  const active = state.miningExpanded || state.taskExpanded || state.configExpanded;
  el.workspaceBackdrop?.classList.toggle("hidden", !active);
  document.body.classList.toggle("side-popover-open", active);
}

function closeSidePopovers() {
  setMiningExpanded(false);
  setTaskExpanded(false);
  setConfigExpanded(false);
}

function renderSchedule() {
  const schedule = state.schedules[0];
  if (!el.scheduleStatus) return;
  if (!state.apiAvailable) {
    el.scheduleStatus.textContent = "本地服务未连接。";
    el.miningWidget?.classList.remove("schedule-enabled");
    el.scheduleIndicator?.classList.add("hidden");
    el.scheduleFields?.classList.add("hidden");
    if (el.scheduleFields) el.scheduleFields.hidden = true;
    return;
  }
  if (!schedule) {
    el.scheduleStatus.textContent = "暂无定时配置。";
    el.miningWidget?.classList.remove("schedule-enabled");
    el.scheduleIndicator?.classList.add("hidden");
    el.scheduleFields?.classList.add("hidden");
    if (el.scheduleFields) el.scheduleFields.hidden = true;
    return;
  }
  el.scheduleEnabled.checked = Boolean(schedule.enabled);
  el.scheduleFields?.classList.toggle("hidden", !schedule.enabled);
  if (el.scheduleFields) el.scheduleFields.hidden = !schedule.enabled;
  el.scheduleTime.value = schedule.run_time || "09:00";
  el.scheduleDays.value = schedule.days || 1;
  el.scheduleCategories.value = (schedule.categories || []).join(",");
  el.scheduleStatus.textContent = schedule.enabled
    ? `已启用，下次 ${prettyTime(schedule.next_run_at)}`
    : "未启用";
  el.miningWidget?.classList.toggle("schedule-enabled", Boolean(schedule.enabled));
  el.scheduleIndicator?.classList.toggle("hidden", !schedule.enabled);
  if (el.scheduleIndicator && schedule.enabled) {
    el.scheduleIndicator.textContent = "定时 ON";
    el.scheduleIndicator.title = `下次运行：${prettyTime(schedule.next_run_at)}`;
  }
}

function renderConfig() {
  if (!el.configList || !el.configTabs) return;
  if (!state.apiAvailable) {
    el.configTabs.innerHTML = "";
    el.configList.innerHTML = '<div class="detail-empty compact-empty">配置面板需要本地服务。</div>';
    return;
  }
  const important = state.configItems;
  if (!important.length) {
    el.configTabs.innerHTML = "";
    el.configList.innerHTML = '<div class="detail-empty compact-empty">暂无配置项。</div>';
    return;
  }
  const groups = [];
  const grouped = new Map();
  important.forEach((item) => {
    if (!grouped.has(item.group)) {
      grouped.set(item.group, []);
      groups.push(item.group);
    }
    grouped.get(item.group).push(item);
  });
  if (!groups.includes(state.activeConfigGroup)) {
    state.activeConfigGroup = groups[0] || "";
  }
  el.configTabs.innerHTML = groups.map((group) => {
    const count = grouped.get(group)?.length || 0;
    return `
      <button class="config-tab-button ${group === state.activeConfigGroup ? "active" : ""}" data-config-group="${escapeHtml(group)}" type="button">
        <span>${escapeHtml(group)}</span>
        <strong>${count}</strong>
      </button>
    `;
  }).join("");

  const currentItems = grouped.get(state.activeConfigGroup) || [];
  el.configList.innerHTML = currentItems.map((item) => {
    const value = Array.isArray(item.value)
      ? item.value.join(", ")
      : typeof item.value === "object"
        ? JSON.stringify(item.value)
        : String(item.value ?? "");
    return `
      <label class="config-item">
        <span>${escapeHtml(item.key)} <em>${escapeHtml(item.source)}</em></span>
        <input data-config-key="${escapeHtml(item.key)}" data-config-type="${escapeHtml(item.type)}" value="${escapeHtml(value)}" ${item.editable ? "" : "disabled"} />
      </label>
    `;
  }).join("");
  el.configTabs.querySelectorAll("[data-config-group]").forEach((node) => {
    node.addEventListener("click", () => {
      state.activeConfigGroup = node.dataset.configGroup || "";
      renderConfig();
    });
  });
  el.configList.querySelectorAll("[data-config-key]").forEach((node) => {
    node.addEventListener("change", () => saveConfigItem(node));
  });
}

function setMiningExpanded(expanded) {
  state.miningExpanded = Boolean(expanded);
  el.miningWidget.classList.toggle("collapsed", !state.miningExpanded);
  el.miningWidget.classList.toggle("expanded", state.miningExpanded);
  el.miningToggle.setAttribute("aria-expanded", String(state.miningExpanded));
  updateWorkspaceBackdrop();
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

async function setPaperRead(paper, read, options = {}) {
  if (!state.apiAvailable) {
    if (!options.silent) {
      showError("已读状态需要通过本地 Dashboard 服务访问。");
    }
    return;
  }
  const date = paperDate(paper);
  try {
    const item = await apiJson(`/api/papers/${encodeURIComponent(paper.arxiv_id)}/state`, {
      method: "PATCH",
      body: JSON.stringify({ date, read }),
    });
    state.paperStates[stateKey(paper.arxiv_id, date)] = item;
    state.paperStates[stateKey(paper.arxiv_id, item.date || "")] = item;
    paper.state = item;
    renderDailyCards();
    renderSelectedTable();
    if (options.refreshDetail) {
      renderPaperDetail(paper);
    }
  } catch (error) {
    showError(`已读状态更新失败：${error.message}`);
  }
}

async function openPaperDetail(paper) {
  if (!paper) return;
  if (state.apiAvailable && !isPaperRead(paper)) {
    await setPaperRead(paper, true, { silent: true });
  }
  renderPaperDetail(paper);
}

async function submitUpvote(paper) {
  if (!state.apiAvailable) {
    showError("upvote 需要通过本地 Dashboard 服务访问。");
    return;
  }
  try {
    const item = await apiJson(`/api/feedback/${encodeURIComponent(paper.arxiv_id)}/upvote`, {
      method: "POST",
      body: JSON.stringify({ date: paperDate(paper) }),
    });
    const paperState = item.state || item;
    state.paperStates[stateKey(paper.arxiv_id, paperState.date || paperDate(paper))] = paperState;
    paper.state = paperState;
    renderDailyCards();
    renderSelectedTable();
    renderPaperDetail(paper);
  } catch (error) {
    showError(`upvote 失败：${error.message}`);
  }
}

async function submitDownvote(paper) {
  if (!state.apiAvailable) {
    showError("downvote 需要通过本地 Dashboard 服务访问。");
    return;
  }
  const reason = window.prompt("为什么不喜欢这篇？我会生成配置建议，确认后才会应用。");
  if (!reason || !reason.trim()) return;
  try {
    const item = await apiJson(`/api/feedback/${encodeURIComponent(paper.arxiv_id)}/downvote`, {
      method: "POST",
      body: JSON.stringify({ date: paperDate(paper), reason: reason.trim() }),
    });
    const changes = item.suggestion?.config_changes || [];
    const summary = item.suggestion?.summary || "已生成配置建议。";
    const ok = window.confirm(`${summary}\n\n建议 ${changes.length} 项配置变更。是否应用？`);
    if (ok) {
      await apiJson(`/api/feedback/${item.id}/apply`, { method: "POST" });
    }
    await loadPaperStates();
    paper.state = getPaperState(paper);
    renderDailyCards();
    renderSelectedTable();
    renderPaperDetail(paper);
  } catch (error) {
    showError(`downvote 失败：${error.message}`);
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

async function deleteDeepAnalysis(arxivId, date = "") {
  if (!state.apiAvailable) {
    showError("删除 AI解读需要通过本地 Dashboard 服务访问。");
    return;
  }
  const ok = window.confirm(`确认删除 ${arxivId} 的 AI解读吗？这会同时移除对应的报告文件。`);
  if (!ok) return;
  try {
    const query = date ? `?date=${encodeURIComponent(date)}` : "";
    await apiJson(`/api/deep-analysis/${encodeURIComponent(arxivId)}${query}`, {
      method: "DELETE",
    });
    delete state.deepAnalysis[arxivId];
    await loadDeepReads();
    await loadTasks();
    renderDeepReads();
    renderTasks();
    renderDailyDetail();
    renderSelectedTable();
  } catch (error) {
    showError(`删除 AI解读失败：${error.message}`);
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
      const read = isPaperRead(paper);
      return `
        <article class="paper-card ${active} ${read ? "read" : ""}" data-daily-id="${escapeHtml(paper.arxiv_id)}">
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
            <button class="chip-button" data-read-id="${escapeHtml(paper.arxiv_id)}">${read ? "已读" : "未读"}</button>
            <span class="subtle">${escapeHtml(paper.arxiv_id)}</span>
          </div>
        </article>
      `;
    })
    .join("");

  el.dailyTopGrid.querySelectorAll("[data-daily-id]").forEach((node) => {
    node.addEventListener("click", async () => {
      setActiveDailyPaper(node.dataset.dailyId);
      const paper = papers.find((item) => item.arxiv_id === node.dataset.dailyId);
      if (paper) await openPaperDetail(paper);
    });
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
  el.dailyTopGrid.querySelectorAll("[data-read-id]").forEach((node) => {
    node.addEventListener("click", (event) => {
      event.stopPropagation();
      const paper = papers.find((item) => item.arxiv_id === node.dataset.readId);
      if (paper) setPaperRead(paper, !isPaperRead(paper));
    });
  });
  renderMath(el.dailyTopGrid);
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
      <p class="eyebrow">Highlights Detail</p>
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
  renderMath(el.dailyDetail);
}

function renderPaperDetail(paper) {
  if (!paper || !el.paperDetailModal) return;
  const read = isPaperRead(paper);
  const upvoted = isPaperUpvoted(paper);
  const downvoted = isPaperDownvoted(paper);
  const authors = paper.authors_display || joinOrDash(paper.authors);
  const institutions = institutionDisplay(paper);
  const insightDone = hasAiInsight(paper.arxiv_id);
  el.paperDetailContent.innerHTML = `
    <article class="drawer-paper">
      <p class="eyebrow">${escapeHtml(paper.topic_category || "Paper Detail")}</p>
      <h2>${escapeHtml(paper.title || paper.arxiv_id)}</h2>
      <div class="detail-tags">
        <span class="tag">${escapeHtml(paper.arxiv_id)}</span>
        <span class="tag ${read ? "active-soft" : ""}">${read ? "已读" : "未读"}</span>
        ${upvoted ? '<span class="tag active-soft">已赞</span>' : ""}
        ${downvoted ? '<span class="tag active-soft">已踩</span>' : ""}
        ${paper.total_score !== undefined ? `<span class="tag">总分 ${escapeHtml(paper.total_score)}</span>` : ""}
        ${insightDone ? '<span class="tag">已有 AI解读</span>' : ""}
      </div>
      <div class="detail-block"><strong>Authors</strong><span>${escapeHtml(authors)}</span></div>
      <div class="detail-block"><strong>Institutions</strong><span>${escapeHtml(institutions)}</span></div>
      <div class="detail-block"><strong>Abstract</strong><span>${escapeHtml(paper.abstract || "暂无摘要")}</span></div>
      <div class="detail-block"><strong>Comments</strong><span>${escapeHtml(paper.comments || "—")}</span></div>
      <div class="detail-block"><strong>Summary</strong><span>${escapeHtml(paper.one_line_summary || "—")}</span></div>
      <div class="action-row">
        <a class="link-chip" href="${escapeHtml(paper.primary_url || `https://arxiv.org/abs/${paper.arxiv_id}`)}" target="_blank" rel="noreferrer">arXiv</a>
        <button class="primary-button small" data-detail-read="${read ? "0" : "1"}">${read ? "标为未读" : "标为已读"}</button>
        <button class="primary-button small" data-detail-ai="${escapeHtml(paper.arxiv_id)}">AI解读</button>
        <button class="vote-button ${upvoted ? "active up" : ""}" data-detail-upvote="${escapeHtml(paper.arxiv_id)}" title="Upvote">▲</button>
        <button class="vote-button ${downvoted ? "active down" : ""}" data-detail-downvote="${escapeHtml(paper.arxiv_id)}" title="Downvote">▼</button>
      </div>
    </article>
  `;
  el.paperDetailModal.classList.remove("hidden");
  el.paperDetailContent.querySelector("[data-detail-read]")?.addEventListener("click", (event) => {
    setPaperRead(paper, event.currentTarget.dataset.detailRead === "1", { refreshDetail: true });
  });
  el.paperDetailContent.querySelector("[data-detail-ai]")?.addEventListener("click", () => {
    requestDeepAnalysis(paper.arxiv_id);
  });
  el.paperDetailContent.querySelector("[data-detail-upvote]")?.addEventListener("click", () => {
    submitUpvote(paper);
  });
  el.paperDetailContent.querySelector("[data-detail-downvote]")?.addEventListener("click", () => {
    submitDownvote(paper);
  });
  renderMath(el.paperDetailContent);
}

function closePaperDetail() {
  el.paperDetailModal?.classList.add("hidden");
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
  if (state.selectedUnreadOnly) {
    filtered = filtered.filter((paper) => !isPaperRead(paper));
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
        const read = isPaperRead(paper);
        return `
        <tr class="${read ? "read-row" : ""}" data-paper-row="${escapeHtml(paper.arxiv_id)}">
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
              <button class="icon-button ${read ? "active-soft" : ""}" data-read-id="${escapeHtml(paper.arxiv_id)}" data-tooltip="${read ? "标为未读" : "标为已读"}">${read ? "✓" : "○"}</button>
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
  el.selectedTableBody.querySelectorAll("[data-paper-row]").forEach((node) => {
    node.addEventListener("click", async () => {
      const paper = papers.find((item) => item.arxiv_id === node.dataset.paperRow);
      if (paper) await openPaperDetail(paper);
    });
  });
  el.selectedTableBody.querySelectorAll("[data-read-id]").forEach((node) => {
    node.addEventListener("click", (event) => {
      event.stopPropagation();
      const paper = papers.find((item) => item.arxiv_id === node.dataset.readId);
      if (paper) setPaperRead(paper, !isPaperRead(paper));
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
  renderMath(el.selectedTableBody);
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
    el.deepReadList.innerHTML = '<div class="detail-empty">还没有已完成的 AI解读。可以从 Highlights 卡片或 Longlist 表格里点击“AI解读”生成。</div>';
    return;
  }
  el.deepReadList.innerHTML = items
    .map((item) => {
      const read = isPaperRead(item);
      return `
      <a class="deep-read-card ${read ? "read" : ""}" href="${escapeHtml(deepReportUrl(item))}" target="_blank" rel="noreferrer">
        <div>
          <p class="eyebrow">${escapeHtml(item.date || item.announced_day || "AI Insights")}</p>
          <h3>${escapeHtml(item.title || item.arxiv_id)}</h3>
          <p class="subtle">${escapeHtml(item.authors_display || joinOrDash(item.authors))}</p>
          <p>${escapeHtml(item.one_line_summary || "暂无一句话总结")}</p>
        </div>
        <div class="deep-read-meta">
          <span class="tag">${escapeHtml(item.arxiv_id)}</span>
          <span class="tag">${read ? "已读" : "未读"}</span>
          <span class="tag">${escapeHtml(item.topic_category || "未分类")}</span>
          ${item.total_score !== "" ? `<span class="tag">总分 ${escapeHtml(item.total_score)}</span>` : ""}
          <span class="link-chip">查看报告 ↗</span>
          <button class="chip-button danger-button" type="button" data-delete-deep-id="${escapeHtml(item.arxiv_id)}" data-delete-deep-date="${escapeHtml(item.date || "")}">删除</button>
        </div>
      </a>
    `;
    })
    .join("");
  el.deepReadList.querySelectorAll("[data-delete-deep-id]").forEach((node) => {
    node.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      deleteDeepAnalysis(node.dataset.deleteDeepId, node.dataset.deleteDeepDate || "");
    });
  });
  renderMath(el.deepReadList);
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
  await loadPaperStates();

  renderDateRail();
  renderMeta();
  renderDailySummary();
  renderDailyCards();
  renderDailyDetail();
  renderDeepAnalysis();
  renderSelected();
  renderDeepReads();
  renderFavorites();
  renderMath(document.body);
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
    el.jobProgress.value = 0;
    el.jobProgress.classList.add("hidden");
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
  el.jobProgress.value = job.progress || 0;
  el.jobProgress.classList.remove("hidden");
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
      await loadTasks();
      renderTasks();
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
    await loadTasks();
    renderTasks();
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
    await loadTasks();
    renderTasks();
  } catch (error) {
    showError(`停止任务失败：${error.message}`);
  }
}

async function saveSchedule(event) {
  event?.preventDefault?.();
  if (!state.apiAvailable) {
    showError("定时任务需要通过本地 Dashboard 服务访问。");
    return;
  }
  try {
    el.scheduleStatus.textContent = "正在保存定时配置...";
    await apiJson("/api/schedules", {
      method: "POST",
      body: JSON.stringify({
        enabled: el.scheduleEnabled.checked,
        run_time: el.scheduleTime.value || "09:00",
        days: Number(el.scheduleDays.value || 1),
        categories: el.scheduleCategories.value || "cs.CV,cs.RO",
      }),
    });
    await loadSchedules();
    renderSchedule();
  } catch (error) {
    showError(`定时任务保存失败：${error.message}`);
  }
}

async function toggleScheduleEnabled() {
  el.scheduleFields?.classList.toggle("hidden", !el.scheduleEnabled.checked);
  if (el.scheduleFields) el.scheduleFields.hidden = !el.scheduleEnabled.checked;
  await saveSchedule();
}

async function runScheduleNow() {
  if (!state.apiAvailable) return;
  try {
    const payload = await apiJson("/api/jobs/mining", {
      method: "POST",
      body: JSON.stringify({
        days: Number(el.scheduleDays.value || 1),
        categories: el.scheduleCategories.value || "cs.CV,cs.RO",
      }),
    });
    await loadTasks();
    renderTasks();
    await pollJob(payload.job_id);
  } catch (error) {
    showError(`立即试跑失败：${error.message}`);
  }
}

async function saveConfigItem(node) {
  const key = node.dataset.configKey;
  const type = node.dataset.configType;
  let value = node.value;
  if (type === "int") value = Number(value || 0);
  if (type === "list") value = value.split(",").map((item) => item.trim()).filter(Boolean);
  if (type === "dict") {
    try {
      value = JSON.parse(value || "{}");
    } catch (error) {
      showError(`配置 ${key} 需要合法 JSON。`);
      return;
    }
  }
  try {
    await apiJson("/api/config", {
      method: "PATCH",
      body: JSON.stringify({ key, value }),
    });
    await loadConfig();
    renderConfig();
  } catch (error) {
    showError(`配置保存失败：${error.message}`);
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
  await loadSchedules();
  await loadConfig();
  await loadTasks();
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
  el.selectedUnreadOnly.addEventListener("change", (event) => {
    state.selectedUnreadOnly = event.target.checked;
    renderSelectedTable();
  });
  el.miningForm.addEventListener("submit", startMiningJob);
  el.miningToggle.addEventListener("click", () => {
    setMiningExpanded(!state.miningExpanded);
    setTaskExpanded(false);
    setConfigExpanded(false);
  });
  el.miningTabButtons.forEach((button) => {
    button.addEventListener("click", () => switchMiningTab(button.dataset.miningTab));
  });
  el.jobCancelButton.addEventListener("click", cancelMiningJob);
  el.jobResetButton.addEventListener("click", resetActiveMiningJobs);
  el.taskToggle?.addEventListener("click", () => {
    setTaskExpanded(!state.taskExpanded);
    setMiningExpanded(false);
    setConfigExpanded(false);
  });
  el.configToggle?.addEventListener("click", () => {
    setConfigExpanded(!state.configExpanded);
    setMiningExpanded(false);
    setTaskExpanded(false);
  });
  el.tasksRefresh.addEventListener("click", async () => {
    await loadTasks();
    renderTasks();
  });
  el.scheduleForm.addEventListener("submit", saveSchedule);
  el.scheduleEnabled.addEventListener("change", toggleScheduleEnabled);
  el.scheduleRunNow.addEventListener("click", runScheduleNow);
  el.paperDetailClose.addEventListener("click", closePaperDetail);
  el.paperDetailBackdrop?.addEventListener("click", closePaperDetail);
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    closeSidePopovers();
    closePaperDetail();
  });
  el.workspaceBackdrop?.addEventListener("click", closeSidePopovers);
  document.addEventListener("click", (event) => {
    if (!state.miningExpanded && !state.taskExpanded && !state.configExpanded) return;
    if (
      el.miningWidget.contains(event.target) ||
      el.taskWidget?.contains(event.target) ||
      el.configWidget?.contains(event.target)
    ) return;
    closeSidePopovers();
  });
  el.miningWidget.addEventListener("click", (event) => {
    event.stopPropagation();
  });
  el.taskWidget?.addEventListener("click", (event) => {
    event.stopPropagation();
  });
  el.configWidget?.addEventListener("click", (event) => {
    event.stopPropagation();
  });

  switchTab(state.currentTab);
  switchMiningTab(state.miningTab);
  setMiningExpanded(false);
  setTaskExpanded(false);
  setConfigExpanded(false);
  renderJobStatus(null);
  renderSchedule();
  renderConfig();
  renderTasks();
  state.taskPollTimer = setInterval(async () => {
    await loadTasks();
    renderTasks();
  }, 5000);
  state.currentDate = defaultDate;
  renderDateRail();
  await loadDate(defaultDate);
}

init().catch((error) => {
  showError(`页面初始化失败：${error.message}`);
  console.error(error);
});

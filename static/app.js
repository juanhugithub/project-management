/* 科技项目台账 - 前端逻辑（原生 JS，无框架） */
"use strict";

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

const STAGES = ["申报中", "已立项", "实施中", "待验收", "已验收", "绩效跟踪", "已完结", "中止", "撤销"];
const FUND_STATUS = ["未拨付", "已拨付", "已到账"];
const NODE_STATUS = ["待办", "已完成", "已逾期"];

const UI_TEXT_CATALOG = [
  { group: "导航", key: "brand.title", label: "品牌名称", selector: ".brand > span", fallback: "科技项目台账" },
  { group: "导航", key: "brand.subtitle", label: "品牌副标题", selector: ".brand small", fallback: "全生命周期管理" },
  { group: "导航", key: "nav.dashboard", label: "工作台", selector: '[data-tab="dashboard"]', fallback: "工作台" },
  { group: "导航", key: "nav.projects", label: "项目总览", selector: '[data-tab="projects"]', fallback: "项目总览" },
  { group: "导航", key: "nav.reminders", label: "提醒", selector: '[data-tab="reminders"]', fallback: "提醒" },
  { group: "导航", key: "nav.enterprises", label: "企业", selector: '[data-tab="enterprises"]', fallback: "企业" },
  { group: "导航", key: "nav.stats", label: "资金统计", selector: '[data-tab="stats"]', fallback: "资金统计" },
  { group: "导航", key: "nav.settings", label: "设置", selector: "#btn-settings-toggle span", fallback: "设置" },
  { group: "工作台", key: "dashboard.title", label: "工作台标题", selector: "#tab-dashboard h1", fallback: "项目概览" },
  { group: "工作台", key: "dashboard.add", label: "新增项目按钮", selector: "#btn-hero-project", fallback: "新增项目" },
  { group: "工作台", key: "dashboard.refresh", label: "刷新按钮", selector: "#btn-hero-refresh", fallback: "刷新数据" },
  { group: "列表页", key: "projects.add", label: "新增项目按钮", selector: "#btn-add-project", fallback: "＋ 新增项目" },
  { group: "列表页", key: "projects.search", label: "项目查询按钮", selector: "#btn-search", fallback: "查询" },
  { group: "列表页", key: "enterprises.add", label: "新增企业按钮", selector: "#btn-add-enterprise", fallback: "＋ 新增企业" },
  { group: "列表页", key: "enterprises.search", label: "企业搜索按钮", selector: "#btn-enterprise-search", fallback: "搜索" },
  { group: "系统", key: "settings.dict", label: "配置入口", selector: '[data-tab="dict"]', fallback: "配置" },
  { group: "系统", key: "settings.guide", label: "使用助手入口", selector: '[data-tab="guide"]', fallback: "使用助手" },
  { group: "系统", key: "settings.usage", label: "使用分析入口", selector: '[data-tab="usage"]', fallback: "使用分析" },
  { group: "系统", key: "settings.update", label: "检查更新入口", selector: "#btn-check-update", fallback: "检查并更新" },
];
const state = { dict: {}, uiTexts: {}, enterprises: [], enterprisePage: { page: 1, pageSize: 50, q: "", advFilters: [], sort: "id", direction: "desc", total: 0, totalPages: 0 }, projectPage: { page: 1, pageSize: 50, sort: "id", direction: "desc", total: 0, totalPages: 0 }, filters: {}, archivedYears: [], projectSort: null };
function textFor(key) { const item = UI_TEXT_CATALOG.find(x => x.key === key); return state.uiTexts[key] ?? item?.fallback ?? key; }
function applyUiTexts() {
  for (const item of UI_TEXT_CATALOG) {
    const element = document.querySelector(item.selector);
    if (element) element.textContent = textFor(item.key);
  }
}
function trackUsage(module, action = "view") { fetch("/api/usage", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ module, action }) }).catch(() => {}); }

function showLogin(message = "请登录后继续使用台账。") {
  $("#auth-panel").classList.remove("hidden");
  $("#auth-error").textContent = message;
  $("#auth-error").classList.remove("hidden");
  setTimeout(() => $("#auth-username").focus(), 0);
}

function hideLogin() {
  $("#auth-panel").classList.add("hidden");
  $("#auth-error").classList.add("hidden");
}

/* ---------- API ---------- */
async function api(path, method = "GET", body = null) {
  const opt = { method, headers: {} };
  if (body) { opt.headers["Content-Type"] = "application/json"; opt.body = JSON.stringify(body); }
  const res = await fetch("/api" + path, opt);
  let data = {};
  try { data = await res.json(); } catch (e) { /* ignore */ }
  if (!res.ok) {
    const error = new Error(data.error || `请求失败(${res.status})`);
    error.status = res.status;
    if (res.status === 401 && path !== "/auth/login") showLogin("会话未登录或已失效，请登录后重试。");
    throw error;
  }
  return data;
}

/* ---------- 表单定义 ---------- */
const FORMS = {
  enterprise: [
    { k: "name", label: "企业名称", type: "text", required: true },
    { k: "credit_code", label: "统一社会信用代码", type: "text" },
    { k: "enterprise_type", label: "企业类型", type: "select", dict: "enterprise_type" },
    { k: "district", label: "区镇", type: "select", dict: "district" },
    { k: "qualifications", label: "资质", type: "text" },
    { k: "contact_person", label: "联系人", type: "text" },
    { k: "contact_phone", label: "联系电话", type: "text" },
    { k: "address", label: "地址", type: "text" },
    { k: "note", label: "备注", type: "textarea", full: true },
  ],
  project: [
    { k: "name", label: "项目名称", type: "text", required: true },
    { k: "project_no", label: "项目编号/文号", type: "text" },
    { k: "level", label: "层级", type: "select", dict: "level" },
    { k: "category", label: "类型", type: "select", dict: "category" },
    { k: "enterprise_id", label: "承担企业", type: "enterprise" },
    { k: "total_amount", label: "总金额(万元)", type: "number" },
    { k: "start_date", label: "开始日期", type: "date" },
    { k: "end_date", label: "结束日期", type: "date" },
    { k: "stage", label: "当前阶段", type: "select", options: STAGES },
    { k: "match_ratio", label: "配套比例(如1=1:1)", type: "number" },
    { k: "leader", label: "项目负责人", type: "text" },
    { k: "contact_phone", label: "联系人手机号", type: "text" },
    { k: "note", label: "备注", type: "textarea", full: true },
  ],
  funding: [
    { k: "source_type", label: "资金来源", type: "select", dict: "funding_source" },
    { k: "amount", label: "金额(万元)", type: "number" },
    { k: "batch", label: "批次", type: "text" },
    { k: "plan_date", label: "应拨时间", type: "date" },
    { k: "actual_date", label: "实拨时间", type: "date" },
    { k: "status", label: "状态", type: "select", options: FUND_STATUS },
    { k: "note", label: "备注", type: "text" },
  ],
  node: [
    { k: "node_type", label: "节点类型", type: "select", dict: "node_type" },
    { k: "plan_date", label: "计划时间", type: "date" },
    { k: "actual_date", label: "实际完成", type: "date" },
    { k: "status", label: "状态", type: "select", options: NODE_STATUS },
    { k: "has_major_change", label: "重大事项变更", type: "checkbox" },
    { k: "note", label: "备注", type: "text" },
  ],
};

function fieldOptions(f) {
  if (f.options) return f.options;
  if (f.dict) return state.dict[f.dict] || [];
  return [];
}

function buildFieldHtml(f, value) {
  const req = f.required ? ' required' : '';
  const val = value ?? "";
  const cls = f.full ? ' class="full"' : "";
  if (f.type === "select") {
    let opts = `<option value="">请选择</option>`;
    for (const o of fieldOptions(f)) {
      const sel = String(val) === String(o) ? " selected" : "";
      opts += `<option value="${escapeHtml(o)}"${sel}>${escapeHtml(o)}</option>`;
    }
    return `<label${cls}><span class="t">${f.label}</span><select name="${f.k}"${req}>${opts}</select></label>`;
  }
  if (f.type === "enterprise") {
    let opts = `<option value="">请选择</option>`;
    for (const e of state.enterprises) {
      const sel = Number(val) === Number(e.id) ? " selected" : "";
      opts += `<option value="${e.id}"${sel}>${escapeHtml(e.name)}</option>`;
    }
    return `<label${cls}><span class="t">${f.label}</span><select name="${f.k}"${req}>${opts}</select></label>`;
  }
  if (f.type === "textarea") {
    return `<label${cls}><span class="t">${f.label}</span><textarea name="${f.k}">${escapeHtml(val)}</textarea></label>`;
  }
  if (f.type === "checkbox") {
    const checked = value ? " checked" : "";
    return `<label${cls}><span class="t">${f.label}</span><input type="checkbox" name="${f.k}"${checked}></label>`;
  }
  return `<label${cls}><span class="t">${f.label}</span><input type="${f.type}" name="${f.k}" value="${escapeHtml(val)}"${req}></label>`;
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[c]));
}

function fmtDate(d) { return d ? d : "—"; }
function fmtMoney(v) { return v == null ? "—" : Number(v).toLocaleString("zh-CN", { maximumFractionDigits: 2 }); }

/* ---------- Toast ---------- */
let toastTimer = null;
function toast(msg, type = "ok") {
  const el = $("#toast");
  el.textContent = msg;
  el.className = "toast " + type;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.add("hidden"), 2600);
}

/* ---------- Tab 切换 ---------- */
const SETTINGS_TABS = new Set(["dict", "ui-text", "guide", "usage"]);
const settingsToggle = $("#btn-settings-toggle");
const settingsMenu = $("#settings-menu");

function closeSettingsMenu() {
  settingsMenu.classList.add("hidden");
  settingsToggle.setAttribute("aria-expanded", "false");
}

settingsToggle.addEventListener("click", event => {
  event.stopPropagation();
  const opening = settingsMenu.classList.contains("hidden");
  settingsMenu.classList.toggle("hidden", !opening);
  settingsToggle.setAttribute("aria-expanded", String(opening));
});
document.addEventListener("click", event => {
  if (!event.target.closest(".settings-nav")) closeSettingsMenu();
});

$$(".tab-btn[data-tab]").forEach(btn => {
  btn.addEventListener("click", () => {
    $$(".tab-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    settingsToggle.classList.toggle("active", SETTINGS_TABS.has(btn.dataset.tab));
    closeSettingsMenu();
    $$(".tab").forEach(t => t.classList.remove("active"));
    $("#tab-" + btn.dataset.tab).classList.add("active");
    if (btn.dataset.tab === "dashboard") loadDashboard();
    if (btn.dataset.tab === "reminders") loadReminders();
    if (btn.dataset.tab === "stats") loadStats();
    trackUsage(btn.dataset.tab, "view");
    if (btn.dataset.tab === "usage") loadUsage();
    if (btn.dataset.tab === "ui-text") renderUiTextConfig();
  });
});

async function loadUsage() {
  const data = await api("/usage");
  const render = (items, target) => {
    const el = $(target);
    if (!items.length) { el.innerHTML = '<div class="usage-empty">还没有使用记录</div>'; return; }
    const max = Math.max(...items.map(x => x.count));
    el.innerHTML = items.map(item => `<div class="usage-row"><span title="${escapeHtml(item.name)}">${escapeHtml(item.name)}</span><span class="bar"><i style="width:${Math.max(2, item.count / max * 100)}%"></i></span><b>${item.count}</b></div>`).join("");
  };
  render(data.modules || [], "#usage-modules"); render(data.actions || [], "#usage-actions");
}

async function applyAvailableUpdate(button, banner) {
  if (button) { button.disabled = true; button.textContent = "正在下载并安装…"; }
  toast("正在下载并安装新版本");
  try {
    const pageVersion = document.querySelector('meta[name="app-version"]')?.content || "";
    await api("/update/apply", "POST", {});
    if (banner) banner.innerHTML = "正在安装，完成后页面会自动刷新…";
    toast("正在安装新版本，请保持页面打开");
    await waitForUpdatedServer(pageVersion, button, banner);
  } catch (error) {
    if (button) { button.disabled = false; button.textContent = "重试更新"; }
    toast(error.message, "err");
  }
}

async function waitForUpdatedServer(pageVersion, button, banner) {
  // 安装时间取决于网络和磁盘速度；只有新后台真正监听端口后才刷新页面。
  while (true) {
    await new Promise(resolve => setTimeout(resolve, 1000));
    try {
      const result = await api("/update");
      if (result.update_state === "failed") {
        const updateError = new Error(result.update_error || "更新安装失败");
        updateError.status = 409;
        throw updateError;
      }
      if (result.running_version && result.running_version !== pageVersion && result.running_version === result.current_version) {
        location.replace(`/?app-version=${encodeURIComponent(result.running_version)}`);
        return;
      }
    } catch (error) {
      // 服务重启期间连接暂时中断属于正常过程；明确的安装失败才恢复按钮。
      if (!error.status) continue;
      if (button) { button.disabled = false; button.textContent = "重试更新"; }
      if (banner) banner.textContent = error.message;
      throw error;
    }
  }
}

async function checkForUpdate(autoApply = false) {
  const banner = $("#update-banner");
  try {
    const result = await api("/update");
    const pageVersion = document.querySelector('meta[name="app-version"]')?.content || "";
    // 页面版本只与实际提供请求的后台版本比较，不能使用已写入配置但尚未启动的版本。
    if (pageVersion && result.running_version && pageVersion !== result.running_version) {
      banner.classList.add("hidden");
      location.replace(`/?app-version=${encodeURIComponent(result.running_version)}`);
      return { configured: true, available: true, reloading: true };
    }
    if (result.running_version && result.current_version !== result.running_version) {
      banner.classList.remove("hidden");
      banner.textContent = "新版本已安装，正在等待后台切换…";
      waitForUpdatedServer(pageVersion, null, banner);
      return { configured: true, available: true, restarting: true };
    }
    if (!result.update_available) { banner.classList.add("hidden"); return { configured: true, available: false }; }
    if (autoApply) {
      banner.classList.add("hidden");
      await applyAvailableUpdate($("#btn-check-update"), null);
      return { configured: true, available: true, applying: true };
    }
    banner.innerHTML = `<span><b>发现新版本 ${escapeHtml(result.release_version)}</b>${(result.notes || []).length ? "：" + escapeHtml(result.notes.join("；")) : ""}</span><button id="btn-apply-update" class="primary small">下载并更新</button>`;
    banner.classList.remove("hidden");
    $("#btn-apply-update").addEventListener("click", async () => {
      await applyAvailableUpdate($("#btn-apply-update"), banner);
    });
    return { configured: true, available: true };
  } catch (error) {
    if (error.status === 409) return { configured: false, available: false, error: error.message };
    console.warn("更新检查失败", error.message);
    return { configured: false, available: false };
  }
}

/* ---------- 字典与基础数据加载 ---------- */
async function loadDict() {
  state.dict = await api("/dict");
  fillSelect("#flt-level", state.dict.level || [], "全部层级");
  fillSelect("#flt-category", state.dict.category || [], "全部类型");
  fillSelect("#flt-stage", STAGES, "全部阶段");
  fillSelect("#flt-district", state.dict.district || [], "全部区镇");
}
function fillSelect(sel, items, placeholder) {
  const el = $(sel);
  el.innerHTML = `<option value="">${placeholder}</option>` +
    items.map(v => `<option value="${escapeHtml(v)}">${escapeHtml(v)}</option>`).join("");
}

async function loadEnterprises() {
  // 企业选项与企业列表分离：项目录入需要完整名称索引，但企业页只请求当前分页。
  state.enterprises = await api("/enterprises?lookup=1");
  await loadEnterprisePage();
}

async function loadEnterprisePage() {
  const p = state.enterprisePage;
  const params = new URLSearchParams({ page: p.page, page_size: p.pageSize });
  if (p.q) params.set("q", p.q);
  if (p.advFilters?.length) params.set("filters", JSON.stringify(p.advFilters));
  if (p.sort) { params.set("sort", p.sort); params.set("direction", p.direction); }
  const result = await api("/enterprises?" + params.toString());
  state.enterprisePage = { ...p, ...result, totalPages: result.total_pages ?? result.totalPages ?? 0 };
  renderEnterpriseTable();
}

/* ---------- 项目 ---------- */
async function loadProjects() {
  const params = new URLSearchParams();
  const page = state.projectPage;
  params.set("page", page.page); params.set("page_size", page.pageSize);
  params.set("sort", page.sort); params.set("direction", page.direction);
  if (state.filters.level) params.set("level", state.filters.level);
  if (state.filters.category) params.set("category", state.filters.category);
  if (state.filters.stage) params.set("stage", state.filters.stage);
  if (state.filters.district) params.set("district", state.filters.district);
  if (state.filters.q) params.set("q", state.filters.q);
  if (state.filters.advFilters && state.filters.advFilters.length) {
    params.set("filters", JSON.stringify(state.filters.advFilters));
  }
  const qs = params.toString();
  const result = await api("/projects" + (qs ? "?" + qs : ""));
  state.projectPage = { ...page, ...result, totalPages: result.total_pages ?? result.totalPages ?? 0 };
  state.lastProjects = result.items || [];
  renderProjectTable(state.lastProjects);
  renderProjectPagination();
}

function stageBadge(stage) {
  const map = { "申报中": "gray", "已立项": "green", "实施中": "", "待验收": "orange", "已验收": "green", "绩效跟踪": "", "已完结": "gray", "中止": "orange", "撤销": "orange" };
  return `<span class="badge ${map[stage] || ""}">${escapeHtml(stage || "—")}</span>`;
}

const PROJECT_TEXT_COLLATOR = new Intl.Collator("zh-CN", { numeric: true, sensitivity: "base" });
const PROJECT_SORT_FIELDS = {
  name: { type: "text" },
  project_no: { type: "text" },
  level: { type: "ordered", values: () => state.dict.level || [] },
  category: { type: "ordered", values: () => state.dict.category || [] },
  enterprise_name: { type: "text" },
  enterprise_district: { type: "ordered", values: () => state.dict.district || [] },
  total_amount: { type: "number" },
  disbursed_total: { type: "number" },
  stage: { type: "ordered", values: () => STAGES },
};

function compareProjectValues(left, right, rule, direction) {
  // 无论升序还是降序，未填写的字段始终排在末尾，便于优先核对有效业务数据。
  const leftEmpty = left === null || left === undefined || left === "";
  const rightEmpty = right === null || right === undefined || right === "";
  if (leftEmpty || rightEmpty) return leftEmpty === rightEmpty ? 0 : (leftEmpty ? 1 : -1);

  if (rule.type === "number") return (Number(left) - Number(right)) * direction;
  if (rule.type === "ordered") {
    const values = rule.values();
    const leftIndex = values.indexOf(left);
    const rightIndex = values.indexOf(right);
    const leftKnown = leftIndex >= 0;
    const rightKnown = rightIndex >= 0;
    // 历史数据中已停用的字典值不参与当前配置顺序，统一放在有效字典值之后。
    if (leftKnown !== rightKnown) return leftKnown ? -1 : 1;
    if (leftKnown && leftIndex !== rightIndex) return (leftIndex - rightIndex) * direction;
  }
  return PROJECT_TEXT_COLLATOR.compare(String(left), String(right)) * direction;
}

function sortProjects(list) {
  if (!state.projectSort) return [...list];
  const { field, direction } = state.projectSort;
  const rule = PROJECT_SORT_FIELDS[field];
  if (!rule) return [...list];
  const multiplier = direction === "desc" ? -1 : 1;
  return list.map((project, index) => ({ project, index })).sort((left, right) => {
    const compared = compareProjectValues(left.project[field], right.project[field], rule, multiplier);
    return compared || left.index - right.index;
  }).map(item => item.project);
}

function updateProjectSortHeaders() {
  $$("#project-table th[data-sort]").forEach(header => {
    const button = header.querySelector(".project-sort");
    const indicator = header.querySelector(".sort-indicator");
    const active = state.projectSort && state.projectSort.field === header.dataset.sort;
    const direction = active ? state.projectSort.direction : null;
    header.setAttribute("aria-sort", direction === "asc" ? "ascending" : direction === "desc" ? "descending" : "none");
    button.classList.toggle("is-active", !!active);
    indicator.textContent = direction === "asc" ? "↑" : direction === "desc" ? "↓" : "↕";
  });
}

function renderProjectTable(list) {
  const tbody = $("#project-table tbody");
  $("#project-empty").classList.toggle("hidden", list.length > 0);
  $("#result-count").textContent = `共 ${state.projectPage.total || list.length} 条结果，第 ${state.projectPage.page}/${state.projectPage.totalPages || 1} 页`;
  const arch = state.archivedYears || [];
  const sortedList = sortProjects(list);
  updateProjectSortHeaders();
  tbody.innerHTML = sortedList.map(p => {
    const isArch = !!(p.start_date && arch.includes(p.start_date.slice(0, 4)));
    return `<tr>
      <td><a href="#" class="p-name" data-id="${p.id}">${escapeHtml(p.name)}</a></td>
      <td>${escapeHtml(p.project_no || "—")}</td>
      <td>${escapeHtml(p.level || "—")}</td>
      <td>${escapeHtml(p.category || "—")}</td>
      <td>${escapeHtml(p.enterprise_name || "—")}</td>
      <td>${escapeHtml(p.enterprise_district || "—")}</td>
      <td class="num">${fmtMoney(p.total_amount)}</td>
      <td class="num">${fmtMoney(p.disbursed_total)}</td>
      <td>${stageBadge(p.stage)}${isArch ? ` <span class="badge gray">已归档</span>` : ""}</td>
      <td>
        ${isArch
          ? `<span class="badge gray">仅查看</span>`
          : `<button class="small p-view" data-id="${p.id}">查看</button>
             <button class="small p-edit" data-id="${p.id}">编辑</button>
             <button class="small danger p-del" data-id="${p.id}">删除</button>`}
      </td>
    </tr>`;
  }).join("");
}

function renderProjectPagination() {
  const box = $("#project-pagination");
  const { page, totalPages } = state.projectPage;
  box.innerHTML = totalPages ? `<button class="small" data-page="prev" ${page <= 1 ? "disabled" : ""}>上一页</button><span>第 ${page} / ${totalPages} 页</span><button class="small" data-page="next" ${page >= totalPages ? "disabled" : ""}>下一页</button>` : "";
}

/* ---------- 项目详情 ---------- */
function buildProjectTimeline(p) {
  // V1 只使用已经存在的项目、资金和节点事实，同一条业务记录的计划与实际分别入轴。
  const today = new Date().toISOString().slice(0, 10);
  const events = [];
  const add = (date, kind, mode, title, detail, alert = false) => {
    if (date) events.push({ date, kind, mode, title, detail, alert });
  };
  add(p.start_date, "stage", "actual", "项目开始", `当前阶段：${p.stage || "未设置"}`);
  add(p.end_date, "stage", "planned", "计划完成", "项目计划结束日期", !!(p.end_date && p.end_date < today && !["已完结", "中止"].includes(p.stage)));
  (p.fundings || []).forEach(f => {
    const money = `${fmtMoney(f.amount)} 万元${f.batch ? ` · ${f.batch}` : ""}`;
    add(f.plan_date, "funding", "planned", `${f.source_type || "资金"}应拨`, money, !!(f.plan_date < today && !f.actual_date));
    add(f.actual_date, "funding", "actual", `${f.source_type || "资金"}实拨`, `${money} · ${f.status || "已记录"}`);
  });
  (p.nodes || []).forEach(n => {
    const changed = !!n.has_major_change;
    add(n.plan_date, "node", "planned", `${n.node_type || "项目节点"}计划`, n.status || "待办", changed || !!(n.plan_date < today && n.status !== "已完成"));
    add(n.actual_date, "node", "actual", `${n.node_type || "项目节点"}完成`, changed ? "已完成 · 存在重大变更" : "已完成", changed);
  });
  events.sort((a, b) => a.date.localeCompare(b.date) || (a.mode === "planned" ? -1 : 1));
  const kindLabel = { stage: "阶段", funding: "资金", node: "节点" };
  const cards = events.map((event, index) => `
    <article class="timeline-event ${event.mode} ${event.alert ? "alert" : ""}" data-kind="${event.kind}" data-alert="${event.alert ? "1" : "0"}">
      <div class="timeline-card">
        <div class="timeline-card-meta"><time>${escapeHtml(event.date)}</time><span>${kindLabel[event.kind]}</span></div>
        <strong>${escapeHtml(event.title)}</strong>
        <p>${escapeHtml(event.detail)}</p>
      </div>
      <span class="timeline-marker" aria-hidden="true"></span>
      <span class="timeline-seq">${String(index + 1).padStart(2, "0")}</span>
    </article>`).join("");
  return `
    <section class="project-timeline" aria-label="项目数字时间轴">
      <div class="timeline-head">
        <div><p class="timeline-kicker">PROJECT CHRONICLE</p><h4>项目数字时间轴</h4></div>
        <div class="timeline-stage"><span>当前阶段</span>${stageBadge(p.stage)}</div>
      </div>
      <div class="timeline-toolbar" role="group" aria-label="时间轴筛选">
        <button class="timeline-filter active" data-filter="all">全部</button>
        <button class="timeline-filter" data-filter="stage">阶段</button>
        <button class="timeline-filter" data-filter="node">节点</button>
        <button class="timeline-filter" data-filter="funding">资金</button>
        <button class="timeline-filter" data-filter="alert">异常</button>
        <span class="timeline-legend"><i class="planned"></i>计划 <i class="actual"></i>实际</span>
      </div>
      <div class="timeline-viewport">
        <div class="timeline-track">${cards || `<div class="timeline-empty">录入项目日期、资金或节点后，这里将自动生成时间轴。</div>`}</div>
      </div>
    </section>`;
}

function bindProjectTimelineFilters(root) {
  // 筛选只改变时间轴视图，不修改任何项目事实或表格记录。
  root.querySelectorAll(".timeline-filter").forEach(button => button.addEventListener("click", () => {
    root.querySelectorAll(".timeline-filter").forEach(item => item.classList.toggle("active", item === button));
    const filter = button.dataset.filter;
    let visible = 0;
    root.querySelectorAll(".timeline-event").forEach(event => {
      const show = filter === "all" || event.dataset.kind === filter || (filter === "alert" && event.dataset.alert === "1");
      event.classList.toggle("hidden", !show);
      if (show) visible += 1;
    });
    root.querySelector(".timeline-track").classList.toggle("filtered-empty", visible === 0);
  }));
}

async function showProjectDetail(id) {
  const p = await api("/projects/" + id);
  // 资金口径必须并列展示：页面不再把所有资金笼统称为“已到位”。
  const plannedTotal = (p.fundings || []).filter(f => f.plan_date).reduce((s, f) => s + (f.amount || 0), 0);
  const disbursedTotal = (p.fundings || []).filter(f => ["已拨付", "已到账"].includes(f.status)).reduce((s, f) => s + (f.amount || 0), 0);
  const receivedTotal = (p.fundings || []).filter(f => f.status === "已到账").reduce((s, f) => s + (f.amount || 0), 0);
  const pendingTotal = (p.fundings || []).filter(f => !["已拨付", "已到账"].includes(f.status)).reduce((s, f) => s + (f.amount || 0), 0);
  const bySource = {};
  (p.fundings || []).forEach(f => { bySource[f.source_type] = (bySource[f.source_type] || 0) + (f.amount || 0); });
  const sumUp = bySource["上级拨付"] || 0, sumMatch = bySource["本级配套"] || 0, sumSelf = bySource["本级自付"] || 0;
  const checkIssues = [];
  if (p.total_amount != null && Math.abs(sumUp + sumMatch + sumSelf - p.total_amount) > 0.005) {
    checkIssues.push(`资金合计(${fmtMoney(sumUp + sumMatch + sumSelf)}) 与项目总金额(${fmtMoney(p.total_amount)})不一致`);
  }
  if (p.match_ratio && sumUp) {
    const expected = sumUp * p.match_ratio;
    if (Math.abs(sumMatch - expected) > 0.005) {
      checkIssues.push(`本级配套(${fmtMoney(sumMatch)}) 与应配额(${fmtMoney(expected)})不一致`);
    }
  }
  const lastNode = (p.nodes || []).filter(n => n.status !== "已完成").sort((a, b) => (a.plan_date || "").localeCompare(b.plan_date || ""))[0];
  const arch = state.archivedYears || [];
  const isArch = !!(p.start_date && arch.includes(p.start_date.slice(0, 4)));
  $("#project-detail").innerHTML = `
    <div class="detail">
      <div class="detail-head">
        <h3>${escapeHtml(p.name)}${isArch ? ` <span class="badge gray">已归档</span>` : ""}</h3>
        <div>
          ${isArch ? "" : `<button class="small" id="btn-detail-edit">编辑项目</button>`}
          <button class="small" onclick="document.getElementById('project-detail').innerHTML=''">收起</button>
        </div>
      </div>
      <div class="detail-grid fact-grid" aria-label="项目资金事实">
        ${kv("项目总金额", fmtMoney(p.total_amount) + " 万元")}
        ${kv("计划拨付", fmtMoney(plannedTotal) + " 万元")}
        ${kv("已拨付", fmtMoney(disbursedTotal) + " 万元")}
        ${kv("已到账", fmtMoney(receivedTotal) + " 万元")}
        ${kv("待拨", fmtMoney(pendingTotal) + " 万元")}
        ${kv("资金勾稽", checkIssues.length ? "存在差异" : "一致")}
      </div>
      <div class="detail-grid">
        ${kv("项目编号", p.project_no)}${kv("层级", p.level)}${kv("类型", p.category)}
        ${kv("当前阶段", stageBadge(p.stage))}${kv("配套比例", p.match_ratio == null ? "—" : p.match_ratio + " : 1")}
        ${kv("起止时间", (p.start_date || "—") + " ~ " + (p.end_date || "—"))}
        ${kv("负责人", p.leader)}${kv("联系人手机", p.contact_phone)}
        ${kv("备注", p.note, true)}
      </div>

      ${buildProjectTimeline(p)}

      <div class="sub-title">承担企业</div>
      <div class="detail-grid">
        ${p.enterprise ? kv("企业名称", p.enterprise.name) + kv("信用代码", p.enterprise.credit_code) + kv("区镇", p.enterprise.district) + kv("联系人", p.enterprise.contact_person + " " + (p.enterprise.contact_phone || "")) : kv("企业", "未关联")}
      </div>

      ${checkIssues.length
        ? `<div class="fund-check warn"><b>⚠ ${checkIssues.join("；")}</b></div>`
        : `<div class="fund-check ok">✅ 资金勾稽一致：上级 ${fmtMoney(sumUp)} + 配套 ${fmtMoney(sumMatch)} + 自付 ${fmtMoney(sumSelf)} = ${fmtMoney(sumUp + sumMatch + sumSelf)}</div>`}
      <div class="sub-title">资金明细（计划 ${fmtMoney(plannedTotal)} / 已拨 ${fmtMoney(disbursedTotal)} / 已到账 ${fmtMoney(receivedTotal)} 万元）</div>
      <table class="sub-table">
        <thead><tr><th>来源</th><th>金额(万)</th><th>批次</th><th>应拨</th><th>实拨</th><th>状态</th><th>操作</th></tr></thead>
        <tbody>
          ${(p.fundings || []).map(f => `<tr>
            <td>${escapeHtml(f.source_type || "—")}</td><td class="num">${fmtMoney(f.amount)}</td>
            <td>${escapeHtml(f.batch || "—")}</td><td>${fmtDate(f.plan_date)}</td><td>${fmtDate(f.actual_date)}</td>
            <td>${escapeHtml(f.status || "—")}</td>
            <td>${isArch ? "" : `<button class="small danger f-del" data-id="${f.id}">删除</button>`}</td>
          </tr>`).join("") || `<tr><td colspan="7" class="empty">暂无资金记录</td></tr>`}
        </tbody>
      </table>
      ${isArch ? "" : `<div class="inline-add" data-kind="funding" data-pid="${p.id}"></div>`}

      <div class="sub-title">项目节点${lastNode ? `（下一节点：${escapeHtml(lastNode.node_type)} ${fmtDate(lastNode.plan_date)}）` : ""}</div>
      <table class="sub-table">
        <thead><tr><th>节点</th><th>计划时间</th><th>实际完成</th><th>状态</th><th>重大变更</th><th>操作</th></tr></thead>
        <tbody>
          ${(p.nodes || []).map(n => `<tr>
            <td>${escapeHtml(n.node_type || "—")}</td><td>${fmtDate(n.plan_date)}</td><td>${fmtDate(n.actual_date)}</td>
            <td>${escapeHtml(n.status || "—")}</td>
            <td>${n.has_major_change ? "⚠️ 是" : "否"}</td>
            <td>${isArch ? "" : `<button class="small danger n-del" data-id="${n.id}">删除</button>`}</td>
          </tr>`).join("") || `<tr><td colspan="6" class="empty">暂无节点</td></tr>`}
        </tbody>
      </table>
      ${isArch ? "" : `<div class="inline-add" data-kind="node" data-pid="${p.id}"></div>`}
    </div>`;

  const editBtn = $("#btn-detail-edit");
  if (editBtn) editBtn.addEventListener("click", () => openProjectModal(p.id));
  bindProjectTimelineFilters($("#project-detail"));
  $("#project-detail").querySelectorAll(".f-del").forEach(b => b.addEventListener("click", async () => {
    if (!confirm("删除这笔资金？")) return;
    await api("/fundings/" + b.dataset.id, "DELETE"); toast("已删除"); showProjectDetail(id);
  }));
  $("#project-detail").querySelectorAll(".n-del").forEach(b => b.addEventListener("click", async () => {
    if (!confirm("删除这个节点？")) return;
    await api("/nodes/" + b.dataset.id, "DELETE"); toast("已删除"); showProjectDetail(id);
  }));
  if (!isArch) {
    buildInlineAdd($("#project-detail").querySelector('[data-kind="funding"]'), "funding", p.id, () => showProjectDetail(id));
    buildInlineAdd($("#project-detail").querySelector('[data-kind="node"]'), "node", p.id, () => showProjectDetail(id));
  }
  $("#project-detail").scrollIntoView({ behavior: "smooth", block: "start" });
}

function kv(k, v, full) {
  return `<div class="item"${full ? ' style="grid-column:1/-1"' : ""}><div class="k">${escapeHtml(k)}</div><div class="v">${v ?? "—"}</div></div>`;
}

/* 内联添加表单（资金/节点） */
function buildInlineAdd(container, kind, pid, after) {
  const fields = FORMS[kind];
  container.innerHTML = fields.map(f => {
    if (f.type === "select") {
      return `<select data-k="${f.k}"><option value="">${f.label}</option>${
        fieldOptions(f).map(o => `<option>${escapeHtml(o)}</option>`).join("")}</select>`;
    }
    if (f.type === "checkbox") {
      return `<label style="font-size:12px;color:var(--muted)"><input type="checkbox" data-k="${f.k}">${f.label}</label>`;
    }
    if (f.type === "date") return `<input type="date" data-k="${f.k}" title="${f.label}">`;
    if (f.type === "number") return `<input type="number" step="0.01" data-k="${f.k}" placeholder="${f.label}">`;
    return `<input type="text" data-k="${f.k}" placeholder="${f.label}">`;
  }).join("") + `<button class="primary small" data-add>添加</button>`;

  container.querySelector("[data-add]").addEventListener("click", async () => {
    const body = { project_id: Number(pid) };
    for (const f of fields) {
      const el = container.querySelector(`[data-k="${f.k}"]`);
      if (!el) continue;
      if (f.type === "checkbox") body[f.k] = el.checked ? 1 : 0;
      else if (el.value !== "") body[f.k] = el.value;
    }
    if (kind === "funding" && !body.source_type) { toast("请选择资金来源", "err"); return; }
    if (kind === "node" && !body.node_type) { toast("请选择节点类型", "err"); return; }
    await api(`/${kind === "funding" ? "fundings" : "nodes"}`, "POST", body);
    toast("已添加"); after();
  });
}

/* ---------- 项目 弹窗 ---------- */
let modalContext = null; // {kind, id}

function openProjectModal(id) {
  openModal("project", id, async (formData) => {
    if (id) await api("/projects/" + id, "PUT", formData);
    else await api("/projects", "POST", formData);
    toast(id ? "已更新" : "已新增");
    await loadProjects(); closeModal();
  });
}

async function openModal(kind, id, onSubmit) {
  modalContext = { kind, id, onSubmit };
  // 新增项目和新增企业均提供批量导入；编辑单条记录时只保留手动表单。
  const showTabs = ((kind === "project" || kind === "enterprise") && !id);
  $("#modal-tabs").classList.toggle("hidden", !showTabs);
  $("#excel-result").innerHTML = "";
  if (showTabs) switchMTab("manual");
  const data = id ? await api(`/${kind === "enterprise" ? "enterprises" : "projects"}/${id}`) : {};
  $("#modal-title").textContent = (id ? "编辑" : "新增") + (kind === "enterprise" ? "企业" : "项目");
  $("#modal-form").innerHTML = FORMS[kind].map(f => buildFieldHtml(f, data[f.k])).join("");
  $("#btn-modal-save").style.display = "";
  $("#btn-modal-cancel").textContent = "取消";
  $("#modal").classList.remove("hidden");
}

function closeModal() {
  $("#modal").classList.add("hidden");
  modalContext = null;
  $("#btn-modal-save").style.display = "";
  $("#btn-modal-save").textContent = "保存";
  $("#btn-modal-cancel").textContent = "取消";
  $("#modal-tabs").classList.add("hidden");
  $("#excel-result").innerHTML = "";
}

function switchMTab(name) {
  const manual = name === "manual";
  $$("#modal-tabs .mtab").forEach(b => b.classList.toggle("active", b.dataset.mtab === name));
  $("#mtab-manual").classList.toggle("hidden", !manual);
  $("#mtab-excel").classList.toggle("hidden", manual);
  $("#btn-modal-save").style.display = manual ? "" : "none";
  $("#btn-modal-cancel").textContent = manual ? "取消" : "关闭";
  if (name === "excel") configureExcelPanel();
}

$("#btn-modal-cancel").addEventListener("click", closeModal);
$("#btn-modal-close").addEventListener("click", closeModal);
$("#modal").addEventListener("click", e => { if (e.target === $("#modal")) closeModal(); });
$("#btn-modal-save").addEventListener("click", async () => {
  if (!modalContext) return;
  if (modalContext.kind === "export") { doExportCSV(); return; }
  const form = $("#modal-form");
  if (!form.checkValidity()) { form.reportValidity(); return; }
  const data = {};
  for (const f of FORMS[modalContext.kind]) {
    const el = form.elements[f.k];
    if (!el) continue;
    if (f.type === "checkbox") data[f.k] = el.checked ? 1 : 0;
    else if (el.value !== "") data[f.k] = el.value;
  }
  try { await modalContext.onSubmit(data); }
  catch (e) { toast(e.message, "err"); }
});

/* ---------- 企业 ---------- */
function renderEnterpriseTable() {
  const tbody = $("#enterprise-table tbody");
  const items = state.enterprisePage.items || [];
  $("#enterprise-empty").classList.toggle("hidden", items.length > 0);
  tbody.innerHTML = items.map(e => `
    <tr>
      <td>${escapeHtml(e.name)}</td>
      <td>${escapeHtml(e.credit_code || "—")}</td>
      <td>${escapeHtml(e.enterprise_type || "—")}</td>
      <td>${escapeHtml(e.district || "—")}</td>
      <td>${escapeHtml(e.qualifications || "—")}</td>
      <td class="num">${e.project_count ?? 0}</td>
      <td class="num">${fmtMoney(e.total_amount_sum)}</td>
      <td>
        <button class="small e-view" data-id="${e.id}">画像</button>
        <button class="small e-edit" data-id="${e.id}">编辑</button>
        <button class="small danger e-del" data-id="${e.id}">删除</button>
      </td>
    </tr>`).join("");
  $("#enterprise-result-bar").textContent = state.enterprisePage.total ? `共 ${state.enterprisePage.total} 家企业，第 ${state.enterprisePage.page}/${state.enterprisePage.totalPages} 页` : "暂无企业";
  renderEnterprisePagination();
}

function renderEnterprisePagination() {
  const { page, totalPages } = state.enterprisePage;
  const content = totalPages ? `<button class="small" data-page="prev" ${page <= 1 ? "disabled" : ""}>上一页</button><span>第 ${page} / ${totalPages} 页</span><button class="small" data-page="next" ${page >= totalPages ? "disabled" : ""}>下一页</button>` : "";
  ["#enterprise-pagination-top", "#enterprise-pagination"].forEach(selector => { $(selector).innerHTML = content; });
}

function openEnterpriseModal(id) {
  openModal("enterprise", id, async (formData) => {
    if (id) await api("/enterprises/" + id, "PUT", formData);
    else await api("/enterprises", "POST", formData);
    toast(id ? "已更新" : "已新增");
    await loadEnterprises(); closeModal();
  });
}

async function delEnterprise(id) {
  if (!confirm("确定删除该企业？其下项目将变为未关联企业。")) return;
  await api("/enterprises/" + id, "DELETE");
  toast("已删除"); await loadEnterprisePage();
}

async function delProject(id) {
  if (!confirm("确定删除该项目？其资金、节点记录将一并删除。")) return;
  await api("/projects/" + id, "DELETE");
  toast("已删除"); await loadProjects();
}

async function loadConfig() {
  const cfg = await api("/config");
  state.archivedYears = cfg.archived_years || [];
  state.uiTexts = cfg.ui_texts || {};
  applyUiTexts();
}

function renderUiTextConfig() {
  const container = $("#ui-text-list");
  const groups = [...new Set(UI_TEXT_CATALOG.map(item => item.group))];
  container.innerHTML = groups.map(group => `
    <section class="ui-text-group"><h3>${escapeHtml(group)}</h3>
      ${UI_TEXT_CATALOG.filter(item => item.group === group).map(item => `
        <label class="ui-text-row"><span><b>${escapeHtml(item.label)}</b><small>${escapeHtml(item.key)}</small></span>
          <input data-ui-key="${escapeHtml(item.key)}" value="${escapeHtml(textFor(item.key))}" maxlength="80">
          <em>默认：${escapeHtml(item.fallback)}</em>
        </label>`).join("")}
    </section>`).join("");
}

async function saveUiTexts() {
  const values = {};
  $$("#ui-text-list [data-ui-key]").forEach(input => {
    const key = input.dataset.uiKey;
    const item = UI_TEXT_CATALOG.find(x => x.key === key);
    const value = input.value.trim();
    if (value && value !== item.fallback) values[key] = value;
  });
  await api("/config", "PUT", { ui_texts: values });
  state.uiTexts = values;
  applyUiTexts();
  renderUiTextConfig();
  toast("界面文字已保存");
}

async function resetUiTexts() {
  await api("/config", "PUT", { ui_texts: {} });
  state.uiTexts = {};
  applyUiTexts();
  renderUiTextConfig();
  toast("已恢复默认文字");
}

/* ---------- 工作台 ---------- */
async function loadDashboard() {
  const d = await api("/dashboard");
  const cards = [
    { k: "项目总数", v: d.project_count },
    { k: "承担企业", v: d.enterprise_count },
    { k: "已拨付资金", v: fmtMoney(d.funded_total) + " 万" },
    { k: "计划拨付", v: fmtMoney(d.plan_total) + " 万" },
    { k: "逾期节点", v: d.overdue_nodes, warn: d.overdue_nodes > 0 },
    { k: "3 个月内到期", v: d.due90_nodes, warn: d.due90_nodes > 0 },
    { k: "该拨未拨", v: d.overdue_funding_count + " 笔", warn: d.overdue_funding_count > 0 },
  ];
  $("#dash-cards").innerHTML = cards.map(c => `
    <div class="dash-card ${c.warn ? "warn" : ""}">
      <div class="dc-v">${c.v}</div><div class="dc-k">${c.k}</div>
    </div>`).join("");

  // 待办节点（简版）
  const rem = await api("/reminders?days=90");
  const levelMap = { overdue: ["已逾期", "overdue"], red: ["≤7天", "red"], yellow: ["≤30天", "yellow"] };
  $("#dash-reminders").innerHTML = rem.length
    ? `<table class="sub-table"><thead><tr><th>项目</th><th>节点</th><th>计划</th><th>级别</th></tr></thead><tbody>
       ${rem.slice(0, 8).map(r => `<tr>
         <td><a href="#" class="dash-p" data-id="${r.project_id}">${escapeHtml(r.project_name)}</a></td>
         <td>${escapeHtml(r.node_type || "—")}</td>
         <td>${fmtDate(r.plan_date)}</td>
         <td><span class="badge ${levelMap[r.level] ? levelMap[r.level][1] : "later"}">${levelMap[r.level] ? levelMap[r.level][0] : "—"}</span></td>
       </tr>`).join("")}
       ${rem.length > 8 ? `<tr><td colspan="4" class="empty">…还有 ${rem.length - 8} 条，见「⏰ 提醒」页</td></tr>` : ""}
       </tbody></table>`
    : `<div class="empty">3 个月内没有到期节点</div>`;
  $("#dash-reminders").querySelectorAll(".dash-p").forEach(a => a.addEventListener("click", e => { e.preventDefault(); gotoProject(a.dataset.id); }));

  // 资金待办（该拨未拨）
  const plan = await api("/funding-plan");
  const over = plan.items.filter(x => x.is_overdue);
  $("#dash-funding").innerHTML = over.length
    ? `<table class="sub-table"><thead><tr><th>项目</th><th>来源</th><th>金额(万)</th><th>应拨</th></tr></thead><tbody>
       ${over.slice(0, 8).map(f => `<tr>
         <td><a href="#" class="dash-p" data-id="${f.project_id}">${escapeHtml(f.project_name)}</a></td>
         <td>${escapeHtml(f.source_type || "—")}</td>
         <td class="num">${fmtMoney(f.amount)}</td>
         <td>${fmtDate(f.plan_date)}</td>
       </tr>`).join("")}
       ${over.length > 8 ? `<tr><td colspan="4" class="empty">…还有 ${over.length - 8} 笔</td></tr>` : ""}
       </tbody></table>
       <div class="fund-check warn" style="margin-top:6px">共 ${over.length} 笔、${fmtMoney(plan.summary.overdue_amount)} 万元该拨未拨；拨付执行率 ${(plan.summary.execution_rate * 100).toFixed(1)}%</div>`
    : `<div class="empty">✅ 没有该拨未拨的资金</div>`;
  $("#dash-funding").querySelectorAll(".dash-p").forEach(a => a.addEventListener("click", e => { e.preventDefault(); gotoProject(a.dataset.id); }));
}

function gotoProject(id) {
  $$(".tab-btn").forEach(b => b.classList.remove("active"));
  $('.tab-btn[data-tab="projects"]').classList.add("active");
  $$(".tab").forEach(t => t.classList.remove("active"));
  $("#tab-projects").classList.add("active");
  showProjectDetail(id);
}

// 工作台固定入口不依赖卡片悬停，键盘亦可直接触发。
$("#btn-hero-project").addEventListener("click", () => openProjectModal());
$("#btn-hero-refresh").addEventListener("click", async () => {
  try { await loadDashboard(); toast("工作台数据已刷新"); }
  catch (e) { toast("刷新失败：" + e.message, "err"); }
});

/* ---------- 提醒 ---------- */
async function loadReminders() {
  const days = $("#rm-days").value;
  const list = await api("/reminders?days=" + days);
  const tbody = $("#reminder-table tbody");
  $("#reminder-empty").classList.toggle("hidden", list.length > 0);
  const levelMap = {
    overdue: ["已逾期", "overdue"], red: ["≤7天", "red"], yellow: ["≤30天", "yellow"], later: ["30天外", "later"]
  };
  tbody.innerHTML = list.map(r => {
    const [label, cls] = levelMap[r.level] || ["", "later"];
    return `<tr>
      <td><span class="badge ${cls}">${label}</span></td>
      <td><a href="#" class="rm-p" data-id="${r.project_id}">${escapeHtml(r.project_name)}</a></td>
      <td>${escapeHtml(r.project_level || "—")}</td>
      <td>${escapeHtml(r.node_type || "—")}</td>
      <td>${fmtDate(r.plan_date)}</td>
      <td class="num">${r.days_left == null ? "—" : Math.ceil(r.days_left)}</td>
      <td>${escapeHtml(r.status || "—")}</td>
      <td><button class="small rm-done" data-id="${r.id}">标记完成</button></td>
    </tr>`;
  }).join("");
  tbody.querySelectorAll(".rm-p").forEach(a => a.addEventListener("click", e => {
    e.preventDefault();
    $$(".tab-btn").forEach(b => b.classList.remove("active"));
    $('.tab-btn[data-tab="projects"]').classList.add("active");
    $$(".tab").forEach(t => t.classList.remove("active"));
    $("#tab-projects").classList.add("active");
    showProjectDetail(a.dataset.id);
  }));
  tbody.querySelectorAll(".rm-done").forEach(b => b.addEventListener("click", async () => {
    if (!confirm("标记该节点为已完成？")) return;
    await api("/nodes/" + b.dataset.id, "PUT", { status: "已完成", actual_date: new Date().toISOString().slice(0, 10) });
    toast("已标记完成"); loadReminders();
  }));
}

/* ---------- 统计 ---------- */
let currentStats = [];
async function loadStats() {
  const by = $("#st-by").value;
  currentStats = await api("/stats?by=" + by);
  const tbody = $("#stats-table tbody");
  $("#stats-empty").classList.toggle("hidden", currentStats.length > 0);
  tbody.innerHTML = currentStats.map(s => `
    <tr><td>${escapeHtml(s.key)}</td><td class="num">${s.count}</td><td class="num">${fmtMoney(s.amount)}</td></tr>`).join("");
}
function exportCSV() {
  if (!currentStats.length) { toast("暂无数据可导出", "err"); return; }
  const head = "维度,项目数,金额合计(万元)\n";
  const body = currentStats.map(s => `${s.key},${s.count},${s.amount}`).join("\n");
  const blob = new Blob(["\ufeff" + head + body], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "资金统计报表_" + new Date().toISOString().slice(0, 10) + ".csv";
  a.click();
  URL.revokeObjectURL(a.href);
}

/* ---------- 企业画像 ---------- */
async function openEnterpriseDetail(id) {
  const e = await api("/enterprises/" + id);
  $("#modal-title").textContent = "企业画像：" + e.name;
  const total = (e.projects || []).reduce((s, p) => s + (p.total_amount || 0), 0);
  $("#modal-form").innerHTML = `
    <div class="detail-grid" style="grid-column:1/-1">
      ${kv("统一信用代码", e.credit_code)}${kv("企业类型", e.enterprise_type)}${kv("区镇", e.district)}
      ${kv("资质", e.qualifications)}${kv("联系人", (e.contact_person || "") + " " + (e.contact_phone || ""))}
      ${kv("承担项目数", (e.projects || []).length + " 个")}${kv("累计金额", fmtMoney(total) + " 万元")}
    </div>
    <div class="sub-title" style="grid-column:1/-1">承担项目</div>
    <div style="grid-column:1/-1">
      <table class="sub-table">
        <thead><tr><th>项目</th><th>层级</th><th>类型</th><th>总金额(万)</th><th>阶段</th></tr></thead>
        <tbody>${(e.projects || []).map(p => `<tr>
          <td>${escapeHtml(p.name)}</td><td>${escapeHtml(p.level || "—")}</td><td>${escapeHtml(p.category || "—")}</td>
          <td class="num">${fmtMoney(p.total_amount)}</td><td>${stageBadge(p.stage)}</td></tr>`).join("")
          || `<tr><td colspan="5" class="empty">暂无承担项目</td></tr>`}
        </tbody>
      </table>
    </div>`;
  $("#btn-modal-save").style.display = "none";
  $("#btn-modal-cancel").textContent = "关闭";
  $("#modal").classList.remove("hidden");
}

/* ---------- 配置管理（自助增/停用） ---------- */
async function renderDict() {
  const types = await api("/dict/types");
  const titles = { level: "层级", category: "类型", funding_source: "资金来源", node_type: "节点类型", district: "区镇", enterprise_type: "企业类型" };
  let html = "";
  for (const t of types) {
    const items = await api("/dict?type=" + t + "&all=1");
    const activeItems = items.filter(x => x.is_active);
    const inactiveItems = items.filter(x => !x.is_active);
    html += `<div class="dict-group">
      <h4>${titles[t] || t}</h4>
      <div class="dict-tags dict-sortable" data-type="${t}">
        ${activeItems.map(x => `<span class="dict-item" draggable="true" data-id="${x.id}" title="拖动调整顺序"><b class="drag-grip">⋮⋮</b>${escapeHtml(x.value)}
          <button class="small d-off" data-id="${x.id}">停用</button></span>`).join("")}
        ${inactiveItems.length ? `<details class="dict-inactive"><summary>已停用 ${inactiveItems.length} 项（展开）</summary><div class="dict-tags">${inactiveItems.map(x => `<span class="off dict-item">${escapeHtml(x.value)}（停用）<button class="small d-on" data-id="${x.id}">启用</button></span>`).join("")}</div></details>` : ""}
        <span class="dict-add"><input data-new-val placeholder="新增取值"><button class="small primary d-add" data-type="${t}">新增</button></span>
      </div>
    </div>`;
  }
  // 年度归档冻结
  const cfg = await api("/config");
  const years = cfg.archived_years || [];
  html += `<div class="dict-group"><h4>📦 年度归档冻结</h4>
    <div class="dict-tags">
      ${years.map(y => `<span>${y} 年<button class="small a-del" data-y="${y}">解除</button></span>`).join("") || `<span class="off">未归档任何年度</span>`}
      <span class="dict-add"><input data-arch-year placeholder="年份，如 2024"><button class="small primary a-add">归档</button></span>
    </div>
    <div style="font-size:12px;color:var(--muted);margin-top:6px">归档后该年度项目及其资金/节点只能查看、禁止修改；需改动时先「解除」。</div>
  </div>`;
  $("#dict-view").innerHTML = html;
  $("#dict-view").querySelectorAll(".d-off").forEach(b => b.addEventListener("click", async () => {
    if (!confirm("停用该取值？历史数据不受影响。")) return;
    await api("/dict/" + b.dataset.id, "DELETE");
    toast("已停用"); renderDict(); loadDict();
  }));
  $("#dict-view").querySelectorAll(".d-on").forEach(b => b.addEventListener("click", async () => {
    await api("/dict/" + b.dataset.id, "PUT", { is_active: 1 });
    toast("已启用"); renderDict(); loadDict();
  }));
  // HTML5 原生拖拽排序：只保存顺序，不改动取值内容和历史业务数据。
  $("#dict-view").querySelectorAll(".dict-sortable").forEach(list => {
    let dragging = null;
    list.querySelectorAll(".dict-item").forEach(item => {
      item.addEventListener("dragstart", event => { event.stopPropagation(); dictionaryDragging = true; dragging = item; item.classList.add("dragging"); });
      item.addEventListener("dragend", event => { event.stopPropagation(); dictionaryDragging = false; item.classList.remove("dragging"); dragging = null; });
      item.addEventListener("dragover", event => {
        event.stopPropagation();
        event.preventDefault();
        if (!dragging || dragging === item) return;
        const box = item.getBoundingClientRect();
        list.insertBefore(dragging, event.clientY < box.top + box.height / 2 ? item : item.nextSibling);
      });
    });
    list.addEventListener("drop", async () => {
      const ordered = Array.from(list.querySelectorAll(":scope > .dict-item"));
      for (const [index, item] of ordered.entries()) await api("/dict/" + item.dataset.id, "PUT", { sort_order: index + 1 });
      toast("顺序已保存");
    });
  });
  $("#dict-view").querySelectorAll(".d-add").forEach(b => b.addEventListener("click", async () => {
    const input = b.parentElement.querySelector("input");
    const val = (input.value || "").trim();
    if (!val) { toast("请输入取值", "err"); return; }
    try {
      await api("/dict", "POST", { dict_type: b.dataset.type, value: val });
      toast("已新增"); renderDict(); loadDict();
    } catch (e) { toast(e.message, "err"); }
  }));
  // 年度归档：归档/解除
  $("#dict-view").querySelectorAll(".a-add").forEach(b => b.addEventListener("click", async () => {
    const input = b.parentElement.querySelector("input");
    const y = (input.value || "").trim();
    if (!/^\d{4}$/.test(y)) { toast("请输入 4 位年份", "err"); return; }
    const cur = (await api("/config")).archived_years || [];
    if (cur.includes(y)) { toast("该年度已归档", "err"); return; }
    await api("/config", "PUT", { archived_years: [...cur, y].sort() });
    state.archivedYears = [...cur, y].sort();
    toast("已归档 " + y + " 年"); renderDict(); loadProjects();
  }));
  $("#dict-view").querySelectorAll(".a-del").forEach(b => b.addEventListener("click", async () => {
    const cur = (await api("/config")).archived_years || [];
    const next = cur.filter(x => x !== b.dataset.y);
    await api("/config", "PUT", { archived_years: next });
    state.archivedYears = next;
    toast("已解除归档"); renderDict(); loadProjects();
  }));
}

/* ---------- 高级筛选 ---------- */
const ADV_FIELDS = [
  { v: "name", l: "项目名称" }, { v: "project_no", l: "项目编号" },
  { v: "level", l: "层级" }, { v: "category", l: "类型" }, { v: "stage", l: "阶段" },
  { v: "enterprise_name", l: "承担企业" }, { v: "district", l: "区镇" },
  { v: "total_amount", l: "总金额(万元)" }, { v: "match_ratio", l: "配套比例" },
  { v: "start_date", l: "开始日期" }, { v: "end_date", l: "结束日期" },
  { v: "leader", l: "负责人" }, { v: "contact_phone", l: "联系人手机" },
];
const ADV_OPS = [
  { v: "eq", l: "等于" }, { v: "contains", l: "包含" },
  { v: "gte", l: "大于等于" }, { v: "lte", l: "小于等于" },
];
const ENTERPRISE_ADV_FIELDS = [
  { v: "name", l: "企业名称" }, { v: "credit_code", l: "统一信用代码" },
  { v: "enterprise_type", l: "企业类型" }, { v: "district", l: "区镇" },
  { v: "qualifications", l: "资质" }, { v: "contact_person", l: "联系人" },
  { v: "contact_phone", l: "联系电话" }, { v: "address", l: "地址" },
  { v: "project_count", l: "项目数" }, { v: "total_amount_sum", l: "累计金额(万元)" },
];

function addAdvRow(presetField, presetOp, presetVal) {
  const row = document.createElement("div");
  row.className = "adv-row";
  row.innerHTML = `
    <select class="af-field">${ADV_FIELDS.map(f => `<option value="${f.v}"${f.v === presetField ? " selected" : ""}>${f.l}</option>`).join("")}</select>
    <select class="af-op">${ADV_OPS.map(o => `<option value="${o.v}"${o.v === presetOp ? " selected" : ""}>${o.l}</option>`).join("")}</select>
    <input class="af-val" type="text" placeholder="条件值" value="${escapeHtml(presetVal || "")}">
    <button class="small danger af-del">删除</button>`;
  row.querySelector(".af-del").addEventListener("click", () => row.remove());
  $("#adv-rows").appendChild(row);
}

function collectAdvFilters() {
  const out = [];
  document.querySelectorAll("#adv-rows .adv-row").forEach(row => {
    const field = row.querySelector(".af-field").value;
    const op = row.querySelector(".af-op").value;
    const val = row.querySelector(".af-val").value.trim();
    if (field && op && val) out.push({ field, op, value: val });
  });
  return out;
}

function addEnterpriseAdvRow(presetField, presetOp, presetVal) {
  const row = document.createElement("div");
  row.className = "adv-row";
  row.innerHTML = `
    <select class="af-field">${ENTERPRISE_ADV_FIELDS.map(f => `<option value="${f.v}"${f.v === presetField ? " selected" : ""}>${f.l}</option>`).join("")}</select>
    <select class="af-op">${ADV_OPS.map(o => `<option value="${o.v}"${o.v === presetOp ? " selected" : ""}>${o.l}</option>`).join("")}</select>
    <input class="af-val" type="text" placeholder="条件值" value="${escapeHtml(presetVal || "")}">
    <button class="small danger af-del">删除</button>`;
  row.querySelector(".af-del").addEventListener("click", () => row.remove());
  $("#enterprise-adv-rows").appendChild(row);
}

function collectEnterpriseAdvFilters() {
  return $$("#enterprise-adv-rows .adv-row").map(row => ({
    field: row.querySelector(".af-field").value,
    op: row.querySelector(".af-op").value,
    value: row.querySelector(".af-val").value.trim(),
  })).filter(item => item.field && item.op && item.value);
}

/* ---------- Excel 批量导入（新增项目、企业共用弹窗） ---------- */
function activeImportKind() {
  return modalContext && modalContext.kind === "enterprise" ? "enterprise" : "project";
}

function configureExcelPanel() {
  const enterprise = activeImportKind() === "enterprise";
  $("#btn-modal-template").textContent = enterprise
    ? "📄 下载企业导入模板"
    : "📄 下载模板（一张表，自动归仓）";
  $("#drop-zone-sub").textContent = enterprise
    ? "每行一家企业，上传后先预览再确认入库（.xlsx）"
    : "一张总表包含企业与项目所有字段，系统自动拆分归仓（.xlsx）";
}

async function importFile(file) {
  if (!/\.xlsx?$/i.test(file.name)) { toast("请选择 .xlsx 文件", "err"); return; }
  const importKind = activeImportKind();
  const reader = new FileReader();
  reader.onload = async () => {
    const b64 = reader.result.split(",")[1];
    try {
      const endpoint = importKind === "enterprise" ? "/enterprise-import" : "/import";
      const res = await api(endpoint, "POST", { filename: file.name, data: b64 });
      showExcelTab(importKind);
      if (importKind === "enterprise") renderEnterpriseImportPreview(res, file.name);
      else {
        renderExcelResult(res, file.name);
        await loadProjects();
        await loadEnterprises();
      }
    } catch (err) {
      toast("导入失败：" + err.message, "err");
    }
  };
  reader.readAsDataURL(file);
}

// 打开弹窗并切到当前业务对象的「Excel 批量导入」标签。
function showExcelTab(kind = activeImportKind()) {
  $("#modal-tabs").classList.remove("hidden");
  $$("#modal-tabs .mtab").forEach(b => b.classList.toggle("active", b.dataset.mtab === "excel"));
  $("#mtab-manual").classList.add("hidden");
  $("#mtab-excel").classList.remove("hidden");
  $("#modal-title").textContent = kind === "enterprise" ? "新增企业" : "新增项目";
  $("#btn-modal-save").style.display = "none";
  $("#btn-modal-cancel").textContent = "关闭";
  $("#modal").classList.remove("hidden");
  configureExcelPanel();
}

function renderEnterpriseImportPreview(res, filename) {
  const preview = res.preview || { rows: [], summary: { new_enterprise: 0, blocking: 0 } };
  const summary = preview.summary;
  const statusLabel = {
    new_enterprise: "可导入",
    duplicate: "重复企业",
    missing_identity: "缺少必填项",
    field_error: "字段不匹配",
  };
  $("#excel-result").innerHTML = `
    <div class="sub-title">导入预览：${escapeHtml(filename)}</div>
    <div class="fund-check ${summary.blocking ? "warn" : "ok"}">
      <b>可新增 ${summary.new_enterprise} 家　|　需处理 ${summary.blocking} 行</b>
    </div>
    <table class="sub-table"><thead><tr><th>行号</th><th>结论</th><th>说明</th></tr></thead><tbody>
      ${preview.rows.map(row => `<tr><td class="num">${row.row_no + 1}</td><td>${statusLabel[row.conclusion] || row.conclusion}</td><td>${escapeHtml(row.error || "检查通过")}</td></tr>`).join("")}
    </tbody></table>
    ${summary.blocking
      ? `<div class="notice">请按说明修改 Excel 后重新上传。存在阻断项时不会写入任何企业。</div>`
      : `<div class="modal-actions"><button id="btn-confirm-enterprise-import" class="primary">确认导入 ${summary.new_enterprise} 家企业</button></div>`}
  `;
  const confirmButton = $("#btn-confirm-enterprise-import");
  if (confirmButton) confirmButton.addEventListener("click", async () => {
    try {
      const result = await api(`/enterprise-import/${res.id}/confirm`, "POST");
      $("#excel-result").innerHTML = `<div class="sub-title">导入完成</div><div class="fund-check ok"><b>已新增 ${result.enterprise_count} 家企业</b></div>`;
      await loadEnterprises();
      toast(`已导入 ${result.enterprise_count} 家企业`);
    } catch (error) {
      toast("确认导入失败：" + error.message, "err");
    }
  });
}

// 渲染导入结果到 excel 标签
function renderExcelResult(res, filename) {
  const ent = res.enterprise || { ok: 0, errors: [] };
  const proj = res.project || { ok: 0, errors: [] };
  const fails = [
    ...ent.errors.map(x => ({ sheet: "企业", ...x })),
    ...proj.errors.map(x => ({ sheet: "项目", ...x })),
  ];
  $("#excel-result").innerHTML = `
    <div class="sub-title">导入结果：${escapeHtml(filename)}</div>
    <div class="fund-check ${fails.length ? "warn" : "ok"}">
      <b>企业：成功 ${ent.ok} / 失败 ${ent.errors.length}　|　项目：成功 ${proj.ok} / 失败 ${proj.errors.length}</b>
    </div>
    ${fails.length
      ? `<table class="sub-table"><thead><tr><th>表</th><th>行号</th><th>原因</th></tr></thead><tbody>
         ${fails.map(f => `<tr><td>${f.sheet}</td><td class="num">${f.row}</td><td>${escapeHtml(f.reason)}</td></tr>`).join("")}
         </tbody></table>
         <div class="notice" style="margin-top:8px">提示：失败的企业行修正后重新导入；项目行若提示企业不存在，请先导入企业。修正后可重新拖入同一文件。</div>`
      : `<div class="sub-title">全部导入成功 ✅</div>`}
  `;
}

// 弹窗内：下载模板 + 拖放区域 + 文件选择 + 标签切换
$("#btn-modal-template").addEventListener("click", () => {
  window.location.href = activeImportKind() === "enterprise" ? "/api/enterprise-template" : "/api/template";
});
const dz = $("#drop-zone");
dz.addEventListener("click", () => $("#file-import2").click());
dz.addEventListener("dragover", e => { e.preventDefault(); dz.classList.add("over"); });
dz.addEventListener("dragleave", () => dz.classList.remove("over"));
dz.addEventListener("drop", e => {
  e.preventDefault();
  dz.classList.remove("over");
  const f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
  if (f) importFile(f);
});
$("#file-import2").addEventListener("change", (e) => {
  const f = e.target.files[0];
  if (f) importFile(f);
  e.target.value = "";
});
$$("#modal-tabs .mtab").forEach(b => b.addEventListener("click", () => switchMTab(b.dataset.mtab)));

// 整页拖拽导入（任何页面都可拖入，统一走弹窗展示结果）
let dragDepth = 0;
let dictionaryDragging = false;
["dragenter", "dragover"].forEach(evt => {
  document.addEventListener(evt, e => {
    if (dictionaryDragging || e.target.closest(".dict-item") || !e.dataTransfer?.types?.includes("Files")) return;
    e.preventDefault();
    dragDepth++;
    document.body.classList.add("dragging");
  });
});
["dragleave", "drop"].forEach(evt => {
  document.addEventListener(evt, e => {
    if (dictionaryDragging || e.target.closest(".dict-item")) return;
    e.preventDefault();
    dragDepth--;
    if (dragDepth <= 0) { dragDepth = 0; document.body.classList.remove("dragging"); }
  });
});
document.addEventListener("drop", e => {
  if (dictionaryDragging || e.target.closest(".dict-item")) return;
  e.preventDefault();
  dragDepth = 0;
  document.body.classList.remove("dragging");
  const file = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
  if (file) importFile(file);
});

/* ---------- 导出当前结果（自定义字段） ---------- */
const EXPORT_FIELDS = [
  { k: "name", l: "项目名称" }, { k: "project_no", l: "项目编号/文号" },
  { k: "level", l: "层级" }, { k: "category", l: "类型" },
  { k: "enterprise_name", l: "承担企业" }, { k: "enterprise_district", l: "区镇" },
  { k: "total_amount", l: "总金额(万元)" }, { k: "disbursed_total", l: "已拨付(万元)" },
  { k: "stage", l: "阶段" }, { k: "leader", l: "负责人" },
  { k: "contact_phone", l: "联系人手机" },
  { k: "start_date", l: "开始日期" }, { k: "end_date", l: "结束日期" },
  { k: "match_ratio", l: "配套比例" }, { k: "note", l: "备注" },
];

function exportCurrent() {
  const list = state.lastProjects || [];
  if (!list.length) { toast("当前没有可导出的结果", "err"); return; }
  modalContext = { kind: "export", id: null, onSubmit: null };
  $("#modal-title").textContent = `导出当前结果（${list.length} 条）`;
  $("#modal-tabs").classList.add("hidden");
  $("#mtab-manual").classList.remove("hidden");
  $("#mtab-excel").classList.add("hidden");
  $("#modal-form").innerHTML = `
    <div style="grid-column:1/-1" class="export-fields">
      <div style="margin-bottom:8px;color:var(--muted);font-size:12px">勾选要导出的列（默认全选）：</div>
      ${EXPORT_FIELDS.map(f => `<label class="ef"><input type="checkbox" data-k="${f.k}" checked> ${f.l}</label>`).join("")}
    </div>`;
  $("#btn-modal-save").style.display = "";
  $("#btn-modal-save").textContent = "导出 CSV";
  $("#btn-modal-cancel").textContent = "取消";
  $("#modal").classList.remove("hidden");
}

function doExportCSV() {
  const checked = [];
  document.querySelectorAll(".ef input:checked").forEach(el => checked.push(el.dataset.k));
  if (!checked.length) { toast("请至少勾选一列", "err"); return; }
  const list = state.lastProjects || [];
  const head = checked.map(k => { const f = EXPORT_FIELDS.find(x => x.k === k); return f ? f.l : k; });
  const esc = v => {
    const s = v == null ? "" : String(v);
    return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  };
  const lines = [head.join(","), ...list.map(p => checked.map(k => esc(p[k])).join(","))];
  const blob = new Blob(["\ufeff" + lines.join("\n")], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "查询结果_" + new Date().toISOString().slice(0, 10) + ".csv";
  a.click();
  URL.revokeObjectURL(a.href);
  closeModal();
  toast(`已导出 ${list.length} 条结果`);
}

/* ---------- 事件绑定 ---------- */
$("#btn-search").addEventListener("click", () => {
  state.filters = {
    level: $("#flt-level").value, category: $("#flt-category").value,
    stage: $("#flt-stage").value, district: $("#flt-district").value,
    q: $("#flt-q").value.trim(), advFilters: collectAdvFilters(),
  };
  state.projectPage.page = 1;
  loadProjects();
});
$("#project-page-size").addEventListener("change", async event => {
  state.projectPage.pageSize = Number(event.target.value);
  state.projectPage.page = 1;
  await loadProjects();
});
["flt-level", "flt-category", "flt-stage", "flt-district"].forEach(id => {
  $("#" + id).addEventListener("change", () => $("#btn-search").click());
});
$("#flt-q").addEventListener("keydown", e => { if (e.key === "Enter") $("#btn-search").click(); });

$("#btn-adv").addEventListener("click", () => {
  const panel = $("#adv-panel");
  panel.classList.toggle("hidden");
  if (!panel.classList.contains("hidden") && !$("#adv-rows").children.length) addAdvRow();
});
$("#btn-adv-add").addEventListener("click", () => addAdvRow());
$("#btn-adv-clear").addEventListener("click", () => { $("#adv-rows").innerHTML = ""; addAdvRow(); });

$("#btn-add-project").addEventListener("click", () => openProjectModal(null));
$("#btn-add-enterprise").addEventListener("click", () => openEnterpriseModal(null));
$("#btn-export-current").addEventListener("click", exportCurrent);

$("#project-table tbody").addEventListener("click", event => {
  const button = event.target.closest("[data-id]");
  if (!button) return;
  if (button.matches(".p-name, .p-view")) { event.preventDefault(); showProjectDetail(button.dataset.id); }
  else if (button.classList.contains("p-edit")) openProjectModal(button.dataset.id);
  else if (button.classList.contains("p-del")) delProject(button.dataset.id);
});
$("#project-pagination").addEventListener("click", async event => {
  const button = event.target.closest("button[data-page]");
  if (!button || button.disabled) return;
  state.projectPage.page += button.dataset.page === "next" ? 1 : -1;
  await loadProjects();
});

// 企业表只在 tbody 上绑定一次事件，分页换页不会为每一行重复创建监听器。
$("#enterprise-table tbody").addEventListener("click", event => {
  const button = event.target.closest("button[data-id]");
  if (!button) return;
  if (button.classList.contains("e-view")) openEnterpriseDetail(button.dataset.id);
  else if (button.classList.contains("e-edit")) openEnterpriseModal(button.dataset.id);
  else if (button.classList.contains("e-del")) delEnterprise(button.dataset.id);
});
$$("#enterprise-pagination-top, #enterprise-pagination").forEach(container => container.addEventListener("click", async event => {
  const button = event.target.closest("button[data-page]");
  if (!button || button.disabled) return;
  state.enterprisePage.page += button.dataset.page === "next" ? 1 : -1;
  await loadEnterprisePage();
  $("#enterprise-table").scrollIntoView({ behavior: "smooth", block: "start" });
}));
$("#btn-enterprise-search").addEventListener("click", async () => {
  state.enterprisePage.q = $("#enterprise-q").value.trim();
  state.enterprisePage.advFilters = collectEnterpriseAdvFilters();
  state.enterprisePage.page = 1;
  await loadEnterprisePage();
  trackUsage("企业", "搜索");
});
$("#btn-enterprise-adv").addEventListener("click", () => {
  const panel = $("#enterprise-adv-panel");
  panel.classList.toggle("hidden");
  if (!panel.classList.contains("hidden") && !$("#enterprise-adv-rows").children.length) addEnterpriseAdvRow();
});
$("#btn-enterprise-adv-add").addEventListener("click", () => addEnterpriseAdvRow());
$("#btn-enterprise-adv-clear").addEventListener("click", () => { $("#enterprise-adv-rows").innerHTML = ""; addEnterpriseAdvRow(); });
$("#enterprise-q").addEventListener("keydown", event => {
  if (event.key === "Enter") $("#btn-enterprise-search").click();
});
$("#enterprise-page-size").addEventListener("change", async event => {
  state.enterprisePage.pageSize = Number(event.target.value);
  state.enterprisePage.page = 1;
  await loadEnterprisePage();
});
$("#enterprise-table thead").addEventListener("click", async event => {
  const button = event.target.closest(".enterprise-sort");
  if (!button) return;
  const field = button.dataset.sort;
  const p = state.enterprisePage;
  p.direction = p.sort === field && p.direction === "asc" ? "desc" : "asc";
  p.sort = field;
  p.page = 1;
  await loadEnterprisePage();
  trackUsage("企业", "字段排序");
});

$$("#project-table .project-sort").forEach(button => button.addEventListener("click", () => {
  const field = button.dataset.sort;
  const current = state.projectSort;
  state.projectSort = current && current.field === field
    ? { field, direction: current.direction === "asc" ? "desc" : "asc" }
    : { field, direction: "asc" };
  state.projectPage.sort = field;
  state.projectPage.direction = state.projectSort.direction;
  state.projectPage.page = 1;
  loadProjects();
  trackUsage("项目总览", "字段排序");
}));

$("#btn-st-export").addEventListener("click", exportCSV);
$("#st-by").addEventListener("change", loadStats);
$("#rm-days").addEventListener("change", loadReminders);
$("#btn-rm-refresh").addEventListener("click", loadReminders);
$("#btn-rm-export").addEventListener("click", () => {
  window.location.href = "/api/export?resource=reminders&days=" + encodeURIComponent($("#rm-days").value);
  trackUsage("提醒", "导出当前结果");
});
$("#btn-enterprise-export").addEventListener("click", () => {
  const params = new URLSearchParams({ resource: "enterprises", q: state.enterprisePage.q || "" });
  if (state.enterprisePage.advFilters?.length) params.set("filters", JSON.stringify(state.enterprisePage.advFilters));
  window.location.href = "/api/export?" + params.toString();
  trackUsage("企业", "导出当前结果");
});
$("#btn-usage-refresh").addEventListener("click", loadUsage);
$("#btn-ui-text-save").addEventListener("click", saveUiTexts);
$("#btn-ui-text-reset").addEventListener("click", resetUiTexts);
$("#btn-check-update").addEventListener("click", async () => {
  closeSettingsMenu();
  try { const result = await checkForUpdate(true); if (!result.configured) toast(result.error || "更新检查未完成", "err"); else if (!result.available) toast("当前已是最新版本"); }
  catch (error) { toast(error.message, "err"); }
});

$("#auth-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const username = $("#auth-username").value.trim();
  const password = $("#auth-password").value;
  try {
    await api("/auth/login", "POST", { username, password });
    $("#auth-password").value = "";
    hideLogin();
    await loadWorkspace();
  } catch (e) {
    $("#auth-error").textContent = e.message || "登录失败，请检查账号和密码。";
    $("#auth-error").classList.remove("hidden");
    $("#auth-password").focus();
  }
});

/* 使用助手中的配置复制：不依赖剪贴板权限时仍给出明确提示。 */
document.querySelectorAll(".copy-btn").forEach(button => {
  button.addEventListener("click", async () => {
    const target = document.getElementById(button.dataset.copyTarget);
    if (!target) return;
    try {
      await navigator.clipboard.writeText(target.textContent);
      button.textContent = "已复制";
      setTimeout(() => { button.textContent = "复制"; }, 1600);
    } catch (e) {
      toast("浏览器未允许复制，请手动选中配置", "err");
    }
  });
});

/* ---------- 初始化 ---------- */
async function loadWorkspace() {
  await loadDict();
  await loadConfig();
  await loadEnterprises();
  await loadProjects();
  renderDict();
  await loadDashboard();
  checkForUpdate();
}

(async function init() {
  try {
    await loadWorkspace();
  } catch (e) {
    if (e.status !== 401) toast("加载失败：" + e.message, "err");
  }
})();

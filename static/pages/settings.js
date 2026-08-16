/** 设置页面：配置、界面文字、使用分析和版本更新集中在此模块。 */
import { STAGES } from "../core/constants.js";
import { $, $$, escapeHtml } from "../core/dom.js";
import { renderSelectOptions } from "../components/filters.js";

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

export function createSettingsPage(context) {
  const { api, state, toast, setPageStatus, onDictChanged, loadProjects } = context;
  const textFor = key => state.getState().uiTexts?.[key] ?? UI_TEXT_CATALOG.find(item => item.key === key)?.fallback ?? key;

  function applyUiTexts() { UI_TEXT_CATALOG.forEach(item => { const element = document.querySelector(item.selector); if (element) element.textContent = textFor(item.key); }); }

  async function loadDict() {
    const dict = await api.get("/dict");
    state.setState(current => ({ ...current, dict }));
    renderSelectOptions($("#flt-level"), dict.level || [], { placeholder: "全部层级" });
    renderSelectOptions($("#flt-category"), dict.category || [], { placeholder: "全部类型" });
    renderSelectOptions($("#flt-stage"), STAGES, { placeholder: "全部阶段" });
    renderSelectOptions($("#flt-district"), dict.district || [], { placeholder: "全部区镇" });
    return dict;
  }

  async function loadConfig() {
    const config = await api.get("/config");
    state.setState(current => ({ ...current, archivedYears: config.archived_years || [], uiTexts: config.ui_texts || {} }));
    applyUiTexts();
    return config;
  }

  async function loadUsage() {
    setPageStatus?.("usage", "loading", { error: null });
    try {
      const data = await api.get("/usage");
      const render = (items, selector) => { const element = $(selector); if (!items.length) { element.innerHTML = '<div class="usage-empty">还没有使用记录</div>'; return; } const max = Math.max(...items.map(item => item.count)); element.innerHTML = items.map(item => `<div class="usage-row"><span title="${escapeHtml(item.name)}">${escapeHtml(item.name)}</span><span class="bar"><i style="width:${Math.max(2, item.count / max * 100)}%"></i></span><b>${item.count}</b></div>`).join(""); };
      render(data.modules || [], "#usage-modules"); render(data.actions || [], "#usage-actions");
      setPageStatus?.("usage", "ready", { data, error: null });
    } catch (error) { setPageStatus?.("usage", "error", { data: [], error: error.message }); toast(error.message, "err"); }
  }

  function renderUiTextConfig() {
    const container = $("#ui-text-list");
    const groups = [...new Set(UI_TEXT_CATALOG.map(item => item.group))];
    container.innerHTML = groups.map(group => `<section class="ui-text-group"><h3>${escapeHtml(group)}</h3>${UI_TEXT_CATALOG.filter(item => item.group === group).map(item => `<label class="ui-text-row"><span><b>${escapeHtml(item.label)}</b><small>${escapeHtml(item.key)}</small></span><input data-ui-key="${escapeHtml(item.key)}" value="${escapeHtml(textFor(item.key))}" maxlength="80"><em>默认：${escapeHtml(item.fallback)}</em></label>`).join("")}</section>`).join("");
  }

  async function saveUiTexts() {
    const values = {};
    $$("#ui-text-list [data-ui-key]").forEach(input => { const item = UI_TEXT_CATALOG.find(candidate => candidate.key === input.dataset.uiKey); const value = input.value.trim(); if (value && value !== item.fallback) values[item.key] = value; });
    await api.put("/config", { ui_texts: values }); state.setState(current => ({ ...current, uiTexts: values })); applyUiTexts(); renderUiTextConfig(); toast("界面文字已保存");
  }

  async function resetUiTexts() { await api.put("/config", { ui_texts: {} }); state.setState(current => ({ ...current, uiTexts: {} })); applyUiTexts(); renderUiTextConfig(); toast("已恢复默认文字"); }

  async function renderDict() {
    const types = await api.get("/dict/types");
    const titles = { level: "层级", category: "类型", funding_source: "资金来源", node_type: "节点类型", district: "区镇", enterprise_type: "企业类型" };
    const groups = await Promise.all(types.map(async type => ({ type, items: await api.get("/dict?type=" + type + "&all=1") })));
    const config = await api.get("/config"); state.setState(current => ({ ...current, archivedYears: config.archived_years || [] }));
    $("#dict-view").innerHTML = groups.map(group => { const active = group.items.filter(item => item.is_active), inactive = group.items.filter(item => !item.is_active); return `<div class="dict-group"><h4>${titles[group.type] || group.type}</h4><div class="dict-tags dict-sortable" data-type="${group.type}">${active.map(item => `<span class="dict-item" draggable="true" data-id="${item.id}"><b class="drag-grip">⋮⋮</b>${escapeHtml(item.value)} <button class="small d-off" data-id="${item.id}">停用</button></span>`).join("")}${inactive.length ? `<details class="dict-inactive"><summary>已停用 ${inactive.length} 项（展开）</summary><div class="dict-tags">${inactive.map(item => `<span class="off dict-item">${escapeHtml(item.value)}（停用）<button class="small d-on" data-id="${item.id}">启用</button></span>`).join("")}</div></details>` : ""}<span class="dict-add"><input data-new-val placeholder="新增取值"><button class="small primary d-add" data-type="${group.type}">新增</button></span></div></div>`; }).join("") + `<div class="dict-group"><h4>📦 年度归档冻结</h4><div class="dict-tags">${(config.archived_years || []).map(year => `<span>${year} 年<button class="small a-del" data-y="${year}">解除</button></span>`).join("") || '<span class="off">未归档任何年度</span>'}<span class="dict-add"><input data-arch-year placeholder="年份，如 2024"><button class="small primary a-add">归档</button></span></div></div>`;
    bindDictActions();
  }

  function bindDictActions() {
    $$("#dict-view .d-off").forEach(button => button.addEventListener("click", async () => { if (!confirm("停用该取值？历史数据不受影响。")) return; try { await api.delete("/dict/" + button.dataset.id); toast("已停用"); await renderDict(); await loadDict(); onDictChanged?.(); } catch (error) { toast(error.message, "err"); } }));
    $$("#dict-view .d-on").forEach(button => button.addEventListener("click", async () => { try { await api.put("/dict/" + button.dataset.id, { is_active: 1 }); toast("已启用"); await renderDict(); await loadDict(); } catch (error) { toast(error.message, "err"); } }));
    $$("#dict-view .d-add").forEach(button => button.addEventListener("click", async () => { const input = button.parentElement.querySelector("input"); const value = input.value.trim(); if (!value) { toast("请输入取值", "err"); return; } try { await api.post("/dict", { dict_type: button.dataset.type, value }); toast("已新增"); await renderDict(); await loadDict(); } catch (error) { toast(error.message, "err"); } }));
    $$("#dict-view .a-add").forEach(button => button.addEventListener("click", async () => { const input = button.parentElement.querySelector("input"), year = input.value.trim(); if (!/^\d{4}$/.test(year)) { toast("请输入 4 位年份", "err"); return; } const current = (await api.get("/config")).archived_years || []; if (current.includes(year)) { toast("该年度已归档", "err"); return; } await api.put("/config", { archived_years: [...current, year].sort() }); toast("已归档 " + year + " 年"); await renderDict(); await loadProjects?.(); }));
    $$("#dict-view .a-del").forEach(button => button.addEventListener("click", async () => { const current = (await api.get("/config")).archived_years || []; await api.put("/config", { archived_years: current.filter(year => year !== button.dataset.y) }); toast("已解除归档"); await renderDict(); await loadProjects?.(); }));
  }

  async function checkForUpdate(autoApply = false) {
    const result = await api.get("/update");
    if (!result.update_available) return { configured: true, available: false };
    if (!autoApply) { const banner = $("#update-banner"); banner.innerHTML = `<span><b>发现新版本 ${escapeHtml(result.release_version)}</b></span><button id="btn-apply-update" class="primary small">下载并更新</button>`; banner.classList.remove("hidden"); $("#btn-apply-update").addEventListener("click", () => applyUpdate()); return { configured: true, available: true }; }
    await applyUpdate(); return { configured: true, available: true, applying: true };
  }
  async function applyUpdate() { const button = $("#btn-apply-update") || $("#btn-check-update"); button.disabled = true; button.textContent = "正在安装…"; try { await api.post("/update/apply", {}); toast("正在安装新版本，请保持页面打开"); } catch (error) { button.disabled = false; toast(error.message, "err"); } }
  function bind() { $("#btn-ui-text-save").addEventListener("click", () => saveUiTexts().catch(error => toast(error.message, "err"))); $("#btn-ui-text-reset").addEventListener("click", () => resetUiTexts().catch(error => toast(error.message, "err"))); $("#btn-usage-refresh").addEventListener("click", loadUsage); $("#btn-check-update").addEventListener("click", async () => { try { const result = await checkForUpdate(true); if (!result.available) toast("当前已是最新版本"); } catch (error) { toast(error.message, "err"); } }); }
  return { loadDict, loadConfig, loadUsage, renderUiTextConfig, renderDict, checkForUpdate, bind, applyUiTexts };
}

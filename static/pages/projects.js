/**
 * 项目总览页面。
 * 该模块拥有项目列表和项目详情的业务状态，所有网络查询都经过最新请求协调器，
 * 连续搜索或翻页时旧响应会被 AbortController 取消，避免过期数据覆盖新筛选结果。
 */
import { createLatestRequest } from "../core/api.js";
import { FORMS, buildFieldHtml, fieldOptions } from "../core/forms.js";
import { EXPORT_FIELDS, PROJECT_ADV_FIELDS, ADV_OPS, STAGES } from "../core/constants.js";
import { $, $$, escapeHtml } from "../core/dom.js";
import { fmtDate, fmtMoney, kv, stageBadge, csvEscape, downloadText, collectAdvancedFilters } from "../core/utils.js";
import { renderPaginations } from "../components/pagination.js";

const SORT_FIELDS = {
  name: "text", project_no: "text", level: "ordered", category: "ordered", enterprise_name: "text",
  enterprise_district: "ordered", total_amount: "number", disbursed_total: "number", stage: "ordered",
};
const COLLATOR = new Intl.Collator("zh-CN", { numeric: true, sensitivity: "base" });

export function createProjectsPage(context) {
  const { api, state, toast, modal, setPageStatus, trackUsage, prepareImport } = context;
  const latest = createLatestRequest();

  const snapshot = () => state.getState();
  const page = () => snapshot().pages.projects;
  const setPage = patch => state.setState(current => ({ ...current, pages: { ...current.pages, projects: { ...current.pages.projects, ...patch } } }));

  function queryParams() {
    const value = page();
    const params = new URLSearchParams({ page: value.pagination.page, page_size: value.pagination.pageSize, sort: value.pagination.sort || "id", direction: value.pagination.direction || "desc" });
    for (const [key, field] of Object.entries(value.filters || {})) if (field && key !== "advFilters") params.set(key, field);
    if (value.filters?.advFilters?.length) params.set("filters", JSON.stringify(value.filters.advFilters));
    return params;
  }

  async function load() {
    setPageStatus?.("projects", "loading", { error: null });
    render();
    try {
      const result = await latest("projects-list", signal => api.get("/projects?" + queryParams().toString(), { signal }));
      const items = result.items || [];
      setPage({ status: "ready", data: items, error: null, pagination: { ...page().pagination, ...result, totalPages: result.total_pages ?? result.totalPages ?? 0 } });
      render();
      return result;
    } catch (error) {
      if (error.name === "AbortError") return null;
      setPage({ status: "error", data: [], error: error.message });
      render();
      throw error;
    }
  }

  function compare(left, right, field, direction) {
    const a = left[field], b = right[field];
    const emptyA = a == null || a === "", emptyB = b == null || b === "";
    if (emptyA || emptyB) return emptyA === emptyB ? 0 : emptyA ? 1 : -1;
    const multiplier = direction === "desc" ? -1 : 1;
    if (SORT_FIELDS[field] === "number") return (Number(a) - Number(b)) * multiplier;
    if (SORT_FIELDS[field] === "ordered") {
      const source = field === "stage" ? STAGES : field === "enterprise_district" ? snapshot().dict?.district || [] : snapshot().dict?.[field] || [];
      const ai = source.indexOf(a), bi = source.indexOf(b);
      if (ai !== bi) return ((ai < 0 ? source.length : ai) - (bi < 0 ? source.length : bi)) * multiplier;
    }
    return COLLATOR.compare(String(a), String(b)) * multiplier;
  }

  function sortedItems() {
    const value = page(), sort = value.sort || { field: "id", direction: "desc" };
    if (!sort.field || !SORT_FIELDS[sort.field]) return [...(value.data || [])];
    return [...(value.data || [])].sort((a, b) => compare(a, b, sort.field, sort.direction));
  }

  function render() {
    const value = page(), items = sortedItems(), body = $("#project-table tbody");
    $("#project-empty").classList.toggle("hidden", value.status === "loading" || items.length > 0);
    if (value.status === "loading") { body.innerHTML = `<tr><td colspan="10" class="table-loading">正在加载项目…</td></tr>`; return; }
    if (value.status === "error") { body.innerHTML = `<tr><td colspan="10" class="table-error">加载失败：${escapeHtml(value.error)} <button class="small" data-retry-projects>重试</button></td></tr>`; return; }
    $("#result-count").textContent = `共 ${value.pagination.total || items.length} 条结果，第 ${value.pagination.page || 1}/${value.pagination.totalPages || 1} 页`;
    const archived = snapshot().archivedYears || [];
    body.innerHTML = items.map(item => {
      const isArchived = !!(item.start_date && archived.includes(item.start_date.slice(0, 4)));
      return `<tr><td><a href="#" class="p-name" data-id="${item.id}">${escapeHtml(item.name)}</a></td><td>${escapeHtml(item.project_no || "—")}</td><td>${escapeHtml(item.level || "—")}</td><td>${escapeHtml(item.category || "—")}</td><td>${escapeHtml(item.enterprise_name || "—")}</td><td>${escapeHtml(item.enterprise_district || "—")}</td><td class="num">${fmtMoney(item.total_amount)}</td><td class="num">${fmtMoney(item.disbursed_total)}</td><td>${stageBadge(item.stage)}${isArchived ? ' <span class="badge gray">已归档</span>' : ""}</td><td>${isArchived ? '<span class="badge gray">仅查看</span>' : `<button class="small p-view" data-id="${item.id}">查看</button><button class="small p-edit" data-id="${item.id}">编辑</button><button class="small danger p-del" data-id="${item.id}">删除</button>`}</td></tr>`;
    }).join("");
    updateSortHeaders();
    renderPaginations([$("#project-pagination")], { page: value.pagination.page, totalPages: value.pagination.totalPages, onChange: target => { setPage({ pagination: { ...page().pagination, page: target } }); load(); } });
  }

  function updateSortHeaders() {
    const sort = page().sort;
    $$("#project-table th[data-sort]").forEach(header => {
      const active = sort?.field === header.dataset.sort;
      const button = header.querySelector(".project-sort");
      const indicator = header.querySelector(".sort-indicator");
      header.setAttribute("aria-sort", active ? sort.direction === "asc" ? "ascending" : "descending" : "none");
      button?.classList.toggle("is-active", active);
      if (indicator) indicator.textContent = active ? sort.direction === "asc" ? "↑" : "↓" : "↕";
    });
  }

  async function showDetail(id) {
    setPageStatus?.("project-detail", "loading", { error: null });
    try {
      const project = await api.get("/projects/" + id);
      renderDetail(project);
      setPageStatus?.("project-detail", "ready", { data: project, error: null });
    } catch (error) { setPageStatus?.("project-detail", "error", { data: [], error: error.message }); toast(error.message, "err"); }
  }

  function renderDetail(project) {
    const fundings = project.fundings || [], nodes = project.nodes || [], archived = snapshot().archivedYears || [];
    const plannedTotal = fundings.filter(item => item.plan_date).reduce((sum, item) => sum + (item.amount || 0), 0);
    const disbursedTotal = fundings.filter(item => ["已拨付", "已到账"].includes(item.status)).reduce((sum, item) => sum + (item.amount || 0), 0);
    const receivedTotal = fundings.filter(item => item.status === "已到账").reduce((sum, item) => sum + (item.amount || 0), 0);
    const pendingTotal = fundings.filter(item => !["已拨付", "已到账"].includes(item.status)).reduce((sum, item) => sum + (item.amount || 0), 0);
    const sourceTotals = fundings.reduce((result, item) => ({ ...result, [item.source_type]: (result[item.source_type] || 0) + (item.amount || 0) }), {});
    const sumUp = sourceTotals["上级拨付"] || 0, sumMatch = sourceTotals["本级配套"] || 0, sumSelf = sourceTotals["本级自付"] || 0;
    const issues = [];
    if (project.total_amount != null && Math.abs(sumUp + sumMatch + sumSelf - project.total_amount) > 0.005) issues.push(`资金合计(${fmtMoney(sumUp + sumMatch + sumSelf)}) 与项目总金额(${fmtMoney(project.total_amount)})不一致`);
    if (project.match_ratio && sumUp && Math.abs(sumMatch - sumUp * project.match_ratio) > 0.005) issues.push(`本级配套(${fmtMoney(sumMatch)}) 与应配额(${fmtMoney(sumUp * project.match_ratio)})不一致`);
    const isArchived = !!(project.start_date && archived.includes(project.start_date.slice(0, 4)));
    $("#project-detail").innerHTML = `<div class="detail"><div class="detail-head"><h3>${escapeHtml(project.name)}${isArchived ? ' <span class="badge gray">已归档</span>' : ""}</h3><div>${isArchived ? "" : '<button class="small" data-detail-edit>编辑项目</button>'}<button class="small" data-detail-close>收起</button></div></div><div class="detail-grid fact-grid" aria-label="项目资金事实">${kv("项目总金额", fmtMoney(project.total_amount) + " 万元")}${kv("计划拨付", fmtMoney(plannedTotal) + " 万元")}${kv("已拨付", fmtMoney(disbursedTotal) + " 万元")}${kv("已到账", fmtMoney(receivedTotal) + " 万元")}${kv("待拨", fmtMoney(pendingTotal) + " 万元")}${kv("资金勾稽", issues.length ? "存在差异" : "一致")}</div><div class="detail-grid">${kv("项目编号", project.project_no)}${kv("层级", project.level)}${kv("类型", project.category)}${kv("当前阶段", stageBadge(project.stage))}${kv("配套比例", project.match_ratio == null ? "—" : project.match_ratio + " : 1")}${kv("起止时间", (project.start_date || "—") + " ~ " + (project.end_date || "—"))}${kv("负责人", project.leader)}${kv("联系人手机", project.contact_phone)}${kv("备注", project.note, true)}</div>${timeline(project)}<div class="sub-title">承担企业</div><div class="detail-grid">${project.enterprise ? kv("企业名称", project.enterprise.name) + kv("信用代码", project.enterprise.credit_code) + kv("区镇", project.enterprise.district) + kv("联系人", (project.enterprise.contact_person || "") + " " + (project.enterprise.contact_phone || "")) : kv("企业", "未关联")}</div>${issues.length ? `<div class="fund-check warn"><b>⚠ ${issues.join("；")}</b></div>` : `<div class="fund-check ok">✅ 资金勾稽一致：上级 ${fmtMoney(sumUp)} + 配套 ${fmtMoney(sumMatch)} + 自付 ${fmtMoney(sumSelf)} = ${fmtMoney(sumUp + sumMatch + sumSelf)}</div>`}<div class="sub-title">资金明细（计划 ${fmtMoney(plannedTotal)} / 已拨 ${fmtMoney(disbursedTotal)} / 已到账 ${fmtMoney(receivedTotal)} 万元）</div><table class="sub-table"><thead><tr><th>来源</th><th>金额(万)</th><th>批次</th><th>应拨</th><th>实拨</th><th>状态</th><th>操作</th></tr></thead><tbody>${fundings.map(item => `<tr><td>${escapeHtml(item.source_type || "—")}</td><td class="num">${fmtMoney(item.amount)}</td><td>${escapeHtml(item.batch || "—")}</td><td>${fmtDate(item.plan_date)}</td><td>${fmtDate(item.actual_date)}</td><td>${escapeHtml(item.status || "—")}</td><td>${isArchived ? "" : `<button class="small danger f-del" data-id="${item.id}">删除</button>`}</td></tr>`).join("") || '<tr><td colspan="7" class="empty">暂无资金记录</td></tr>'}</tbody></table>${isArchived ? "" : '<div class="inline-add" data-kind="funding"></div>'}<div class="sub-title">项目节点</div><table class="sub-table"><thead><tr><th>节点</th><th>计划时间</th><th>实际完成</th><th>状态</th><th>重大变更</th><th>操作</th></tr></thead><tbody>${nodes.map(item => `<tr><td>${escapeHtml(item.node_type || "—")}</td><td>${fmtDate(item.plan_date)}</td><td>${fmtDate(item.actual_date)}</td><td>${escapeHtml(item.status || "—")}</td><td>${item.has_major_change ? "⚠️ 是" : "否"}</td><td>${isArchived ? "" : `<button class="small danger n-del" data-id="${item.id}">删除</button>`}</td></tr>`).join("") || '<tr><td colspan="6" class="empty">暂无节点</td></tr>'}</tbody></table>${isArchived ? "" : '<div class="inline-add" data-kind="node"></div>'}</div>`;
    $("#project-detail").querySelector("[data-detail-close]").addEventListener("click", () => { $("#project-detail").replaceChildren(); });
    $("#project-detail").querySelector("[data-detail-edit]")?.addEventListener("click", () => openProjectModal(project.id));
    bindTimelineFilters($("#project-detail"));
    $$("#project-detail .f-del").forEach(button => button.addEventListener("click", () => removeChild("fundings", button.dataset.id, project.id)));
    $$("#project-detail .n-del").forEach(button => button.addEventListener("click", () => removeChild("nodes", button.dataset.id, project.id)));
    if (!isArchived) { buildInlineAdd($("#project-detail [data-kind=funding]"), "funding", project.id); buildInlineAdd($("#project-detail [data-kind=node]"), "node", project.id); }
    $("#project-detail").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function bindTimelineFilters(root) {
    $$(".timeline-filter", root).forEach(button => button.addEventListener("click", () => {
      $$(".timeline-filter", root).forEach(item => item.classList.toggle("active", item === button));
      const filter = button.dataset.filter;
      let visible = 0;
      $$(".timeline-event", root).forEach(event => {
        const show = filter === "all" || event.dataset.kind === filter || (filter === "alert" && event.dataset.alert === "1");
        event.classList.toggle("hidden", !show);
        if (show) visible += 1;
      });
      root.querySelector(".timeline-track")?.classList.toggle("filtered-empty", visible === 0);
    }));
  }

  function timeline(project) {
    const today = new Date().toISOString().slice(0, 10), events = [];
    const add = (date, kind, mode, title, detail, alert = false) => { if (date) events.push({ date, kind, mode, title, detail, alert }); };
    add(project.start_date, "stage", "actual", "项目开始", `当前阶段：${project.stage || "未设置"}`);
    add(project.end_date, "stage", "planned", "计划完成", "项目计划结束日期", !!(project.end_date < today && !["已完结", "中止"].includes(project.stage)));
    (project.fundings || []).forEach(item => { const money = `${fmtMoney(item.amount)} 万元${item.batch ? ` · ${item.batch}` : ""}`; add(item.plan_date, "funding", "planned", `${item.source_type || "资金"}应拨`, money, !!(item.plan_date < today && !item.actual_date)); add(item.actual_date, "funding", "actual", `${item.source_type || "资金"}实拨`, `${money} · ${item.status || "已记录"}`); });
    (project.nodes || []).forEach(item => { const changed = !!item.has_major_change; add(item.plan_date, "node", "planned", `${item.node_type || "项目节点"}计划`, item.status || "待办", changed || !!(item.plan_date < today && item.status !== "已完成")); add(item.actual_date, "node", "actual", `${item.node_type || "项目节点"}完成`, changed ? "已完成 · 存在重大变更" : "已完成", changed); });
    events.sort((a, b) => a.date.localeCompare(b.date) || (a.mode === "planned" ? -1 : 1));
    const labels = { stage: "阶段", funding: "资金", node: "节点" };
    return `<section class="project-timeline" aria-label="项目数字时间轴"><div class="timeline-head"><div><p class="timeline-kicker">PROJECT CHRONICLE</p><h4>项目数字时间轴</h4></div><div class="timeline-stage"><span>当前阶段</span>${stageBadge(project.stage)}</div></div><div class="timeline-toolbar" role="group" aria-label="时间轴筛选"><button class="timeline-filter active" data-filter="all">全部</button><button class="timeline-filter" data-filter="stage">阶段</button><button class="timeline-filter" data-filter="node">节点</button><button class="timeline-filter" data-filter="funding">资金</button><button class="timeline-filter" data-filter="alert">异常</button><span class="timeline-legend"><i class="planned"></i>计划 <i class="actual"></i>实际</span></div><div class="timeline-viewport"><div class="timeline-track">${events.map((event, index) => `<article class="timeline-event ${event.mode} ${event.alert ? "alert" : ""}" data-kind="${event.kind}" data-alert="${event.alert ? "1" : "0"}"><div class="timeline-card"><div class="timeline-card-meta"><time>${escapeHtml(event.date)}</time><span>${labels[event.kind]}</span></div><strong>${escapeHtml(event.title)}</strong><p>${escapeHtml(event.detail)}</p></div><span class="timeline-marker" aria-hidden="true"></span><span class="timeline-seq">${String(index + 1).padStart(2, "0")}</span></article>`).join("") || '<div class="timeline-empty">录入项目日期、资金或节点后，这里将自动生成时间轴。</div>'}</div></div></section>`;
  }

  async function removeChild(resource, id, projectId) {
    if (!confirm(resource === "fundings" ? "删除这笔资金？" : "删除这个节点？")) return;
    try { await api.delete(`/${resource}/${id}`); toast("已删除"); await showDetail(projectId); } catch (error) { toast(error.message, "err"); }
  }

  function buildInlineAdd(container, kind, projectId) {
    if (!container) return;
    const fields = FORMS[kind];
    container.innerHTML = fields.map(field => field.type === "select" ? `<select data-k="${field.k}"><option value="">${field.label}</option>${fieldOptions(field, context).map(option => `<option value="${escapeHtml(option)}">${escapeHtml(option)}</option>`).join("")}</select>` : field.type === "checkbox" ? `<label style="font-size:12px;color:var(--muted)"><input type="checkbox" data-k="${field.k}">${field.label}</label>` : `<input type="${field.type}" data-k="${field.k}" placeholder="${field.label}"${field.type === "number" ? ' step="0.01"' : ""}>`).join("") + '<button class="primary small" data-add>添加</button>';
    container.querySelector("[data-add]").addEventListener("click", async buttonEvent => {
      const body = { project_id: Number(projectId) };
      fields.forEach(field => { const element = container.querySelector(`[data-k="${field.k}"]`); if (element) body[field.k] = field.type === "checkbox" ? (element.checked ? 1 : 0) : element.value || undefined; });
      if (kind === "funding" && !body.source_type) { toast("请选择资金来源", "err"); return; }
      if (kind === "node" && !body.node_type) { toast("请选择节点类型", "err"); return; }
      buttonEvent.currentTarget.disabled = true;
      try { await api.post(kind === "funding" ? "/fundings" : "/nodes", body); toast("已添加"); await showDetail(projectId); } catch (error) { buttonEvent.currentTarget.disabled = false; toast(error.message, "err"); }
    });
  }

  async function openProjectModal(id = null) {
    prepareImport?.("project", !id);
    const data = id ? await api.get("/projects/" + id) : {};
    modal.open({ heading: (id ? "编辑" : "新增") + "项目", content: FORMS.project.map(field => buildFieldHtml(field, data[field.k], context)).join(""), onSave: async form => {
      if (!form.checkValidity()) { form.reportValidity(); return; }
      const values = Object.fromEntries(FORMS.project.map(field => { const input = form.elements[field.k]; return [field.k, field.type === "checkbox" ? (input?.checked ? 1 : 0) : input?.value || undefined]; }).filter(([, value]) => value !== undefined));
      if (id) await api.put("/projects/" + id, values); else await api.post("/projects", values);
      toast(id ? "已更新" : "已新增"); modal.close(); await load();
    }});
  }

  async function removeProject(id) {
    if (!confirm("确定删除该项目？其资金、节点记录将一并删除。")) return;
    try {
      await api.delete("/projects/" + id);
      toast("已删除");
      $("#project-detail").replaceChildren();
      await load();
    } catch (error) {
      toast(error.message, "err");
    }
  }

  function exportCurrent() {
    const list = page().data || []; if (!list.length) { toast("当前没有可导出的结果", "err"); return; }
    modal.open({ heading: `导出当前结果（${list.length} 条）`, content: `<div class="export-fields"><div style="margin-bottom:8px;color:var(--muted);font-size:12px">勾选要导出的列（默认全选）：</div>${EXPORT_FIELDS.map(field => `<label class="ef"><input type="checkbox" data-k="${field.k}" checked> ${field.l}</label>`).join("")}</div>`, saveLabel: "导出 CSV", onSave: async form => { const fields = $$(".ef input:checked", form).map(input => input.dataset.k); if (!fields.length) { toast("请至少勾选一列", "err"); return; } const head = fields.map(key => EXPORT_FIELDS.find(field => field.k === key)?.l || key); const rows = [head.join(","), ...list.map(item => fields.map(key => csvEscape(item[key])).join(","))]; downloadText("查询结果_" + new Date().toISOString().slice(0, 10) + ".csv", "\ufeff" + rows.join("\n"), "text/csv;charset=utf-8"); modal.close(); toast(`已导出 ${list.length} 条结果`); } });
  }

  function addAdvancedRow(root, fields = PROJECT_ADV_FIELDS) {
    const row = document.createElement("div"); row.className = "adv-row";
    row.innerHTML = `<select class="af-field">${fields.map(field => `<option value="${field.v}">${field.l}</option>`).join("")}</select><select class="af-op">${ADV_OPS.map(op => `<option value="${op.v}">${op.l}</option>`).join("")}</select><input class="af-val" placeholder="条件值"><button class="small danger af-del">删除</button>`;
    row.querySelector(".af-del").addEventListener("click", () => row.remove()); root.append(row);
  }

  function filtersFromDom() {
    return { level: $("#flt-level").value, category: $("#flt-category").value, stage: $("#flt-stage").value, district: $("#flt-district").value, q: $("#flt-q").value.trim(), advFilters: collectAdvancedFilters($("#adv-rows")) };
  }

  function bind() {
    $("#btn-search").addEventListener("click", () => { setPage({ filters: filtersFromDom(), pagination: { ...page().pagination, page: 1 } }); load().catch(error => toast(error.message, "err")); });
    ["flt-level", "flt-category", "flt-stage", "flt-district"].forEach(id => $("#" + id).addEventListener("change", () => $("#btn-search").click()));
    $("#flt-q").addEventListener("keydown", event => { if (event.key === "Enter") $("#btn-search").click(); });
    $("#project-page-size").addEventListener("change", event => { setPage({ pagination: { ...page().pagination, page: 1, pageSize: Number(event.target.value) } }); load().catch(error => toast(error.message, "err")); });
    $("#btn-adv").addEventListener("click", () => { const panel = $("#adv-panel"); panel.classList.toggle("hidden"); if (!panel.classList.contains("hidden") && !$("#adv-rows").children.length) addAdvancedRow($("#adv-rows")); });
    $("#btn-adv-add").addEventListener("click", () => addAdvancedRow($("#adv-rows")));
    $("#btn-adv-clear").addEventListener("click", () => { $("#adv-rows").replaceChildren(); addAdvancedRow($("#adv-rows")); });
    $("#btn-add-project").addEventListener("click", () => openProjectModal().catch(error => toast(error.message, "err")));
    $("#btn-export-current").addEventListener("click", exportCurrent);
    $("#project-table tbody").addEventListener("click", event => { const target = event.target.closest("[data-id]"); if (!target) return; if (target.matches(".p-name,.p-view")) { event.preventDefault(); showDetail(target.dataset.id); } else if (target.matches(".p-edit")) openProjectModal(target.dataset.id); else if (target.matches(".p-del")) removeProject(target.dataset.id); });
    $("#project-table thead").addEventListener("click", event => { const button = event.target.closest(".project-sort"); if (!button) return; const current = page().sort; setPage({ sort: { field: button.dataset.sort, direction: current?.field === button.dataset.sort && current.direction === "asc" ? "desc" : "asc" }, pagination: { ...page().pagination, page: 1 } }); load().catch(error => toast(error.message, "err")); trackUsage?.("项目总览", "字段排序"); });
    $("#project-table tbody").addEventListener("click", event => { if (event.target.matches("[data-retry-projects]")) load().catch(error => toast(error.message, "err")); });
  }
  return { load, render, bind, showDetail, openProjectModal, exportCurrent, addAdvancedRow };
}

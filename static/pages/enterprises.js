/** 企业页面：保持后端分页，查询请求按页面键取消，避免 3000+ 企业连续操作时响应串线。 */
import { createLatestRequest } from "../core/api.js";
import { FORMS, buildFieldHtml } from "../core/forms.js";
import { ADV_OPS, ENTERPRISE_ADV_FIELDS } from "../core/constants.js";
import { $, $$, escapeHtml } from "../core/dom.js";
import { fmtMoney, kv, stageBadge, collectAdvancedFilters } from "../core/utils.js";
import { renderPaginations } from "../components/pagination.js";

export function createEnterprisesPage(context) {
  const { api, state, toast, modal, setPageStatus, trackUsage, onEnterpriseSelected, prepareImport } = context;
  const latest = createLatestRequest();
  const snapshot = () => state.getState();
  const page = () => snapshot().pages.enterprises;
  const setPage = patch => state.setState(current => ({ ...current, pages: { ...current.pages, enterprises: { ...current.pages.enterprises, ...patch } } }));

  function queryParams() {
    const value = page();
    const params = new URLSearchParams({ page: value.pagination.page, page_size: value.pagination.pageSize, sort: value.pagination.sort || "id", direction: value.pagination.direction || "desc" });
    if (value.filters.q) params.set("q", value.filters.q);
    if (value.filters.advFilters?.length) params.set("filters", JSON.stringify(value.filters.advFilters));
    return params;
  }

  async function load() {
    setPageStatus?.("enterprises", "loading", { error: null });
    render();
    try {
      const result = await latest("enterprise-list", signal => api.get("/enterprises?" + queryParams().toString(), { signal }));
      setPage({ status: "ready", data: result.items || [], error: null, pagination: { ...page().pagination, ...result, totalPages: result.total_pages ?? result.totalPages ?? 0 } });
      render();
      return result;
    } catch (error) {
      if (error.name === "AbortError") return null;
      setPage({ status: "error", data: [], error: error.message }); render(); throw error;
    }
  }

  function render() {
    const value = page(), tbody = $("#enterprise-table tbody"), items = value.data || [];
    $("#enterprise-empty").classList.toggle("hidden", value.status === "loading" || items.length > 0);
    if (value.status === "loading") { tbody.innerHTML = '<tr><td colspan="8" class="table-loading">正在加载企业…</td></tr>'; return; }
    if (value.status === "error") { tbody.innerHTML = `<tr><td colspan="8" class="table-error">加载失败：${escapeHtml(value.error)} <button class="small" data-retry-enterprises>重试</button></td></tr>`; return; }
    $("#enterprise-result-bar").textContent = value.pagination.total ? `共 ${value.pagination.total} 家企业，第 ${value.pagination.page}/${value.pagination.totalPages} 页` : "暂无企业";
    tbody.innerHTML = items.map(item => `<tr><td>${escapeHtml(item.name)}</td><td>${escapeHtml(item.credit_code || "—")}</td><td>${escapeHtml(item.enterprise_type || "—")}</td><td>${escapeHtml(item.district || "—")}</td><td>${escapeHtml(item.qualifications || "—")}</td><td class="num">${item.project_count ?? 0}</td><td class="num">${fmtMoney(item.total_amount_sum)}</td><td><button class="small e-view" data-id="${item.id}">画像</button><button class="small e-edit" data-id="${item.id}">编辑</button><button class="small danger e-del" data-id="${item.id}">删除</button></td></tr>`).join("");
    renderPaginations([$("#enterprise-pagination-top"), $("#enterprise-pagination")], { page: value.pagination.page, totalPages: value.pagination.totalPages, onChange: target => { setPage({ pagination: { ...page().pagination, page: target } }); load().catch(error => toast(error.message, "err")); } });
  }

  async function openModal(id = null) {
    prepareImport?.("enterprise", !id);
    const data = id ? await api.get("/enterprises/" + id) : {};
    modal.open({ heading: (id ? "编辑" : "新增") + "企业", content: FORMS.enterprise.map(field => buildFieldHtml(field, data[field.k], context)).join(""), onSave: async form => {
      if (!form.checkValidity()) { form.reportValidity(); return; }
      const values = Object.fromEntries(FORMS.enterprise.map(field => { const input = form.elements[field.k]; return [field.k, field.type === "checkbox" ? (input?.checked ? 1 : 0) : input?.value || undefined]; }).filter(([, value]) => value !== undefined));
      if (id) await api.put("/enterprises/" + id, values); else await api.post("/enterprises", values);
      toast(id ? "已更新" : "已新增"); modal.close(); await loadLookup(); await load();
    }});
  }

  async function loadLookup() {
    const lookup = await api.get("/enterprises?lookup=1");
    state.setState(current => ({ ...current, enterprises: lookup }));
    return lookup;
  }

  async function remove(id) {
    if (!confirm("确定删除该企业？其下项目将变为未关联企业。")) return;
    try { await api.delete("/enterprises/" + id); toast("已删除"); await loadLookup(); await load(); } catch (error) { toast(error.message, "err"); }
  }

  async function showDetail(id) {
    try {
      const enterprise = await api.get("/enterprises/" + id);
      const total = (enterprise.projects || []).reduce((sum, project) => sum + (project.total_amount || 0), 0);
      modal.open({ heading: "企业画像：" + enterprise.name, showSave: false, content: `<div class="detail-grid" style="grid-column:1/-1">${kv("统一信用代码", enterprise.credit_code)}${kv("企业类型", enterprise.enterprise_type)}${kv("区镇", enterprise.district)}${kv("资质", enterprise.qualifications)}${kv("联系人", (enterprise.contact_person || "") + " " + (enterprise.contact_phone || ""))}${kv("承担项目数", (enterprise.projects || []).length + " 个")}${kv("累计金额", fmtMoney(total) + " 万元")}</div><div class="sub-title" style="grid-column:1/-1">承担项目</div><table class="sub-table" style="grid-column:1/-1"><thead><tr><th>项目</th><th>层级</th><th>类型</th><th>总金额(万)</th><th>阶段</th></tr></thead><tbody>${(enterprise.projects || []).map(project => `<tr><td>${escapeHtml(project.name)}</td><td>${escapeHtml(project.level || "—")}</td><td>${escapeHtml(project.category || "—")}</td><td class="num">${fmtMoney(project.total_amount)}</td><td>${stageBadge(project.stage)}</td></tr>`).join("") || '<tr><td colspan="5" class="empty">暂无承担项目</td></tr>'}</tbody></table>` });
      onEnterpriseSelected?.(enterprise);
    } catch (error) { toast(error.message, "err"); }
  }

  function addAdvancedRow() {
    const row = document.createElement("div"); row.className = "adv-row";
    row.innerHTML = `<select class="af-field">${ENTERPRISE_ADV_FIELDS.map(field => `<option value="${field.v}">${field.l}</option>`).join("")}</select><select class="af-op">${ADV_OPS.map(op => `<option value="${op.v}">${op.l}</option>`).join("")}</select><input class="af-val" placeholder="条件值"><button class="small danger af-del">删除</button>`;
    row.querySelector(".af-del").addEventListener("click", () => row.remove()); $("#enterprise-adv-rows").append(row);
  }

  function bind() {
    $("#btn-enterprise-search").addEventListener("click", () => { setPage({ filters: { q: $("#enterprise-q").value.trim(), advFilters: collectAdvancedFilters($("#enterprise-adv-rows")) }, pagination: { ...page().pagination, page: 1 } }); load().catch(error => toast(error.message, "err")); trackUsage?.("企业", "搜索"); });
    $("#enterprise-q").addEventListener("keydown", event => { if (event.key === "Enter") $("#btn-enterprise-search").click(); });
    $("#enterprise-page-size").addEventListener("change", event => { setPage({ pagination: { ...page().pagination, page: 1, pageSize: Number(event.target.value) } }); load().catch(error => toast(error.message, "err")); });
    $("#btn-enterprise-adv").addEventListener("click", () => { const panel = $("#enterprise-adv-panel"); panel.classList.toggle("hidden"); if (!panel.classList.contains("hidden") && !$("#enterprise-adv-rows").children.length) addAdvancedRow(); });
    $("#btn-enterprise-adv-add").addEventListener("click", addAdvancedRow);
    $("#btn-enterprise-adv-clear").addEventListener("click", () => { $("#enterprise-adv-rows").replaceChildren(); addAdvancedRow(); });
    $("#btn-add-enterprise").addEventListener("click", () => openModal().catch(error => toast(error.message, "err")));
    $("#btn-enterprise-export").addEventListener("click", () => { const params = new URLSearchParams({ resource: "enterprises", q: page().filters.q || "" }); if (page().filters.advFilters?.length) params.set("filters", JSON.stringify(page().filters.advFilters)); window.location.href = "/api/export?" + params; });
    $("#enterprise-table tbody").addEventListener("click", event => { const button = event.target.closest("button[data-id]"); if (!button) return; if (button.classList.contains("e-view")) showDetail(button.dataset.id); else if (button.classList.contains("e-edit")) openModal(button.dataset.id); else if (button.classList.contains("e-del")) remove(button.dataset.id); });
    $("#enterprise-table tbody").addEventListener("click", event => { if (event.target.matches("[data-retry-enterprises]")) load().catch(error => toast(error.message, "err")); });
    $("#enterprise-table thead").addEventListener("click", event => { const button = event.target.closest(".enterprise-sort"); if (!button) return; const current = page().pagination; const sort = button.dataset.sort; setPage({ pagination: { ...current, page: 1, sort, direction: current.sort === sort && current.direction === "asc" ? "desc" : "asc" } }); load().catch(error => toast(error.message, "err")); trackUsage?.("企业", "字段排序"); });
  }
  return { load, loadLookup, render, bind, openModal, showDetail };
}

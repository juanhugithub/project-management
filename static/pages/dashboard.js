/** 工作台页面：只负责概览、待办节点和资金待拨三块事实的加载与渲染。 */
import { $, escapeHtml } from "../core/dom.js";
import { fmtDate, fmtMoney } from "../core/utils.js";

export function createDashboardPage(context) {
  const { api, gotoProject, setPageStatus } = context;

  async function load() {
    setPageStatus?.("dashboard", "loading", { data: [], error: null });
    try {
      const [dashboard, reminders, fundingPlan] = await Promise.all([
        api.get("/dashboard"), api.get("/reminders?days=90"), api.get("/funding-plan"),
      ]);
      const cards = [
        { k: "项目总数", v: dashboard.project_count }, { k: "承担企业", v: dashboard.enterprise_count },
        { k: "已拨付资金", v: fmtMoney(dashboard.funded_total) + " 万" }, { k: "计划拨付", v: fmtMoney(dashboard.plan_total) + " 万" },
        { k: "逾期节点", v: dashboard.overdue_nodes, warn: dashboard.overdue_nodes > 0 },
        { k: "3 个月内到期", v: dashboard.due90_nodes, warn: dashboard.due90_nodes > 0 },
        { k: "该拨未拨", v: dashboard.overdue_funding_count + " 笔", warn: dashboard.overdue_funding_count > 0 },
      ];
      $("#dash-cards").innerHTML = cards.map(card => `<div class="dash-card ${card.warn ? "warn" : ""}"><div class="dc-v">${card.v}</div><div class="dc-k">${card.k}</div></div>`).join("");
      renderReminders(reminders);
      renderFunding(fundingPlan);
      setPageStatus?.("dashboard", "ready", { data: { dashboard, reminders, fundingPlan }, error: null });
    } catch (error) {
      setPageStatus?.("dashboard", "error", { data: [], error: error.message });
      $("#dash-reminders").innerHTML = `<div class="empty error-state">工作台加载失败：${escapeHtml(error.message)}</div>`;
      $("#dash-funding").innerHTML = `<div class="empty error-state">资金数据加载失败，请刷新重试</div>`;
      throw error;
    }
  }

  function renderReminders(list) {
    const levelMap = { overdue: ["已逾期", "overdue"], red: ["≤7天", "red"], yellow: ["≤30天", "yellow"] };
    $("#dash-reminders").innerHTML = list.length ? `<table class="sub-table"><thead><tr><th>项目</th><th>节点</th><th>计划</th><th>级别</th></tr></thead><tbody>${list.slice(0, 8).map(item => `<tr><td><a href="#" class="dash-p" data-id="${item.project_id}">${escapeHtml(item.project_name)}</a></td><td>${escapeHtml(item.node_type || "—")}</td><td>${fmtDate(item.plan_date)}</td><td><span class="badge ${levelMap[item.level]?.[1] || "later"}">${levelMap[item.level]?.[0] || "—"}</span></td></tr>`).join("")}${list.length > 8 ? `<tr><td colspan="4" class="empty">…还有 ${list.length - 8} 条，见「提醒」页</td></tr>` : ""}</tbody></table>` : `<div class="empty">3 个月内没有到期节点</div>`;
    $("#dash-reminders").querySelectorAll(".dash-p").forEach(link => link.addEventListener("click", event => { event.preventDefault(); gotoProject(link.dataset.id); }));
  }

  function renderFunding(plan) {
    const overdue = (plan.items || []).filter(item => item.is_overdue);
    $("#dash-funding").innerHTML = overdue.length ? `<table class="sub-table"><thead><tr><th>项目</th><th>来源</th><th>金额(万)</th><th>应拨</th></tr></thead><tbody>${overdue.slice(0, 8).map(item => `<tr><td><a href="#" class="dash-p" data-id="${item.project_id}">${escapeHtml(item.project_name)}</a></td><td>${escapeHtml(item.source_type || "—")}</td><td class="num">${fmtMoney(item.amount)}</td><td>${fmtDate(item.plan_date)}</td></tr>`).join("")}${overdue.length > 8 ? `<tr><td colspan="4" class="empty">…还有 ${overdue.length - 8} 笔</td></tr>` : ""}</tbody></table><div class="fund-check warn" style="margin-top:6px">共 ${overdue.length} 笔、${fmtMoney(plan.summary.overdue_amount)} 万元该拨未拨；拨付执行率 ${(plan.summary.execution_rate * 100).toFixed(1)}%</div>` : `<div class="empty">✅ 没有该拨未拨的资金</div>`;
    $("#dash-funding").querySelectorAll(".dash-p").forEach(link => link.addEventListener("click", event => { event.preventDefault(); gotoProject(link.dataset.id); }));
  }

  return { load };
}

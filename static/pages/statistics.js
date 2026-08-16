/** 资金统计页面：统计维度由后端决定，导出只使用当前已展示的数据。 */
import { downloadText, escapeHtml, fmtMoney } from "../core/utils.js";
import { $ } from "../core/dom.js";

export function createStatisticsPage(context) {
  const { api, setPageStatus, toast } = context;
  let current = [];
  async function load() {
    setPageStatus?.("statistics", "loading", { data: [], error: null });
    try {
      current = await api.get("/stats?by=" + $("#st-by").value);
      $("#stats-empty").classList.toggle("hidden", current.length > 0);
      $("#stats-table tbody").innerHTML = current.map(item => `<tr><td>${escapeHtml(item.key)}</td><td class="num">${item.count}</td><td class="num">${fmtMoney(item.amount)}</td></tr>`).join("");
      setPageStatus?.("statistics", "ready", { data: current, error: null });
    } catch (error) { setPageStatus?.("statistics", "error", { data: [], error: error.message }); throw error; }
  }
  function exportCsv() {
    if (!current.length) { toast("暂无数据可导出", "err"); return; }
    const rows = ["维度,项目数,金额合计(万元)", ...current.map(item => [item.key, item.count, item.amount].join(","))];
    downloadText("资金统计报表_" + new Date().toISOString().slice(0, 10) + ".csv", "\ufeff" + rows.join("\n"), "text/csv;charset=utf-8");
  }
  return { load, exportCsv };
}

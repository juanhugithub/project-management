/** 提醒页面：后端负责日期计算，页面只呈现状态并处理节点完成动作。 */
import { $, escapeHtml } from "../core/dom.js";
import { fmtDate } from "../core/utils.js";

export function createRemindersPage(context) {
  const { api, toast, gotoProject, setPageStatus } = context;
  async function load() {
    setPageStatus?.("reminders", "loading", { data: [], error: null });
    try {
      const list = await api.get("/reminders?days=" + $("#rm-days").value);
      const levelMap = { overdue: ["已逾期", "overdue"], red: ["≤7天", "red"], yellow: ["≤30天", "yellow"], later: ["30天外", "later"] };
      const tbody = $("#reminder-table tbody");
      $("#reminder-empty").classList.toggle("hidden", list.length > 0);
      tbody.innerHTML = list.map(item => { const [label, cls] = levelMap[item.level] || ["", "later"]; return `<tr><td><span class="badge ${cls}">${label}</span></td><td><a href="#" class="rm-p" data-id="${item.project_id}">${escapeHtml(item.project_name)}</a></td><td>${escapeHtml(item.project_level || "—")}</td><td>${escapeHtml(item.node_type || "—")}</td><td>${fmtDate(item.plan_date)}</td><td class="num">${item.days_left == null ? "—" : Math.ceil(item.days_left)}</td><td>${escapeHtml(item.status || "—")}</td><td><button class="small rm-done" data-id="${item.id}">标记完成</button></td></tr>`; }).join("");
      tbody.querySelectorAll(".rm-p").forEach(link => link.addEventListener("click", event => { event.preventDefault(); gotoProject(link.dataset.id); }));
      tbody.querySelectorAll(".rm-done").forEach(button => button.addEventListener("click", async () => {
        if (!confirm("标记该节点为已完成？")) return;
        button.disabled = true;
        try { await api.put("/nodes/" + button.dataset.id, { status: "已完成", actual_date: new Date().toISOString().slice(0, 10) }); toast("已标记完成"); await load(); }
        catch (error) { button.disabled = false; toast(error.message, "err"); }
      }));
      setPageStatus?.("reminders", "ready", { data: list, error: null });
      return list;
    } catch (error) { setPageStatus?.("reminders", "error", { data: [], error: error.message }); throw error; }
  }
  return { load };
}

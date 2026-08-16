/**
 * 科技项目台账前端入口。
 * 入口只装配基础设施和页面模块，业务逻辑由 pages/ 与 components/ 各自负责。
 */
import { api, setUnauthorizedHandler } from "./core/api.js";
import { createHashRouter } from "./core/router.js";
import { createStore, createPageState, setPageStatus as updatePageStatus } from "./core/store.js";
import { initToast, toast } from "./core/toast.js";
import { $, $$ } from "./core/dom.js";
import { createModal } from "./components/modal.js";
import { createExcelImporter } from "./components/importer.js";
import { createDashboardPage } from "./pages/dashboard.js";
import { createProjectsPage } from "./pages/projects.js";
import { createEnterprisesPage } from "./pages/enterprises.js";
import { createRemindersPage } from "./pages/reminders.js";
import { createStatisticsPage } from "./pages/statistics.js";
import { createSettingsPage } from "./pages/settings.js";

const store = createStore({
  dict: {}, enterprises: [], archivedYears: [], uiTexts: {},
  pages: {
    dashboard: createPageState({ data: {} }),
    projects: { ...createPageState(), filters: { level: "", category: "", stage: "", district: "", q: "", advFilters: [] }, pagination: { page: 1, pageSize: 50, total: 0, totalPages: 0, sort: "id", direction: "desc" }, sort: { field: "id", direction: "desc" } },
    enterprises: { ...createPageState(), filters: { q: "", advFilters: [] }, pagination: { page: 1, pageSize: 50, total: 0, totalPages: 0, sort: "id", direction: "desc" } },
    reminders: createPageState(), statistics: createPageState(), usage: createPageState(), "project-detail": createPageState(),
  },
});

initToast();
const modal = createModal();
let importer;
const pageStatus = (page, status, patch = {}) => updatePageStatus(store, page, status, patch);
const trackUsage = (module, action = "view") => { api.post("/usage", { module, action }).catch(() => {}); };

function showLogin(message = "请登录后继续使用台账。") {
  $("#auth-panel").classList.remove("hidden"); $("#auth-error").textContent = message; $("#auth-error").classList.remove("hidden");
  window.setTimeout(() => $("#auth-username")?.focus(), 0);
}
function hideLogin() { $("#auth-panel").classList.add("hidden"); $("#auth-error").classList.add("hidden"); }
setUnauthorizedHandler(({ path }) => showLogin(`会话已失效，请登录后重试：${path}`));

let dashboardPage;
let projectsPage;
let enterprisesPage;
let remindersPage;
let statisticsPage;
const settingsPage = createSettingsPage({ api, state: store, toast, setPageStatus: pageStatus, loadProjects: () => projectsPage?.load(), onDictChanged: () => projectsPage?.render() });

function activateTab(route) {
  const settingsRoutes = ["dict", "ui-text", "guide", "usage"];
  $$(".tab-btn[data-tab]").forEach(button => button.classList.toggle("active", button.dataset.tab === route));
  $$(".tab").forEach(tab => tab.classList.toggle("active", tab.id === "tab-" + route));
  $("#btn-settings-toggle").classList.toggle("active", settingsRoutes.includes(route));
  $("#settings-menu")?.classList.add("hidden");
  trackUsage(route, "view");
}

const router = createHashRouter({ defaultRoute: "dashboard" });
const pageLoaders = {
  dashboard: () => dashboardPage.load(), projects: () => projectsPage.load(), reminders: () => remindersPage.load(),
  enterprises: () => enterprisesPage.load(),
  stats: () => statisticsPage.load(), usage: () => settingsPage.loadUsage(), "ui-text": () => settingsPage.renderUiTextConfig(),
  dict: () => settingsPage.renderDict(), guide: () => Promise.resolve(),
};
Object.entries(pageLoaders).forEach(([route, load]) => router.register(route, async () => { activateTab(route); try { await load(); } catch (error) { if (error.status !== 401) toast("加载失败：" + error.message, "err"); } }));

function gotoProject(id) { router.navigate("projects"); window.setTimeout(() => projectsPage.showDetail(id), 0); }

async function loadWorkspace() {
  // 共享数据只在这里加载，当前路由页面由 router.dispatch 统一加载一次。
  await Promise.all([settingsPage.loadDict(), settingsPage.loadConfig(), enterprisesPage.loadLookup()]);
  settingsPage.renderUiTextConfig();
  await router.dispatch();
}

function bindNavigation() {
  const toggle = $("#btn-settings-toggle"), menu = $("#settings-menu");
  toggle.addEventListener("click", event => { event.stopPropagation(); const opening = menu.classList.contains("hidden"); menu.classList.toggle("hidden", !opening); toggle.setAttribute("aria-expanded", String(opening)); });
  document.addEventListener("click", event => { if (!event.target.closest(".settings-nav")) menu.classList.add("hidden"); });
  $$(".tab-btn[data-tab]").forEach(button => button.addEventListener("click", () => router.navigate(button.dataset.tab)));
  $("#btn-hero-project").addEventListener("click", () => projectsPage.openProjectModal().catch(error => toast(error.message, "err")));
  $("#btn-hero-refresh").addEventListener("click", () => dashboardPage.load().then(() => toast("工作台数据已刷新")).catch(error => toast(error.message, "err")));
  $("#btn-rm-refresh").addEventListener("click", () => remindersPage.load().catch(error => toast(error.message, "err")));
  $("#rm-days").addEventListener("change", () => remindersPage.load().catch(error => toast(error.message, "err")));
  $("#btn-rm-export").addEventListener("click", () => { window.location.href = "/api/export?resource=reminders&days=" + encodeURIComponent($("#rm-days").value); trackUsage("提醒", "导出当前结果"); });
  $("#st-by").addEventListener("change", () => statisticsPage.load().catch(error => toast(error.message, "err")));
  $("#btn-st-export").addEventListener("click", statisticsPage.exportCsv);
}

function bindAuth() {
  $("#auth-form").addEventListener("submit", async event => {
    event.preventDefault(); const username = $("#auth-username").value.trim(); const password = $("#auth-password").value;
    try { await api.post("/auth/login", { username, password }); $("#auth-password").value = ""; hideLogin(); await loadWorkspace(); }
    catch (error) { $("#auth-error").textContent = error.message || "登录失败，请检查账号和密码。"; $("#auth-error").classList.remove("hidden"); $("#auth-password").focus(); }
  });
}

function bindCopyButtons() { $$(".copy-btn").forEach(button => button.addEventListener("click", async () => { const target = document.getElementById(button.dataset.copyTarget); if (!target) return; try { await navigator.clipboard.writeText(target.textContent); button.textContent = "已复制"; window.setTimeout(() => { button.textContent = "复制"; }, 1600); } catch { toast("浏览器未允许复制，请手动选中配置", "err"); } })); }

async function init() {
  dashboardPage = createDashboardPage({ api, state: store, toast, setPageStatus: pageStatus, gotoProject });
  importer = createExcelImporter({ api, toast, afterProjectImport: async () => { await enterprisesPage?.loadLookup(); await projectsPage?.load(); }, afterEnterpriseImport: async () => enterprisesPage?.loadLookup() });
  projectsPage = createProjectsPage({ api, state: store, toast, modal, setPageStatus: pageStatus, trackUsage, prepareImport: importer.prepare });
  enterprisesPage = createEnterprisesPage({ api, state: store, toast, modal, setPageStatus: pageStatus, trackUsage, prepareImport: importer.prepare });
  remindersPage = createRemindersPage({ api, state: store, toast, setPageStatus: pageStatus, gotoProject });
  statisticsPage = createStatisticsPage({ api, state: store, toast, setPageStatus: pageStatus });
  projectsPage.bind(); enterprisesPage.bind(); settingsPage.bind(); importer.bind(); bindNavigation(); bindAuth(); bindCopyButtons();
  router.start({ dispatchInitial: false });
  try { await loadWorkspace(); } catch (error) { if (error.status !== 401) toast("加载失败：" + error.message, "err"); }
}

init();

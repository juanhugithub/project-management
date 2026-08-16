/** Excel 导入组件：项目与企业共用上传、预览和确认流程。 */
import { $, $$, escapeHtml } from "../core/dom.js";

export function createExcelImporter({ api, toast, afterProjectImport, afterEnterpriseImport }) {
  let kind = "project";

  function prepare(nextKind, enabled = true) {
    kind = nextKind;
    $("#modal-tabs").classList.toggle("hidden", !enabled);
    $("#excel-result").replaceChildren();
    if (enabled) switchTab("manual");
  }

  function configurePanel() {
    const enterprise = kind === "enterprise";
    $("#btn-modal-template").textContent = enterprise ? "📄 下载企业导入模板" : "📄 下载模板（一张表，自动归仓）";
    $("#drop-zone-sub").textContent = enterprise ? "每行一家企业，上传后先预览再确认入库（.xlsx）" : "一张总表包含企业与项目所有字段，系统自动拆分归仓（.xlsx）";
  }

  function switchTab(name) {
    const manual = name === "manual";
    $$("#modal-tabs .mtab").forEach(button => button.classList.toggle("active", button.dataset.mtab === name));
    $("#mtab-manual").classList.toggle("hidden", !manual); $("#mtab-excel").classList.toggle("hidden", manual);
    $("#btn-modal-save").style.display = manual ? "" : "none"; $("#btn-modal-cancel").textContent = manual ? "取消" : "关闭";
    if (!manual) configurePanel();
  }

  async function importFile(file) {
    if (!/\.xlsx$/i.test(file.name)) { toast("请选择 .xlsx 文件", "err"); return; }
    const base64 = await new Promise((resolve, reject) => { const reader = new FileReader(); reader.onerror = () => reject(reader.error); reader.onload = () => resolve(reader.result.split(",")[1]); reader.readAsDataURL(file); });
    try {
      const result = await api.post(kind === "enterprise" ? "/enterprise-import" : "/import", { filename: file.name, data: base64 });
      switchTab("excel");
      if (kind === "enterprise") renderEnterprisePreview(result, file.name); else { renderProjectResult(result, file.name); await afterProjectImport?.(); }
    } catch (error) { toast("导入失败：" + error.message, "err"); }
  }

  function renderEnterprisePreview(result, filename) {
    const preview = result.preview || { rows: [], summary: { new_enterprise: 0, blocking: 0 } }, summary = preview.summary;
    const labels = { new_enterprise: "可导入", duplicate: "重复企业", missing_identity: "缺少必填项", field_error: "字段不匹配" };
    $("#excel-result").innerHTML = `<div class="sub-title">导入预览：${escapeHtml(filename)}</div><div class="fund-check ${summary.blocking ? "warn" : "ok"}"><b>可新增 ${summary.new_enterprise} 家　|　需处理 ${summary.blocking} 行</b></div><table class="sub-table"><thead><tr><th>行号</th><th>结论</th><th>说明</th></tr></thead><tbody>${preview.rows.map(row => `<tr><td class="num">${row.row_no + 1}</td><td>${labels[row.conclusion] || escapeHtml(row.conclusion)}</td><td>${escapeHtml(row.error || "检查通过")}</td></tr>`).join("")}</tbody></table>${summary.blocking ? '<div class="notice">请按说明修改 Excel 后重新上传。存在阻断项时不会写入任何企业。</div>' : `<div class="modal-actions"><button id="btn-confirm-enterprise-import" class="primary">确认导入 ${summary.new_enterprise} 家企业</button></div>`}`;
    $("#btn-confirm-enterprise-import")?.addEventListener("click", async event => { event.currentTarget.disabled = true; try { const confirmed = await api.post(`/enterprise-import/${result.id}/confirm`, {}); $("#excel-result").innerHTML = `<div class="fund-check ok"><b>已新增 ${confirmed.enterprise_count} 家企业</b></div>`; await afterEnterpriseImport?.(); toast(`已导入 ${confirmed.enterprise_count} 家企业`); } catch (error) { event.currentTarget.disabled = false; toast(error.message, "err"); } });
  }

  function renderProjectResult(result, filename) {
    const enterprise = result.enterprise || { ok: 0, errors: [] }, project = result.project || { ok: 0, errors: [] };
    const failures = [...enterprise.errors.map(item => ({ sheet: "企业", ...item })), ...project.errors.map(item => ({ sheet: "项目", ...item }))];
    $("#excel-result").innerHTML = `<div class="sub-title">导入结果：${escapeHtml(filename)}</div><div class="fund-check ${failures.length ? "warn" : "ok"}"><b>企业：成功 ${enterprise.ok} / 失败 ${enterprise.errors.length}　|　项目：成功 ${project.ok} / 失败 ${project.errors.length}</b></div>${failures.length ? `<table class="sub-table"><thead><tr><th>表</th><th>行号</th><th>原因</th></tr></thead><tbody>${failures.map(item => `<tr><td>${item.sheet}</td><td class="num">${item.row}</td><td>${escapeHtml(item.reason)}</td></tr>`).join("")}</tbody></table>` : '<div class="sub-title">全部导入成功 ✅</div>'}`;
  }

  function bind() {
    $$("#modal-tabs .mtab").forEach(button => button.addEventListener("click", () => switchTab(button.dataset.mtab)));
    $("#btn-modal-template").addEventListener("click", () => { window.location.href = kind === "enterprise" ? "/api/enterprise-template" : "/api/template"; });
    const zone = $("#drop-zone");
    zone.addEventListener("click", () => $("#file-import2").click());
    zone.addEventListener("dragover", event => { event.preventDefault(); zone.classList.add("over"); });
    zone.addEventListener("dragleave", () => zone.classList.remove("over"));
    zone.addEventListener("drop", event => { event.preventDefault(); zone.classList.remove("over"); const file = event.dataTransfer?.files?.[0]; if (file) importFile(file); });
    $("#file-import2").addEventListener("change", event => { const file = event.target.files[0]; if (file) importFile(file); event.target.value = ""; });
  }
  return { prepare, bind, importFile };
}

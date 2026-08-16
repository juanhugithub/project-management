/** 通用格式化和下载工具，页面模块不直接复制这些细节。 */
import { escapeHtml } from "./dom.js";

export { escapeHtml };

export function fmtDate(value) {
  return value || "—";
}

export function fmtMoney(value) {
  return value == null ? "—" : Number(value).toLocaleString("zh-CN", { maximumFractionDigits: 2 });
}

export function downloadText(filename, content, type = "text/plain;charset=utf-8") {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function stageBadge(stage) {
  const map = { "申报中": "gray", "已立项": "green", "实施中": "", "待验收": "orange", "已验收": "green", "绩效跟踪": "", "已完结": "gray", "中止": "orange", "撤销": "orange" };
  return `<span class="badge ${map[stage] || ""}">${escapeHtml(stage || "—")}</span>`;
}

export function kv(key, value, full = false) {
  return `<div class="item"${full ? ' style="grid-column:1/-1"' : ""}><div class="k">${escapeHtml(key)}</div><div class="v">${value ?? "—"}</div></div>`;
}

export function csvEscape(value) {
  const text = value == null ? "" : String(value);
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

export function collectAdvancedFilters(root) {
  return Array.from(root.querySelectorAll(".adv-row")).map(row => ({
    field: row.querySelector(".af-field").value,
    op: row.querySelector(".af-op").value,
    value: row.querySelector(".af-val").value.trim(),
  })).filter(item => item.field && item.op && item.value);
}

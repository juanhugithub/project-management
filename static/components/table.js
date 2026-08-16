import { clear } from "../core/dom.js";

/**
 * 渲染纯展示型表格。业务页面提供列定义与单元格内容，本组件不关心数据请求、排序规则
 * 或行内操作，从而可以同时服务项目与企业两个列表。
 */
export function renderTable(table, { columns, rows, emptyText = "暂无数据", rowKey = "id" }) {
  const thead = table.tHead || table.createTHead();
  const tbody = table.tBodies[0] || table.createTBody();
  clear(thead);
  clear(tbody);

  const headerRow = thead.insertRow();
  for (const column of columns) {
    const cell = document.createElement("th");
    cell.textContent = column.label;
    if (column.className) cell.className = column.className;
    if (column.scope) cell.scope = column.scope;
    headerRow.append(cell);
  }

  if (!rows.length) {
    const row = tbody.insertRow();
    const cell = row.insertCell();
    cell.colSpan = columns.length;
    cell.className = "table-empty";
    cell.textContent = emptyText;
    return;
  }

  for (const item of rows) {
    const row = tbody.insertRow();
    row.dataset.rowKey = String(item[rowKey]);
    for (const column of columns) {
      const cell = row.insertCell();
      if (column.className) cell.className = column.className;
      const content = column.render ? column.render(item) : item[column.key];
      if (content instanceof Node) cell.append(content);
      else cell.textContent = content ?? "";
    }
  }
}

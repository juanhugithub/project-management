import { clear } from "../core/dom.js";

/**
 * 统一渲染上一页、当前页和下一页。点击事件只回传目标页码，具体加载逻辑由业务页面负责。
 */
export function renderPagination(container, { page = 1, totalPages = 0, onChange } = {}) {
  clear(container);
  if (!totalPages) return;

  const createButton = (label, targetPage, disabled) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "small";
    button.textContent = label;
    button.disabled = disabled;
    button.addEventListener("click", () => onChange?.(targetPage));
    return button;
  };

  container.append(
    createButton("上一页", page - 1, page <= 1),
    Object.assign(document.createElement("span"), { textContent: `第 ${page} / ${totalPages} 页` }),
    createButton("下一页", page + 1, page >= totalPages),
  );
}

/** 将同一分页状态同步到上下两个分页容器。 */
export function renderPaginations(containers, options) {
  for (const container of containers) renderPagination(container, options);
}

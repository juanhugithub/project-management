/**
 * 无障碍 Toast 视图。元素应在 index.html 中预先存在，避免运行时创建多个提示容器。
 */
export function createToast(selector = "#toast", { duration = 2600 } = {}) {
  const element = document.querySelector(selector);
  if (!element) throw new Error(`未找到 Toast 容器：${selector}`);

  element.setAttribute("role", "status");
  element.setAttribute("aria-live", "polite");
  let timer = null;

  function show(message, type = "ok") {
    element.textContent = message;
    element.className = `toast ${type}`;
    clearTimeout(timer);
    timer = window.setTimeout(hide, duration);
  }

  function hide() {
    element.classList.add("hidden");
  }

  return { show, hide };
}

let defaultToast = null;
export function initToast(selector = "#toast", options = {}) {
  defaultToast = createToast(selector, options);
  return defaultToast;
}

/** 兼容页面直接调用 toast(message, type) 的迁移接口。 */
export function toast(message, type = "ok") {
  if (!defaultToast) defaultToast = createToast();
  defaultToast.show(message, type);
}

import { clear } from "../core/dom.js";

/**
 * 填充下拉筛选项并保留当前选择。筛选状态归业务页面所有，本组件只负责控件结构展示。
 */
export function renderSelectOptions(select, options, { placeholder = "全部", value = "" } = {}) {
  clear(select);
  const placeholderOption = new Option(placeholder, "");
  select.add(placeholderOption);
  for (const option of options) {
    const item = typeof option === "object" ? option : { label: option, value: option };
    select.add(new Option(item.label, item.value, false, String(item.value) === String(value)));
  }
}

/** 从一组具名控件读取筛选值，空值不纳入请求参数。 */
export function collectFilters(root, names) {
  return names.reduce((filters, name) => {
    const control = root.querySelector(`[name="${CSS.escape(name)}"]`);
    const value = control?.value?.trim();
    if (value) filters[name] = value;
    return filters;
  }, {});
}

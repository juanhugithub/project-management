/** 表单字段定义和 HTML 构造集中维护，项目与企业页面共用同一套规则。 */
import { escapeHtml } from "./dom.js";
import { FUND_STATUS, NODE_STATUS, STAGES } from "./constants.js";

export const FORMS = {
  enterprise: [
    { k: "name", label: "企业名称", type: "text", required: true },
    { k: "credit_code", label: "统一社会信用代码", type: "text" },
    { k: "enterprise_type", label: "企业类型", type: "select", dict: "enterprise_type" },
    { k: "district", label: "区镇", type: "select", dict: "district" },
    { k: "qualifications", label: "资质", type: "text" }, { k: "contact_person", label: "联系人", type: "text" },
    { k: "contact_phone", label: "联系电话", type: "text" }, { k: "address", label: "地址", type: "text" },
    { k: "note", label: "备注", type: "textarea", full: true },
  ],
  project: [
    { k: "name", label: "项目名称", type: "text", required: true }, { k: "project_no", label: "项目编号/文号", type: "text" },
    { k: "level", label: "层级", type: "select", dict: "level" }, { k: "category", label: "类型", type: "select", dict: "category" },
    { k: "enterprise_id", label: "承担企业", type: "enterprise" }, { k: "total_amount", label: "总金额(万元)", type: "number" },
    { k: "start_date", label: "开始日期", type: "date" }, { k: "end_date", label: "结束日期", type: "date" },
    { k: "stage", label: "当前阶段", type: "select", options: STAGES }, { k: "match_ratio", label: "配套比例(如1=1:1)", type: "number" },
    { k: "leader", label: "项目负责人", type: "text" }, { k: "contact_phone", label: "联系人手机号", type: "text" },
    { k: "note", label: "备注", type: "textarea", full: true },
  ],
  funding: [
    { k: "source_type", label: "资金来源", type: "select", dict: "funding_source" }, { k: "amount", label: "金额(万元)", type: "number" },
    { k: "batch", label: "批次", type: "text" }, { k: "plan_date", label: "应拨时间", type: "date" },
    { k: "actual_date", label: "实拨时间", type: "date" }, { k: "status", label: "状态", type: "select", options: FUND_STATUS }, { k: "note", label: "备注", type: "text" },
  ],
  node: [
    { k: "node_type", label: "节点类型", type: "select", dict: "node_type" }, { k: "plan_date", label: "计划时间", type: "date" },
    { k: "actual_date", label: "实际完成", type: "date" }, { k: "status", label: "状态", type: "select", options: NODE_STATUS },
    { k: "has_major_change", label: "重大事项变更", type: "checkbox" }, { k: "note", label: "备注", type: "text" },
  ],
};

export function fieldOptions(field, context) {
  if (field.options) return field.options;
  if (field.dict) return context.state.getState().dict?.[field.dict] || [];
  return [];
}

export function buildFieldHtml(field, value, context) {
  const required = field.required ? " required" : "";
  const val = value ?? "";
  const cls = field.full ? ' class="full"' : "";
  if (field.type === "select") {
    const options = fieldOptions(field, context).map(option => `<option value="${escapeHtml(option)}"${String(val) === String(option) ? " selected" : ""}>${escapeHtml(option)}</option>`).join("");
    return `<label${cls}><span class="t">${field.label}</span><select name="${field.k}"${required}><option value="">请选择</option>${options}</select></label>`;
  }
  if (field.type === "enterprise") {
    const enterprises = context.state.getState().enterprises || [];
    const options = enterprises.map(item => `<option value="${item.id}"${Number(val) === Number(item.id) ? " selected" : ""}>${escapeHtml(item.name)}</option>`).join("");
    return `<label${cls}><span class="t">${field.label}</span><select name="${field.k}"${required}><option value="">请选择</option>${options}</select></label>`;
  }
  if (field.type === "textarea") return `<label${cls}><span class="t">${field.label}</span><textarea name="${field.k}">${escapeHtml(val)}</textarea></label>`;
  if (field.type === "checkbox") return `<label${cls}><span class="t">${field.label}</span><input type="checkbox" name="${field.k}"${value ? " checked" : ""}></label>`;
  return `<label${cls}><span class="t">${field.label}</span><input type="${field.type}" name="${field.k}" value="${escapeHtml(val)}"${required}></label>`;
}

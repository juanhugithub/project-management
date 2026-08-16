/** 业务字典常量集中维护，页面模块只依赖这里，避免重复定义状态值。 */
export const STAGES = ["申报中", "已立项", "实施中", "待验收", "已验收", "绩效跟踪", "已完结", "中止", "撤销"];
export const FUND_STATUS = ["未拨付", "已拨付", "已到账"];
export const NODE_STATUS = ["待办", "已完成", "已逾期"];

export const ADV_OPS = [
  { v: "eq", l: "等于" },
  { v: "contains", l: "包含" },
  { v: "gte", l: "大于等于" },
  { v: "lte", l: "小于等于" },
];

export const PROJECT_ADV_FIELDS = [
  { v: "name", l: "项目名称" }, { v: "project_no", l: "项目编号" },
  { v: "level", l: "层级" }, { v: "category", l: "类型" }, { v: "stage", l: "阶段" },
  { v: "enterprise_name", l: "承担企业" }, { v: "district", l: "区镇" },
  { v: "total_amount", l: "总金额(万元)" }, { v: "match_ratio", l: "配套比例" },
  { v: "start_date", l: "开始日期" }, { v: "end_date", l: "结束日期" },
  { v: "leader", l: "负责人" }, { v: "contact_phone", l: "联系人手机" },
];

export const ENTERPRISE_ADV_FIELDS = [
  { v: "name", l: "企业名称" }, { v: "credit_code", l: "统一社会信用代码" },
  { v: "enterprise_type", l: "企业类型" }, { v: "district", l: "区镇" },
  { v: "qualifications", l: "资质" }, { v: "contact_person", l: "联系人" },
  { v: "contact_phone", l: "联系电话" }, { v: "address", l: "地址" },
  { v: "project_count", l: "项目数" }, { v: "total_amount_sum", l: "累计金额(万元)" },
];

export const EXPORT_FIELDS = [
  { k: "name", l: "项目名称" }, { k: "project_no", l: "项目编号/文号" },
  { k: "level", l: "层级" }, { k: "category", l: "类型" },
  { k: "enterprise_name", l: "承担企业" }, { k: "enterprise_district", l: "区镇" },
  { k: "total_amount", l: "总金额(万元)" }, { k: "disbursed_total", l: "已拨付(万元)" },
  { k: "stage", l: "阶段" }, { k: "leader", l: "负责人" },
  { k: "contact_phone", l: "联系人手机" }, { k: "start_date", l: "开始日期" },
  { k: "end_date", l: "结束日期" }, { k: "match_ratio", l: "配套比例" },
  { k: "note", l: "备注" },
];

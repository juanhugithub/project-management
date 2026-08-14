"""G9 模板任务数据层：用稳定模板把台账事实提供给任意获授权 Agent。"""
import hashlib
import json
from datetime import date, timedelta
from pathlib import Path


class TemplateError(ValueError):
    """模板参数、填报内容或衍生稿登记不符合固定契约时抛出。"""


_ROOT = Path(__file__).resolve().parents[1]
_TEMPLATE_PATHS = (
    _ROOT / "templates" / "quarterly_funding_execution.v1.json",
    _ROOT / "templates" / "acceptance_risk_list.v1.json",
)


def _canonical_json(value):
    """使用排序且无空白的 JSON，保证跨 Agent 的快照哈希完全一致。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _definitions():
    """模板文件是 Gitee 版本管理的公共协议，不从业务数据中推断字段。"""
    return [json.loads(path.read_text(encoding="utf-8")) for path in _TEMPLATE_PATHS]


def list_reporting_templates():
    """返回可供 Agent 发现的固定模板目录，不暴露不稳定的表结构。"""
    return [
        {"template_id": item["template_id"], "version": item["version"], "name": item["name"], "description": item["description"]}
        for item in _definitions()
    ]


def get_template_schema(template_id, version=None):
    """按标识和可选版本读取模板契约，版本不匹配时明确拒绝。"""
    for item in _definitions():
        if item["template_id"] == template_id and (version is None or item["version"] == version):
            return item
    raise TemplateError("不存在指定的模板或模板版本")


def _require_int(value, name):
    if isinstance(value, bool) or not isinstance(value, int):
        raise TemplateError(f"{name} 必须是整数")
    return value


def _require_date(value, name):
    if not isinstance(value, str):
        raise TemplateError(f"{name} 必须是 YYYY-MM-DD 日期")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise TemplateError(f"{name} 必须是 YYYY-MM-DD 日期") from exc


def _funding_dataset(conn, params):
    """季度统计严格以计划日期归属季度，使用既有三资金口径且排除软删除。"""
    year = _require_int(params.get("year"), "year")
    quarter = _require_int(params.get("quarter"), "quarter")
    if quarter not in (1, 2, 3, 4):
        raise TemplateError("quarter 必须为 1 至 4")
    district = params.get("district")
    if district is not None and not isinstance(district, str):
        raise TemplateError("district 必须是字符串")
    month_end = quarter * 3
    cutoff = f"{year:04d}-{month_end:02d}-{[31, 30, 30, 31][quarter - 1]:02d}"
    where = ["p.is_deleted=0", "e.is_deleted=0"]
    values = [cutoff, cutoff, cutoff]
    if district:
        where.append("e.district=?")
        values.append(district)
    sql = f"""
        SELECT p.id AS project_id, p.project_no, p.name AS project_name, e.name AS enterprise_name,
               e.district, p.total_amount,
               COALESCE(SUM(CASE WHEN f.is_deleted=0 AND f.plan_date IS NOT NULL AND f.plan_date<=? THEN f.amount ELSE 0 END),0) AS planned_total,
               COALESCE(SUM(CASE WHEN f.is_deleted=0 AND f.actual_date IS NOT NULL AND f.actual_date<=? AND f.status IN ('已拨付','已到账') THEN f.amount ELSE 0 END),0) AS disbursed_total,
               COALESCE(SUM(CASE WHEN f.is_deleted=0 AND f.actual_date IS NOT NULL AND f.actual_date<=? AND f.status='已到账' THEN f.amount ELSE 0 END),0) AS received_total
        FROM project p JOIN enterprise e ON e.id=p.enterprise_id LEFT JOIN funding f ON f.project_id=p.id
        WHERE {' AND '.join(where)} GROUP BY p.id ORDER BY p.project_no, p.id
    """
    rows = [dict(row) for row in conn.execute(sql, values).fetchall()]
    return {"template_id": "quarterly_funding_execution", "template_version": "1.0.0", "parameters": {"year": year, "quarter": quarter, **({"district": district} if district else {})}, "money_unit": "万元", "rows": rows}


def _acceptance_dataset(conn, params):
    """验收风险只以明确阶段或未完成验收节点判定，不让 Agent 自行猜测风险。"""
    reference = _require_date(params.get("reference_date"), "reference_date")
    days = _require_int(params.get("days"), "days")
    if days < 0:
        raise TemplateError("days 不得小于 0")
    district = params.get("district")
    if district is not None and not isinstance(district, str):
        raise TemplateError("district 必须是字符串")
    deadline = (reference + timedelta(days=days)).isoformat()
    where = ["p.is_deleted=0", "e.is_deleted=0", "(p.stage='待验收' OR (n.id IS NOT NULL AND n.plan_date<=?))"]
    values = [deadline]
    if district:
        where.append("e.district=?")
        values.append(district)
    sql = f"""
        SELECT p.id AS project_id, p.project_no, p.name AS project_name, e.name AS enterprise_name,
               e.district, p.stage, n.plan_date AS acceptance_plan_date,
               CASE WHEN n.plan_date IS NOT NULL AND n.plan_date<? THEN '验收节点已逾期'
                    WHEN n.plan_date IS NOT NULL THEN '验收节点临期'
                    ELSE '项目处于待验收阶段' END AS risk_reason,
               COALESCE(SUM(CASE WHEN f.is_deleted=0 AND f.plan_date IS NOT NULL THEN f.amount ELSE 0 END),0) AS planned_total,
               COALESCE(SUM(CASE WHEN f.is_deleted=0 AND f.status='已到账' THEN f.amount ELSE 0 END),0) AS received_total
        FROM project p JOIN enterprise e ON e.id=p.enterprise_id
        LEFT JOIN node n ON n.project_id=p.id AND n.is_deleted=0 AND n.node_type='验收' AND (n.actual_date IS NULL OR n.actual_date='')
        LEFT JOIN funding f ON f.project_id=p.id
        WHERE {' AND '.join(where)} GROUP BY p.id, n.id ORDER BY acceptance_plan_date, p.project_no, p.id
    """
    rows = [dict(row) for row in conn.execute(sql, [reference.isoformat(), *values]).fetchall()]
    return {"template_id": "acceptance_risk_list", "template_version": "1.0.0", "parameters": {"reference_date": reference.isoformat(), "days": days, **({"district": district} if district else {})}, "money_unit": "万元", "rows": rows}


def build_template_dataset(conn, template_id, parameters, version=None):
    """构建可复算的结构化数据集；输出及哈希仅由固定参数和当前事实决定。"""
    definition = get_template_schema(template_id, version)
    if not isinstance(parameters, dict):
        raise TemplateError("parameters 必须是对象")
    if template_id == "quarterly_funding_execution":
        dataset = _funding_dataset(conn, parameters)
    elif template_id == "acceptance_risk_list":
        dataset = _acceptance_dataset(conn, parameters)
    else:  # get_template_schema 已保护；此处保留不可变分派的明确错误。
        raise TemplateError("模板尚未配置数据集构建器")
    dataset["schema"] = definition["columns"]
    dataset["source_project_ids"] = sorted({row["project_id"] for row in dataset["rows"]})
    dataset["snapshot_hash"] = hashlib.sha256(_canonical_json(dataset).encode("utf-8")).hexdigest()
    return dataset


def validate_filled_template(template_id, rows, version=None):
    """校验填表结构与必填项，不擅自修改 Agent 输出或补造台账事实。"""
    definition = get_template_schema(template_id, version)
    if not isinstance(rows, list):
        raise TemplateError("rows 必须是数组")
    names = [column["name"] for column in definition["columns"]]
    required = {column["name"] for column in definition["columns"] if column.get("required")}
    errors = []
    for number, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            errors.append({"row_no": number, "field": "*", "message": "行必须是对象"})
            continue
        for field in row:
            if field not in names:
                errors.append({"row_no": number, "field": field, "message": "字段不属于模板"})
        for field in required:
            if row.get(field) in (None, ""):
                errors.append({"row_no": number, "field": field, "message": "必填字段不能为空"})
    return {"valid": not errors, "errors": errors, "template_id": template_id, "template_version": definition["version"]}


def register_derivative_draft(conn, dataset, agent_model, human_status="待确认", export_path=None, note=None):
    """登记 Agent 的衍生稿证据；登记不改变任何项目、资金或节点正式事实。"""
    if not isinstance(dataset, dict) or not dataset.get("snapshot_hash"):
        raise TemplateError("必须登记 build_template_dataset 返回的数据集")
    definition = get_template_schema(dataset.get("template_id"), dataset.get("template_version"))
    if not isinstance(agent_model, str) or not agent_model.strip():
        raise TemplateError("agent_model 必须明确记录")
    if human_status not in ("待确认", "已确认", "已驳回"):
        raise TemplateError("human_status 不合法")
    if export_path is not None and not isinstance(export_path, str):
        raise TemplateError("export_path 必须是字符串")
    source_ids = dataset.get("source_project_ids")
    if not isinstance(source_ids, list) or any(not isinstance(item, int) for item in source_ids):
        raise TemplateError("source_project_ids 必须是项目整数标识列表")
    cur = conn.execute(
        "INSERT INTO derivative_draft(template_id,template_version,mcp_parameters_json,dataset_snapshot_hash,source_project_ids_json,agent_model,human_status,export_path,note,confirmed_at) VALUES(?,?,?,?,?,?,?,?,?,CASE WHEN ?='已确认' THEN datetime('now','localtime') ELSE NULL END)",
        (definition["template_id"], definition["version"], _canonical_json(dataset["parameters"]), dataset["snapshot_hash"], _canonical_json(sorted(set(source_ids))), agent_model.strip(), human_status, export_path, note, human_status),
    )
    conn.commit()
    return dict(conn.execute("SELECT * FROM derivative_draft WHERE id=?", (cur.lastrowid,)).fetchone())

"""G2 写入校验；这里不做猜测性修复，非法输入一律明确拒绝。"""
import datetime
import math
from decimal import Decimal, InvalidOperation

from .errors import DomainError

NORMAL_STAGES = ("申报中", "已立项", "实施中", "待验收", "已验收", "绩效跟踪", "已完结")
ALL_STAGES = set(NORMAL_STAGES) | {"中止", "撤销"}
DICT_FIELDS = {
    ("enterprise", "enterprise_type"): "enterprise_type",
    ("enterprise", "district"): "district",
    ("project", "level"): "level",
    ("project", "category"): "category",
    ("funding", "source_type"): "funding_source",
    ("node", "node_type"): "node_type",
}


def amount(value, field):
    """金额保持 SQLite 当前数值列兼容，但严格执行非负且最多两位小数。"""
    if value is None:
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise DomainError(f"{field} 必须是非负且最多两位小数的金额")
    if not number.is_finite() or number < 0 or number.as_tuple().exponent < -2:
        raise DomainError(f"{field} 必须是非负且最多两位小数的金额")
    return float(number)


def date(value, field):
    if value is None:
        return None
    if not isinstance(value, str) or len(value) != 10:
        raise DomainError(f"{field} 必须是有效 YYYY-MM-DD 日期")
    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        raise DomainError(f"{field} 必须是有效 YYYY-MM-DD 日期")
    return value


def validate_dicts(conn, table, payload):
    for (target, field), dict_type in DICT_FIELDS.items():
        if target != table or payload.get(field) is None:
            continue
        row = conn.execute("SELECT 1 FROM dict_item WHERE dict_type=? AND value=? AND is_active=1",
                           (dict_type, payload[field])).fetchone()
        if not row:
            raise DomainError(f"{field} 必须引用启用的字典项")


def validate_funding(payload):
    if "amount" in payload:
        payload["amount"] = amount(payload["amount"], "amount")
    for field in ("plan_date", "actual_date"):
        if field in payload:
            payload[field] = date(payload[field], field)
    status = payload.get("status")
    if status is not None and status not in {"未拨付", "已拨付", "已到账"}:
        raise DomainError("status 必须是未拨付、已拨付或已到账")
    if status in {"已拨付", "已到账"} and not payload.get("actual_date"):
        raise DomainError("已拨付或已到账资金必须填写 actual_date")
    if status == "未拨付" and payload.get("actual_date"):
        raise DomainError("未拨付资金不得填写 actual_date")


def validate_project(conn, payload, current=None):
    merged = dict(current or {})
    merged.update(payload)
    if "total_amount" in payload:
        payload["total_amount"] = amount(payload["total_amount"], "total_amount")
        merged["total_amount"] = payload["total_amount"]
    for field in ("start_date", "end_date"):
        if field in payload:
            payload[field] = date(payload[field], field)
            merged[field] = payload[field]
    if merged.get("start_date") and merged.get("end_date") and merged["start_date"] > merged["end_date"]:
        raise DomainError("start_date 不得晚于 end_date")
    stage = payload.get("stage")
    if stage is not None:
        if stage not in ALL_STAGES:
            raise DomainError("stage 不是有效阶段")
        old = (current or {}).get("stage")
        if old is not None and old != stage and not allowed_stage_transition(old, stage):
            raise DomainError(f"不允许阶段流转：{old}→{stage}")
    validate_dicts(conn, "project", payload)


def allowed_stage_transition(old, new):
    """撤销只允许显式写入且不可恢复；其来源授权尚未确认，故不臆造来源限制。"""
    if old in {"中止", "撤销", "已完结"}:
        return False
    if new == "撤销":
        return True
    if new == "中止":
        return old in {"已立项", "实施中", "待验收"}
    return old in NORMAL_STAGES and new in NORMAL_STAGES and NORMAL_STAGES.index(new) == NORMAL_STAGES.index(old) + 1

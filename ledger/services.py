"""G2 最小事务写服务。所有调用者先走这里，再提交。"""
import sqlite3
from .errors import DomainError
from .validation import validate_dicts, validate_funding, validate_project, date

def create(conn, table, payload):
    if table == "project":
        enterprise_id = payload.get("enterprise_id")
        if not enterprise_id or not conn.execute("SELECT 1 FROM enterprise WHERE id=?", (enterprise_id,)).fetchone():
            raise DomainError("enterprise_id 必须引用存在的承担企业")
        validate_project(conn, payload)
    elif table == "funding":
        validate_funding(payload); validate_dicts(conn, table, payload)
    elif table == "node":
        for field in ("plan_date", "actual_date"):
            if field in payload: payload[field] = date(payload[field], field)
        validate_dicts(conn, table, payload)
    elif table == "enterprise": validate_dicts(conn, table, payload)
    cols = list(payload)
    try:
        cur = conn.execute(f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})", [payload[k] for k in cols])
    except sqlite3.IntegrityError as exc:
        raise DomainError(str(exc))
    conn.commit(); return dict(conn.execute(f"SELECT * FROM {table} WHERE id=?", (cur.lastrowid,)).fetchone())

def update_project(conn, project_id, payload):
    current = conn.execute("SELECT * FROM project WHERE id=?", (project_id,)).fetchone()
    if not current: raise DomainError("项目不存在")
    validate_project(conn, payload, dict(current))
    if "enterprise_id" in payload and not conn.execute("SELECT 1 FROM enterprise WHERE id=?", (payload["enterprise_id"],)).fetchone(): raise DomainError("enterprise_id 必须引用存在的承担企业")
    sets = ", ".join(f"{key}=?" for key in payload)
    try: conn.execute(f"UPDATE project SET {sets}, updated_at=datetime('now','localtime') WHERE id=?", [*payload.values(), project_id])
    except sqlite3.IntegrityError as exc: raise DomainError(str(exc))
    conn.commit(); return dict(conn.execute("SELECT * FROM project WHERE id=?", (project_id,)).fetchone())


def update(conn, table, record_id, payload):
    """子表更新先与现有记录合并校验，避免只改 status 时绕过日期约束。"""
    current = conn.execute(f"SELECT * FROM {table} WHERE id=?", (record_id,)).fetchone()
    if not current:
        raise DomainError("记录不存在")
    merged = dict(current); merged.update(payload)
    if table == "funding":
        validate_funding(merged); validate_dicts(conn, table, merged)
    elif table == "node":
        for field in ("plan_date", "actual_date"):
            if field in merged: merged[field] = date(merged[field], field)
        validate_dicts(conn, table, merged)
    sets = ", ".join(f"{key}=?" for key in payload)
    try:
        conn.execute(f"UPDATE {table} SET {sets} WHERE id=?", [*payload.values(), record_id])
    except sqlite3.IntegrityError as exc:
        raise DomainError(str(exc))
    conn.commit(); return dict(conn.execute(f"SELECT * FROM {table} WHERE id=?", (record_id,)).fetchone())

"""G2/G3 领域写服务：所有写入口在此集中执行归档、软删除和审计。"""
import json
import sqlite3

from .errors import DomainError
from .validation import validate_dicts, validate_funding, validate_project, date


def _summary(row):
    """将数据库行稳定编码为审计摘要，保留恢复和追溯需要的原始事实。"""
    return json.dumps(dict(row), ensure_ascii=False, sort_keys=True) if row else None


def _audit(conn, action, object_type, object_id, before=None, after=None, reason=None):
    """在同一事务写入本地单人台账审计，避免业务成功但审计缺失。"""
    conn.execute(
        "INSERT INTO audit_log(ts,operator,action,object_type,object_id,before_summary,after_summary,reason) "
        "VALUES(datetime('now','localtime'),'local-user',?,?,?,?,?,?)",
        (action, object_type, object_id, _summary(before), _summary(after), reason),
    )


def archived_years(conn):
    row = conn.execute("SELECT value FROM system_config WHERE key='archived_years'").fetchone()
    return {year.strip() for year in (row[0] if row else '').split(',') if year.strip()}


def _project_for_record(conn, table, record_id):
    if table == 'project':
        return conn.execute("SELECT * FROM project WHERE id=?", (record_id,)).fetchone()
    return conn.execute(
        f"SELECT p.* FROM {table} c JOIN project p ON c.project_id=p.id WHERE c.id=?", (record_id,)
    ).fetchone()


def _require_mutable_project(conn, project):
    """按项目开始年度冻结，项目自身和一切子表写操作使用同一判断。"""
    if not project:
        raise DomainError('记录不存在')
    if project['start_date'] and project['start_date'][:4] in archived_years(conn):
        raise DomainError('该年度项目已归档，禁止写入')


def create(conn, table, payload, commit=True):
    if table == 'project':
        start_date = payload.get('start_date')
        if start_date and start_date[:4] in archived_years(conn):
            raise DomainError('该年度项目已归档，禁止新增')
        enterprise_id = payload.get('enterprise_id')
        enterprise = conn.execute("SELECT 1 FROM enterprise WHERE id=? AND is_deleted=0", (enterprise_id,)).fetchone()
        if not enterprise:
            raise DomainError('enterprise_id 必须引用存在且未删除的承担企业')
        validate_project(conn, payload)
    elif table in ('funding', 'node'):
        _require_mutable_project(conn, conn.execute("SELECT * FROM project WHERE id=? AND is_deleted=0", (payload.get('project_id'),)).fetchone())
        if table == 'funding':
            validate_funding(payload)
        else:
            for field in ('plan_date', 'actual_date'):
                if field in payload:
                    payload[field] = date(payload[field], field)
        validate_dicts(conn, table, payload)
    elif table == 'enterprise':
        validate_dicts(conn, table, payload)
    cols = list(payload)
    try:
        cur = conn.execute(f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})", [payload[k] for k in cols])
    except sqlite3.IntegrityError as exc:
        raise DomainError(str(exc))
    row = conn.execute(f"SELECT * FROM {table} WHERE id=?", (cur.lastrowid,)).fetchone()
    _audit(conn, 'create', table, cur.lastrowid, after=row)
    if commit:
        conn.commit()
    return dict(row)


def update(conn, table, record_id, payload):
    current = conn.execute(f"SELECT * FROM {table} WHERE id=? AND is_deleted=0", (record_id,)).fetchone()
    if not current:
        raise DomainError('记录不存在')
    if table in ('project', 'funding', 'node'):
        _require_mutable_project(conn, _project_for_record(conn, table, record_id))
    merged = dict(current); merged.update(payload)
    if table == 'project':
        validate_project(conn, payload, dict(current))
        if 'enterprise_id' in payload and not conn.execute("SELECT 1 FROM enterprise WHERE id=? AND is_deleted=0", (payload['enterprise_id'],)).fetchone():
            raise DomainError('enterprise_id 必须引用存在且未删除的承担企业')
    elif table == 'funding':
        validate_funding(merged); validate_dicts(conn, table, merged)
    elif table == 'node':
        for field in ('plan_date', 'actual_date'):
            if field in merged: merged[field] = date(merged[field], field)
        validate_dicts(conn, table, merged)
    sets = ', '.join(f'{key}=?' for key in payload)
    try:
        conn.execute(f"UPDATE {table} SET {sets} WHERE id=?", [*payload.values(), record_id])
    except sqlite3.IntegrityError as exc:
        raise DomainError(str(exc))
    row = conn.execute(f"SELECT * FROM {table} WHERE id=?", (record_id,)).fetchone()
    _audit(conn, 'update', table, record_id, current, row)
    conn.commit()
    return dict(row)


def soft_delete(conn, table, record_id, reason=None):
    """只标记删除，子记录保持原状，以便逐条恢复并防止隐式级联丢失。"""
    current = conn.execute(f"SELECT * FROM {table} WHERE id=? AND is_deleted=0", (record_id,)).fetchone()
    if not current:
        raise DomainError('记录不存在')
    if table in ('project', 'funding', 'node'):
        _require_mutable_project(conn, _project_for_record(conn, table, record_id))
    conn.execute(f"UPDATE {table} SET is_deleted=1, deleted_at=datetime('now','localtime') WHERE id=?", (record_id,))
    row = conn.execute(f"SELECT * FROM {table} WHERE id=?", (record_id,)).fetchone()
    _audit(conn, 'delete', table, record_id, current, row, reason)
    conn.commit()


def restore(conn, table, record_id, reason):
    """恢复前重验年度冻结和父引用，拒绝恢复为孤儿记录。"""
    current = conn.execute(f"SELECT * FROM {table} WHERE id=? AND is_deleted=1", (record_id,)).fetchone()
    if not current:
        raise DomainError('不存在可恢复的已删除记录')
    if table in ('funding', 'node'):
        parent = conn.execute("SELECT * FROM project WHERE id=? AND is_deleted=0", (current['project_id'],)).fetchone()
        if not parent:
            raise DomainError('父项目不存在或已删除，不能恢复')
        _require_mutable_project(conn, parent)
    elif table == 'project':
        _require_mutable_project(conn, current)
        if not conn.execute("SELECT 1 FROM enterprise WHERE id=? AND is_deleted=0", (current['enterprise_id'],)).fetchone():
            raise DomainError('承担企业不存在或已删除，不能恢复')
    conn.execute(f"UPDATE {table} SET is_deleted=0, deleted_at=NULL WHERE id=?", (record_id,))
    row = conn.execute(f"SELECT * FROM {table} WHERE id=?", (record_id,)).fetchone()
    _audit(conn, 'restore', table, record_id, current, row, reason)
    conn.commit()
    return dict(row)


def set_archived_years(conn, years, reason=None):
    """归档配置变更也必须留痕；解除归档必须明确给出理由。"""
    before = conn.execute("SELECT value FROM system_config WHERE key='archived_years'").fetchone()
    before_years = {x for x in (before[0] if before else '').split(',') if x}
    after_years = {str(x).strip() for x in years if str(x).strip()}
    if before_years - after_years and not reason:
        raise DomainError('解除归档必须填写理由')
    conn.execute("INSERT INTO system_config(key,value) VALUES('archived_years',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (','.join(sorted(after_years)),))
    action = 'archive' if after_years - before_years else 'unarchive'
    _audit(conn, action, 'system', None, {'archived_years': sorted(before_years)}, {'archived_years': sorted(after_years)}, reason)
    conn.commit()

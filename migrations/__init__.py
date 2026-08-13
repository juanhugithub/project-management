"""版本化 SQLite 迁移入口；调用方必须显式传入目标数据库。"""
from pathlib import Path


def _apply_g3_soft_delete(conn, path):
    """按当前表结构升级 G3 字段，避免全新库重复添加已存在列。"""
    pending = []
    for table in ("enterprise", "project", "funding", "node"):
        columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if "is_deleted" not in columns:
            pending.append(f"ALTER TABLE {table} ADD COLUMN is_deleted INTEGER NOT NULL DEFAULT 0;")
        if "deleted_at" not in columns:
            pending.append(f"ALTER TABLE {table} ADD COLUMN deleted_at TEXT;")
    script = path.read_text(encoding="utf-8")
    audit_sql = script[script.index("-- M004"):]
    conn.executescript("\n".join(pending) + "\n" + audit_sql)


def _apply_g7_identity_enterprise_status(conn, path):
    """新库已有 G7 字段，老库才执行 ALTER；两类数据库均可显式迁移。"""
    enterprise_columns = {row[1] for row in conn.execute("PRAGMA table_info(enterprise)")}
    project_columns = {row[1] for row in conn.execute("PRAGMA table_info(project)")}
    pending = []
    if "is_active" not in enterprise_columns:
        pending.append("ALTER TABLE enterprise ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1;")
    if "identity_status" not in project_columns:
        pending.append("ALTER TABLE project ADD COLUMN identity_status TEXT NOT NULL DEFAULT '正式编号';")
    conn.executescript("\n".join(pending) + "\n" + "UPDATE project SET identity_status = CASE WHEN project_no IS NULL OR project_no = '' THEN '人工编号待补' ELSE '正式编号' END;")


def apply(conn, directory=None):
    directory = Path(directory or Path(__file__).parent)
    conn.execute("CREATE TABLE IF NOT EXISTS schema_migration (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
    done = {row[0] for row in conn.execute("SELECT version FROM schema_migration")}
    for path in sorted(directory.glob("[0-9][0-9][0-9]_*.sql")):
        if path.name in done: continue
        with conn:
            if path.name == "002_g3_soft_delete_audit.sql":
                _apply_g3_soft_delete(conn, path)
            elif path.name == "004_g7_identity_enterprise_status.sql":
                _apply_g7_identity_enterprise_status(conn, path)
            else:
                conn.executescript(path.read_text(encoding="utf-8"))
            conn.execute("INSERT INTO schema_migration(version) VALUES (?)", (path.name,))

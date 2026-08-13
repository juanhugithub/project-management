# -*- coding: utf-8 -*-
"""G7 身份编号与企业停用契约：只使用临时库，覆盖迁移和服务层事实。"""
import sqlite3
from pathlib import Path

from conftest import db_conn
from migrations import apply as apply_migrations


def test_g7_migration_marks_legacy_no_number_project_as_manual_pending(tmp_path):
    """老库的无编号历史记录迁移后必须可识别，不可被伪装成正式编号项目。"""
    root = Path(__file__).resolve().parents[1]
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript((root / "schema.sql").read_text(encoding="utf-8"))
        conn.execute("INSERT INTO enterprise(name, credit_code) VALUES('迁移企业', '91320000G7MIG01')")
        conn.execute("INSERT INTO project(name, enterprise_id, stage) VALUES('旧无编号项目', 1, '已立项')")
        # 模拟 G7 前数据库：先移除新列，再让显式迁移补齐。
        conn.execute("ALTER TABLE enterprise DROP COLUMN is_active")
        conn.execute("ALTER TABLE project DROP COLUMN identity_status")
        conn.commit()
        apply_migrations(conn)
        row = conn.execute("SELECT identity_status FROM project WHERE id=1").fetchone()
        assert row["identity_status"] == "人工编号待补"
        assert conn.execute("SELECT is_active FROM enterprise WHERE id=1").fetchone()["is_active"] == 1
    finally:
        conn.close()


def test_identity_status_is_returned_in_project_api(tmp_db, client):
    """API 必须回传编号身份，前端才能将人工待补项目纳入编号补正工作清单。"""
    status, ent = client.request("POST", "/api/enterprises", {"name": "身份读取企业", "credit_code": "91320000G7API01"})
    assert status == 200
    status, project = client.request("POST", "/api/projects", {
        "name": "身份读取项目", "enterprise_id": ent["id"], "identity_status": "人工编号待补", "stage": "已立项"})
    assert status == 200
    status, listed = client.request("GET", "/api/projects")
    assert status == 200
    assert next(row for row in listed if row["id"] == project["id"])["identity_status"] == "人工编号待补"

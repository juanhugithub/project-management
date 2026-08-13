# -*- coding: utf-8 -*-
"""G5 备份与恢复验证契约测试。

所有可写数据库都位于 pytest 临时目录；正式库仅用于只读备份哈希守卫。
"""

import hashlib
import sqlite3

from backup import create_backup, verify_restore
from conftest import OFFICIAL_DB


def _sha256(path):
    """按块计算文件哈希，断言正式库没有被备份工具写入。"""
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_database(path):
    """构造有业务数据且具有外键关系的最小源库，用于验证完整备份。"""
    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("CREATE TABLE enterprise (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
        connection.execute("CREATE TABLE project (id INTEGER PRIMARY KEY, enterprise_id INTEGER NOT NULL, "
                           "name TEXT NOT NULL, FOREIGN KEY(enterprise_id) REFERENCES enterprise(id))")
        connection.execute("INSERT INTO enterprise (id, name) VALUES (1, 'G5 企业')")
        connection.execute("INSERT INTO project (id, enterprise_id, name) VALUES (1, 1, 'G5 项目')")
        connection.commit()
    finally:
        connection.close()


def test_create_backup_uses_sqlite_snapshot_and_keeps_business_rows(tmp_path):
    """备份必须保留源库表数据，并以时间标识生成独立文件。"""
    source = tmp_path / "source.db"
    _source_database(source)
    backup = create_backup(source, tmp_path / "backups")

    assert backup.exists()
    assert backup.parent == tmp_path / "backups"
    assert backup.name.startswith("project_") and backup.suffix == ".db"
    connection = sqlite3.connect(backup)
    try:
        assert connection.execute("SELECT name FROM enterprise WHERE id=1").fetchone()[0] == "G5 企业"
        assert connection.execute("SELECT name FROM project WHERE id=1").fetchone()[0] == "G5 项目"
    finally:
        connection.close()


def test_verify_restore_checks_a_real_temporary_restoration(tmp_path):
    """恢复验证必须可通过备份副本重建临时数据库，并返回完整性结果。"""
    source = tmp_path / "source.db"
    _source_database(source)
    backup = create_backup(source, tmp_path / "backups")

    result = verify_restore(backup)

    assert result["backup_path"] == str(backup)
    assert result["integrity_check"] == "ok"
    assert result["foreign_key_violations"] == 0


def test_backup_never_changes_formal_database_hash(tmp_path):
    """把正式库作为只读源创建备份前后，其 SHA-256 必须完全一致。"""
    before = _sha256(OFFICIAL_DB)
    backup = create_backup(OFFICIAL_DB, tmp_path / "formal-backups")
    result = verify_restore(backup)
    after = _sha256(OFFICIAL_DB)

    assert result["integrity_check"] == "ok"
    assert after == before

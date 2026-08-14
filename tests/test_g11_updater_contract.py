# -*- coding: utf-8 -*-
"""G11 更新器契约：只更新代码、只快进、失败时只回退代码。"""

import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from updater import UpdateError, apply_stable_update, assert_release_manifest_clean, check_stable_update


def _run(arguments, cwd):
    """在临时仓库执行 Git，测试仓库完全脱离正式项目目录。"""
    return subprocess.run(arguments, cwd=cwd, check=True, text=True, encoding="utf-8", capture_output=True)


def _git(cwd, *arguments):
    """简化临时 Git 仓库初始化和提交操作。"""
    return _run(["git", *arguments], cwd).stdout.strip()


def _commit(repository: Path, message: str):
    """提交测试版本，确保远程 stable 有可供更新器发现的版本历史。"""
    _git(repository, "add", ".")
    _git(repository, "commit", "-m", message)


def _make_remote_pair(tmp_path):
    """构造 bare 远程、发布工作副本和待更新本机副本。"""
    remote = tmp_path / "remote.git"
    publisher = tmp_path / "publisher"
    local = tmp_path / "local"
    _git(tmp_path, "init", "--bare", str(remote))
    _git(tmp_path, "init", "-b", "stable", str(publisher))
    _git(publisher, "config", "user.email", "test@example.invalid")
    _git(publisher, "config", "user.name", "G11 Test")
    (publisher / "VERSION").write_text("0.1.0\n", encoding="utf-8")
    (publisher / "service.txt").write_text("first\n", encoding="utf-8")
    _commit(publisher, "initial stable")
    _git(publisher, "remote", "add", "origin", str(remote))
    _git(publisher, "push", "-u", "origin", "stable")
    _git(tmp_path, "clone", "--branch", "stable", str(remote), str(local))
    _git(local, "config", "user.email", "test@example.invalid")
    _git(local, "config", "user.name", "G11 Test")
    return publisher, local


def _database(path):
    """创建最小临时库，供更新前 online backup 断言使用。"""
    connection = sqlite3.connect(path)
    try:
        connection.execute("CREATE TABLE records (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
        connection.execute("INSERT INTO records (name) VALUES ('G11 临时记录')")
        connection.commit()
    finally:
        connection.close()


def test_check_stable_update_returns_version_and_commit_changes(tmp_path):
    """检查应返回 stable 版本和人工可读的提交差异，但不更新本机代码。"""
    publisher, local = _make_remote_pair(tmp_path)
    (publisher / "VERSION").write_text("0.2.0\n", encoding="utf-8")
    (publisher / "service.txt").write_text("second\n", encoding="utf-8")
    _commit(publisher, "release 0.2.0")
    _git(publisher, "push")

    plan = check_stable_update(local)

    assert plan.current_version == "0.1.0"
    assert plan.stable_version == "0.2.0"
    assert plan.update_available is True
    assert plan.fast_forward_only is True
    assert any("release 0.2.0" in item for item in plan.changes)
    assert (local / "VERSION").read_text(encoding="utf-8").strip() == "0.1.0"


def test_apply_update_creates_online_backup_and_fast_forwards_code(tmp_path):
    """成功更新必须先备份临时库，随后只快进到 stable 并运行健康检查。"""
    publisher, local = _make_remote_pair(tmp_path)
    (publisher / "VERSION").write_text("0.2.0\n", encoding="utf-8")
    _commit(publisher, "release 0.2.0")
    _git(publisher, "push")
    database = tmp_path / "ledger.db"
    _database(database)

    result = apply_stable_update(
        local, database, tmp_path / "backups", health_command=[sys.executable, "-c", "raise SystemExit(0)"],
    )

    assert result["updated"] is True
    assert result["backup"].exists()
    assert (local / "VERSION").read_text(encoding="utf-8").strip() == "0.2.0"
    assert sqlite3.connect(database).execute("SELECT name FROM records").fetchone()[0] == "G11 临时记录"


def test_failed_health_check_rolls_back_code_without_touching_database(tmp_path):
    """健康检查失败只能回退 Git 代码；临时数据库内容仍保持更新前状态。"""
    publisher, local = _make_remote_pair(tmp_path)
    (publisher / "VERSION").write_text("0.2.0\n", encoding="utf-8")
    _commit(publisher, "release 0.2.0")
    _git(publisher, "push")
    database = tmp_path / "ledger.db"
    _database(database)

    with pytest.raises(UpdateError, match="代码已回退"):
        apply_stable_update(
            local, database, tmp_path / "backups", health_command=[sys.executable, "-c", "raise SystemExit(1)"],
        )

    assert (local / "VERSION").read_text(encoding="utf-8").strip() == "0.1.0"
    assert sqlite3.connect(database).execute("SELECT name FROM records").fetchone()[0] == "G11 临时记录"
    assert list((tmp_path / "backups").glob("project_*.db"))


def test_release_manifest_rejects_database_archives_and_secrets(tmp_path):
    """发布清单不得将本机数据、导入原件或密钥当作代码更新内容。"""
    _, local = _make_remote_pair(tmp_path)
    for relative in ("data/project.db", "import-archives/source.xlsx", ".env"):
        path = local / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("forbidden", encoding="utf-8")
        _git(local, "add", "-f", relative)
    _git(local, "commit", "-m", "invalid release files")

    with pytest.raises(UpdateError, match="受保护文件"):
        assert_release_manifest_clean(local)

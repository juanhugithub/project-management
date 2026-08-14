#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""D13 数据路径分离：用户配置优先级与首次旧数据复制契约。"""

import json
import sqlite3
from pathlib import Path

import pytest

import runtime_paths


def _create_database(path: Path) -> None:
    """建立最小有效 SQLite 库，专门验证迁移过程不依赖正式台账。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        connection.execute("CREATE TABLE evidence (id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute("INSERT INTO evidence(value) VALUES ('保留旧库')")
        connection.commit()
    finally:
        connection.close()


def test_environment_variable_has_highest_priority(tmp_path):
    """测试通过 LEDGER_HOME 隔离运行目录，环境变量必须覆盖安装器配置。"""
    configured = tmp_path / "configured"
    config_path = tmp_path / "runtime-paths.json"
    config_path.write_text(json.dumps({"ledger_home": str(configured)}), encoding="utf-8")
    paths = runtime_paths.get_runtime_paths({
        "LOCALAPPDATA": str(tmp_path / "appdata"),
        "LEDGER_PATHS_CONFIG": str(config_path),
        "LEDGER_HOME": str(tmp_path / "environment"),
    })
    assert paths.home == (tmp_path / "environment").resolve()
    assert paths.database == paths.home / "data" / "project.db"


def test_installer_config_allows_non_system_drive_path(tmp_path):
    """安装器配置可把数据目录指定到用户选择的任意盘符或目录。"""
    chosen = tmp_path / "user-selected-data"
    config_path = tmp_path / "installer" / "runtime-paths.json"
    config_path.parent.mkdir()
    config_path.write_text(json.dumps({"ledger_home": str(chosen)}), encoding="utf-8")
    paths = runtime_paths.get_runtime_paths({
        "LOCALAPPDATA": str(tmp_path / "appdata"),
        "LEDGER_PATHS_CONFIG": str(config_path),
    })
    assert paths.home == chosen.resolve()


def test_first_run_copies_old_data_and_keeps_old_database(tmp_path, monkeypatch):
    """旧 data 只复制到新目录，复制后旧库仍在且副本内容可读。"""
    code_root = tmp_path / "code"
    legacy_database = code_root / "data" / "project.db"
    _create_database(legacy_database)
    (code_root / "data" / "legacy-note.txt").write_text("保留材料", encoding="utf-8")
    runtime_home = tmp_path / "selected-data"
    paths = runtime_paths.get_runtime_paths({"LEDGER_HOME": str(runtime_home)})
    monkeypatch.setattr(runtime_paths, "PROJECT_ROOT", code_root)

    report = runtime_paths.migrate_legacy_data_if_needed(paths)

    assert report is not None and report.exists()
    assert legacy_database.exists()
    assert (paths.data_dir / "legacy-note.txt").read_text(encoding="utf-8") == "保留材料"
    copied = sqlite3.connect(paths.database)
    try:
        assert copied.execute("SELECT value FROM evidence").fetchone()[0] == "保留旧库"
    finally:
        copied.close()
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["legacy_data_retained"] is True


def test_existing_new_data_directory_is_never_overwritten(tmp_path, monkeypatch):
    """新目录已有材料而缺库时，停止而不是覆盖，要求人工检查。"""
    code_root = tmp_path / "code"
    _create_database(code_root / "data" / "project.db")
    paths = runtime_paths.get_runtime_paths({"LEDGER_HOME": str(tmp_path / "selected-data")})
    paths.data_dir.mkdir(parents=True)
    (paths.data_dir / "important.txt").write_text("不能覆盖", encoding="utf-8")
    monkeypatch.setattr(runtime_paths, "PROJECT_ROOT", code_root)

    with pytest.raises(RuntimeError, match="避免覆盖"):
        runtime_paths.migrate_legacy_data_if_needed(paths)
    assert (paths.data_dir / "important.txt").read_text(encoding="utf-8") == "不能覆盖"

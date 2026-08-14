# -*- coding: utf-8 -*-
"""D13 诊断契约：报告只能读取台账，且必须在首次启动前给出明确状态。"""

import hashlib
import json
import sqlite3
from pathlib import Path

from diagnostics import collect_diagnostics, render_report, resolve_runtime_root
from migrations import apply


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _create_database(path):
    connection = sqlite3.connect(path)
    try:
        schema = (Path(__file__).resolve().parents[1] / "schema.sql").read_text(encoding="utf-8")
        connection.executescript(schema)
        apply(connection)
    finally:
        connection.close()


def test_d13_uses_explicit_ledger_home_and_reports_uninitialized_database(tmp_path):
    """首次安装尚未建库时也必须明确报告，而不是隐式初始化数据库。"""
    root = tmp_path / "ledger-home"
    report = collect_diagnostics({"LEDGER_HOME": str(root)})

    assert resolve_runtime_root({"LEDGER_HOME": str(root)}) == root
    assert report["runtime_root"] == str(root)
    assert report["installation_directory"] == str(Path(__file__).resolve().parents[1])
    assert report["data_directory"] == str(root / "data")
    assert report["database"]["exists"] is False
    assert report["database"]["integrity_check"] is None
    assert report["backups"]["count"] == 0


def test_d13_reads_installer_path_configuration_for_non_default_drive(tmp_path):
    """安装器选择任意磁盘后，报告必须展示该实际数据目录而非固定默认盘。"""
    root = tmp_path / "selected-data-volume" / "ledger"
    config = tmp_path / "installer" / "runtime-paths.json"
    config.parent.mkdir()
    config.write_text(json.dumps({"ledger_home": str(root)}), encoding="utf-8")

    report = collect_diagnostics({"LEDGER_PATHS_CONFIG": str(config), "LOCALAPPDATA": str(tmp_path / "unused")})

    assert report["runtime_root"] == str(root.resolve())
    assert report["data_directory"] == str((root / "data").resolve())


def test_d13_checks_database_migrations_backups_and_never_changes_database(tmp_path):
    """完整报告必须返回 SQLite 事实，且读取前后正式库哈希完全相同。"""
    root = tmp_path / "ledger-home"
    database = root / "data" / "project.db"
    database.parent.mkdir(parents=True)
    _create_database(database)
    backups = root / "backups"
    backups.mkdir()
    latest = backups / "project_20260814_120000_000000.db"
    latest.write_bytes(b"backup evidence")
    before = _sha256(database)

    report = collect_diagnostics({
        "LEDGER_HOME": str(root),
        "LEDGER_LOCAL_MCP_ENABLED": "1",
        "LEDGER_LOCAL_MCP_TOKEN_FILE": str(root / "config" / "agent.token"),
    })

    assert _sha256(database) == before
    assert report["database"]["integrity_check"] == "ok"
    assert report["database"]["foreign_key_violations"] == 0
    assert "001_g2_constraints.sql" in report["database"]["migrations"]
    assert report["backups"]["latest"] == str(latest)
    assert report["local_mcp"]["enabled"] is True
    assert "正式库：存在" in render_report(report)


def test_d13_reports_occupied_web_port_without_connecting_to_database(tmp_path):
    """端口冲突必须可见，方便安装器在首次启动前停止并提示用户。"""
    import socket
    import diagnostics

    root = tmp_path / "ledger-home"
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    original = diagnostics.DEFAULT_WEB_PORT
    diagnostics.DEFAULT_WEB_PORT = listener.getsockname()[1]
    try:
        report = collect_diagnostics({"LEDGER_HOME": str(root)})
    finally:
        diagnostics.DEFAULT_WEB_PORT = original
        listener.close()

    assert report["ports"][0]["occupied"] is True

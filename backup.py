#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""科技项目台账的 SQLite 备份与恢复验证工具。

用法：
    python backup.py create
    python backup.py create --source data/project.db --backup-dir backups
    python backup.py verify backups/project_20260813_120000_123456.db

本工具只从源库读取；备份和恢复验证均写入调用者指定的备份目录或系统临时目录，
不会修改 ``data/project.db``。
"""

import argparse
import datetime as dt
import sqlite3
import tempfile
from pathlib import Path
from runtime_paths import get_runtime_paths


BASE_DIR = Path(__file__).resolve().parent
RUNTIME_PATHS = get_runtime_paths()
DEFAULT_SOURCE = RUNTIME_PATHS.database
DEFAULT_BACKUP_DIR = RUNTIME_PATHS.backups


def _readonly_connection(database_path: Path) -> sqlite3.Connection:
    """以 SQLite URI 只读方式打开源库，明确隔离备份流程与正式库写入。"""
    absolute_path = database_path.resolve()
    return sqlite3.connect(f"file:{absolute_path.as_posix()}?mode=ro", uri=True)


def validate_database(database_path: str | Path) -> dict:
    """执行备份库或恢复库的完整性、外键校验，并返回可记录的结果。"""
    path = Path(database_path)
    connection = _readonly_connection(path)
    try:
        integrity_rows = connection.execute("PRAGMA integrity_check").fetchall()
        foreign_key_rows = connection.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        connection.close()

    integrity = integrity_rows[0][0] if integrity_rows else ""
    result = {
        "path": str(path),
        "integrity_check": integrity,
        "foreign_key_violations": len(foreign_key_rows),
    }
    if integrity != "ok" or foreign_key_rows:
        raise ValueError(f"SQLite 校验未通过: {result}")
    return result


def create_backup(source_path: str | Path = DEFAULT_SOURCE,
                  backup_dir: str | Path = DEFAULT_BACKUP_DIR) -> Path:
    """使用 SQLite backup API 创建带时间标识的备份，并在返回前校验备份文件。"""
    source = Path(source_path)
    destination_dir = Path(backup_dir)
    destination_dir.mkdir(parents=True, exist_ok=True)

    # 微秒保证同一秒连续备份时仍能得到不同文件名，避免覆盖上一份证据。
    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    destination = destination_dir / f"project_{timestamp}.db"
    source_connection = _readonly_connection(source)
    destination_connection = sqlite3.connect(str(destination))
    try:
        # SQLite 在同一逻辑快照中复制全部页，避免普通文件复制遇到 WAL 状态不一致。
        source_connection.backup(destination_connection)
    finally:
        destination_connection.close()
        source_connection.close()

    validate_database(destination)
    return destination


def verify_restore(backup_path: str | Path) -> dict:
    """将指定备份恢复到系统临时目录，并校验恢复副本；原备份和正式库均不写入。"""
    backup = Path(backup_path)
    with tempfile.TemporaryDirectory(prefix="ledger-restore-verify-") as directory:
        restored = Path(directory) / "restored-project.db"
        source_connection = _readonly_connection(backup)
        restored_connection = sqlite3.connect(str(restored))
        try:
            # 恢复验证同样使用 SQLite backup API，真正覆盖数据库页复制路径。
            source_connection.backup(restored_connection)
        finally:
            restored_connection.close()
            source_connection.close()
        result = validate_database(restored)
        result["backup_path"] = str(backup)
        return result


def main() -> int:
    """提供创建备份和验证既有备份两个明确命令，不隐式执行恢复写入。"""
    parser = argparse.ArgumentParser(description="科技项目台账 SQLite 备份与恢复验证")
    subparsers = parser.add_subparsers(dest="command", required=True)
    create_parser = subparsers.add_parser("create", help="创建并校验备份")
    create_parser.add_argument("--source", default=str(DEFAULT_SOURCE), help="只读源数据库路径")
    create_parser.add_argument("--backup-dir", default=str(DEFAULT_BACKUP_DIR), help="备份输出目录")
    verify_parser = subparsers.add_parser("verify", help="恢复到临时目录并校验备份")
    verify_parser.add_argument("backup", help="待验证备份文件路径")
    arguments = parser.parse_args()

    if arguments.command == "create":
        backup = create_backup(arguments.source, arguments.backup_dir)
        print(f"备份完成并校验通过：{backup}")
        return 0
    result = verify_restore(arguments.backup)
    print(f"临时恢复验证通过：{result['backup_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

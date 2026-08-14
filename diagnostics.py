#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""D13 首次启动只读诊断工具。

诊断只读取运行时目录中的程序、数据库、备份和本机 MCP 配置。它绝不初始化、
迁移、修复或备份正式库，以便失败报告本身不会改变正式台账。
"""

import argparse
import json
import os
import socket
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_WEB_PORT = 8765
DEFAULT_REMOTE_MCP_PORT = 8001


def resolve_runtime_root(env: dict[str, str] | None = None) -> Path:
    """按安装器配置确定数据根目录；开发目录仅是旧代码兼容路径。"""
    values = os.environ if env is None else env
    try:
        from runtime_paths import get_runtime_paths
    except ImportError:
        # 此分支仅服务于尚未升级 runtime_paths 的历史开发版本；安装交付物必须
        # 使用安装器配置，不能把数据目录默认为代码目录。
        configured = values.get("LEDGER_HOME", "").strip()
        return Path(configured).expanduser() if configured else PROJECT_ROOT
    return get_runtime_paths(values).home


def _database_report(path: Path) -> dict:
    """在只读 URI 中执行 SQLite 校验，数据库缺失时给出可行动状态。"""
    result = {"path": str(path), "exists": path.is_file()}
    if not path.is_file():
        return result | {"integrity_check": None, "foreign_key_violations": None, "migrations": []}

    connection = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
    try:
        integrity = [row[0] for row in connection.execute("PRAGMA integrity_check")]
        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
        has_migrations = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migration'"
        ).fetchone()
        migrations = [row[0] for row in connection.execute("SELECT version FROM schema_migration ORDER BY version")] if has_migrations else []
    finally:
        connection.close()
    return result | {
        "integrity_check": integrity[0] if integrity else None,
        "foreign_key_violations": len(foreign_keys),
        "migrations": migrations,
    }


def _backup_report(directory: Path) -> dict:
    """仅枚举备份文件和最近修改时间，不验证或写入任何备份。"""
    backups = sorted(directory.glob("project_*.db"), key=lambda item: item.stat().st_mtime, reverse=True) if directory.is_dir() else []
    latest = backups[0] if backups else None
    return {
        "directory": str(directory),
        "exists": directory.is_dir(),
        "count": len(backups),
        "latest": str(latest) if latest else None,
        "latest_modified_at": datetime.fromtimestamp(latest.stat().st_mtime, timezone.utc).isoformat() if latest else None,
    }


def _port_report(port: int) -> dict:
    """检测回环端口是否正在被占用；不连接服务，也不改变端口状态。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.2)
        occupied = probe.connect_ex(("127.0.0.1", port)) == 0
    return {"host": "127.0.0.1", "port": port, "occupied": occupied}


def _local_mcp_report(root: Path, env: dict[str, str]) -> dict:
    """展示本机 MCP 是否已显式启用；Token 仅报告存在性，永不读取内容。"""
    config_file = root / "config" / "local_mcp.json"
    enabled = env.get("LEDGER_LOCAL_MCP_ENABLED", "").strip().lower() == "1"
    token_file = Path(env["LEDGER_LOCAL_MCP_TOKEN_FILE"]) if env.get("LEDGER_LOCAL_MCP_TOKEN_FILE") else root / "config" / "local_mcp.token"
    return {
        "transport": "stdio",
        "enabled": enabled,
        "config_file": str(config_file),
        "config_exists": config_file.is_file(),
        "token_file": str(token_file),
        "token_present": token_file.is_file() and token_file.stat().st_size > 0,
    }


def collect_diagnostics(env: dict[str, str] | None = None) -> dict:
    """收集可序列化的诊断事实，供安装器、快捷方式和命令行共用。"""
    values = dict(os.environ if env is None else env)
    root = resolve_runtime_root(values)
    try:
        from runtime_paths import get_runtime_paths
    except ImportError:
        database = root / "data" / "project.db"
        backups = root / "backups"
        config = root / "config"
    else:
        paths = get_runtime_paths(values)
        database = paths.database
        backups = paths.backups
        config = paths.config
    version_file = PROJECT_ROOT / "VERSION"
    version = version_file.read_text(encoding="utf-8").strip() if version_file.is_file() else "未找到 VERSION"
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "application_version": version,
        "installation_directory": str(PROJECT_ROOT),
        "runtime_root": str(root),
        "data_directory": str(database.parent),
        "database": _database_report(database),
        "backups": _backup_report(backups),
        "ports": [_port_report(DEFAULT_WEB_PORT), _port_report(DEFAULT_REMOTE_MCP_PORT)],
        "local_mcp": _local_mcp_report(config.parent, values),
    }


def render_report(report: dict) -> str:
    """渲染人工可读报告，保留 JSON 内的完整机器可读事实。"""
    database = report["database"]
    backups = report["backups"]
    ports = report["ports"]
    mcp = report["local_mcp"]
    return "\n".join([
        "科技项目台账 D13 诊断报告",
        f"生成时间（UTC）：{report['generated_at']}",
        f"应用版本：{report['application_version']}",
        f"安装目录：{report['installation_directory']}",
        f"运行时根目录：{report['runtime_root']}",
        f"数据目录：{report['data_directory']}",
        f"正式库：{'存在' if database['exists'] else '未初始化'}（{database['path']}）",
        f"完整性检查：{database['integrity_check'] if database['exists'] else '未执行'}",
        f"外键违规数：{database['foreign_key_violations'] if database['exists'] else '未执行'}",
        f"已应用迁移：{', '.join(database['migrations']) if database['migrations'] else '无'}",
        f"备份目录：{'存在' if backups['exists'] else '不存在'}，有效备份数：{backups['count']}",
        f"最近备份：{backups['latest'] or '无'}",
        "端口状态：" + "；".join(f"{item['host']}:{item['port']} {'已占用' if item['occupied'] else '空闲'}" for item in ports),
        f"本机 MCP：{'已启用' if mcp['enabled'] else '未启用'}，传输方式：{mcp['transport']}，Token：{'已就绪' if mcp['token_present'] else '未生成'}",
    ])


def main() -> int:
    """提供终端和安装器可直接调用的只读诊断入口。"""
    parser = argparse.ArgumentParser(description="科技项目台账 D13 只读诊断")
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    arguments = parser.parse_args()
    report = collect_diagnostics()
    print(json.dumps(report, ensure_ascii=False, indent=2) if arguments.json else render_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

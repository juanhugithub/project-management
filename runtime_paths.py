#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""科技项目台账的代码目录与本机运行数据目录边界。

代码、模板、静态资源和迁移脚本始终位于安装目录；会变化的台账数据、备份、
导入原件、日志和本机配置则统一位于 ``LEDGER_HOME``。未设置该变量时，使用
当前 Windows 用户的 ``%LOCALAPPDATA%\\科技项目台账``，从而使程序升级不会覆盖数据。
"""

import hashlib
import json
import os
import shutil
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
APP_DIRECTORY_NAME = "科技项目台账"
RUNTIME_CONFIG_FILENAME = "runtime-paths.json"


@dataclass(frozen=True)
class RuntimePaths:
    """一个本机安装实例的全部可写位置；代码目录不在其中。"""

    home: Path
    data_dir: Path
    database: Path
    backups: Path
    imports: Path
    import_archive: Path
    config: Path
    logs: Path
    reports: Path


def _default_home(values: dict[str, str]) -> Path:
    """返回未配置时的建议目录；这里不创建目录，也不会写入安装目录。"""
    local_app_data = values.get("LOCALAPPDATA", "").strip()
    if not local_app_data:
        raise RuntimeError("未设置 LOCALAPPDATA；请显式设置 LEDGER_HOME 后再启动")
    return Path(local_app_data) / APP_DIRECTORY_NAME


def _installer_config_path(values: dict[str, str]) -> Path:
    """定位安装器写入的路径配置，允许安装器把数据放到任意用户选择的位置。"""
    configured = values.get("LEDGER_PATHS_CONFIG", "").strip()
    if configured:
        return Path(configured).expanduser()
    return _default_home(values) / "config" / RUNTIME_CONFIG_FILENAME


def _configured_home(values: dict[str, str]) -> Path | None:
    """读取安装器配置；文件存在但格式不合法时明确失败，避免悄悄写到错误位置。"""
    config_path = _installer_config_path(values)
    if not config_path.exists():
        return None
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"运行路径配置文件无效：{config_path}") from error
    home = payload.get("ledger_home") if isinstance(payload, dict) else None
    if not isinstance(home, str) or not home.strip():
        raise RuntimeError(f"运行路径配置文件必须包含非空 ledger_home：{config_path}")
    return Path(home.strip()).expanduser()


def get_runtime_paths(env: dict[str, str] | None = None) -> RuntimePaths:
    """按环境变量、安装器配置、默认目录的优先级得到运行目录。

    安装器可在 ``LEDGER_PATHS_CONFIG`` 指向的位置，或默认配置文件中写入
    ``{\"ledger_home\": \"D:\\\\台账数据\"}``，以支持非 C 盘安装。
    """
    values = os.environ if env is None else env
    configured_home = values.get("LEDGER_HOME", "").strip()
    if configured_home:
        home = Path(configured_home).expanduser()
    else:
        home = _configured_home(values) or _default_home(values)
    home = home.resolve()
    data_dir = home / "data"
    imports = home / "imports"
    return RuntimePaths(
        home=home,
        data_dir=data_dir,
        database=data_dir / "project.db",
        backups=home / "backups",
        imports=imports,
        import_archive=imports / "archive",
        config=home / "config",
        logs=home / "logs",
        reports=home / "reports",
    )


def _database_validation(path: Path) -> dict:
    """只读校验迁移副本，复制失败时绝不把不完整内容作为新的正式库。"""
    connection = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        connection.close()
    if integrity != "ok" or foreign_keys:
        raise RuntimeError(f"旧台账副本校验失败：integrity={integrity}，foreign_keys={len(foreign_keys)}")
    return {"integrity_check": integrity, "foreign_key_violations": len(foreign_keys)}


def _sha256(path: Path) -> str:
    """记录迁移来源和副本的哈希，供人工确认两者一致。"""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_report(paths: RuntimePaths, report: dict) -> Path:
    """将迁移结果写入独立报告目录，报告不混入正式数据目录。"""
    paths.reports.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    report_path = paths.reports / f"runtime-data-migration-{timestamp}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report_path


def migrate_legacy_data_if_needed(paths: RuntimePaths | None = None) -> Path | None:
    """首次启动时只复制旧 ``data`` 目录，不删除也不改写安装目录中的任何内容。

    这不是数据库结构迁移：不调用 ``migrations.apply``，也不执行任何 SQL 写操作。
    为避免覆盖用户已创建的新数据目录，只在新目录完全不存在时执行一次复制。
    """
    paths = paths or get_runtime_paths()
    legacy_data = PROJECT_ROOT / "data"
    if paths.database.exists() or not legacy_data.exists():
        return None
    if paths.data_dir.exists():
        raise RuntimeError(
            f"检测到旧数据目录 {legacy_data}，但新数据目录 {paths.data_dir} 已存在且没有正式库；"
            "为避免覆盖文件，已停止自动迁移，请由维护人员检查后处理。"
        )
    legacy_database = legacy_data / "project.db"
    if not legacy_database.exists():
        raise RuntimeError(f"旧数据目录缺少正式库：{legacy_database}")

    paths.home.mkdir(parents=True, exist_ok=True)
    staging = paths.home / f"data.migrating-{uuid.uuid4().hex}"
    try:
        # 保留旧 data 下的全部材料；先在同一磁盘的临时目录完成复制和校验，再原子改名。
        shutil.copytree(legacy_data, staging)
        validation = _database_validation(staging / "project.db")
        source_hash = _sha256(legacy_database)
        copied_hash = _sha256(staging / "project.db")
        if source_hash != copied_hash:
            raise RuntimeError("旧正式库与复制副本的 SHA-256 不一致")
        staging.replace(paths.data_dir)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise

    report = {
        "at": datetime.now(timezone.utc).isoformat(),
        "action": "copied_legacy_data_directory",
        "legacy_data": str(legacy_data),
        "runtime_data": str(paths.data_dir),
        "database_sha256": source_hash,
        **validation,
        "legacy_data_retained": True,
    }
    return _write_report(paths, report)


def ensure_runtime_layout(paths: RuntimePaths | None = None) -> RuntimePaths:
    """准备本机目录，并在需要时完成一次保守的旧数据目录复制。"""
    paths = paths or get_runtime_paths()
    migrate_legacy_data_if_needed(paths)
    for directory in (paths.home, paths.backups, paths.import_archive, paths.config, paths.logs, paths.reports):
        directory.mkdir(parents=True, exist_ok=True)
    return paths

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""发布包内容清单。

这里的清单是安装包唯一允许收集的项目资源。数据库、备份、导入原件和本机
配置均不在其中，避免构建过程把用户数据带入发布物。
"""

from pathlib import Path


RESOURCE_DIRECTORIES = ("ledger", "static", "templates", "migrations", "imports")
RESOURCE_FILES = (
    "schema.sql", "VERSION", "version.py", "backup.py", "mcp_server.py", "remote_mcp.py",
    "mcp_contract.py", "make_template.py", "enterprise_excel.py", "import_excel.py", "requirements.txt", "requirements-mcp.txt",
    "导入模板.xlsx",
)
FORBIDDEN_PARTS = {"data", "backups", "imports/archive", "config", ".env"}


def assert_safe_relative_path(relative: Path) -> None:
    """拒绝把用户数据或密钥目录作为发布资源。"""
    normalized = relative.as_posix().lower()
    if normalized in FORBIDDEN_PARTS or normalized.startswith(("data/", "backups/", "config/", "imports/archive/")):
        raise ValueError(f"发布清单禁止包含用户数据或密钥：{relative}")


def application_data_sources(project_root: Path) -> list[tuple[Path, Path]]:
    """返回 PyInstaller 的 (源路径, 发布包内目标目录) 清单。"""
    sources: list[tuple[Path, Path]] = []
    for name in RESOURCE_FILES:
        source = project_root / name
        if source.exists():
            assert_safe_relative_path(Path(name))
            sources.append((source, Path(".")))
    for name in RESOURCE_DIRECTORIES:
        source = project_root / name
        if source.exists():
            assert_safe_relative_path(Path(name))
            sources.append((source, Path(name)))
    return sources

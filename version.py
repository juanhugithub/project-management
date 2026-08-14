# -*- coding: utf-8 -*-
"""应用版本的单一读取入口。

更新器、健康检查和人工发布说明均通过此模块读取 ``VERSION``，避免在多个
脚本中散落版本字符串。版本文件只属于代码发布物，绝不与 SQLite 数据绑定。
"""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
VERSION_FILE = PROJECT_ROOT / "VERSION"


def get_version(root: str | Path = PROJECT_ROOT) -> str:
    """读取指定代码目录的版本号，供当前版本和远程稳定版本使用。"""
    return (Path(root) / "VERSION").read_text(encoding="utf-8").strip()

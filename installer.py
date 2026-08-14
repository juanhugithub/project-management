#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""科技项目台账当前用户安装器。

安装器只写入用户目录中的程序版本和启动入口；数据目录始终独立保留，卸载也
绝不删除数据、备份、导入原件或本机配置。
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


PRODUCT_NAME = "科技项目台账"
APP_DIRECTORY = "app"
DATA_DIRECTORIES = ("data", "backups", "imports", "config")


def default_user_root(local_app_data: str | None = None) -> Path:
    """取得建议目录；安装时用户可改为任意盘符，绝不硬编码 C 盘。"""
    value = local_app_data or os.environ.get("LOCALAPPDATA")
    if not value:
        raise RuntimeError("未找到 LOCALAPPDATA，无法确定当前用户安装目录")
    return Path(value) / PRODUCT_NAME


def default_install_root(local_app_data: str | None = None) -> Path:
    """兼容调用方的默认程序目录。"""
    return default_user_root(local_app_data) / APP_DIRECTORY


def release_root() -> Path:
    """同时兼容源码运行和 PyInstaller 单文件解压运行。"""
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def read_payload_version(payload: Path) -> str:
    application = payload / "项目台账"
    # PyInstaller onedir 会将数据资源放入 _internal；源码测试包则直接放在程序目录。
    version_file = application / "VERSION"
    if not version_file.is_file():
        version_file = application / "_internal" / "VERSION"
    if not version_file.is_file():
        raise RuntimeError(f"安装包缺少版本文件：{version_file}")
    version = version_file.read_text(encoding="utf-8").strip()
    if not version:
        raise RuntimeError("安装包版本号为空")
    return version


def ensure_data_directories(data_root: Path) -> None:
    """创建稳定用户数据目录；已存在的数据不会读取、覆盖或重建。"""
    for name in DATA_DIRECTORIES:
        (data_root / name).mkdir(parents=True, exist_ok=True)


def write_location_config(config_root: Path, program_root: Path, data_root: Path) -> Path:
    """把用户选择保存到程序目录之外，供更新器与卸载入口查阅。"""
    config_root.mkdir(parents=True, exist_ok=True)
    location_file = config_root / "install_locations.json"
    location_file.write_text(json.dumps({"program_root": str(program_root), "data_root": str(data_root)}, ensure_ascii=False, indent=2), encoding="utf-8")
    # runtime_paths 模块只认识 ledger_home；此文件与安装位置记录并列且不在程序目录内。
    (config_root / "runtime-paths.json").write_text(json.dumps({"ledger_home": str(data_root)}, ensure_ascii=False, indent=2), encoding="utf-8")
    return location_file


def write_launcher(path: Path, command: str) -> None:
    """写入显式的 cmd 启动入口，避免依赖 Python、Git 或 PATH。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("@echo off\r\n" + command + "\r\n", encoding="utf-8")


def create_shortcut(shortcut: Path, target: Path, arguments: str = "") -> None:
    """借助 Windows Script Host 创建 .lnk，不引入额外 Python 依赖。"""
    if os.name != "nt":
        raise RuntimeError("桌面快捷方式只能在 Windows 上创建")
    script = (
        'var shell = new ActiveXObject("WScript.Shell");\n'
        'var link = shell.CreateShortcut(WScript.Arguments.Item(0));\n'
        'link.TargetPath = WScript.Arguments.Item(1);\n'
        'link.Arguments = WScript.Arguments.Item(2);\n'
        'link.WorkingDirectory = WScript.Arguments.Item(3);\n'
        'link.Save();\n'
    )
    with tempfile.TemporaryDirectory(prefix="ledger-shortcut-") as temporary:
        script_path = Path(temporary) / "create-shortcut.js"
        script_path.write_text(script, encoding="utf-8")
        subprocess.run(
            ["cscript.exe", "//nologo", str(script_path), str(shortcut), str(target), arguments, str(target.parent)],
            check=True,
        )


def create_launch_entries(program_root: Path, data_root: Path, config_root: Path, version: str, desktop: Path | None = None, start_menu: Path | None = None) -> dict[str, Path]:
    """创建启动、备份、诊断和卸载入口；它们均只操作当前安装版本。"""
    program = program_root / version
    launcher_dir = config_root / "launchers"
    app_executable = program / "项目台账" / "项目台账.exe"
    backup_executable = program / "台账备份" / "台账备份.exe"
    installer_executable = program / "台账安装器.exe"
    runtime_config = config_root / "runtime-paths.json"
    environment = f'set "LEDGER_PATHS_CONFIG={runtime_config}" && '
    launchers = {
        "启动": launcher_dir / "启动科技项目台账.cmd",
        "备份": launcher_dir / "备份科技项目台账.cmd",
        "诊断": launcher_dir / "诊断科技项目台账.cmd",
        "卸载": launcher_dir / "卸载科技项目台账.cmd",
    }
    write_launcher(launchers["启动"], environment + f'start "" "{app_executable}"')
    write_launcher(launchers["备份"], environment + f'"{backup_executable}"')
    write_launcher(launchers["诊断"], environment + f'"{installer_executable}" diagnose --program-root "{program_root}" --data-root "{data_root}"')
    write_launcher(launchers["卸载"], environment + f'"{installer_executable}" uninstall --program-root "{program_root}" --version "{version}"')
    for folder in (desktop, start_menu):
        if folder is not None:
            create_shortcut(folder / f"{PRODUCT_NAME}.lnk", launchers["启动"])
            create_shortcut(folder / f"{PRODUCT_NAME} - 备份.lnk", launchers["备份"])
            create_shortcut(folder / f"{PRODUCT_NAME} - 诊断.lnk", launchers["诊断"])
            create_shortcut(folder / f"{PRODUCT_NAME} - 卸载.lnk", launchers["卸载"])
    return launchers


def install_release(payload: Path, program_root: Path, data_root: Path, config_root: Path, desktop: Path | None = None, start_menu: Path | None = None) -> dict[str, Path | str]:
    """安装一个新程序版本，遇到同版本已存在时明确拒绝覆盖。"""
    version = read_payload_version(payload)
    source_program = payload / "项目台账"
    if not source_program.is_dir():
        raise RuntimeError(f"安装包缺少主程序目录：{source_program}")
    target = program_root / version
    if target.exists():
        raise RuntimeError(f"版本 {version} 已安装，安装器不会覆盖已有程序目录")
    ensure_data_directories(data_root)
    location_file = write_location_config(config_root, program_root, data_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_program, target / "项目台账")
    for name in ("台账备份",):
        source = payload / name
        if source.is_dir():
            shutil.copytree(source, target / name)
        elif source.is_file():
            shutil.copy2(source, target / name)
    # 独立安装器运行时从自身可执行文件复制，源码测试则可由 payload 提供样例文件。
    own_installer = payload / "台账安装器.exe"
    if not own_installer.is_file() and getattr(sys, "frozen", False):
        own_installer = Path(sys.executable)
    if own_installer.is_file():
        shutil.copy2(own_installer, target / "台账安装器.exe")
    launchers = create_launch_entries(program_root, data_root, config_root, version, desktop, start_menu)
    return {"version": version, "program": target, "location_config": location_file, **launchers}


def uninstall_release(program_root: Path, version: str) -> Path:
    """只移除指定程序版本；稳定用户数据目录永远不在删除范围内。"""
    target = program_root / version
    if not target.is_dir():
        raise RuntimeError(f"未找到要卸载的程序版本：{target}")
    shutil.rmtree(target)
    return target


def diagnose(program_root: Path, data_root: Path) -> dict[str, str]:
    """输出可交给维护人员的最小安装状态，且不读取台账内容。"""
    return {
        "program_root": str(program_root),
        "data_root": str(data_root),
        "app_versions": ", ".join(sorted(p.name for p in program_root.glob("*") if p.is_dir())) or "无",
        "data_exists": str((data_root / "data").is_dir()),
        "backups_exists": str((data_root / "backups").is_dir()),
        "imports_exists": str((data_root / "imports").is_dir()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="科技项目台账当前用户安装器")
    parser.add_argument("command", choices=("install", "uninstall", "diagnose"), nargs="?", default="install")
    suggested_root = default_user_root()
    parser.add_argument("--program-root", type=Path, default=suggested_root / APP_DIRECTORY, help="程序版本目录，可选择任意盘符")
    parser.add_argument("--data-root", type=Path, default=suggested_root / "user-data", help="台账数据根目录，可选择任意盘符")
    parser.add_argument("--config-root", type=Path, default=suggested_root / "config", help="本机配置目录，位于程序目录之外")
    parser.add_argument("--version")
    args = parser.parse_args()
    if args.command == "install":
        result = install_release(release_root() / "payload", args.program_root, args.data_root, args.config_root)
    elif args.command == "uninstall":
        if not args.version:
            parser.error("卸载必须指定 --version")
        result = {"removed": str(uninstall_release(args.program_root, args.version))}
    else:
        result = diagnose(args.program_root, args.data_root)
    for key, value in result.items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

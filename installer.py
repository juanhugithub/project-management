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
import winreg
import sys
import tempfile
from pathlib import Path


PRODUCT_NAME = "科技项目台账"
APP_DIRECTORY = "app"
DATA_DIRECTORIES = ("data", "backups", "imports", "config")


def brand_icon_path() -> Path:
    """按源码或单文件安装器运行形态返回同一品牌图标。"""
    if getattr(sys, "frozen", False):
        return release_root() / "brand-icon.ico"
    return Path(__file__).resolve().parent / "assets" / "brand-icon.ico"


def launch_install_gui(payload: Path | None = None, suggested_root: Path | None = None) -> int:
    """在 Windows 桌面显示安装位置选择界面。

    图形界面只在用户双击安装器、且没有传入命令行参数时使用。自动化构建、
    更新器和维护脚本仍通过 ``install --program-root ...`` 调用命令行入口，二者
    共用 ``install_release``，避免产生两套安装逻辑。
    """
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox
    except ImportError as error:
        print("无法启动图形安装界面：此运行环境没有 tkinter。请在 Windows 图形化桌面中双击安装器。", file=sys.stderr)
        return 2

    selected_payload = payload or release_root() / "payload"
    try:
        version = read_payload_version(selected_payload)
    except RuntimeError as error:
        print(f"无法启动图形安装界面：{error}", file=sys.stderr)
        return 2
    root_path = suggested_root or default_user_root()
    defaults = {
        "program": root_path / APP_DIRECTORY,
        "data": root_path / "user-data",
        "config": root_path / "config",
    }
    try:
        window = tk.Tk()
    except tk.TclError as error:
        print("无法启动图形安装界面：未检测到可用的 Windows 桌面。请在图形化 Windows 桌面中双击安装器。", file=sys.stderr)
        return 2

    window.title(f"{PRODUCT_NAME} 安装器")
    window.iconbitmap(default=str(brand_icon_path()))
    window.resizable(False, False)
    window.columnconfigure(1, weight=1)
    values = {name: tk.StringVar(value=str(path)) for name, path in defaults.items()}

    tk.Label(window, text=f"{PRODUCT_NAME} {version}", font=("Microsoft YaHei UI", 12, "bold")).grid(
        row=0, column=0, columnspan=3, padx=18, pady=(18, 6), sticky="w"
    )
    tk.Label(
        window,
        justify="left",
        text="请分别选择程序、台账数据和本机配置的保存位置。\n"
             "数据库、备份和导入原件只写入数据目录；安装和更新不会覆盖已有数据。\n"
             "安装完成后，桌面和开始菜单会提供启动、备份、诊断、更新与卸载入口。",
    ).grid(row=1, column=0, columnspan=3, padx=18, pady=(0, 14), sticky="w")

    labels = (("program", "程序目录（版本文件）"), ("data", "数据目录（数据库、备份、导入）"), ("config", "配置目录（安装位置记录）"))
    for row, (name, label) in enumerate(labels, start=2):
        tk.Label(window, text=label).grid(row=row, column=0, padx=(18, 8), pady=5, sticky="w")
        tk.Entry(window, textvariable=values[name], width=58).grid(row=row, column=1, padx=4, pady=5, sticky="ew")

        def choose_directory(key: str = name) -> None:
            """只选择目录，不创建、不清理、更不读取用户台账。"""
            chosen = filedialog.askdirectory(parent=window, title=f"选择{dict(labels)[key]}", initialdir=values[key].get())
            if chosen:
                values[key].set(chosen)

        tk.Button(window, text="选择…", command=choose_directory).grid(row=row, column=2, padx=(6, 18), pady=5)

    def install_from_window() -> None:
        """将用户明确选定的位置交给唯一的安装实现，失败时不关闭窗口。"""
        program_root = Path(values["program"].get().strip()).expanduser()
        data_root = Path(values["data"].get().strip()).expanduser()
        config_root = Path(values["config"].get().strip()).expanduser()
        if not all(str(path) and str(path) != "." for path in (program_root, data_root, config_root)):
            messagebox.showerror(PRODUCT_NAME, "程序目录、数据目录和配置目录均不能为空。", parent=window)
            return
        try:
            desktop, start_menu = default_shortcut_folders()
            result = install_release(
                selected_payload, program_root, data_root, config_root,
                desktop=desktop, start_menu=start_menu,
            )
        except Exception as error:
            messagebox.showerror(PRODUCT_NAME, f"安装未完成：{error}\n\n已有数据库和数据目录未被覆盖。", parent=window)
            return
        messagebox.showinfo(
            PRODUCT_NAME,
            f"安装完成，版本：{result['version']}\n\n"
            "请通过桌面或开始菜单中的“科技项目台账”启动。\n"
            "需要升级时，使用同一位置中的“科技项目台账 - 更新”。",
            parent=window,
        )
        window.destroy()

    tk.Button(window, text="开始安装", command=install_from_window, width=16).grid(
        row=5, column=1, padx=4, pady=(16, 18), sticky="e"
    )
    tk.Button(window, text="取消", command=window.destroy, width=10).grid(
        row=5, column=2, padx=(6, 18), pady=(16, 18)
    )
    window.mainloop()
    return 0


def default_user_root(local_app_data: str | None = None) -> Path:
    """取得建议目录；安装时用户可改为任意盘符，绝不硬编码 C 盘。"""
    value = local_app_data or os.environ.get("LOCALAPPDATA")
    if not value:
        raise RuntimeError("未找到 LOCALAPPDATA，无法确定当前用户安装目录")
    return Path(value) / PRODUCT_NAME


def default_install_root(local_app_data: str | None = None) -> Path:
    """兼容调用方的默认程序目录。"""
    return default_user_root(local_app_data) / APP_DIRECTORY


def default_shortcut_folders() -> tuple[Path, Path]:
    """返回当前用户桌面和开始菜单程序目录，安装及热更新均刷新这些入口。"""
    desktop = Path(os.environ["USERPROFILE"]) / "Desktop"
    start_menu = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    return desktop, start_menu


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


def write_location_config(config_root: Path, program_root: Path, data_root: Path, version: str, manifest_url: str | None = None) -> Path:
    """把用户选择保存到程序目录之外，供更新器与卸载入口查阅。"""
    config_root.mkdir(parents=True, exist_ok=True)
    location_file = config_root / "install_locations.json"
    current_file = config_root / "current-install.json"
    previous = {}
    if current_file.exists():
        try:
            previous = json.loads(current_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            previous = {}
    # install_locations 保持为稳定的路径契约；当前版本和更新地址单独保存，避免
    # 旧版诊断程序误把版本信息当作路径字段处理。
    location_file.write_text(json.dumps({"program_root": str(program_root), "data_root": str(data_root)}, ensure_ascii=False, indent=2), encoding="utf-8")
    payload = {"current_version": version}
    if manifest_url:
        payload["update_manifest_url"] = manifest_url
    elif isinstance(previous.get("update_manifest_url"), str):
        payload["update_manifest_url"] = previous["update_manifest_url"]
    current_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    # runtime_paths 模块只认识 ledger_home；此文件与安装位置记录并列且不在程序目录内。
    (config_root / "runtime-paths.json").write_text(json.dumps({"ledger_home": str(data_root)}, ensure_ascii=False, indent=2), encoding="utf-8")
    return location_file


def create_shortcut(shortcut: Path, target: Path, arguments: tuple[str, ...] = (), icon: Path | None = None) -> None:
    """创建 Windows 快捷方式，并显式指定品牌图标而不是继承 cmd 图标。"""
    if os.name != "nt":
        raise RuntimeError("桌面快捷方式只能在 Windows 上创建")
    script = (
        'var shell = new ActiveXObject("WScript.Shell");\n'
        'var link = shell.CreateShortcut(WScript.Arguments.Item(0));\n'
        'link.TargetPath = WScript.Arguments.Item(1);\n'
        'link.WorkingDirectory = WScript.Arguments.Item(2);\n'
        'link.IconLocation = WScript.Arguments.Item(3);\n'
        'var commandArguments = [];\n'
        'for (var index = 4; index < WScript.Arguments.length; index++) {\n'
        '  commandArguments.push("\\\"" + WScript.Arguments.Item(index).replace(/"/g, "\\\\\\\"") + "\\\"");\n'
        '}\n'
        'link.Arguments = commandArguments.join(" ");\n'
        'link.Save();\n'
    )
    with tempfile.TemporaryDirectory(prefix="ledger-shortcut-") as temporary:
        script_path = Path(temporary) / "create-shortcut.js"
        script_path.write_text(script, encoding="utf-8")
        subprocess.run(
            ["cscript.exe", "//nologo", str(script_path), str(shortcut), str(target),
             str(target.parent), str(icon or target), *arguments],
            check=True,
        )


def installed_environment(config_root: Path) -> dict[str, str]:
    """为安装版程序构造明确的运行环境，路径直接使用 Windows Unicode 字符串。"""
    environment = os.environ.copy()
    environment["LEDGER_PATHS_CONFIG"] = str(config_root / "runtime-paths.json")
    environment["LEDGER_INSTALL_CONFIG"] = str(config_root / "current-install.json")
    return environment


def launch_application(program_root: Path, config_root: Path, version: str, resident: bool = False) -> Path:
    """不经过 cmd.exe 启动主程序，彻底避免中文安装路径被系统代码页误解码。"""
    executable = program_root / version / "项目台账" / "项目台账.exe"
    if not executable.is_file():
        raise RuntimeError(f"主程序不存在：{executable}")
    command = [str(executable)]
    if resident:
        command.append("--resident")
    subprocess.Popen(
        command,
        env=installed_environment(config_root),
        close_fds=True,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    return executable


def launch_backup(program_root: Path, config_root: Path, version: str) -> Path:
    """通过无窗口进程启动备份程序，并传入与主程序相同的数据目录配置。"""
    executable = program_root / version / "台账备份" / "台账备份.exe"
    if not executable.is_file():
        raise RuntimeError(f"备份程序不存在：{executable}")
    subprocess.Popen(
        [str(executable)],
        env=installed_environment(config_root),
        close_fds=True,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    return executable


def create_launch_entries(program_root: Path, data_root: Path, config_root: Path, version: str, desktop: Path | None = None, start_menu: Path | None = None) -> dict[str, Path]:
    """创建纯 EXE 启动入口，避免中文路径经过 cmd.exe 后出现代码页乱码。"""
    program = program_root / version
    app_executable = program / "项目台账" / "项目台账.exe"
    installer_executable = program / "台账安装器.exe"
    updater_executable = program / "台账更新器.exe"
    common = (
        "--program-root", str(program_root), "--data-root", str(data_root),
        "--config-root", str(config_root), "--version", version,
    )
    targets = {
        "启动": (installer_executable, ("launch", *common)),
        "备份": (installer_executable, ("backup", *common)),
        "诊断": (installer_executable, (
            "diagnose", "--program-root", str(program_root), "--data-root", str(data_root),
            "--config-root", str(config_root),
        )),
        "卸载": (installer_executable, ("uninstall", "--program-root", str(program_root), "--version", version)),
        "更新": (updater_executable, (
            "update", "--program-root", str(program_root), "--data-root", str(data_root),
            "--config-root", str(config_root),
        )),
    }
    # 开机自启同样通过安装器设置运行环境，不再直接启动缺少配置的主程序。
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(
            key, PRODUCT_NAME, 0, winreg.REG_SZ,
            subprocess.list2cmdline([str(installer_executable), "launch", *common, "--resident"]),
        )
    for folder in (desktop, start_menu):
        if folder is not None:
            folder.mkdir(parents=True, exist_ok=True)
            for label, (target, arguments) in targets.items():
                shortcut_name = PRODUCT_NAME if label == "启动" else f"{PRODUCT_NAME} - {label}"
                create_shortcut(folder / f"{shortcut_name}.lnk", target, arguments=arguments, icon=app_executable)
    return {label: target for label, (target, _) in targets.items()}


def install_release(payload: Path, program_root: Path, data_root: Path, config_root: Path, desktop: Path | None = None, start_menu: Path | None = None, manifest_url: str | None = None) -> dict[str, Path | str]:
    """安装一个新程序版本，遇到同版本已存在时明确拒绝覆盖。"""
    version = read_payload_version(payload)
    source_program = payload / "项目台账"
    if not source_program.is_dir():
        raise RuntimeError(f"安装包缺少主程序目录：{source_program}")
    target = program_root / version
    if target.exists():
        raise RuntimeError(f"版本 {version} 已安装，安装器不会覆盖已有程序目录")
    ensure_data_directories(data_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = program_root / f".installing-{version}"
    if staging.exists():
        raise RuntimeError(f"检测到未完成的安装目录：{staging}；请先由维护人员检查后删除")
    config_files = tuple(config_root / name for name in ("install_locations.json", "current-install.json", "runtime-paths.json"))
    previous_config = {path: path.read_bytes() if path.exists() else None for path in config_files}
    try:
        # 先在同一程序根目录完整复制；只有复制成功才把新版本变成可见版本目录。
        shutil.copytree(source_program, staging / "项目台账")
        for name in ("台账备份",):
            source = payload / name
            if source.is_dir():
                shutil.copytree(source, staging / name)
            elif source.is_file():
                shutil.copy2(source, staging / name)
        # 独立安装器运行时从自身可执行文件复制，源码测试则可由 payload 提供样例文件。
        own_installer = payload / "台账安装器.exe"
        if not own_installer.is_file() and getattr(sys, "frozen", False):
            own_installer = Path(sys.executable)
        if own_installer.is_file():
            shutil.copy2(own_installer, staging / "台账安装器.exe")
        updater = payload / "台账更新器.exe"
        if updater.is_file():
            shutil.copy2(updater, staging / "台账更新器.exe")
        staging.replace(target)
        location_file = write_location_config(config_root, program_root, data_root, version, manifest_url)
        launchers = create_launch_entries(program_root, data_root, config_root, version, desktop, start_menu)
    except Exception:
        # 新版本尚未成为当前版本时仅清理其程序文件；不删除任何用户数据目录。
        if staging.exists():
            shutil.rmtree(staging)
        if target.exists():
            shutil.rmtree(target)
        # 启动入口创建失败时，恢复旧启动版本记录，避免用户入口指向半完成版本。
        for path, content in previous_config.items():
            if content is None:
                if path.exists():
                    path.unlink()
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
        raise
    return {"version": version, "program": target, "location_config": location_file, **launchers}


def uninstall_release(program_root: Path, version: str) -> Path:
    """只移除指定程序版本；稳定用户数据目录永远不在删除范围内。"""
    target = program_root / version
    if not target.is_dir():
        raise RuntimeError(f"未找到要卸载的程序版本：{target}")
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE) as key:
        try:
            winreg.DeleteValue(key, PRODUCT_NAME)
        except FileNotFoundError:
            pass
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


def main(argv: list[str] | None = None) -> int:
    """分流双击图形安装与维护命令行；无桌面环境时不执行静默安装。"""
    command_line = sys.argv[1:] if argv is None else argv
    if not command_line:
        return launch_install_gui()
    parser = argparse.ArgumentParser(description="科技项目台账当前用户安装器")
    parser.add_argument("command", choices=("install", "launch", "backup", "uninstall", "diagnose"), nargs="?", default="install")
    suggested_root = default_user_root()
    parser.add_argument("--program-root", type=Path, default=suggested_root / APP_DIRECTORY, help="程序版本目录，可选择任意盘符")
    parser.add_argument("--data-root", type=Path, default=suggested_root / "user-data", help="台账数据根目录，可选择任意盘符")
    parser.add_argument("--config-root", type=Path, default=suggested_root / "config", help="本机配置目录，位于程序目录之外")
    parser.add_argument("--version")
    parser.add_argument("--resident", action="store_true", help="启动后不自动打开浏览器，用于开机常驻")
    parser.add_argument("--manifest-url", help="Gitee 发布清单 HTTPS 地址，用于安装版人工更新")
    args = parser.parse_args(command_line)
    if args.command == "install":
        desktop, start_menu = default_shortcut_folders()
        result = install_release(
            release_root() / "payload", args.program_root, args.data_root, args.config_root,
            desktop=desktop, start_menu=start_menu, manifest_url=args.manifest_url,
        )
    elif args.command == "launch":
        if not args.version:
            parser.error("启动必须指定 --version")
        result = {"launched": str(launch_application(args.program_root, args.config_root, args.version, args.resident))}
    elif args.command == "backup":
        if not args.version:
            parser.error("备份必须指定 --version")
        result = {"launched": str(launch_backup(args.program_root, args.config_root, args.version))}
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

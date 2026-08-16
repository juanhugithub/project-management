#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""D13 安装包边界：发布物无用户数据，安装卸载在临时用户目录可验证。"""

import json
from pathlib import Path

import pytest

import installer
from release_tools.release_manifest import application_data_sources, assert_safe_relative_path


ROOT = Path(__file__).resolve().parents[1]


def _payload(tmp_path: Path, version: str = "0.1.0") -> Path:
    payload = tmp_path / "payload"
    app = payload / "项目台账"
    app.mkdir(parents=True)
    (app / "VERSION").write_text(version, encoding="utf-8")
    (app / "项目台账.exe").write_bytes(b"test")
    (payload / "台账备份").mkdir()
    (payload / "台账备份" / "台账备份.exe").write_bytes(b"test")
    (payload / "台账安装器.exe").write_bytes(b"test")
    return payload


def test_release_manifest_excludes_database_secret_and_user_directories():
    names = {source.relative_to(ROOT).as_posix() for source, _ in application_data_sources(ROOT)}
    assert not any(name == "data" or name.startswith("data/") for name in names)
    assert not any(name == "backups" or name.startswith("backups/") for name in names)
    assert not any(name == "config" or name.startswith("config/") for name in names)
    with pytest.raises(ValueError):
        assert_safe_relative_path(Path("data/project.db"))
    with pytest.raises(ValueError):
        assert_safe_relative_path(Path(".env"))


def test_install_uses_temporary_current_user_directory_and_preserves_existing_data(tmp_path, monkeypatch):
    program_root = tmp_path / "D盘" / "台账程序"
    data_root = tmp_path / "E盘" / "台账数据"
    config_root = tmp_path / "F盘" / "本机配置"
    data = data_root / "data"
    data.mkdir(parents=True)
    (data / "project.db").write_bytes(b"formal-data")
    monkeypatch.setattr(installer, "create_launch_entries", lambda *args, **kwargs: {})
    result = installer.install_release(_payload(tmp_path), program_root, data_root, config_root)
    assert result["version"] == "0.1.0"
    assert (program_root / "0.1.0" / "项目台账" / "项目台账.exe").is_file()
    assert (data / "project.db").read_bytes() == b"formal-data"
    assert all((data_root / directory).is_dir() for directory in installer.DATA_DIRECTORIES)
    saved = json.loads((config_root / "install_locations.json").read_text(encoding="utf-8"))
    assert saved == {"program_root": str(program_root), "data_root": str(data_root)}
    runtime_paths = json.loads((config_root / "runtime-paths.json").read_text(encoding="utf-8"))
    assert runtime_paths == {"ledger_home": str(data_root)}


def test_uninstall_only_removes_selected_program_version(tmp_path):
    program_root = tmp_path / "D盘" / "台账程序"
    data_root = tmp_path / "E盘" / "台账数据"
    program = program_root / "0.1.0"
    program.mkdir(parents=True)
    (data_root / "data").mkdir(parents=True)
    (data_root / "data" / "project.db").write_bytes(b"formal-data")
    installer.uninstall_release(program_root, "0.1.0")
    assert not program.exists()
    assert (data_root / "data" / "project.db").read_bytes() == b"formal-data"


def test_chinese_install_paths_use_direct_exe_shortcuts_instead_of_cmd(tmp_path, monkeypatch):
    """中文路径必须作为 Unicode 快捷方式参数保存，禁止再经过 cmd.exe 代码页解码。"""
    program_root = tmp_path / "程序目录" / "科技项目台账"
    data_root = tmp_path / "数据目录" / "项目数据"
    config_root = tmp_path / "配置目录" / "本机配置"
    desktop = tmp_path / "桌面"
    recorded_shortcuts = []
    recorded_registry = {}

    class RegistryKey:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    monkeypatch.setattr(installer.winreg, "OpenKey", lambda *args, **kwargs: RegistryKey())
    monkeypatch.setattr(
        installer.winreg, "SetValueEx",
        lambda key, name, reserved, kind, value: recorded_registry.update({name: value}),
    )
    monkeypatch.setattr(
        installer, "create_shortcut",
        lambda shortcut, target, arguments="", icon=None: recorded_shortcuts.append(
            {"shortcut": shortcut, "target": target, "arguments": arguments, "icon": icon}
        ),
    )

    installer.create_launch_entries(
        program_root, data_root, config_root, "1.2.3", desktop=desktop, start_menu=None,
    )

    assert len(recorded_shortcuts) == 5
    assert all(item["target"].suffix.lower() == ".exe" for item in recorded_shortcuts)
    assert not list(config_root.rglob("*.cmd")), "安装入口不得生成会乱码的批处理文件"
    start = next(item for item in recorded_shortcuts if item["shortcut"].name == "科技项目台账.lnk")
    assert start["target"].name == "台账安装器.exe"
    assert start["arguments"].startswith("launch ")
    assert str(program_root) in start["arguments"] and str(config_root) in start["arguments"]
    assert "台账安装器.exe" in recorded_registry[installer.PRODUCT_NAME]
    assert " launch " in recorded_registry[installer.PRODUCT_NAME]


def test_direct_launcher_sets_install_environment_without_console_window(tmp_path, monkeypatch):
    """无 cmd 启动仍须把数据和安装配置传给主程序，并保持无黑框运行。"""
    program_root = tmp_path / "程序根目录"
    config_root = tmp_path / "配置根目录"
    executable = program_root / "1.2.3" / "项目台账" / "项目台账.exe"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"test")
    recorded = {}

    def fake_popen(command, **kwargs):
        recorded["command"] = command
        recorded.update(kwargs)
        return object()

    monkeypatch.setattr(installer.subprocess, "Popen", fake_popen)
    result = installer.launch_application(program_root, config_root, "1.2.3", resident=True)

    assert result == executable
    assert recorded["command"] == [str(executable), "--resident"]
    assert recorded["env"]["LEDGER_PATHS_CONFIG"] == str(config_root / "runtime-paths.json")
    assert recorded["env"]["LEDGER_INSTALL_CONFIG"] == str(config_root / "current-install.json")
    assert recorded["creationflags"] == installer.subprocess.CREATE_NO_WINDOW


def test_real_windows_shortcut_round_trips_chinese_install_path(tmp_path, monkeypatch):
    """实际生成并读取 Windows 快捷方式，确认中文路径未经过批处理编码转换。"""
    from win32com.client import Dispatch

    program_root = tmp_path / "单位电脑" / "程序目录"
    data_root = tmp_path / "单位电脑" / "台账数据"
    config_root = tmp_path / "单位电脑" / "本机配置"
    desktop = tmp_path / "单位电脑" / "桌面"

    class RegistryKey:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    monkeypatch.setattr(installer.winreg, "OpenKey", lambda *args, **kwargs: RegistryKey())
    monkeypatch.setattr(installer.winreg, "SetValueEx", lambda *args, **kwargs: None)
    installer.install_release(
        _payload(tmp_path), program_root, data_root, config_root,
        desktop=desktop, start_menu=None,
    )

    shortcut = Dispatch("WScript.Shell").CreateShortcut(str(desktop / "科技项目台账.lnk"))
    expected_target = program_root / "0.1.0" / "台账安装器.exe"
    assert Path(shortcut.TargetPath) == expected_target
    assert shortcut.Arguments.startswith("launch ")
    assert str(program_root) in shortcut.Arguments
    assert str(data_root) in shortcut.Arguments
    assert str(config_root) in shortcut.Arguments
    assert not list(config_root.rglob("*.cmd"))

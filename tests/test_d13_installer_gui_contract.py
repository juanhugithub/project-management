#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""D13 双击安装界面契约：可选路径、保留命令行且不静默安装。"""

import ast
import inspect
from pathlib import Path

import installer


def test_double_click_without_arguments_enters_gui(monkeypatch):
    """无参数代表用户双击，必须显示选择界面而不是采用默认路径静默安装。"""
    calls = []
    monkeypatch.setattr(installer, "launch_install_gui", lambda: calls.append("gui") or 0)

    assert installer.main([]) == 0
    assert calls == ["gui"]


def test_command_line_install_parameters_remain_available(monkeypatch, tmp_path):
    """更新器和自动化测试仍可显式传入三个独立路径，不经过 tkinter。"""
    calls = []
    monkeypatch.setattr(installer, "install_release", lambda *args, **kwargs: calls.append((args, kwargs)) or {"version": "1.2.3"})
    monkeypatch.setattr(installer, "release_root", lambda: tmp_path / "release")
    program_root = tmp_path / "D盘" / "程序"
    data_root = tmp_path / "E盘" / "数据"
    config_root = tmp_path / "F盘" / "配置"

    assert installer.main([
        "install", "--program-root", str(program_root), "--data-root", str(data_root), "--config-root", str(config_root),
    ]) == 0
    assert calls[0][0][1:4] == (program_root, data_root, config_root)


def test_gui_contract_exposes_three_directory_selectors_and_update_entry():
    """界面文案必须让用户选择三类目录，并明确安装后可从更新入口升级。"""
    source = inspect.getsource(installer.launch_install_gui)

    assert "程序目录" in source
    assert "数据目录" in source
    assert "配置目录" in source
    assert "更新" in source
    assert "askdirectory" in source
    assert "agent.token" not in source
    ast.parse(source)


def test_gui_unavailable_returns_explicit_error(monkeypatch, capsys):
    """无图形环境只能明确报错，不能改为默认目录的后台安装。"""
    monkeypatch.setattr(installer, "read_payload_version", lambda payload: "1.2.3")

    import sys
    from types import ModuleType
    fake_tk = ModuleType("tkinter")
    fake_tk.TclError = type("TclError", (Exception,), {})
    fake_tk.Tk = lambda: (_ for _ in ()).throw(fake_tk.TclError("no display"))
    fake_tk.filedialog = ModuleType("tkinter.filedialog")
    fake_tk.messagebox = ModuleType("tkinter.messagebox")
    monkeypatch.setitem(sys.modules, "tkinter", fake_tk)

    assert installer.launch_install_gui(Path("payload"), Path("chosen")) == 2
    assert "未检测到可用的 Windows 桌面" in capsys.readouterr().err

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""品牌科技图标在网页、Windows 程序和快捷方式中的统一契约。"""

from pathlib import Path

from PIL import Image

import build_release
import installer


ROOT = Path(__file__).resolve().parents[1]


def test_web_brand_uses_orbit_icon_instead_of_text_mark():
    """左上角和浏览器页签均应引用科技图标，不再以“台”字充当标识。"""
    html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    svg = (ROOT / "static" / "brand-icon.svg").read_text(encoding="utf-8")
    assert '<img class="brand-mark" src="/static/brand-icon.svg' in html
    assert '<link rel="icon" type="image/svg+xml" href="/static/brand-icon.svg' in html
    assert '<span class="brand-mark" aria-hidden="true">台</span>' not in html
    assert "ellipse" in svg and "circle" in svg


def test_windows_icon_contains_all_launcher_sizes():
    """ICO 必须覆盖任务栏、桌面和高分屏常用尺寸。"""
    icon_path = ROOT / "assets" / "brand-icon.ico"
    with Image.open(icon_path) as icon:
        assert icon.format == "ICO"
        sizes = icon.ico.sizes()
    assert {(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)} <= sizes


def test_every_pyinstaller_target_embeds_brand_icon(tmp_path):
    """主程序、备份、更新器和安装器共享同一 PyInstaller 图标参数。"""
    command = build_release.pyinstaller_command(
        ROOT / "app.py", "项目台账", tmp_path / "dist", tmp_path / "work", tmp_path / "spec", []
    )
    icon_index = command.index("--icon")
    assert Path(command[icon_index + 1]) == ROOT / "assets" / "brand-icon.ico"


def test_shortcut_explicitly_uses_application_icon(tmp_path, monkeypatch):
    """快捷方式目标虽是启动脚本，但 IconLocation 必须指向带品牌图标的主程序。"""
    recorded = {}

    def fake_run(command, **kwargs):
        recorded["command"] = command
        recorded["script"] = Path(command[2]).read_text(encoding="utf-8")

    monkeypatch.setattr(installer.subprocess, "run", fake_run)
    shortcut = tmp_path / "科技项目台账.lnk"
    launcher = tmp_path / "启动科技项目台账.cmd"
    icon = tmp_path / "项目台账.exe"
    installer.create_shortcut(shortcut, launcher, icon=icon)

    assert "link.IconLocation" in recorded["script"]
    assert recorded["command"][-1] == str(icon)

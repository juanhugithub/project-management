#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""D13 已安装版更新契约：只更换程序版本，数据和配置路径不被更新器改写。"""

import hashlib
import json
from pathlib import Path

import pytest

import app
import installed_updater


def _file_url(path: Path) -> str:
    """构造跨平台 file URL，供完全离线的发布源模拟使用。"""
    return path.resolve().as_uri()


def _installed_config(tmp_path: Path, version: str = "0.1.0") -> tuple[Path, Path, Path, Path]:
    """建立程序、数据、配置彼此隔离的最小安装实例。"""
    program_root = tmp_path / "D盘" / "程序"
    data_root = tmp_path / "E盘" / "数据"
    config_root = tmp_path / "F盘" / "配置"
    (program_root / version / "项目台账").mkdir(parents=True)
    (data_root / "data").mkdir(parents=True)
    database = data_root / "data" / "project.db"
    database.write_bytes(b"formal-ledger-data")
    config_root.mkdir(parents=True)
    (config_root / "install_locations.json").write_text(json.dumps({"program_root": str(program_root), "data_root": str(data_root)}, ensure_ascii=False), encoding="utf-8")
    (config_root / "current-install.json").write_text(json.dumps({"current_version": version}, ensure_ascii=False), encoding="utf-8")
    return program_root, data_root, config_root, database


def _manifest(tmp_path: Path, version: str, installer: Path) -> str:
    """生成本地发布清单；文件本身不含用户数据、路径或密钥。"""
    manifest = tmp_path / "release-manifest.json"
    manifest.write_text(json.dumps({"version": version, "installer_url": _file_url(installer), "installer_sha256": hashlib.sha256(installer.read_bytes()).hexdigest(), "notes": ["本地测试发布"]}, ensure_ascii=False), encoding="utf-8")
    return _file_url(manifest)


def test_check_reads_local_release_manifest_without_writing_installation(tmp_path):
    program_root, data_root, config_root, database = _installed_config(tmp_path)
    installer_file = tmp_path / "台账安装器.exe"
    installer_file.write_bytes(b"new-installer")
    result = installed_updater.check_installed_update(_manifest(tmp_path, "0.2.0", installer_file), config_root)
    assert result["update_available"] is True
    assert result["current_version"] == "0.1.0"
    assert database.read_bytes() == b"formal-ledger-data"
    assert not list(program_root.glob("0.2.0"))


def test_apply_downloads_verified_installer_and_keeps_database_untouched(tmp_path, monkeypatch):
    program_root, data_root, config_root, database = _installed_config(tmp_path)
    installer_file = tmp_path / "台账安装器.exe"
    installer_file.write_bytes(b"verified-new-installer")
    manifest_url = _manifest(tmp_path, "0.2.0", installer_file)
    commands = []

    def fake_run(command, **kwargs):
        commands.append(command)
        # 模拟独立安装器：只新增程序版本并切换启动记录，绝不写 data_root。
        (program_root / "0.2.0" / "项目台账").mkdir(parents=True)
        location = config_root / "current-install.json"
        payload = json.loads(location.read_text(encoding="utf-8"))
        payload["current_version"] = "0.2.0"
        location.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        class Result:
            returncode = 0
            stdout = "installed"
            stderr = ""
        return Result()

    monkeypatch.setattr(installed_updater.subprocess, "run", fake_run)
    result = installed_updater.apply_installed_update(manifest_url, program_root, data_root, config_root)
    assert result["updated"] is True
    assert result["installed_version"] == "0.2.0"
    assert database.read_bytes() == b"formal-ledger-data"
    assert commands[0][1] == "install"
    assert str(data_root) in commands[0]
    assert str(config_root) in commands[0]


def test_bad_installer_hash_refuses_before_invoking_installer(tmp_path, monkeypatch):
    program_root, data_root, config_root, database = _installed_config(tmp_path)
    installer_file = tmp_path / "台账安装器.exe"
    installer_file.write_bytes(b"tampered")
    manifest = tmp_path / "release-manifest.json"
    manifest.write_text(json.dumps({"version": "0.2.0", "installer_url": _file_url(installer_file), "installer_sha256": "0" * 64}), encoding="utf-8")
    monkeypatch.setattr(installed_updater.subprocess, "run", lambda *args, **kwargs: pytest.fail("SHA 失败时不可运行安装器"))
    with pytest.raises(installed_updater.InstalledUpdateError, match="SHA-256"):
        installed_updater.apply_installed_update(_file_url(manifest), program_root, data_root, config_root)
    assert database.read_bytes() == b"formal-ledger-data"
    assert not (program_root / "0.2.0").exists()


def test_update_api_reads_install_paths_from_install_locations(tmp_path, monkeypatch):
    """网页更新接口必须遵守安装器的双配置文件契约，并从新版本目录重启。"""
    program_root = tmp_path / "程序目录"
    data_root = tmp_path / "数据目录"
    config_root = tmp_path / "配置目录"
    config_root.mkdir()
    current_install = config_root / "current-install.json"
    current_install.write_text(json.dumps({
        "current_version": "0.1.0",
        "update_manifest_url": "https://gitee.example/release-manifest.json",
    }, ensure_ascii=False), encoding="utf-8")
    (config_root / "install_locations.json").write_text(json.dumps({
        "program_root": str(program_root),
        "data_root": str(data_root),
    }, ensure_ascii=False), encoding="utf-8")

    applied = {}
    started = []

    def fake_apply(manifest, actual_program_root, actual_data_root, actual_config_root):
        """模拟安装器切换版本，同时记录网页接口传入的三个安装路径。"""
        applied.update({
            "manifest": manifest,
            "program_root": actual_program_root,
            "data_root": actual_data_root,
            "config_root": actual_config_root,
        })
        payload = json.loads(current_install.read_text(encoding="utf-8"))
        payload["current_version"] = "0.2.0"
        current_install.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    class ImmediateThread:
        """让后台更新任务在测试线程内立即执行，便于精确断言重启结果。"""

        def __init__(self, target, daemon):
            self.target = target

        def start(self):
            self.target()

    class FakeServer:
        def __init__(self):
            self.stopped = False

        def shutdown(self):
            self.stopped = True

    class FakeHandler:
        def __init__(self):
            self.server = FakeServer()
            self.response = None

        def _ok(self, payload):
            self.response = (200, payload)

        def _err(self, status, message):
            self.response = (status, {"error": message})

    monkeypatch.setattr(app, "INSTALL_CONFIG", str(current_install))
    monkeypatch.setattr(installed_updater, "apply_installed_update", fake_apply)
    monkeypatch.setattr(app.threading, "Thread", ImmediateThread)
    monkeypatch.setattr(app.subprocess, "Popen", lambda command, **kwargs: started.append(command))

    handler = FakeHandler()
    app.Handler._api_update(handler, "POST", ["apply"])

    assert handler.response == (200, {"started": True})
    assert applied == {
        "manifest": "https://gitee.example/release-manifest.json",
        "program_root": program_root,
        "data_root": data_root,
        "config_root": config_root,
    }
    assert started == [[str(program_root / "0.2.0" / "项目台账" / "项目台账.exe"), "--resident"]]
    assert handler.server.stopped is True

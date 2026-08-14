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

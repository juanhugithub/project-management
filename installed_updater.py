#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""已安装版的人工更新器。

它不使用 Git，也不触碰 SQLite、备份、导入原件或本机配置中的运行路径；只从
发布清单下载完整安装器，校验 SHA-256 后让安装器把新程序版本放入既有程序根目录。
"""

import argparse
import hashlib
import json
import subprocess
import tempfile
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import installer


class InstalledUpdateError(RuntimeError):
    """发布清单、下载包或安装过程不符合更新契约时的明确错误。"""


@dataclass(frozen=True)
class InstalledRelease:
    """经过格式校验的安装版发布信息。"""

    version: str
    installer_url: str
    installer_sha256: str
    notes: tuple[str, ...]


def _version_parts(value: str) -> tuple[int, ...]:
    """只接受确定的数字版本号，避免把非正式标签误判为可升级版本。"""
    if not isinstance(value, str) or not value or any(not part.isdecimal() for part in value.split(".")):
        raise InstalledUpdateError(f"发布版本号无效：{value!r}")
    return tuple(int(part) for part in value.split("."))


def _read_url(url: str) -> bytes:
    """读取 HTTPS 或本地 file 发布物；测试可使用 file，正式发布应使用 HTTPS。"""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"https", "file"}:
        raise InstalledUpdateError("发布地址必须使用 HTTPS；仅自动化测试允许 file 地址")
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            return response.read()
    except OSError as error:
        raise InstalledUpdateError(f"无法读取发布物：{url}") from error


def _sha256_bytes(content: bytes) -> str:
    """以分块哈希避免大安装包复制出额外内存。"""
    digest = hashlib.sha256()
    digest.update(content)
    return digest.hexdigest()


def read_release_manifest(manifest_url: str) -> InstalledRelease:
    """下载并严格校验发布清单，拒绝缺失校验值或未知字段类型的发布。"""
    try:
        payload = json.loads(_read_url(manifest_url).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise InstalledUpdateError("发布清单不是有效 UTF-8 JSON") from error
    if not isinstance(payload, dict):
        raise InstalledUpdateError("发布清单必须是对象")
    version = payload.get("version")
    installer_url = payload.get("installer_url")
    checksum = payload.get("installer_sha256")
    notes = payload.get("notes", [])
    _version_parts(version)
    if not isinstance(installer_url, str) or not installer_url.strip():
        raise InstalledUpdateError("发布清单缺少 installer_url")
    if not isinstance(checksum, str) or len(checksum) != 64 or any(char not in "0123456789abcdef" for char in checksum.lower()):
        raise InstalledUpdateError("发布清单 installer_sha256 必须为 64 位十六进制 SHA-256")
    if not isinstance(notes, list) or any(not isinstance(note, str) for note in notes):
        raise InstalledUpdateError("发布清单 notes 必须是字符串数组")
    return InstalledRelease(version, installer_url, checksum.lower(), tuple(notes))


def read_installed_version(config_root: Path) -> str:
    """从安装器持久化的位置记录读取当前启动版本，不扫描或修改用户数据目录。"""
    location = config_root / "current-install.json"
    try:
        payload = json.loads(location.read_text(encoding="utf-8"))
        version = payload["current_version"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise InstalledUpdateError(f"未找到有效的当前安装版本记录：{location}") from error
    _version_parts(version)
    return version


def configured_manifest_url(config_root: Path) -> str:
    """从独立本机配置取得发布清单地址；缺失时要求维护人员明确配置。"""
    location = config_root / "current-install.json"
    try:
        value = json.loads(location.read_text(encoding="utf-8")).get("update_manifest_url")
    except (OSError, json.JSONDecodeError) as error:
        raise InstalledUpdateError(f"无法读取更新配置：{location}") from error
    if not isinstance(value, str) or not value.strip():
        raise InstalledUpdateError("此安装尚未配置 Gitee 发布清单地址；请使用安装器的 --manifest-url 重新安装同一发布版本")
    return value.strip()


def check_installed_update(manifest_url: str | None, config_root: Path) -> dict:
    """只检查，不下载、不安装、不写入程序或数据目录。"""
    current = read_installed_version(config_root)
    release = read_release_manifest(manifest_url or configured_manifest_url(config_root))
    return {"current_version": current, "release": release, "update_available": _version_parts(release.version) > _version_parts(current)}


def _download_verified_installer(release: InstalledRelease, temporary: Path) -> Path:
    """下载到临时文件后再校验，校验失败绝不调用安装器。"""
    content = _read_url(release.installer_url)
    actual = _sha256_bytes(content)
    if actual != release.installer_sha256:
        raise InstalledUpdateError(f"安装器 SHA-256 校验失败：期望 {release.installer_sha256}，实际 {actual}")
    target = temporary / "台账安装器.exe"
    target.write_bytes(content)
    return target


def apply_installed_update(manifest_url: str | None, program_root: Path, data_root: Path, config_root: Path) -> dict:
    """校验后启动新安装器；安装器只新增版本目录并重写启动入口，不执行数据库迁移。"""
    plan = check_installed_update(manifest_url, config_root)
    if not plan["update_available"]:
        return {"updated": False, **plan}
    release: InstalledRelease = plan["release"]
    with tempfile.TemporaryDirectory(prefix="ledger-installed-update-") as directory:
        downloaded = _download_verified_installer(release, Path(directory))
        command = [str(downloaded), "install", "--program-root", str(program_root), "--data-root", str(data_root), "--config-root", str(config_root)]
        result = subprocess.run(command, text=True, encoding="utf-8", errors="replace", capture_output=True)
    if result.returncode != 0:
        raise InstalledUpdateError("新版本安装失败；原程序版本、数据库和配置均未改动：" + (result.stderr or result.stdout).strip())
    installed = read_installed_version(config_root)
    if installed != release.version:
        raise InstalledUpdateError(f"安装器完成后当前版本不一致：期望 {release.version}，实际 {installed}")
    return {"updated": True, **plan, "installed_version": installed}


def main() -> int:
    """仅提供人工点击入口；不支持后台静默更新。"""
    parser = argparse.ArgumentParser(description="科技项目台账安装版更新器")
    parser.add_argument("command", choices=("check", "update"))
    parser.add_argument("--manifest-url", help="Gitee 发布清单 HTTPS 地址；未填写时读取本机安装配置")
    parser.add_argument("--program-root", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--config-root", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "check":
        result = check_installed_update(args.manifest_url, args.config_root)
        print("发现新版本：" + ("是" if result["update_available"] else "否"))
        print(f"当前版本：{result['current_version']}；发布版本：{result['release'].version}")
        return 0
    result = apply_installed_update(args.manifest_url, args.program_root, args.data_root, args.config_root)
    print("更新完成" if result["updated"] else "当前已是最新版本")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

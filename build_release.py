#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成可离线分发的 Windows 主程序、备份程序与当前用户安装器。"""

import shutil
import subprocess
import sys
from pathlib import Path

from release_tools.release_manifest import application_data_sources


PROJECT_ROOT = Path(__file__).resolve().parent
BUILD_ROOT = PROJECT_ROOT / "build" / "d13"
RELEASE_ROOT = PROJECT_ROOT / "release"


def pyinstaller_command(entry: Path, name: str, dist: Path, work: Path, spec: Path, data: list[tuple[Path, Path]], onefile: bool = False) -> list[str]:
    """构造确定的 PyInstaller 命令；数据清单只来自 release_manifest。"""
    bundle_mode = "--onefile" if onefile else "--onedir"
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", bundle_mode, "--name", name,
               "--distpath", str(dist), "--workpath", str(work), "--specpath", str(spec)]
    for source, destination in data:
        command.extend(["--add-data", f"{source};{destination}"])
    command.append(str(entry))
    return command


def build() -> Path:
    """先构建运行时目录，再将其封装进独立安装器。"""
    if BUILD_ROOT.exists():
        shutil.rmtree(BUILD_ROOT)
    if RELEASE_ROOT.exists():
        shutil.rmtree(RELEASE_ROOT)
    stage = BUILD_ROOT / "stage"
    dist = stage / "payload"
    work = BUILD_ROOT / "work"
    spec = BUILD_ROOT / "spec"
    data = application_data_sources(PROJECT_ROOT)
    subprocess.run(pyinstaller_command(PROJECT_ROOT / "app.py", "项目台账", dist, work / "app", spec, data), check=True)
    subprocess.run(pyinstaller_command(PROJECT_ROOT / "backup.py", "台账备份", dist, work / "backup", spec, []), check=True)
    installer_data = [(dist, Path("payload"))]
    subprocess.run(pyinstaller_command(PROJECT_ROOT / "installer.py", "台账安装器", RELEASE_ROOT, work / "installer", spec, installer_data, onefile=True), check=True)
    return RELEASE_ROOT / "台账安装器.exe"


if __name__ == "__main__":
    print(build())

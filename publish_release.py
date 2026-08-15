#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""使用 GITEE_API_TOKEN 发布当前安装包并更新稳定清单。

Token 只从环境变量读取，绝不写入仓库、输出或发布资产。执行前应已完成
build_release.py；脚本会复用同名 Release，避免重复创建版本。
"""
import hashlib
import json
import os
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OWNER = "juanhu6"
REPO = "project-management"
API = f"https://gitee.com/api/v5/repos/{OWNER}/{REPO}"
MANIFEST = ROOT / "updates" / "release-manifest.json"


def _request(path, method="GET", payload=None):
    token = os.environ.get("GITEE_API_TOKEN", "").strip()
    if not token:
        raise RuntimeError("未配置 GITEE_API_TOKEN")
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    headers = {"Authorization": f"token {token}", "Content-Type": "application/json"}
    request = urllib.request.Request(API + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace")
        raise RuntimeError(f"Gitee API {error.code}: {detail}") from error


def _preflight_token():
    """发布前验证 Token 的仓库访问权限，避免先创建半成品 Release。"""
    _request("")


def _upload_asset(release_id, package):
    """以 multipart 上传安装器；不打印响应中的 Token 或请求头。"""
    token = os.environ["GITEE_API_TOKEN"].strip()
    boundary = "----ReasonixReleaseBoundary"
    content = package.read_bytes()
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=access_token\r\n\r\n{token}\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=file; filename=台账安装器.exe\r\n"
            "Content-Type: application/octet-stream\r\n\r\n").encode("utf-8") + content + f"\r\n--{boundary}--\r\n".encode()
    request = urllib.request.Request(
        f"{API}/releases/{release_id}/attach_files", data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace")
        raise RuntimeError(f"上传 Release 资产失败 {error.code}: {detail}") from error


def publish():
    _preflight_token()
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    package = ROOT / "release" / "台账安装器.exe"
    if not package.is_file():
        raise RuntimeError("缺少 release/台账安装器.exe，请先运行 build_release.py")
    digest = hashlib.sha256(package.read_bytes()).hexdigest()
    releases = _request("/releases")
    release = next((item for item in releases if item.get("tag_name") == version), None)
    if release is None:
        release = _request("/releases", "POST", {"tag_name": version, "name": f"台账安装器 {version}",
                                                    "target_commitish": "master", "body": f"科技项目台账 {version}"})
    asset = next((item for item in release.get("assets", []) if item.get("name") == "台账安装器.exe"), None)
    if asset is None:
        asset = _upload_asset(release["id"], package)
    manifest = {"version": version, "installer_url": asset["browser_download_url"],
                "installer_sha256": digest, "notes": [f"科技项目台账 {version}"]}
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    subprocess.run(["git", "add", str(MANIFEST)], cwd=ROOT, check=True)
    subprocess.run(["git", "commit", "-m", f"release: publish {version} manifest"], cwd=ROOT, check=False)
    subprocess.run(["git", "push", "origin", "master"], cwd=ROOT, check=True)
    print(f"已发布 Gitee Release {version}，安装包 SHA-256：{digest}")


if __name__ == "__main__":
    publish()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""科技项目台账的本地代码更新器。

更新器只更新 Git 管理的代码。正式数据库、备份、导入原件和本机密钥不属于
发布物；更新前只为指定数据库创建在线备份，绝不执行数据库迁移或降级。
"""

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from backup import create_backup
from runtime_paths import get_runtime_paths
from version import get_version


PROJECT_ROOT = Path(__file__).resolve().parent
RUNTIME_PATHS = get_runtime_paths()
DEFAULT_DATABASE = RUNTIME_PATHS.database
DEFAULT_BACKUP_DIR = RUNTIME_PATHS.backups

# 这些路径代表正式事实、本机运行材料或凭据，任何一个进入发布版本都必须失败。
PROTECTED_PREFIXES = (
    "data/",
    "backups/",
    "import-archives/",
    "imports/archive/",
    "imports/archives/",
    "imports/originals/",
    "secrets/",
)
PROTECTED_NAMES = {".env", ".env.local", "local-config.json", "credentials.json"}
PROTECTED_SUFFIXES = (".key", ".pem", ".pfx")


class UpdateError(RuntimeError):
    """更新前置条件、Git 状态或健康检查不满足时给调用方的明确失败。"""


@dataclass(frozen=True)
class UpdatePlan:
    """一次稳定版检查的确定性结果，可直接展示给人工操作者。"""

    current_commit: str
    stable_commit: str
    current_version: str
    stable_version: str
    changes: tuple[str, ...]
    fast_forward_only: bool

    @property
    def update_available(self) -> bool:
        """当前提交落后于 stable 时才允许进入更新操作。"""
        return self.current_commit != self.stable_commit


def _git(repo: str | Path, *arguments: str, check: bool = True) -> str:
    """以统一 UTF-8 方式运行 Git 命令，失败时保留 Git 的原始原因。"""
    result = subprocess.run(
        ["git", *arguments], cwd=Path(repo), text=True, encoding="utf-8",
        errors="replace", capture_output=True,
    )
    if check and result.returncode != 0:
        raise UpdateError((result.stderr or result.stdout).strip() or "Git 命令执行失败")
    return result.stdout.strip()


def _is_protected(path: str) -> bool:
    """判断一个 Git 跟踪路径是否违反代码与本机数据隔离约束。"""
    normalized = path.replace("\\", "/").lstrip("./")
    name = normalized.rsplit("/", 1)[-1]
    return (
        normalized.startswith(PROTECTED_PREFIXES)
        or name in PROTECTED_NAMES
        or name.endswith(PROTECTED_SUFFIXES)
    )


def assert_release_manifest_clean(repo: str | Path = PROJECT_ROOT) -> None:
    """拒绝含数据库、导入原件、备份或密钥的 Git 发布清单。"""
    tracked = _git(repo, "ls-files", "-z")
    forbidden = [item for item in tracked.split("\0") if item and _is_protected(item)]
    if forbidden:
        raise UpdateError("发布清单包含受保护文件：" + "、".join(forbidden))


def check_stable_update(repo: str | Path = PROJECT_ROOT, remote: str = "origin",
                        branch: str = "stable") -> UpdatePlan:
    """拉取稳定分支元数据并生成更新预览，不修改工作树或数据库。"""
    repo = Path(repo)
    assert_release_manifest_clean(repo)
    _git(repo, "fetch", remote, branch)
    stable_ref = f"{remote}/{branch}"
    current_commit = _git(repo, "rev-parse", "HEAD")
    stable_commit = _git(repo, "rev-parse", stable_ref)
    current_version = get_version(repo)
    stable_version = _git(repo, "show", f"{stable_ref}:VERSION")
    relation = subprocess.run(
        ["git", "merge-base", "--is-ancestor", "HEAD", stable_ref], cwd=repo,
        text=True, encoding="utf-8", errors="replace", capture_output=True,
    )
    fast_forward_only = relation.returncode == 0
    changes = tuple(filter(None, _git(repo, "log", "--format=%h %s", f"HEAD..{stable_ref}").splitlines()))
    return UpdatePlan(current_commit, stable_commit, current_version, stable_version, changes, fast_forward_only)


def run_health_check(repo: str | Path, command: list[str] | None = None) -> None:
    """在代码更新完成后执行明确的健康检查，任何失败都由更新流程回退代码。"""
    command = command or [sys.executable, "scripts/check.py"]
    result = subprocess.run(command, cwd=Path(repo), text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise UpdateError(f"更新后健康检查失败（exit={result.returncode}）")


def apply_stable_update(repo: str | Path = PROJECT_ROOT, database_path: str | Path = DEFAULT_DATABASE,
                        backup_dir: str | Path = DEFAULT_BACKUP_DIR, remote: str = "origin",
                        branch: str = "stable", health_command: list[str] | None = None) -> dict:
    """备份后仅以快进方式合入 stable；健康检查失败时只回退代码提交。"""
    repo = Path(repo)
    plan = check_stable_update(repo, remote, branch)
    if not plan.update_available:
        return {"updated": False, "plan": plan, "backup": None}
    if not plan.fast_forward_only:
        raise UpdateError("当前代码并非 stable 的祖先，拒绝非快进更新")

    # 备份使用现有 SQLite online backup API；它不会修改源数据库。
    backup = create_backup(database_path, backup_dir)
    try:
        _git(repo, "merge", "--ff-only", f"{remote}/{branch}")
        run_health_check(repo, health_command)
    except Exception as error:
        # 失败仅回退受 Git 管理的代码；绝不自动还原或降级数据库。
        _git(repo, "reset", "--hard", plan.current_commit)
        raise UpdateError(f"代码已回退到更新前版本；数据库备份保留在 {backup}。原因：{error}") from error
    return {"updated": True, "plan": plan, "backup": backup, "version": get_version(repo)}


def main() -> int:
    """提供人工触发的检查与更新命令，不实现后台静默更新。"""
    parser = argparse.ArgumentParser(description="科技项目台账安全代码更新器")
    parser.add_argument("command", choices=("check", "update"))
    parser.add_argument("--repo", default=str(PROJECT_ROOT))
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--branch", default="stable")
    parser.add_argument("--database", default=str(DEFAULT_DATABASE))
    parser.add_argument("--backup-dir", default=str(DEFAULT_BACKUP_DIR))
    args = parser.parse_args()
    if args.command == "check":
        plan = check_stable_update(args.repo, args.remote, args.branch)
        print(f"当前版本：{plan.current_version}（{plan.current_commit[:12]}）")
        print(f"稳定版本：{plan.stable_version}（{plan.stable_commit[:12]}）")
        print("可快进更新：" + ("是" if plan.fast_forward_only else "否"))
        for change in plan.changes:
            print("- " + change)
        return 0
    result = apply_stable_update(args.repo, args.database, args.backup_dir, args.remote, args.branch)
    print("更新完成" if result["updated"] else "当前已是稳定版本")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

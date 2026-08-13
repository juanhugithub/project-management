#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""科技项目台账 — 统一检查脚本（G0-4，2026-08-13）

一条命令完成全部基线验证（PLAN G0 验收入口）：
    python scripts/check.py

检查项（对应 PLAN G0-4 与交付约束 2）：
  1. Python 语法检查    —— 对所有 .py 源码做内存编译（compile()，不落盘 pyc）
  2. Node 前端语法检查   —— node --check static/app.js；Node 缺失时明确失败，
                            绝不静默跳过（交付约束 2）
  3. 单元/API 测试      —— python -m pytest tests/ -q
  4. SQLite 正式库检查   —— 以只读模式打开 data/project.db，执行
                            PRAGMA integrity_check 与 foreign_key_check；
                            测试运行前后各做一次，验证测试未破坏正式库
  5. 正式库 SHA-256 守卫 —— 测试运行前后对比 data/project.db 的哈希，
                            任何变化即失败（PLAN G0 验收红线）
  6. .vibe 治理校验     —— 调用 vibe-engineer 的 validate_vibe_project.py

退出码：全部通过 0；任一失败 1（失败项逐条打印，可定位）。

约定：
  - 除运行 pytest 与校验脚本外，本脚本不写任何文件；
  - 正式库永远以只读（mode=ro）方式打开，绝无写路径；
  - 新增检查项时保持「缺工具即失败」原则，禁止静默跳过。
"""

import hashlib
import os
import shutil
import sqlite3
import subprocess
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT_ROOT, "data", "project.db")

# vibe 校验脚本（PLAN G0 验收命令中的固定路径；可用环境变量覆盖）
VIBE_VALIDATOR = os.environ.get(
    "VIBE_VALIDATOR",
    r"C:\Users\Administrator\.codex\skills\vibe-engineer\scripts\validate_vibe_project.py",
)

# 参与 Python 语法检查的源码文件（tests/ 与 scripts/ 下所有 .py 一并纳入）
PY_SOURCES = [
    os.path.join(PROJECT_ROOT, "app.py"),
    os.path.join(PROJECT_ROOT, "backup.py"),
    os.path.join(PROJECT_ROOT, "import_excel.py"),
    os.path.join(PROJECT_ROOT, "make_template.py"),
    os.path.join(PROJECT_ROOT, "mcp_server.py"),
    os.path.join(PROJECT_ROOT, "scripts", "check.py"),
]
TESTS_DIR = os.path.join(PROJECT_ROOT, "tests")
if os.path.isdir(TESTS_DIR):
    PY_SOURCES += sorted(
        os.path.join(TESTS_DIR, f) for f in os.listdir(TESTS_DIR) if f.endswith(".py"))

# 前端语法检查目标
APP_JS = os.path.join(PROJECT_ROOT, "static", "app.js")

RESULTS = []  # (名称, ok: bool, 详情)


def record(name, ok, detail):
    """记录一步检查结果。"""
    RESULTS.append((name, bool(ok), detail))
    tag = "OK  " if ok else "FAIL"
    print(f"[{tag}] {name}: {detail}")


# ---------------------------------------------------------------------------
# 1. Python 语法检查（内存编译，不生成 .pyc）
# ---------------------------------------------------------------------------
def check_python_syntax():
    failed = []
    for path in PY_SOURCES:
        try:
            with open(path, "r", encoding="utf-8") as f:
                compile(f.read(), os.path.relpath(path, PROJECT_ROOT), "exec")
        except SyntaxError as e:
            failed.append(f"{os.path.relpath(path, PROJECT_ROOT)}:{e.lineno} {e.msg}")
    if failed:
        record("Python 语法检查", False, f"{len(failed)} 个文件语法错误: " + "; ".join(failed))
    else:
        record("Python 语法检查", True, f"{len(PY_SOURCES)} 个 .py 文件编译通过")


# ---------------------------------------------------------------------------
# 2. Node 前端语法检查（缺 Node 明确失败）
# ---------------------------------------------------------------------------
def check_node_syntax():
    node = shutil.which("node")
    if node is None:
        record("Node 前端语法检查", False,
               "未找到 node 可执行文件（shutil.which('node') 为空）—— 缺少工具即失败，"
               "不静默跳过。请安装 Node.js 后重试。")
        return
    proc = subprocess.run([node, "--check", APP_JS], capture_output=True, text=True)
    if proc.returncode == 0:
        record("Node 前端语法检查", True, f"node --check {os.path.relpath(APP_JS, PROJECT_ROOT)} 通过")
    else:
        record("Node 前端语法检查", False,
               f"node --check 失败 (exit {proc.returncode}): {(proc.stderr or '').strip()}")


# ---------------------------------------------------------------------------
# 3. 正式库只读完整性 / 外键检查（mode=ro，绝无写路径）
# ---------------------------------------------------------------------------
def check_sqlite_readonly(tag):
    """以只读模式检查 data/project.db 的 integrity_check 与 foreign_key_check。"""
    if not os.path.exists(DB_PATH):
        record(f"SQLite 正式库完整性({tag})", False, f"未找到正式库: {DB_PATH}")
        return
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    except sqlite3.Error as e:
        record(f"SQLite 正式库完整性({tag})", False, f"只读打开失败: {e}")
        return
    try:
        integrity = conn.execute("PRAGMA integrity_check").fetchall()
        fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        ok = len(integrity) == 1 and integrity[0][0] == "ok" and len(fk) == 0
        detail = (f"integrity_check={integrity[0][0] if integrity else integrity}, "
                  f"foreign_key_check={len(fk)} 条违规")
        if not ok:
            detail += f"（违规详情: {fk}）"
        record(f"SQLite 正式库完整性({tag})", ok, detail)
    except sqlite3.Error as e:
        record(f"SQLite 正式库完整性({tag})", False, f"检查执行失败: {e}")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 4. 正式库 SHA-256 守卫
# ---------------------------------------------------------------------------
def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def check_db_sha_guard(before):
    """对比测试运行前后的正式库哈希。"""
    if not os.path.exists(DB_PATH):
        record("正式库 SHA-256 守卫", False, f"未找到正式库: {DB_PATH}")
        return
    after = sha256_of(DB_PATH)
    ok = after == before
    record("正式库 SHA-256 守卫", ok,
           f"运行前 {before[:16]}… / 运行后 {after[:16]}… "
           + ("（一致，正式库未被测试改动）" if ok else "（不一致！测试污染了正式库！）"))


# ---------------------------------------------------------------------------
# 5. pytest 单元/API 测试
# ---------------------------------------------------------------------------
def check_pytest():
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q"],
        cwd=PROJECT_ROOT, capture_output=True, text=True)
    tail = (proc.stdout or "").strip().splitlines()
    tail = tail[-3:] if len(tail) > 3 else tail
    detail = " | ".join(tail) if tail else ""
    if proc.returncode == 0:
        record("pytest 测试", True, f"exit=0 {detail}")
    else:
        record("pytest 测试", False, f"exit={proc.returncode} {detail}")
        # 打印失败详情（x 为 xfail 属预期，f/E 才是问题）
        print((proc.stdout or "")[-3000:])


# ---------------------------------------------------------------------------
# 6. .vibe 治理校验
# ---------------------------------------------------------------------------
def check_vibe():
    if not os.path.isfile(VIBE_VALIDATOR):
        record(".vibe 治理校验", False,
               f"未找到校验脚本: {VIBE_VALIDATOR}（可设环境变量 VIBE_VALIDATOR 指定）")
        return
    proc = subprocess.run(
        [sys.executable, VIBE_VALIDATOR, PROJECT_ROOT],
        capture_output=True, text=True)
    out = ((proc.stdout or "") + (proc.stderr or "")).strip()
    if proc.returncode == 0:
        record(".vibe 治理校验", True, out.splitlines()[0] if out else "通过")
    else:
        record(".vibe 治理校验", False, out or f"exit={proc.returncode}")


# ---------------------------------------------------------------------------
def main():
    # 统一以 UTF-8 输出，避免 Windows GBK 控制台对 ✓ 等字符报 UnicodeEncodeError
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass  # 非 TTY/旧 Python 时忽略

    print(f"===== 科技项目台账 统一检查（{PROJECT_ROOT}）=====")
    print(f"pytest: {sys.executable}\n")

    # 0) 记录正式库基线哈希（此后任何步骤都不得改变它）
    if not os.path.exists(DB_PATH):
        print(f"[FAIL] 未找到正式库: {DB_PATH}")
        return 1
    sha_before = sha256_of(DB_PATH)
    print(f"[基线] 正式库 SHA-256 = {sha_before}")

    # 1) Python 语法
    check_python_syntax()
    # 2) Node 语法（缺工具即失败）
    check_node_syntax()
    # 3) 测试前的正式库只读完整性
    check_sqlite_readonly("测试前")
    # 4) 测试
    check_pytest()
    # 5) 测试后的正式库只读完整性 + SHA 守卫
    check_sqlite_readonly("测试后")
    check_db_sha_guard(sha_before)
    # 6) .vibe 治理校验
    check_vibe()

    print("\n===== 汇总 =====")
    failed = [r for r in RESULTS if not r[1]]
    for name, ok, detail in RESULTS:
        print(f"  [{'OK' if ok else 'FAIL'}] {name}")
    if failed:
        print(f"\n结果: FAIL（{len(failed)} 项未通过）")
        return 1
    print("\n结果: ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

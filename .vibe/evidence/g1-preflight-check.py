#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""G1 正式库只读预检脚本（2026-08-13）

用途：对正式库 data/project.db 做 G1 阶段要求的「只读预检」，输出不合规
记录报告，为后续版本化迁移（docs/migrations/README.md）提供现状基线。

只读保证（G1 契约红线）：
1. 本脚本所有数据库连接一律使用 SQLite 只读 URI
   （`file:...?mode=ro`），URI 层即拒绝任何写事务；
2. 本脚本不创建、不修改、不删除任何文件，只向 stdout 打印结果；
3. 脚本在打开数据库前与检查完成后各计算一次正式库 SHA-256 并对比，
   任何差异都会导致失败退出——从文件哈希层面证明「零写操作」。

可重复性：脚本对空库与有数据库均适用（逐项检查均以「无记录 = 无不合规」
计数），未来迁移前后可再次运行同一脚本对比基线。

用法：python .vibe/evidence/g1-preflight-check.py
"""

import hashlib
import json
import os
import re
import sqlite3
import sys
from datetime import datetime

# ---------------------------------------------------------------------------
# 常量：正式库路径与 G1 已确认契约中的枚举（与 docs/decisions/0001 保持一致）
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.path.join(BASE_DIR, "data", "project.db")

# G1 契约（HUMAN 2026-08-13 确认）：正常流转链（仅沿链前进、禁止回退/跳跃）
NORMAL_FLOW = ["申报中", "已立项", "实施中", "待验收", "已验收", "绩效跟踪", "已完结"]
# 异常态：中止（仅从 已立项/实施中/待验收 进入，不可恢复）、撤销（不可恢复终态）
SUSPEND_SOURCES = {"已立项", "实施中", "待验收"}
VALID_STAGES = NORMAL_FLOW + ["中止", "撤销"]

FUNDING_STATUSES = {"未拨付", "已拨付", "已到账"}
NODE_STATUSES = {"待办", "已完成", "已逾期"}

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# 金额单位「万元」可保留的小数位上限（浮点存储允许 1e-6 容差）
AMOUNT_MAX_DECIMALS = 2

REPORT = []  # (检查项, 违规数, 详情列表)


def record(item, violations, details):
    """登记一项检查结果；violations 为违规记录数，details 为违规明细。"""
    REPORT.append((item, violations, details))


def sha256_of(path):
    """计算文件 SHA-256（分块读取）。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def is_valid_date(s, allow_empty=True):
    """校验 YYYY-MM-DD 格式（并用 datetime 拒绝 2026-13-99 这类假日期）。"""
    if s is None or s == "":
        return allow_empty
    if not DATE_RE.match(s):
        return False
    try:
        datetime.strptime(s, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def amount_is_valid(v):
    """金额校验：非空、非负、可转 float、小数位不超过 2（1e-6 容差）。"""
    if v is None:
        return False
    try:
        f = float(v)
    except (TypeError, ValueError):
        return False
    if f < 0:
        return False
    return abs(f - round(f, AMOUNT_MAX_DECIMALS)) < 1e-6


def main():
    # 统一 UTF-8 输出（Windows GBK 控制台对中文/符号兼容）
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    print("===== G1 正式库只读预检 =====\n")
    print(f"正式库路径: {DB_PATH}")
    print(f"文件大小: {os.path.getsize(DB_PATH)} 字节")
    print(f"修改时间: {datetime.fromtimestamp(os.path.getmtime(DB_PATH)).isoformat()}")

    # ---- 0. 文件哈希基线（打开前）----
    sha_before = sha256_of(DB_PATH)
    print(f"\n[0] 打开前 SHA-256: {sha_before}")

    # ---- 只读连接（mode=ro，URI 层拒绝写）----
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    except sqlite3.Error as e:
        print(f"[FATAL] 只读打开正式库失败: {e}")
        return 2
    conn.row_factory = sqlite3.Row
    print("[连接] 以 mode=ro 只读 URI 打开成功")

    try:
        # ---- 1. 完整性与外键 ----
        integrity = [r[0] for r in conn.execute("PRAGMA integrity_check")]
        fk_violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        ok = integrity == ["ok"] and len(fk_violations) == 0
        record("完整性 integrity_check / 外键 foreign_key_check", 0 if ok else len(fk_violations),
               [] if ok else [f"integrity={integrity}; fk={[dict(r) for r in fk_violations]}"])

        # ---- 2. 版本信息 ----
        user_version = conn.execute("PRAGMA user_version").fetchone()[0]
        journal = conn.execute("PRAGMA journal_mode").fetchone()[0]
        print(f"[版本] user_version={user_version}（0 = 尚未纳入受控迁移，基线 schema）")
        print(f"[模式] journal_mode={journal}")

        # ---- 3. 表与行数 ----
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        print(f"[表] {tables}")
        counts = {}
        for t in tables:
            counts[t] = conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
            print(f"   {t}: {counts[t]} 行")

        # ---- 4. 数据不变量逐项预检（对照 G1 契约）----
        # 4.1 企业信用代码：非空重复（schema 有 UNIQUE，防御性再查）
        dup_cc = conn.execute(
            "SELECT credit_code, COUNT(*) c FROM enterprise "
            "WHERE credit_code IS NOT NULL AND credit_code <> '' "
            "GROUP BY credit_code HAVING c > 1").fetchall()
        record("企业信用代码重复", len(dup_cc), [f"credit_code={r['credit_code']} x{r['c']}" for r in dup_cc])

        # 4.2 金额：project.total_amount / funding.amount 非负且 ≤2 位小数
        amt_viol = []
        for r in conn.execute("SELECT id, total_amount FROM project"):
            if not amount_is_valid(r["total_amount"]):
                amt_viol.append(f"project.id={r['id']} total_amount={r['total_amount']!r}")
        for r in conn.execute("SELECT id, amount FROM funding"):
            if not amount_is_valid(r["amount"]):
                amt_viol.append(f"funding.id={r['id']} amount={r['amount']!r}")
        record("金额非负且≤2位小数", len(amt_viol), amt_viol)

        # 4.3 日期：格式合法 + start<=end
        date_viol = []
        for r in conn.execute("SELECT id, start_date, end_date FROM project"):
            if not is_valid_date(r["start_date"]) or not is_valid_date(r["end_date"]):
                date_viol.append(f"project.id={r['id']} 日期格式非法")
            elif (r["start_date"] and r["end_date"] and r["start_date"] > r["end_date"]):
                date_viol.append(f"project.id={r['id']} start>end")
        for r in conn.execute("SELECT id, plan_date, actual_date FROM funding"):
            if not is_valid_date(r["plan_date"]) or not is_valid_date(r["actual_date"]):
                date_viol.append(f"funding.id={r['id']} 日期格式非法")
        for r in conn.execute("SELECT id, plan_date, actual_date FROM node"):
            if not is_valid_date(r["plan_date"]) or not is_valid_date(r["actual_date"]):
                date_viol.append(f"node.id={r['id']} 日期格式非法")
        record("日期格式与先后关系", len(date_viol), date_viol)

        # 4.4 项目阶段：stage 必须属于 G1 契约状态机取值
        stage_viol = []
        for r in conn.execute("SELECT id, stage FROM project"):
            if r["stage"] not in VALID_STAGES:
                stage_viol.append(f"project.id={r['id']} stage={r['stage']!r}")
        record("项目阶段在状态机取值内", len(stage_viol), stage_viol)

        # 4.5 承担企业：无企业项目（G1 契约：项目必须关联存在企业）
        no_ent = conn.execute(
            "SELECT id, name FROM project WHERE enterprise_id IS NULL").fetchall()
        record("项目必须关联承担企业", len(no_ent),
               [f"project.id={r['id']} name={r['name']!r}" for r in no_ent])

        # 4.6 项目业务唯一键：编号/文号 + 企业 组合重复
        dup_key = conn.execute(
            "SELECT project_no, enterprise_id, COUNT(*) c FROM project "
            "WHERE project_no IS NOT NULL AND project_no <> '' "
            "AND enterprise_id IS NOT NULL "
            "GROUP BY project_no, enterprise_id HAVING c > 1").fetchall()
        record("项目唯一键（编号+企业）无重复", len(dup_key),
               [f"project_no={r['project_no']!r} enterprise_id={r['enterprise_id']} x{r['c']}"
                for r in dup_key])

        # 4.7 字典引用：枚举字段必须能在 dict_item 找到（不含停用与否）
        dict_ok = {}
        for r in conn.execute("SELECT dict_type, value FROM dict_item"):
            dict_ok.setdefault(r["dict_type"], set()).add(r["value"])
        dict_viol = []
        checks = [
            ("project", "level", "level"),
            ("project", "category", "category"),
            ("funding", "source_type", "funding_source"),
            ("node", "node_type", "node_type"),
            ("enterprise", "enterprise_type", "enterprise_type"),
            ("enterprise", "district", "district"),
        ]
        for table, col, dtype in checks:
            for r in conn.execute(f'SELECT id, "{col}" v FROM "{table}"'):
                v = r["v"]
                if v is None or v == "":
                    continue
                if v not in dict_ok.get(dtype, set()):
                    dict_viol.append(f"{table}.id={r['id']} {col}={v!r} 不在字典 {dtype}")
        record("枚举字段引用有效字典项", len(dict_viol), dict_viol)

        # 4.8 资金状态 / 节点状态 / 节点完成一致性
        fund_status = conn.execute(
            "SELECT id, status FROM funding WHERE status NOT IN (?,?,?)",
            tuple(sorted(FUNDING_STATUSES))).fetchall()
        record("资金状态合法", len(fund_status),
               [f"funding.id={r['id']} status={r['status']!r}" for r in fund_status])

        node_status = conn.execute(
            "SELECT id, status FROM node WHERE status NOT IN (?,?,?)",
            tuple(sorted(NODE_STATUSES))).fetchall()
        record("节点状态合法", len(node_status),
               [f"node.id={r['id']} status={r['status']!r}" for r in node_status])

        # 4.9 节点完成一致性：已完成须有 actual_date；未完成不得有 actual_date
        node_done = conn.execute(
            "SELECT id, status, actual_date FROM node "
            "WHERE (status='已完成' AND (actual_date IS NULL OR actual_date='')) "
            "OR (status<>'已完成' AND actual_date IS NOT NULL AND actual_date<>'')").fetchall()
        record("节点完成与实完日期一致", len(node_done),
               [f"node.id={r['id']} status={r['status']!r} actual_date={r['actual_date']!r}"
                for r in node_done])

        # 4.10 归档年度：解析 system_config.archived_years
        arch = conn.execute(
            "SELECT value FROM system_config WHERE key='archived_years'").fetchone()
        arch_years = [y for y in (arch["value"] or "").split(",") if y.strip()] if arch else []
        print(f"[归档] archived_years={arch_years!r}（当前{'已归档' if arch_years else '未归档'}）")

        # 4.11 已删除标记（软删除字段是否存在——基线 schema 无，属预期）
        soft_cols = {}
        for t in ("enterprise", "project", "funding", "node"):
            cols = {r["name"] for r in conn.execute(f'PRAGMA table_info("{t}")')}
            soft_cols[t] = "is_deleted" in cols
        print(f"[软删除] 基线 schema 无 is_deleted 字段（预期，迁移 M003 引入）: {soft_cols}")
    finally:
        conn.close()

    # ---- 5. 关闭后再算哈希，证明零写操作 ----
    sha_after = sha256_of(DB_PATH)
    print(f"\n[0] 检查后 SHA-256: {sha_after}")
    sha_ok = sha_before == sha_after
    print(f"[守卫] 打开前后哈希一致: {'是（零写操作证明成立）' if sha_ok else '否（异常！）'}")

    # ---- 汇总 ----
    print("\n===== 预检汇总 =====")
    total_violations = 0
    for item, n, details in REPORT:
        total_violations += n
        flag = "PASS" if n == 0 else "FAIL"
        print(f"  [{flag}] {item}: 违规 {n} 条")
        for d in details[:10]:          # 明细过长时截断，报告文件为完整权威版本
            print(f"          - {d}")
        if len(details) > 10:
            print(f"          … 其余 {len(details) - 10} 条见 docs/migrations/ 预检报告")
    print(f"\n结果: 不合规记录共 {total_violations} 条；"
          f"SHA-256 {'一致' if sha_ok else '不一致'}；"
          f"{'预检通过（空库或全部合规）' if total_violations == 0 and sha_ok else '存在不合规/异常，禁止自动迁移'}")

    # 输出 JSON 机器可读摘要（仅 stdout）
    summary = {
        "db": DB_PATH,
        "sha256_before": sha_before,
        "sha256_after": sha_after,
        "sha256_match": sha_ok,
        "user_version": user_version,
        "table_counts": counts,
        "violations": {item: n for item, n, _ in REPORT},
        "total_violations": total_violations,
        "checked_at": datetime.now().isoformat(),
    }
    print("\n===== 机器可读摘要 =====")
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    return 0 if total_violations == 0 and sha_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

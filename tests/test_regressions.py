# -*- coding: utf-8 -*-
"""已复现问题清单 —— 失败复现测试（G0-3，2026-08-13）

本文件把 PLAN.md 第 2 节审查出的问题写成「契约断言」：
每一条测试断言的是 PLAN 约定的正确行为（PLAN §3 关键业务契约）。
已由 G2/G3/G7 落地的规则必须正常通过；尚缺业务决策或能力的规则才保留
strict xfail，并在 reason 中说明原因。

重要约定：
- xfail 的 reason 必须写明尚未实现的业务边界，绝不允许通过修改断言或
  静默跳过把缺陷伪装成通过。
- 修复对应问题后移除 xfail 标记并让测试转绿；测试断言本身保持验收作用。
- 测试全部运行在独立临时数据库上（conftest.py 的 tmp_db/client），
  正式库 data/project.db 有会话级哈希守卫，绝不触碰。

覆盖清单（对应 PLAN 交付约束 1）：
  1. P0-02 非法金额文本被静默转为 NULL（应明确 400）
  2. P0-02 任意阶段字符串可直接写入（应 400）
  3. P0-02 未指定承担企业的项目可直接写入（应 400）
  4. P0-03 已归档年度禁止新建和修改项目（应 403）
  5. P0-01 三项资金口径在工作台与项目列表一致
  6. P0-04 旧 Excel 直写入口必须拒绝，避免部分提交
"""

import sqlite3

import pytest

from conftest import db_conn


# ===========================================================================
# P0-02 非法金额文本：clean_payload 用 float() 失败后静默置 None
# ===========================================================================
def test_p002_illegal_amount_text_rejected(client):
    """G2 回归：非法金额文本必须返回 400，且不得静默转为 NULL。"""
    _, ent = client.request(
        "POST", "/api/enterprises", {"name": "丙公司", "credit_code": "91320000TEST03"})
    status, proj = client.request(
        "POST", "/api/projects",
        {"name": "金额文本项目", "enterprise_id": ent["id"], "total_amount": "abc"})
    assert status == 400, (
        f"非法金额文本被接受: status={status}, total_amount={proj.get('total_amount')}"
        f"（契约要求 400 且不写入，当前疑似写入 NULL）")


# ===========================================================================
# P0-02 非法项目阶段：POST /api/projects 只校验 name 必填，不校验 stage
# ===========================================================================
def test_p002_illegal_stage_rejected(client):
    """G2 回归：非法阶段值必须返回 400。"""
    _, ent = client.request(
        "POST", "/api/enterprises", {"name": "戊公司", "credit_code": "91320000TEST05"})
    status, proj = client.request(
        "POST", "/api/projects",
        {"name": "坏阶段项目", "enterprise_id": ent["id"], "stage": "随便写的阶段"})
    assert status == 400, (
        f"非法阶段被接受: status={status}, stage={proj.get('stage')}"
        f"（契约要求 400；合法取值见 app.js STAGES / import_excel.PROJECT_STAGES）")


# ===========================================================================
# P0-02 未关联企业项目：POST /api/projects 不要求 enterprise_id
# ===========================================================================
def test_p002_project_without_enterprise_rejected(client):
    """G2 回归：不带 enterprise_id 的项目必须返回 400。"""
    status, proj = client.request(
        "POST", "/api/projects", {"name": "无企业项目"})
    assert status == 400, (
        f"未指定承担企业的项目被接受: status={status}, "
        f"enterprise_id={proj.get('enterprise_id')}（契约要求 400）")


# ===========================================================================
# P0-03 归档年度仍可新建项目：PUT/DELETE 已拦，POST 新建未拦
# ===========================================================================
def test_p003_archived_year_blocks_new_project(client):
    """G3 回归：归档后，同年度项目的新建与修改都必须被阻断。"""
    _, ent = client.request(
        "POST", "/api/enterprises", {"name": "丁公司", "credit_code": "91320000TEST04"})

    # 先建立项目，随后归档，才能验证归档后的既有记录修改同样受限。
    created_status, ok_proj = client.request(
            "POST", "/api/projects",
            {"name": "归档前项目", "enterprise_id": ent["id"], "start_date": "2024-01-01",
             "identity_status": "人工编号待补"})
    assert created_status == 200 and ok_proj.get("id") is not None

    # 归档 2024 年后，既有记录不可修改，新记录也不可创建。
    status, _ = client.request(
        "PUT", "/api/config", {"archived_years": ["2024"]})
    assert status == 200, f"设置归档年度失败: {status}"

    put_status, _ = client.request(
        "PUT", f"/api/projects/{ok_proj['id']}", {"name": "尝试修改"})
    assert put_status == 403, f"对照断言异常：PUT 应拦截归档项目，实际 {put_status}"

    status, proj = client.request(
        "POST", "/api/projects",
        {"name": "归档年新建项目", "enterprise_id": ent["id"], "start_date": "2024-06-01"})
    assert status == 403, (
        f"已归档年度仍可新建项目: status={status}（契约要求 403）；"
        f"新建的项目 id={proj.get('id')}")


# ===========================================================================
# P0-01 资金口径分歧：同一字段名 funded_total 两处语义不同
# ===========================================================================
def test_p001_funded_total_has_single_semantics(client):
    """G2 回归：工作台与项目列表共用三项明确资金口径。"""
    # 建企业 + 项目（总金额 200 万）
    _, ent = client.request(
        "POST", "/api/enterprises", {"name": "乙公司", "credit_code": "91320000TEST02"})
    _, proj = client.request(
            "POST", "/api/projects",
            {"name": "口径项目", "enterprise_id": ent["id"], "total_amount": 200,
             "identity_status": "人工编号待补"})
    pid = proj["id"]

    # 两笔资金：已到账 100 万（已拨付且到账）、未拨付 50 万（仅计划）
    s1, _ = client.request(
        "POST", "/api/fundings",
        {"project_id": pid, "amount": 100, "status": "已到账", "source_type": "上级拨付",
         "plan_date": "2024-06-01", "actual_date": "2024-06-10"})
    s2, _ = client.request(
        "POST", "/api/fundings",
        {"project_id": pid, "amount": 50, "status": "未拨付", "source_type": "本级配套",
         "plan_date": "2024-07-01"})
    assert s1 == 200 and s2 == 200, f"构造资金失败: {s1} {s2}"

    _, dash = client.request("GET", "/api/dashboard")
    _, projects = client.request("GET", "/api/projects")
    expected = {"planned_total": 150, "disbursed_total": 100, "received_total": 100}
    listing = next(row for row in projects if row["id"] == pid)
    for key, value in expected.items():
        assert dash[key] == value, f"工作台 {key} 应为 {value}，实际 {dash[key]}"
        assert listing[key] == value, f"项目列表 {key} 应为 {value}，实际 {listing[key]}"


# ===========================================================================
# P0-04 Excel 导入部分提交：合法行入库、非法行跳过
# ===========================================================================
def _build_partial_workbook():
    """构造 2 行工作簿：行1 合法（应导入），行2 非法层级（应阻断）。"""
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "项目台账"
    ws.append(["企业名称", "统一社会信用代码", "企业类型", "区镇", "资质",
               "企业联系人", "企业联系电话", "企业地址",
               "项目名称", "项目编号/文号", "层级", "类型", "总金额（万元）",
               "开始日期", "结束日期", "当前阶段", "配套比例",
               "项目负责人", "联系人手机号", "备注"])
    # 行1：合法（层级『省级』在字典中）
    ws.append(["企业A", "91320000IMPA", "高新技术企业", "开发区", "", "", "", "",
               "项目A", "PA-001", "省级", "科技成果转化", 100,
               "2024-01-01", "2024-12-31", "已立项", 1, "张三", "13800000000", ""])
    # 行2：非法（层级『乱写层级』不在字典中，导入应整批拒绝）
    ws.append(["企业B", "91320000IMPB", "高新技术企业", "开发区", "", "", "", "",
               "项目B", "PB-001", "乱写层级", "科技成果转化", 50,
               "2024-01-01", "2024-12-31", "已立项", 1, "李四", "13800000001", ""])
    return wb


def test_p004_import_never_leaves_partial_data(tmp_db):
    """G7 回归：旧直写入口必须明确拒绝，不能再产生部分提交。"""
    from import_excel import import_workbook

    conn = db_conn(tmp_db)
    try:
        before_ent = conn.execute("SELECT COUNT(*) FROM enterprise").fetchone()[0]
        before_proj = conn.execute("SELECT COUNT(*) FROM project").fetchone()[0]

        wb = _build_partial_workbook()
        with pytest.raises(RuntimeError, match="已废弃"):
            import_workbook(wb, conn)

        after_ent = conn.execute("SELECT COUNT(*) FROM enterprise").fetchone()[0]
        after_proj = conn.execute("SELECT COUNT(*) FROM project").fetchone()[0]

        # 契约：旧入口拒绝后，数据库不发生任何变化。
        assert (after_ent, after_proj) == (before_ent, before_proj), (
            f"导入部分提交: 企业 {before_ent}→{after_ent}, 项目 {before_proj}→"
            f"{after_proj}（旧入口被拒绝后仍发生写入），契约要求零写入")
    finally:
        conn.close()

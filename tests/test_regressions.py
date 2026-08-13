# -*- coding: utf-8 -*-
"""已复现问题清单 —— 失败复现测试（G0-3，2026-08-13）

本文件把 PLAN.md 第 2 节审查出的问题写成「契约断言」：
每一条测试断言的是 PLAN 约定的正确行为（PLAN §3 关键业务契约），
而当前业务代码（本轮禁止修改）违反契约，因此这些测试当前全部
标记为 xfail。

重要约定：
- xfail 的 reason 必须写明 PLAN 问题编号（P0-01 ~ P0-04）与契约条款，
  绝不允许通过修改断言/静默跳过把缺陷伪装成通过。
- 修复对应问题后（G2~G4），移除 xfail 标记并让测试转绿即可，
  测试断言本身无需改写——它们就是验收判据。
- 测试全部运行在独立临时数据库上（conftest.py 的 tmp_db/client），
  正式库 data/project.db 有会话级哈希守卫，绝不触碰。

覆盖清单（对应 PLAN 交付约束 1）：
  1. P0-02 非法金额文本被静默转为 NULL（应明确 400）
  2. P0-02 任意阶段字符串可直接写入（应 400）
  3. P0-02 未指定承担企业的项目可直接写入（应 400）
  4. P0-03 已归档年度仍可新建项目（应 403；对照：PUT/DELETE 已拦截）
  5. P0-01 资金口径分歧：同一字段 funded_total 两处语义不同（应统一）
  6. P0-04 Excel 导入部分提交：非法行被跳过、合法行已入库（应零写入）
"""

import sqlite3

import pytest

from conftest import db_conn


# ===========================================================================
# P0-02 非法金额文本：clean_payload 用 float() 失败后静默置 None
# ===========================================================================
@pytest.mark.xfail(strict=True, reason=(
    "P0-02 非法金额文本被静默转 NULL：app.clean_payload 对金额字段 float() "
    "失败后赋 None 并照常写入。契约（PLAN §3.2/§2 P0-02）：非法金额必须 "
    "明确 400 且不写入，严禁把非法值静默转换为 NULL。"))
def test_p002_illegal_amount_text_rejected(client):
    """非法金额文本『abc』应返回 400，当前被接受并写入 NULL。"""
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
@pytest.mark.xfail(strict=True, reason=(
    "P0-02 任意阶段可写入：app._api_project POST 仅检查 name 必填，未校验 "
    "stage 是否属于状态机取值。契约（PLAN §3.2）：项目阶段只能按经确认的 "
    "状态机流转，非法取值必须 400。"))
def test_p002_illegal_stage_rejected(client):
    """阶段『随便写的阶段』应返回 400，当前被接受并写入。"""
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
@pytest.mark.xfail(strict=True, reason=(
    "P0-02 无承担企业的项目可写入：app._api_project POST 不校验 "
    "enterprise_id 是否提供。契约（PLAN §3.2）：项目创建时必须指定存在且 "
    "未删除的承担企业，无企业项目必须 400。（对照：外键只拦截『不存在的 "
    "id』，拦截不了『id 为空』——见 test_baseline.test_foreign_key_rejects_*）"))
def test_p002_project_without_enterprise_rejected(client):
    """不带 enterprise_id 创建项目应返回 400，当前被接受并写入 NULL 关联。"""
    status, proj = client.request(
        "POST", "/api/projects", {"name": "无企业项目"})
    assert status == 400, (
        f"未指定承担企业的项目被接受: status={status}, "
        f"enterprise_id={proj.get('enterprise_id')}（契约要求 400）")


# ===========================================================================
# P0-03 归档年度仍可新建项目：PUT/DELETE 已拦，POST 新建未拦
# ===========================================================================
@pytest.mark.xfail(strict=True, reason=(
    "P0-03 归档年度仍可新建项目：app._api_project 的 PUT/DELETE 已调用 "
    "_is_archived_project 拦截，唯独 POST 新建路径不检查年度归档。契约"
    "（PLAN §3.3）：年度归档后禁止该年度项目的新建、修改、删除和导入，"
    "新建必须返回 403。"))
def test_p003_archived_year_blocks_new_project(client):
    """归档 2024 后新建 2024 项目应 403；对照断言 PUT 修改确实已被拦截。"""
    _, ent = client.request(
        "POST", "/api/enterprises", {"name": "丁公司", "credit_code": "91320000TEST04"})

    # 先归档 2024 年
    status, _ = client.request(
        "PUT", "/api/config", {"archived_years": ["2024"]})
    assert status == 200, f"设置归档年度失败: {status}"

    # 对照基线（绿）：归档项目的修改路径已被拦截 → 证明拦截机制存在
    _, ok_proj = client.request(
        "POST", "/api/projects",
        {"name": "归档前项目", "enterprise_id": ent["id"], "start_date": "2024-01-01"})
    assert ok_proj.get("id") is not None
    put_status, _ = client.request(
        "PUT", f"/api/projects/{ok_proj['id']}", {"name": "尝试修改"})
    assert put_status == 403, f"对照断言异常：PUT 应拦截归档项目，实际 {put_status}"

    # 契约断言（红，xfail）：归档年度新建项目应 403
    status, proj = client.request(
        "POST", "/api/projects",
        {"name": "归档年新建项目", "enterprise_id": ent["id"], "start_date": "2024-06-01"})
    assert status == 403, (
        f"已归档年度仍可新建项目: status={status}（契约要求 403）；"
        f"新建的项目 id={proj.get('id')}")


# ===========================================================================
# P0-01 资金口径分歧：同一字段名 funded_total 两处语义不同
# ===========================================================================
@pytest.mark.xfail(strict=True, reason=(
    "P0-01 资金口径分歧：app.py 中 dashboard.funded_total 只统计 status="
    "'已到账'（app.py:249），而项目列表 funded_total 统计该项目全部资金"
    "（app.py:696 无状态过滤），前端把后者显示为『已到位』（app.js:799）。"
    "契约（PLAN §3.1）：已到账额与全部资金是不同概念，必须分字段、"
    "同语义，禁止同一字段名承载两种口径。"))
def test_p001_funded_total_has_single_semantics(client):
    """同一字段 funded_total 在工作台与项目列表必须同语义（本次用同一组数据对比）。"""
    # 建企业 + 项目（总金额 200 万）
    _, ent = client.request(
        "POST", "/api/enterprises", {"name": "乙公司", "credit_code": "91320000TEST02"})
    _, proj = client.request(
        "POST", "/api/projects",
        {"name": "口径项目", "enterprise_id": ent["id"], "total_amount": 200})
    pid = proj["id"]

    # 两笔资金：已到账 100 万（已拨付且到账）、未拨付 50 万（仅计划）
    s1, _ = client.request(
        "POST", "/api/fundings",
        {"project_id": pid, "amount": 100, "status": "已到账", "source_type": "上级拨付"})
    s2, _ = client.request(
        "POST", "/api/fundings",
        {"project_id": pid, "amount": 50, "status": "未拨付", "source_type": "本级配套"})
    assert s1 == 200 and s2 == 200, f"构造资金失败: {s1} {s2}"

    _, dash = client.request("GET", "/api/dashboard")
    _, projects = client.request("GET", "/api/projects")
    dash_funded = dash.get("funded_total")          # 工作台：仅『已到账』 → 期望 100
    list_funded = projects[0].get("funded_total")   # 项目列表：全部资金 → 期望 100

    # 契约：同一字段名必须同一语义。任何一方不等于 100 都构成口径分歧。
    assert dash_funded == list_funded == 100, (
        f"字段 funded_total 口径分歧: 工作台={dash_funded}（仅已到账） vs "
        f"项目列表={list_funded}（全部资金）。契约要求二者同为『已到账』"
        f"口径=100；若为『全部资金』口径则二者应同为 150，绝不可一 100 一 150。")


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


@pytest.mark.xfail(strict=True, reason=(
    "P0-04 导入部分提交：import_excel.import_workbook 逐行 INSERT、仅对 "
    "非法行记 errors 后 continue，最后统一 commit —— 合法行已入库、非法行"
    "被跳过，形成『部分成功』。契约（PLAN §3.4/P0-04）：导入应先全量校验，"
    "有阻断错误时零写入（不产生孤儿企业、半条项目）。"))
def test_p004_import_never_leaves_partial_data(tmp_db):
    """含非法行的导入应整批零写入，当前合法行已被部分提交。"""
    from import_excel import import_workbook

    conn = db_conn(tmp_db)
    try:
        before_ent = conn.execute("SELECT COUNT(*) FROM enterprise").fetchone()[0]
        before_proj = conn.execute("SELECT COUNT(*) FROM project").fetchone()[0]

        wb = _build_partial_workbook()
        res = import_workbook(wb, conn)

        after_ent = conn.execute("SELECT COUNT(*) FROM enterprise").fetchone()[0]
        after_proj = conn.execute("SELECT COUNT(*) FROM project").fetchone()[0]

        # 契约：任何一行校验失败时，整批零写入
        assert (after_ent, after_proj) == (before_ent, before_proj), (
            f"导入部分提交: 企业 {before_ent}→{after_ent}, 项目 {before_proj}→"
            f"{after_proj}（合法行已写入、非法行被跳过），契约要求零写入；"
            f"导入结果={res}")
    finally:
        conn.close()

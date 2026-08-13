# -*- coding: utf-8 -*-
"""G2 契约测试：核心写入约束与统一查询层（2026-08-13，依据 ADR-0001）

契约权威来源：docs/decisions/0001-领域契约三项决策.md（HUMAN 已签字确认，
2026-08-13）。本文件的每条测试断言都是 ADR-0001 / PLAN.md §3 的验收判据：
- 决策一：资金记录不拆分（计划与实际共处一条记录），口径
  planned_total = Σ(plan_date 非空).amount、
  disbursed_total = Σ(status∈(已拨付,已到账)).amount、
  received_total  = Σ(status=已到账).amount；
- 决策二：项目业务唯一键 =（project_no, enterprise_id）二元组，
  无编号记录不得自动入账；唯一键冲突必须明确拒绝；
- 决策三：项目状态机——正常链仅相邻前进、禁止回退/跳跃；
  中止仅限【已立项、实施中、待验收】进入且为不可恢复终态；
  撤销源为除【已完结、中止、撤销】外的全部阶段且不可恢复。

G2 尚未实现上述规则，因此本文件全部测试 @pytest.mark.xfail(strict=True)：
当前每条测试都失败 → 记为 XFAIL（通过）；G2 实现后测试转绿 →
XPASS(strict) 报错，提示移除 xfail 标记。绝不允许通过弱化断言
（改用不存在的字段名、跳过精确值比对、放宽状态码）把缺陷伪装成通过。

硬约束（与 conftest.py / test_regressions.py 一致）：
- 只使用 conftest 的 tmp_db / client 夹具，所有写库都发生在临时库；
- MCP 层显式 monkeypatch mcp_server.DB_PATH/BASE_DIR 指向 tmp_db，
  绝不触碰正式库 data/project.db（conftest 会话级 SHA-256 守卫兜底）；
- 直接调用 mcp_server 的公开查询函数（FastMCP 装饰后仍为普通函数），
  不伪造 MCP 数据；
- 不修改任何既有文件（app.py/schema.sql/conftest.py/docs 等一律不动）。
"""

import sqlite3

import pytest

from conftest import db_conn


# ===========================================================================
# 通用辅助：构造合法样本（仅操作临时库；样本本身必须符合契约，
# 保证 G2 实现后样本构造仍能成功、测试可真正转绿）
# ===========================================================================
_seq = {"n": 0}


def _new_enterprise(client, credit_code, name=None, **overrides):
    """新建合法企业，返回 (status, resp)。企业类型/区镇取种子字典值。"""
    payload = {
        "name": name or f"G2测试企业-{credit_code}",
        "credit_code": credit_code,
        "enterprise_type": "高新技术企业",
        "district": "开发区",
        **overrides,
    }
    status, resp = client.request("POST", "/api/enterprises", payload)
    assert status == 200, f"建企业失败: status={status} resp={resp}"
    return status, resp


def _new_project(client, eid, **overrides):
    """新建合法项目（挂在企业 eid 下），返回 (status, resp)。

    契约要求 project_no 非空且企业存在（ADR-0001 决策二），故默认带编号。
    """
    _seq["n"] += 1
    payload = {
        "name": "G2契约测试项目",
        "project_no": f"G2-P-{_seq['n']:04d}",
        "enterprise_id": eid,
        "level": "省级",
        "category": "科技成果转化",
        "total_amount": 100,
        "start_date": "2024-01-01",
        "end_date": "2024-12-31",
        "stage": "已立项",
        **overrides,
    }
    status, resp = client.request("POST", "/api/projects", payload)
    assert status == 200, f"建项目失败: status={status} resp={resp}"
    return status, resp


def _count_rows(tmp_db, table):
    """统计临时库某表的行数（用于断言『非法请求不写库』）。"""
    conn = db_conn(tmp_db)
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()


def _get_stage(tmp_db, pid):
    """读取临时库中项目的当前阶段（断言『库中阶段不改变』用）。"""
    conn = db_conn(tmp_db)
    try:
        row = conn.execute("SELECT stage FROM project WHERE id=?", (pid,)).fetchone()
        return row["stage"] if row else None
    finally:
        conn.close()


def _seed_money_sample(client):
    """构造资金口径样本（语义测试与跨层一致性测试共用同一份临时样本）。

    资金记录金额 amount 即「计划/批准金额」（ADR-0001 决策一），单位万元，
    全部取整数避免浮点误差。每条记录都符合状态-日期一致性契约
    （未拨付无 actual_date；已拨付/已到账必有 actual_date），
    保证 G2 实现后样本构造仍合法。

    样本组合：
      F1  100 未拨付  plan_date=2024-06-01  actual_date=None            → planned
      F2   60 已拨付  plan_date=2024-07-01  actual_date=2024-07-10      → planned + disbursed
      F3   40 已到账  plan_date=2024-08-01  actual_date=2024-08-15      → planned + disbursed + received
      F4   20 未拨付  plan_date=None        actual_date=None            → 不计入任何
      F5   30 已到账  plan_date=None        actual_date=2024-09-01      → disbursed + received
      F6   50 已拨付  plan_date=None        actual_date=2024-09-15      → disbursed

    ADR-0001 决策一口径期望值：
      planned_total   = Σ plan_date 非空         = 100+60+40  = 200
      disbursed_total = Σ status∈(已拨付,已到账) = 60+40+30+50 = 180
      received_total  = Σ status=已到账          = 40+30      = 70
    """
    _, ent = _new_enterprise(client, "91320000G2SEM01", "资金口径企业")
    _, proj = _new_project(client, ent["id"], name="资金口径项目", total_amount=400)
    pid = proj["id"]

    fundings = [
        {"project_id": pid, "amount": 100, "status": "未拨付", "source_type": "上级拨付",
         "plan_date": "2024-06-01"},
        {"project_id": pid, "amount": 60, "status": "已拨付", "source_type": "本级配套",
         "plan_date": "2024-07-01", "actual_date": "2024-07-10"},
        {"project_id": pid, "amount": 40, "status": "已到账", "source_type": "本级自付",
         "plan_date": "2024-08-01", "actual_date": "2024-08-15"},
        {"project_id": pid, "amount": 20, "status": "未拨付", "source_type": "上级拨付"},
        {"project_id": pid, "amount": 30, "status": "已到账", "source_type": "本级配套",
         "actual_date": "2024-09-01"},
        {"project_id": pid, "amount": 50, "status": "已拨付", "source_type": "本级自付",
         "actual_date": "2024-09-15"},
    ]
    for f in fundings:
        s, r = client.request("POST", "/api/fundings", f)
        assert s == 200, f"建资金失败: status={s} resp={r} body={f}"

    expected = {"planned_total": 200, "disbursed_total": 180, "received_total": 70}
    return pid, expected


# ===========================================================================
# 1. 资金三口径（ADR-0001 决策一）
#    planned_total / disbursed_total / received_total 必须按口径精确计算，
#    并通过 API 详情、UI 列表/工作台端点、MCP 查询层比对完全相等。
#    断言引用规定字段名与精确数值：字段缺失（KeyError）即测试失败 → XFAIL。
# ===========================================================================
def test_funding_three_totals_across_api_ui_mcp(tmp_db, client, monkeypatch):
    """同一份样本：API 详情 / UI 列表 / UI 工作台 / MCP 查询层 三口径逐项相等。"""
    import mcp_server

    # MCP 默认读模块级 DB_PATH（正式库）——显式重定向到 tmp_db，安全注入
    monkeypatch.setattr(mcp_server, "DB_PATH", str(tmp_db))
    monkeypatch.setattr(mcp_server, "BASE_DIR", str(tmp_db.parent))

    pid, expected = _seed_money_sample(client)

    # —— 逐层取数（UI 数据端点即前端页面实际调用的 HTTP 端点）——
    _, detail = client.request("GET", f"/api/projects/{pid}")      # API/UI 项目详情
    _, listing = client.request("GET", "/api/projects")            # UI 项目列表端点
    _, dash = client.request("GET", "/api/dashboard")              # UI 工作台端点
    mcp_list = mcp_server.list_projects()                          # MCP 列表查询
    mcp_detail = mcp_server.get_project(pid)                       # MCP 详情查询

    layers = {
        "API/UI 项目详情 /api/projects/{id}": detail,
        "UI 列表端点 /api/projects": listing[0],
        "UI 工作台端点 /api/dashboard": dash,
        "MCP list_projects()": mcp_list[0],
        "MCP get_project()": mcp_detail,
    }

    # —— 各层三口径必须等于期望精确值（字段缺失 → KeyError → 预期失败）——
    for name, layer in layers.items():
        for key, want in expected.items():
            got = layer[key]  # 契约规定字段，缺失即为失败，绝不用 .get 跳过
            assert got == want, f"{name} 的 {key} 应等于 {want}（ADR-0001 口径），实际 {got}"

    # —— 层间交叉比对：三口径在所有层必须完全一致 ——
    for key in expected:
        values = {layer[key] for layer in layers.values()}
        assert len(values) == 1, f"{key} 在各层取值不一致: {values}"


def test_funding_disbursed_requires_actual_date(tmp_db, client):
    """status=已拨付 但无 actual_date 必须 400 且不写库（当前被接受并写入）。"""
    _, ent = _new_enterprise(client, "91320000G2SEM02")
    _, proj = _new_project(client, ent["id"])
    before = _count_rows(tmp_db, "funding")
    status, resp = client.request(
        "POST", "/api/fundings",
        {"project_id": proj["id"], "amount": 10, "status": "已拨付",
         "source_type": "上级拨付", "plan_date": "2024-06-01"})
    assert status in (400, 403, 409), f"已拨付却无实拨日期被接受: status={status} {resp}"
    assert _count_rows(tmp_db, "funding") == before, "非法资金记录被写入"


def test_funding_received_requires_actual_date(tmp_db, client):
    """status=已到账 但无 actual_date 必须 400 且不写库（当前被接受并写入）。"""
    _, ent = _new_enterprise(client, "91320000G2SEM03")
    _, proj = _new_project(client, ent["id"])
    before = _count_rows(tmp_db, "funding")
    status, resp = client.request(
        "POST", "/api/fundings",
        {"project_id": proj["id"], "amount": 10, "status": "已到账",
         "source_type": "上级拨付", "plan_date": "2024-06-01"})
    assert status in (400, 403, 409), f"已到账却无实拨日期被接受: status={status} {resp}"
    assert _count_rows(tmp_db, "funding") == before, "非法资金记录被写入"


def test_funding_unpaid_forbids_actual_date(tmp_db, client):
    """status=未拨付 却带 actual_date 必须 400 且不写库（当前被接受并写入）。"""
    _, ent = _new_enterprise(client, "91320000G2SEM04")
    _, proj = _new_project(client, ent["id"])
    before = _count_rows(tmp_db, "funding")
    status, resp = client.request(
        "POST", "/api/fundings",
        {"project_id": proj["id"], "amount": 10, "status": "未拨付",
         "source_type": "上级拨付", "actual_date": "2024-06-01"})
    assert status in (400, 403, 409), f"未拨付却记录实拨日期被接受: status={status} {resp}"
    assert _count_rows(tmp_db, "funding") == before, "非法资金记录被写入"


# ===========================================================================
# 2. 项目业务唯一键（ADR-0001 决策二）
#    同 enterprise 同 project_no 重复拒绝；不同企业同号允许；
#    无编号 POST 项目拒绝且无入库。
# ===========================================================================
def test_project_unique_key_duplicate_rejected(tmp_db, client):
    """同一企业 + 同一 project_no 重复创建必须拒绝；不同企业同号允许。"""
    _, ent_a = _new_enterprise(client, "91320000G2UNI01", "唯一键企业A")
    _, ent_b = _new_enterprise(client, "91320000G2UNI02", "唯一键企业B")

    # 对照（契约要求，当前已满足）：不同企业可用相同 project_no
    s1, proj_b = _new_project(client, ent_b["id"], name="编号项目B", project_no="P-G2-001")
    assert s1 == 200 and proj_b.get("id")

    # 契约断言（当前失败）：同一企业重复 project_no 应拒绝
    _, proj_a = _new_project(client, ent_a["id"], name="编号项目A", project_no="P-G2-001")
    before = _count_rows(tmp_db, "project")
    status, resp = client.request(
        "POST", "/api/projects",
        {"name": "重复编号项目", "enterprise_id": ent_a["id"], "level": "省级",
         "category": "科技成果转化", "project_no": "P-G2-001",
         "start_date": "2024-01-01", "end_date": "2024-12-31", "stage": "已立项"})
    assert status in (400, 409), (
        f"同一企业重复 project_no 被接受: status={status} {resp} "
        f"（企业A首条 id={proj_a.get('id')}）")
    assert _count_rows(tmp_db, "project") == before, "重复记录被写入"


def test_project_without_project_no_rejected(tmp_db, client):
    """无编号不能默认为正式项目，必须由录入员显式承担人工待补标记责任。"""
    _, ent = _new_enterprise(client, "91320000G2UNI03")
    before = _count_rows(tmp_db, "project")
    status, resp = client.request(
        "POST", "/api/projects",
        {"name": "无编号项目", "enterprise_id": ent["id"], "level": "省级",
         "category": "科技成果转化", "total_amount": 100,
         "start_date": "2024-01-01", "end_date": "2024-12-31", "stage": "已立项"})
    assert status == 400, f"无 project_no 的项目被自动入账: status={status} {resp}"
    assert _count_rows(tmp_db, "project") == before, "无编号记录被写入"

    status, created = client.request(
        "POST", "/api/projects",
        {"name": "人工待补编号项目", "identity_status": "人工编号待补", "enterprise_id": ent["id"],
         "level": "省级", "category": "科技成果转化", "total_amount": 100,
         "start_date": "2024-01-01", "end_date": "2024-12-31", "stage": "已立项"})
    assert status == 200, f"显式人工待补标记应允许人工录入: {status} {created}"
    assert created["project_no"] is None and created["identity_status"] == "人工编号待补"


# ===========================================================================
# 3. 项目状态机（ADR-0001 决策三）
#    正常链仅相邻前进、禁止回退/跳跃且库中阶段不改变；
#    中止仅限【已立项、实施中、待验收】且为不可恢复终态；
#    撤销源为除【已完结、中止、撤销】外的全部阶段且不可恢复。
# ===========================================================================
def test_stage_machine_forward_chain_only(tmp_db, client):
    """正常链逐级前进允许；回退/跳跃拒绝且库中阶段不改变。"""
    _, ent = _new_enterprise(client, "91320000G2STM01")
    _, proj = _new_project(client, ent["id"], stage="申报中")
    pid = proj["id"]

    # ① 正常链逐级前进必须成功（对照断言，当前亦通过）
    chain = ["申报中", "已立项", "实施中", "待验收", "已验收", "绩效跟踪", "已完结"]
    for i in range(1, len(chain)):
        status, resp = client.request("PUT", f"/api/projects/{pid}",
                                      {"stage": chain[i]})
        assert status == 200, f"相邻前进 {chain[i-1]}→{chain[i]} 应允许: {status} {resp}"
        assert _get_stage(tmp_db, pid) == chain[i]

    # ② 回退拒绝：已完结 → 绩效跟踪（当前被接受 → 断言失败）
    status, resp = client.request("PUT", f"/api/projects/{pid}", {"stage": "绩效跟踪"})
    assert status in (400, 403, 409), f"回退被接受: status={status} {resp}"
    assert _get_stage(tmp_db, pid) == "已完结", "回退后库中阶段被改变"

    # ③ 跳跃拒绝：申报中 → 待验收（当前被接受 → 断言失败）
    _, proj2 = _new_project(client, ent["id"], stage="申报中")
    pid2 = proj2["id"]
    status, resp = client.request("PUT", f"/api/projects/{pid2}", {"stage": "待验收"})
    assert status in (400, 403, 409), f"跳跃被接受: status={status} {resp}"
    assert _get_stage(tmp_db, pid2) == "申报中", "跳跃后库中阶段被改变"


def test_stage_abort_enter_restricted(tmp_db, client):
    """中止仅限已立项/实施中/待验收进入；其他阶段拒绝。"""
    _, ent = _new_enterprise(client, "91320000G2STM02")

    # 允许源（对照断言，当前亦通过）
    for stage in ["已立项", "实施中", "待验收"]:
        _, proj = _new_project(client, ent["id"], stage=stage)
        status, resp = client.request("PUT", f"/api/projects/{proj['id']}",
                                      {"stage": "中止"})
        assert status == 200, f"{stage} 进入中止应允许: status={status} {resp}"
        assert _get_stage(tmp_db, proj["id"]) == "中止"

    # 拒绝源：申报中（未立项前取消走撤销，不走中止）
    _, proj = _new_project(client, ent["id"], stage="申报中")
    status, resp = client.request("PUT", f"/api/projects/{proj['id']}", {"stage": "中止"})
    assert status in (400, 403, 409), f"申报中进入中止被接受: status={status} {resp}"
    assert _get_stage(tmp_db, proj["id"]) == "申报中", "非法中止后库中阶段被改变"

    # 拒绝源：已验收之后（项目基本完成，不走中止）
    _, proj = _new_project(client, ent["id"], stage="已验收")
    status, resp = client.request("PUT", f"/api/projects/{proj['id']}", {"stage": "中止"})
    assert status in (400, 403, 409), f"已验收进入中止被接受: status={status} {resp}"
    assert _get_stage(tmp_db, proj["id"]) == "已验收", "非法中止后库中阶段被改变"

    # 拒绝源：已完结
    _, proj = _new_project(client, ent["id"], stage="已完结")
    status, resp = client.request("PUT", f"/api/projects/{proj['id']}", {"stage": "中止"})
    assert status in (400, 403, 409), f"已完结进入中止被接受: status={status} {resp}"


def test_stage_abort_terminal_not_recoverable(tmp_db, client):
    """中止为不可恢复终态：后续任何流转（含撤销）必须拒绝。"""
    _, ent = _new_enterprise(client, "91320000G2STM03")
    _, proj = _new_project(client, ent["id"], stage="已立项")
    pid = proj["id"]

    # 进入中止（允许）
    status, resp = client.request("PUT", f"/api/projects/{pid}", {"stage": "中止"})
    assert status == 200, f"已立项进入中止应允许: {status} {resp}"
    assert _get_stage(tmp_db, pid) == "中止"

    # 中止后任何流转必须拒绝（含正常推进、回退、撤销）
    for target in ["实施中", "已完结", "撤销", "申报中"]:
        status, resp = client.request("PUT", f"/api/projects/{pid}", {"stage": target})
        assert status in (400, 403, 409), (
            f"中止终态仍可流转为 {target}: status={status} {resp}")
        assert _get_stage(tmp_db, pid) == "中止", "中止终态被恢复/改变"


def test_stage_revoke_adr_constrained_and_terminal(tmp_db, client):
    """撤销源阶段限定（ADR）+ 撤销不可恢复。"""
    _, ent = _new_enterprise(client, "91320000G2STM04")

    # 允许源（对照断言，当前亦通过）：申报中/已立项/实施中/待验收/已验收/绩效跟踪
    for stage in ["申报中", "已立项", "实施中", "待验收", "已验收", "绩效跟踪"]:
        _, proj = _new_project(client, ent["id"], stage=stage)
        status, resp = client.request("PUT", f"/api/projects/{proj['id']}",
                                      {"stage": "撤销"})
        assert status == 200, f"{stage} 进入撤销应允许: status={status} {resp}"
        assert _get_stage(tmp_db, proj["id"]) == "撤销"

    # 拒绝源：已完结不得撤销
    _, proj = _new_project(client, ent["id"], stage="已完结")
    status, resp = client.request("PUT", f"/api/projects/{proj['id']}", {"stage": "撤销"})
    assert status in (400, 403, 409), f"已完结撤销被接受: status={status} {resp}"
    assert _get_stage(tmp_db, proj["id"]) == "已完结", "非法撤销后库中阶段被改变"

    # 撤销不可恢复：撤销后任何流转（含中止）必须拒绝
    _, proj = _new_project(client, ent["id"], stage="已立项")
    pid = proj["id"]
    status, resp = client.request("PUT", f"/api/projects/{pid}", {"stage": "撤销"})
    assert status == 200, "已立项撤销应允许"
    for target in ["中止", "申报中", "实施中", "已完结"]:
        status, resp = client.request("PUT", f"/api/projects/{pid}", {"stage": target})
        assert status in (400, 403, 409), (
            f"撤销终态仍可流转为 {target}: status={status} {resp}")
        assert _get_stage(tmp_db, pid) == "撤销", "撤销终态被恢复/改变"


# ===========================================================================
# 4. 非法输入必须明确拒绝且无新增行（ADR-0001 / PLAN §3.2）
#    非法金额（负数/超两位小数/NaN/Inf/文本）、非法日期（格式/日历/范围）、
#    非法字典值、企业不存在与停用。
# ===========================================================================
@pytest.mark.parametrize("amount", [-1, 1.234, float("nan"), float("inf"),
                                    float("-inf"), "abc"])
def test_illegal_funding_amount_rejected(tmp_db, client, amount):
    """funding.amount 为 -1/1.234/NaN/Inf/文本 → 400 且不写库。"""
    _, ent = _new_enterprise(client, "91320000G2AMT01")
    _, proj = _new_project(client, ent["id"])
    before = _count_rows(tmp_db, "funding")
    status, resp = client.request(
        "POST", "/api/fundings",
        {"project_id": proj["id"], "amount": amount, "status": "未拨付",
         "source_type": "上级拨付"})
    assert status in (400, 403, 409), f"非法金额被接受: amount={amount!r} status={status} {resp}"
    assert _count_rows(tmp_db, "funding") == before, "非法金额被写入"


@pytest.mark.parametrize("total_amount", [-1, 1.234, float("nan"), float("inf"), "abc"])
def test_illegal_project_total_amount_rejected(tmp_db, client, total_amount):
    """project.total_amount 非法 → 400 且不写库。"""
    _, ent = _new_enterprise(client, "91320000G2AMT02")
    before = _count_rows(tmp_db, "project")
    status, resp = client.request(
        "POST", "/api/projects",
        {"name": "非法总金额项目", "project_no": "G2-AMT-BAD", "enterprise_id": ent["id"],
         "level": "省级", "category": "科技成果转化", "total_amount": total_amount,
         "start_date": "2024-01-01", "end_date": "2024-12-31", "stage": "已立项"})
    assert status in (400, 403, 409), (
        f"非法总金额被接受: total_amount={total_amount!r} status={status} {resp}")
    assert _count_rows(tmp_db, "project") == before, "非法金额被写入"


@pytest.mark.parametrize("field,value", [
    ("start_date", "2026/1/1"),     # 格式错误：分隔符错误
    ("start_date", "2026-02-30"),   # 日历错误：2 月无 30 日
    ("start_date", "2026-13-01"),   # 日历错误：13 月不存在
    ("end_date", "2026/1/1"),       # 格式错误
    ("end_date", "2026-1-1"),       # 格式错误：月份/日非两位
    ("end_date", "2026-02-30"),     # 日历错误
])
def test_illegal_project_date_rejected(tmp_db, client, field, value):
    """项目日期格式/日历非法 → 400 且不写库。"""
    _, ent = _new_enterprise(client, "91320000G2DAT01")
    before = _count_rows(tmp_db, "project")
    payload = {"name": "非法日期项目", "project_no": "G2-DAT-BAD", "enterprise_id": ent["id"],
               "level": "省级", "category": "科技成果转化", "total_amount": 100,
               "start_date": "2024-01-01", "end_date": "2024-12-31", "stage": "已立项"}
    payload[field] = value
    status, resp = client.request("POST", "/api/projects", payload)
    assert status in (400, 403, 409), f"非法日期被接受: {field}={value!r} status={status} {resp}"
    assert _count_rows(tmp_db, "project") == before, "非法日期被写入"


def test_illegal_project_date_range_rejected(tmp_db, client):
    """start_date > end_date → 400 且不写库。"""
    _, ent = _new_enterprise(client, "91320000G2DAT02")
    before = _count_rows(tmp_db, "project")
    status, resp = client.request(
        "POST", "/api/projects",
        {"name": "日期颠倒项目", "project_no": "G2-DAT-RANGE", "enterprise_id": ent["id"],
         "level": "省级", "category": "科技成果转化", "total_amount": 100,
         "start_date": "2024-12-31", "end_date": "2024-01-01", "stage": "已立项"})
    assert status in (400, 403, 409), f"开始晚于结束被接受: status={status} {resp}"
    assert _count_rows(tmp_db, "project") == before, "非法日期被写入"


@pytest.mark.parametrize("field,value", [
    ("plan_date", "2026/1/1"),      # 格式错误
    ("plan_date", "2026-02-30"),    # 日历错误
    ("actual_date", "2026.06.01"),  # 格式错误
    ("actual_date", "2026-02-30"),  # 日历错误
])
def test_illegal_funding_date_rejected(tmp_db, client, field, value):
    """资金计划/实拨日期格式、日历非法 → 400 且不写库。"""
    _, ent = _new_enterprise(client, "91320000G2DAT03")
    _, proj = _new_project(client, ent["id"])
    before = _count_rows(tmp_db, "funding")
    payload = {"project_id": proj["id"], "amount": 10, "status": "未拨付",
               "source_type": "上级拨付"}
    payload[field] = value
    status, resp = client.request("POST", "/api/fundings", payload)
    assert status in (400, 403, 409), f"非法日期被接受: {field}={value!r} status={status} {resp}"
    assert _count_rows(tmp_db, "funding") == before, "非法日期被写入"


@pytest.mark.parametrize("case", [
    ("project", "level", "乱写层级"),
    ("project", "category", "乱写类型"),
    ("funding", "source_type", "乱写来源"),
    ("node", "node_type", "乱写节点"),
    ("enterprise", "enterprise_type", "乱写企业类型"),
    ("enterprise", "district", "乱写区镇"),
])
def test_illegal_dict_value_rejected(tmp_db, client, case):
    """各枚举字段引用不存在的字典项 → 400 且不写库。"""
    kind, field, bad = case
    _, ent = _new_enterprise(client, "91320000G2DIC01")
    _, proj = _new_project(client, ent["id"])
    before = _count_rows(tmp_db, "project") + _count_rows(tmp_db, "funding") \
        + _count_rows(tmp_db, "node")

    if kind == "enterprise":
        status, resp = client.request(
            "POST", "/api/enterprises",
            {"name": "非法字典企业", "credit_code": "91320000G2DIC02", field: bad})
    elif kind == "project":
        status, resp = client.request(
            "POST", "/api/projects",
            {"name": "非法字典项目", "project_no": "G2-DIC-BAD",
             "enterprise_id": ent["id"], field: bad,
             "start_date": "2024-01-01", "end_date": "2024-12-31"})
    elif kind == "funding":
        status, resp = client.request(
            "POST", "/api/fundings",
            {"project_id": proj["id"], "amount": 10, "status": "未拨付", field: bad})
    else:  # node
        status, resp = client.request(
            "POST", "/api/nodes",
            {"project_id": proj["id"], "plan_date": "2024-06-01", field: bad})

    assert status in (400, 403, 409), (
        f"非法字典值被接受: {kind}.{field}={bad!r} status={status} {resp}")
    assert _count_rows(tmp_db, "project") + _count_rows(tmp_db, "funding") \
        + _count_rows(tmp_db, "node") == before, "携带非法字典值的记录被写入"


def _disable_dict_item(client, dict_type, value):
    """通过 API 停用指定字典项（is_active=0）。"""
    _, items = client.request("GET", f"/api/dict?type={dict_type}")
    row = next((i for i in items if i.get("value") == value), None)
    assert row is not None, f"字典项 {dict_type}/{value} 未找到: {items}"
    status, resp = client.request("PUT", f"/api/dict/{row['id']}", {"is_active": 0})
    assert status == 200, f"停用字典项失败: status={status} {resp}"


def test_disabled_dict_item_rejected(client):
    """停用 level/funding_source 后，新增项目/资金不得再引用 → 400。"""
    _, ent = _new_enterprise(client, "91320000G2DIC03")
    _, proj = _new_project(client, ent["id"])

    # 停用『省级』后新增 level=省级 的项目必须被拒
    _disable_dict_item(client, "level", "省级")
    status, resp = client.request(
        "POST", "/api/projects",
        {"name": "引用停用层级项目", "project_no": "G2-DIC-DIS",
         "enterprise_id": ent["id"], "level": "省级",
         "category": "科技成果转化", "total_amount": 100,
         "start_date": "2024-01-01", "end_date": "2024-12-31", "stage": "已立项"})
    assert status in (400, 403, 409), f"停用字典值被用于新增: status={status} {resp}"

    # 停用『上级拨付』后新增 source_type=上级拨付 的资金必须被拒
    _disable_dict_item(client, "funding_source", "上级拨付")
    status, resp = client.request(
        "POST", "/api/fundings",
        {"project_id": proj["id"], "amount": 10, "status": "未拨付",
         "source_type": "上级拨付"})
    assert status in (400, 403, 409), f"停用字典值被用于新增资金: status={status} {resp}"


def test_nonexistent_enterprise_rejected(tmp_db, client):
    """企业不存在 → 明确 400 + 可读 error + 无新增行（当前 599/connection failed）。"""
    before = _count_rows(tmp_db, "project")
    status, resp = client.request(
        "POST", "/api/projects",
        {"name": "孤儿项目", "project_no": "G2-ORPHAN", "enterprise_id": 999999})
    assert status == 400, f"应返回明确 400，实际 {status}：{resp}"
    assert resp.get("error") not in (None, "connection failed"), f"错误信息不可读: {resp}"
    assert _count_rows(tmp_db, "project") == before, "外键约束未生效，项目被写入"


def test_disabled_enterprise_rejected(tmp_db, client):
    """政务停用保留历史查询，仅禁止该企业继续承接新的项目。"""
    _, ent = _new_enterprise(client, "91320000G2OFF01")
    _, historical = _new_project(client, ent["id"], project_no="G2-HISTORY-01")
    status, disabled = client.request("POST", f"/api/enterprises/{ent['id']}/disable", {"reason": "企业资格审核到期"})
    assert status == 200 and disabled["is_active"] == 0
    status, detail = client.request("GET", f"/api/enterprises/{ent['id']}")
    assert status == 200 and any(p["id"] == historical["id"] for p in detail["projects"]), "停用不得隐藏历史项目"
    before = _count_rows(tmp_db, "project")
    status, resp = client.request(
        "POST", "/api/projects",
        {"name": "停用企业项目", "project_no": "G2-OFF-01", "enterprise_id": ent["id"],
         "level": "省级", "category": "科技成果转化", "total_amount": 100,
         "start_date": "2024-01-01", "end_date": "2024-12-31", "stage": "已立项"})
    assert status in (400, 403, 409), f"停用企业承接新项目被接受: status={status} {resp}"
    assert _count_rows(tmp_db, "project") == before, "停用企业承接的项目被写入"
    status, enabled = client.request("POST", f"/api/enterprises/{ent['id']}/enable", {"reason": "资格复审通过"})
    assert status == 200 and enabled["is_active"] == 1
    conn = db_conn(tmp_db)
    try:
        actions = {row["action"] for row in conn.execute("SELECT action FROM audit_log WHERE object_type='enterprise' AND object_id=?", (ent["id"],))}
    finally:
        conn.close()
    assert {"disable", "enable"} <= actions, "启停企业必须留下审计记录"


# ===========================================================================
# 5. 直接 SQLite 写入同类非法数据也必须无法突破
#    （ADR-0001 决策二/三「数据库约束 + 领域校验双保险」：
#      唯一索引/CHECK 约束/触发器兜底直接 SQL/迁移路径）
#    准确断言：sqlite3.IntegrityError 抛出 或 行未写入。
# ===========================================================================
def _direct_sql_expect_rejected(tmp_db, sql, params, table):
    """执行直接 SQL 写入，断言被数据库层拒绝（IntegrityError 或行未写入）。

    返回 True 表示被拒绝（契约满足）；G2 实现前无约束 → 写入成功 → False。
    """
    before = _count_rows(tmp_db, table)
    conn = db_conn(tmp_db)
    try:
        try:
            conn.execute(sql, params)
            conn.commit()
        except sqlite3.IntegrityError:
            return True  # 数据库层拒绝（CHECK/唯一索引/触发器）
    finally:
        conn.close()
    return _count_rows(tmp_db, table) == before


def test_direct_sql_illegal_funding_amount_rejected(tmp_db, client):
    """直接 SQL INSERT funding amount=-1 必须无法突破（IntegrityError 或行未写入）。"""
    _, ent = _new_enterprise(client, "91320000G2SQL01")
    _, proj = _new_project(client, ent["id"])
    pid = proj["id"]

    rejected = _direct_sql_expect_rejected(
        tmp_db,
        "INSERT INTO funding (project_id, amount, status, source_type) "
        "VALUES (?, -1, '未拨付', '上级拨付')",
        (pid,), "funding")
    assert rejected, "直接 SQL 写入非法金额 -1 未被数据库层拦截"


def test_direct_sql_invalid_funding_date_status_rejected(tmp_db, client):
    """直接 SQL INSERT 状态-日期非法组合必须无法突破。"""
    _, ent = _new_enterprise(client, "91320000G2SQL02")
    _, proj = _new_project(client, ent["id"])
    pid = proj["id"]

    # 已到账却无 actual_date
    rejected1 = _direct_sql_expect_rejected(
        tmp_db,
        "INSERT INTO funding (project_id, amount, status, source_type, plan_date) "
        "VALUES (?, 10, '已到账', '上级拨付', '2024-06-01')",
        (pid,), "funding")
    assert rejected1, "直接 SQL 写入『已到账无实拨日期』未被拦截"

    # 未拨付却带 actual_date
    rejected2 = _direct_sql_expect_rejected(
        tmp_db,
        "INSERT INTO funding (project_id, amount, status, source_type, actual_date) "
        "VALUES (?, 10, '未拨付', '上级拨付', '2024-06-01')",
        (pid,), "funding")
    assert rejected2, "直接 SQL 写入『未拨付带实拨日期』未被拦截"


def test_direct_sql_duplicate_project_no_rejected(tmp_db, client):
    """直接 SQL INSERT 同企业同号项目必须无法突破（唯一索引）。"""
    _, ent = _new_enterprise(client, "91320000G2SQL03")
    _, proj = _new_project(client, ent["id"], project_no="P-DIR-001")

    rejected = _direct_sql_expect_rejected(
        tmp_db,
        "INSERT INTO project (name, project_no, enterprise_id) "
        "VALUES ('直接SQL重复', 'P-DIR-001', ?)",
        (ent["id"],), "project")
    assert rejected, "直接 SQL 写入同企业重复 project_no 未被唯一索引拦截"


def test_direct_sql_illegal_stage_update_rejected(tmp_db, client):
    """直接 SQL UPDATE stage 跳跃（申报中→已完结）必须无法突破。"""
    _, ent = _new_enterprise(client, "91320000G2SQL04")
    _, proj = _new_project(client, ent["id"], stage="申报中")
    pid = proj["id"]

    conn = db_conn(tmp_db)
    try:
        try:
            conn.execute("UPDATE project SET stage='已完结' WHERE id=?", (pid,))
            conn.commit()
        except sqlite3.IntegrityError:
            return  # 触发器拒绝 → 契约满足
    finally:
        conn.close()
    assert _get_stage(tmp_db, pid) == "申报中", (
        "直接 SQL 跳跃阶段未被拦截，库中阶段被改变为已完结")


# ===========================================================================
# 6. MCP 查询层安全（ADR-0001 决策一跨层一致性 + 只读原则）
#    monkeypatch mcp_server.DB_PATH/BASE_DIR 指向 tmp_db（安全注入），
#    直接调用公开查询函数比对三口径，绝不触碰正式库。
# ===========================================================================
def test_mcp_funding_totals_consistent_with_api(tmp_db, client, monkeypatch):
    """MCP 查询层（注入 tmp_db）三口径必须与 API 详情一致。"""
    import mcp_server

    # 安全注入：把 mcp_server 的库路径重定向到临时库，绝不触碰正式库
    monkeypatch.setattr(mcp_server, "DB_PATH", str(tmp_db))
    monkeypatch.setattr(mcp_server, "BASE_DIR", str(tmp_db.parent))

    pid, expected = _seed_money_sample(client)

    # 直接调用公开查询函数（FastMCP 装饰后仍是普通函数，不伪造数据）
    mcp_detail = mcp_server.get_project(pid)
    mcp_list = mcp_server.list_projects()
    mcp_row = next((r for r in mcp_list if r.get("id") == pid), None)
    assert mcp_row is not None, f"MCP list_projects 未返回项目 {pid}: {mcp_list}"

    _, api_detail = client.request("GET", f"/api/projects/{pid}")
    for key, want in expected.items():
        got = mcp_detail[key]  # 契约规定字段，缺失即失败
        assert got == want, f"MCP get_project 的 {key} 应等于 {want}，实际 {got}"
    for key, want in expected.items():
        got = mcp_row[key]
        assert got == want, f"MCP list_projects 的 {key} 应等于 {want}，实际 {got}"
    for key in expected:
        assert mcp_detail[key] == api_detail[key], (
            f"{key} 在 MCP 与 API 间不一致: {mcp_detail[key]} vs {api_detail[key]}")

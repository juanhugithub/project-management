# -*- coding: utf-8 -*-
"""G2 测试先行：核心写入约束与统一查询层 —— 契约测试（2026-08-13）

本文件是「G2 测试先行准备」，非业务实现：把 PLAN.md §3.1 / §3.2 / §3.4
（关键业务契约）与 §4 G2（核心写入约束与统一查询层）写成可运行契约，
所有当前尚未实现的需求一律 `pytest.mark.xfail(strict=True)`。

关于 G1 状态（本文件的硬前提）：
- G0 已完成；**G1 三项 HUMAN 决策已确认并冻结**，唯一依据为
  `docs/decisions/0001-领域契约三项决策.md`（ADR-0001，头部标注「已确认
  （HUMAN 签字）」· 2026-08-13）。若 ADR-0001 后续被 HUMAN 修改，本文件
  断言须随之更新。
- ADR-0001 三项决策摘要（本文件全部断言的唯一依据）：
  ① 资金单记录不拆分：amount=计划/批准金额；口径按 PLAN §3.1 输出
     planned_total / disbursed_total / received_total，禁止语义不清的单一
     funded_total 承载两种口径（P0-01 修复目标）；
  ② 项目业务唯一键 = (project_no, enterprise.credit_code)，两者均非空时
     受唯一约束；无编号记录禁止自动入账（只能进入待确认队列）；
  ③ 状态机：正常链 申报中→已立项→实施中→待验收→已验收→绩效跟踪→已完结
     （禁止回退、禁止跳跃）；中止仅从【已立项、实施中、待验收】进入且为
     不可恢复终态；撤销为不可恢复终态（源=申报中/已立项/实施中/待验收/
     已验收/绩效跟踪，已完结/中止/撤销不得进入）。
- 当前 G2 尚未实施（.vibe/stage-gates.md：G1 决策后待授权 G2），本文件把
  上述已冻结契约写成断言；未实现需求一律 xfail(strict=True)。

硬约束（与 test_regressions.py 一致）：
- 只使用 conftest 的 tmp_db / client 夹具，数据库写操作只针对 tmp_db；
- MCP 层显式 monkeypatch `mcp_server.DB_PATH` 到 tmp_db，绝不触碰正式库
  data/project.db（另有 conftest 会话级 SHA-256 守卫兜底）；
- 不修改任何既有文件，本文件只新增。

xfail(strict=True) 语义：需求未实现 → 测试 FAIL → 记为 XFAIL（通过）；
修复对应需求后测试转绿 → 出现 XPASS(strict) 报错 → 提示移除标记。
绝不允许通过弱化断言把缺陷伪装成通过。
"""

import os
import sqlite3

import pytest

from conftest import PROJECT_ROOT, db_conn


# ===========================================================================
# 通用辅助：构造合法样本（仅操作临时库）
# ===========================================================================
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
    """新建合法项目（挂在企业 eid 下），返回 (status, resp)。"""
    payload = {
        "name": "G2契约测试项目",
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


def _seed_money_sample(client):
    """构造金额口径样本（语义测试与跨层一致性测试共用同一份临时样本）。

    资金记录金额 amount 即「计划/批准金额」（PLAN §3.1：勾稽基准是各资金
    来源计划/批准金额之和），单位万元，全部取整数避免浮点误差。

    样本组合（合法组合全覆盖；非法组合见 *_requires_* / *_forbids_* 测试）：
      F1  100 未拨付  plan_date=2024-06-01  actual_date=None            → planned
      F2   60 已拨付  plan_date=2024-07-01  actual_date=2024-07-10      → planned + disbursed
      F3   40 已到账  plan_date=2024-08-01  actual_date=2024-08-15      → planned + disbursed + received
      F4   20 未拨付  plan_date=None        actual_date=None            → 不计入任何
      F5   30 已到账  plan_date=None        actual_date=2024-09-01      → disbursed + received
      F6   50 已拨付  plan_date=None        actual_date=2024-09-15      → disbursed

    PLAN §3.1 口径期望值：
      planned_total   = Σ plan_date 非空        = 100+60+40      = 200
      disbursed_total = Σ status∈(已拨付,已到账) = 60+40+30+50    = 180
      received_total  = Σ status=已到账         = 40+30          = 70
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
# 1. 单资金记录金额语义（任务 1）
#   ADR-0001 决策一（冻结）：资金单记录不拆分，amount=计划/批准金额；
#   plan_date 是否存在、actual_date 是否存在、status 分别精确决定
#   planned_total / disbursed_total / received_total（PLAN §3.1 口径）。
# ===========================================================================
@pytest.mark.xfail(strict=True, reason=(
    "G2 未实现统一资金口径字段：app.py 项目详情/列表/工作台只有 funded_total / "
    "plan_total（且 P0-01 口径分歧），没有 planned_total / disbursed_total / "
    "received_total。契约（PLAN §3.1）：三口径必须按『plan_date 是否为空、"
    "status∈(已拨付,已到账)、status=已到账』精确计算并存于 API 返回。"))
def test_funding_semantics_planned_disbursed_received(client):
    """六笔资金（覆盖状态×日期各合法组合）→ 详情接口三口径必须等于期望值。"""
    pid, expected = _seed_money_sample(client)
    _, detail = client.request("GET", f"/api/projects/{pid}")
    for key, want in expected.items():
        # 当前字段缺失 → KeyError → 预期失败（XFAIL）
        got = detail[key]
        assert got == want, f"{key} 应等于 {want}（PLAN §3.1 口径），实际 {got}"


@pytest.mark.xfail(strict=True, reason=(
    "状态与实拨日期一致性未校验：app._api_child 对 funding 仅要求 project_id，"
    "status='已到账' 且 actual_date 为空也被接受。契约：actual_date 是『实拨时间』"
    "（schema.sql 注释），已到账必须已拨付 → 必须有实拨日期，否则 400 且不写库。"))
def test_funding_received_requires_actual_date(tmp_db, client):
    """status=已到账 但无 actual_date 必须 400（当前被接受并写入）。"""
    _, ent = _new_enterprise(client, "91320000G2SEM02")
    _, proj = _new_project(client, ent["id"])
    before = _count_rows(tmp_db, "funding")
    status, resp = client.request(
        "POST", "/api/fundings",
        {"project_id": proj["id"], "amount": 10, "status": "已到账",
         "source_type": "上级拨付", "plan_date": "2024-06-01"})
    assert status in (400, 403, 409), f"已到账却无实拨日期被接受: status={status} {resp}"
    assert _count_rows(tmp_db, "funding") == before, "非法资金记录被写入"


@pytest.mark.xfail(strict=True, reason=(
    "状态与实拨日期一致性未校验：status='已拨付' 且 actual_date 为空也被接受。"
    "契约：已拨付必有实拨时间（schema.sql 注释 actual_date=实拨时间），"
    "否则 400 且不写库。"))
def test_funding_disbursed_requires_actual_date(tmp_db, client):
    """status=已拨付 但无 actual_date 必须 400（当前被接受并写入）。"""
    _, ent = _new_enterprise(client, "91320000G2SEM03")
    _, proj = _new_project(client, ent["id"])
    before = _count_rows(tmp_db, "funding")
    status, resp = client.request(
        "POST", "/api/fundings",
        {"project_id": proj["id"], "amount": 10, "status": "已拨付",
         "source_type": "上级拨付", "plan_date": "2024-06-01"})
    assert status in (400, 403, 409), f"已拨付却无实拨日期被接受: status={status} {resp}"
    assert _count_rows(tmp_db, "funding") == before, "非法资金记录被写入"


@pytest.mark.xfail(strict=True, reason=(
    "状态与实拨日期一致性未校验：status='未拨付' 却带 actual_date 也被接受。"
    "契约：未拨付意味着拨付动作未发生，不应有实拨时间（schema.sql 注释），"
    "否则 400 且不写库。"))
def test_funding_unpaid_forbids_actual_date(tmp_db, client):
    """status=未拨付 却带 actual_date 必须 400（当前被接受并写入）。"""
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
# 2. 项目业务唯一键（任务 2）
#   ADR-0001 决策二（冻结）：唯一键 = (非空 project_no, 承担企业 credit_code)，
#   落库为 project(project_no, enterprise_id) 唯一索引（两者均非空才受约束）；
#   重复创建拒绝；无编号记录禁止自动入账（应进入待确认队列，当前 API 无该
#   队列 → 断言拒绝）。另见 PLAN §3.4。
# ===========================================================================
@pytest.mark.xfail(strict=True, reason=(
    "唯一键未实施：schema.sql 的 project 表无 (project_no, enterprise_id) 唯一约束，"
    "app._api_project POST 也不校验 project_no。契约（PLAN §3.4）：同一企业下"
    "project_no 重复必须 409/400 且不写库；不同企业的相同 project_no 合法。"))
def test_project_unique_key_duplicate_rejected(tmp_db, client):
    """同一企业 + 同一 project_no 重复创建必须拒绝；不同企业同名编号允许。"""
    _, ent_a = _new_enterprise(client, "91320000G2UNI01", "唯一键企业A")
    _, ent_b = _new_enterprise(client, "91320000G2UNI02", "唯一键企业B")

    # 对照基线（当前已满足）：不同企业可用相同 project_no
    s1, proj_b = _new_project(client, ent_b["id"], name="编号项目B", project_no="P-G2-001")
    assert s1 == 200 and proj_b.get("id")

    # 契约断言（当前失败）：同一企业重复 project_no 应拒绝
    s2, proj_a = _new_project(client, ent_a["id"], name="编号项目A", project_no="P-G2-001")
    before = _count_rows(tmp_db, "project")
    status, resp = client.request(
        "POST", "/api/projects",
        {"name": "重复编号项目", "enterprise_id": ent_a["id"], "level": "省级",
         "category": "科技成果转化", "project_no": "P-G2-001",
         "start_date": "2024-01-01", "end_date": "2024-12-31", "stage": "已立项"})
    assert status in (400, 409), (
        f"同一企业重复 project_no 被接受: status={status} {resp} "
        f"（首条 id={s2 and proj_a.get('id')}）")
    assert _count_rows(tmp_db, "project") == before, "重复记录被写入"


@pytest.mark.xfail(strict=True, reason=(
    "唯一键索引缺失：project 表仅有 idx_project_enterprise(enterprise_id) 非唯一索引。"
    "契约（PLAN §3.4）：必须存在覆盖 (project_no, enterprise_id) 的唯一索引，"
    "保护直接 SQL 写入路径（PLAN G2 工作项 4：唯一索引保护直接 SQL/迁移路径）。"))
def test_project_unique_key_index_exists(tmp_db):
    """数据库层必须存在唯一索引覆盖 project_no + enterprise_id（直接 SQL 防绕过）。"""
    conn = db_conn(tmp_db)
    try:
        found = None
        for idx in conn.execute("PRAGMA index_list('project')").fetchall():
            if idx["unique"] != 1:
                continue
            cols = [r["name"] for r in conn.execute(
                f"PRAGMA index_info('{idx['name']}')").fetchall()]
            if "project_no" in cols and "enterprise_id" in cols:
                found = idx["name"]
                break
        assert found is not None, (
            "project 表缺少覆盖 (project_no, enterprise_id) 的唯一索引，"
            "直接 SQL 写入可绕过业务唯一键")
    finally:
        conn.close()


@pytest.mark.xfail(strict=True, reason=(
    "无编号记录被自动入账：app._api_project POST 只校验 name。契约（PLAN §3.4）："
    "无项目编号的记录只能进入待确认队列，不能自动入账；当前 API 无待确认机制，"
    "故必须拒绝（400）。"))
def test_project_without_project_no_rejected(tmp_db, client):
    """不提供 project_no 的项目必须 400（当前被接受并写入）。"""
    _, ent = _new_enterprise(client, "91320000G2UNI03")
    before = _count_rows(tmp_db, "project")
    status, resp = client.request(
        "POST", "/api/projects",
        {"name": "无编号项目", "enterprise_id": ent["id"], "level": "省级",
         "category": "科技成果转化", "total_amount": 100,
         "start_date": "2024-01-01", "end_date": "2024-12-31", "stage": "已立项"})
    assert status in (400, 403, 409), f"无 project_no 的项目被自动入账: status={status} {resp}"
    assert _count_rows(tmp_db, "project") == before, "无编号记录被写入"


# ===========================================================================
# 3. 项目状态机（任务 3）—— 以 ADR-0001 决策三（冻结）为唯一依据
#   正常链：申报中 → 已立项 → 实施中 → 待验收 → 已验收 → 绩效跟踪 → 已完结
#     （仅沿链前进，禁止回退、禁止跳跃）；
#   中止：仅从【已立项、实施中、待验收】进入；不可恢复终态（不得再流转，含撤销）；
#   撤销：不可恢复终态；源 = 申报中/已立项/实施中/待验收/已验收/绩效跟踪。
#   当前 app.py 对 stage 无任何状态机校验（任意值可写）→ 以下全部 xfail。
# ===========================================================================
def test_state_machine_frozen_contract_anchored(tmp_db):
    """契约锚点（绿）：ADR-0001 冻结契约必须存在且声明状态机规则。

    该测试锚定『状态机断言的唯一依据』：若 ADR-0001 缺失或规则被改写，
    本测试立即变红，防止实现与冻结契约脱节。"""
    adr = os.path.join(PROJECT_ROOT, "docs", "decisions", "0001-领域契约三项决策.md")
    assert os.path.isfile(adr), "G1 冻结契约 ADR-0001 缺失，状态机断言失去依据"
    with open(adr, encoding="utf-8") as f:
        text = f.read()
    assert "已确认（HUMAN 签字）" in text, "ADR-0001 未被 HUMAN 确认"
    for token in ("申报中", "已立项", "实施中", "待验收", "已验收", "绩效跟踪",
                  "已完结", "中止", "撤销", "不可恢复"):
        assert token in text, f"ADR-0001 缺少状态机关键语义: {token}"


@pytest.mark.xfail(strict=True, reason=(
    "状态机流转未校验：app._api_project 对 stage 无任何状态机约束（P0-02 同类），"
    "回退/跳跃/任意值均可写入。契约（ADR-0001 决策三）：正常流转仅沿链前进"
    "（申报中→已立项→实施中→待验收→已验收→绩效跟踪→已完结），"
    "禁止回退、禁止跳跃，违者 400 且不写库。"))
def test_state_machine_normal_transitions_exact(client):
    """正常流转逐跳精确校验：整条链前进放行，回退/跳跃拒绝。"""
    _, ent = _new_enterprise(client, "91320000G2STM01")
    _, proj = _new_project(client, ent["id"], name="正常链项目", stage="申报中")
    pid = proj["id"]

    # 合法：沿正常链逐跳前进，全部必须放行
    for nxt in ("已立项", "实施中", "待验收", "已验收", "绩效跟踪", "已完结"):
        status, resp = client.request("PUT", f"/api/projects/{pid}", {"stage": nxt})
        assert status == 200, f"合法流转 →{nxt} 被拒: status={status} {resp}"

    # 非法：回退（已完结 → 绩效跟踪）必须拒绝
    status, resp = client.request("PUT", f"/api/projects/{pid}", {"stage": "绩效跟踪"})
    assert status in (400, 403, 409), f"状态回退被接受: status={status} {resp}"

    # 非法：跳跃（申报中 → 已验收，跨多级）必须拒绝
    _, proj2 = _new_project(client, ent["id"], name="跳跃项目", stage="申报中")
    status, resp = client.request("PUT", f"/api/projects/{proj2['id']}", {"stage": "已验收"})
    assert status in (400, 403, 409), f"状态跳跃被接受: status={status} {resp}"


@pytest.mark.xfail(strict=True, reason=(
    "中止进入条件未校验：任意阶段都可直接写成『中止』。契约（ADR-0001 决策三）："
    "中止仅允许从【已立项、实施中、待验收】三个阶段进入；申报中（未立项前取消"
    "应走撤销）、已验收及之后不得中止，违者 400 且不写库。"))
def test_state_machine_abort_only_from_three_stages(client):
    """中止仅能从 已立项/实施中/待验收 进入，其余阶段进入必须拒绝。"""
    _, ent = _new_enterprise(client, "91320000G2STM02")

    # 合法：已立项 → 中止（三个允许源阶段之一）
    _, p_ok = _new_project(client, ent["id"], name="中止合法", stage="已立项")
    status, resp = client.request("PUT", f"/api/projects/{p_ok['id']}", {"stage": "中止"})
    assert status == 200, f"已立项→中止 应放行: status={status} {resp}"

    # 非法：申报中 → 中止（未立项前取消应走撤销）
    _, p1 = _new_project(client, ent["id"], name="中止申报中", stage="申报中")
    status, resp = client.request("PUT", f"/api/projects/{p1['id']}", {"stage": "中止"})
    assert status in (400, 403, 409), f"申报中→中止 被接受: status={status} {resp}"

    # 非法：已验收 → 中止（已验收之后不中止）
    _, p2 = _new_project(client, ent["id"], name="中止已验收", stage="已验收")
    status, resp = client.request("PUT", f"/api/projects/{p2['id']}", {"stage": "中止"})
    assert status in (400, 403, 409), f"已验收→中止 被接受: status={status} {resp}"

    # 非法：已完结 → 中止
    _, p3 = _new_project(client, ent["id"], name="中止已完结", stage="已完结")
    status, resp = client.request("PUT", f"/api/projects/{p3['id']}", {"stage": "中止"})
    assert status in (400, 403, 409), f"已完结→中止 被接受: status={status} {resp}"


@pytest.mark.xfail(strict=True, reason=(
    "中止可恢复性未校验：进入『中止』后仍可随意改写 stage。契约（ADR-0001 决策三）："
    "中止为不可恢复终态，进入后不得再流转到任何状态（含撤销），违者 400 且不写库。"))
def test_state_machine_abort_unrecoverable(client):
    """中止后不得流转到任何状态（含撤销）——不可恢复终态。"""
    _, ent = _new_enterprise(client, "91320000G2STM03")
    _, proj = _new_project(client, ent["id"], name="中止终态", stage="实施中")
    pid = proj["id"]
    status, resp = client.request("PUT", f"/api/projects/{pid}", {"stage": "中止"})
    assert status == 200, f"实施中→中止 应放行: status={status} {resp}"

    for nxt in ("已立项", "待验收", "已完结", "撤销"):
        status, resp = client.request("PUT", f"/api/projects/{pid}", {"stage": nxt})
        assert status in (400, 403, 409), f"中止后流转 →{nxt} 被接受: status={status} {resp}"


@pytest.mark.xfail(strict=True, reason=(
    "撤销规则未校验。契约（ADR-0001 决策三）：撤销为不可恢复终态；源状态为"
    "申报中/已立项/实施中/待验收/已验收/绩效跟踪，已完结/中止/撤销不得进入；"
    "撤销后不得再流转，违者 400 且不写库。"))
def test_state_machine_revoke_rules(client):
    """撤销源状态集 + 不可恢复性校验。"""
    _, ent = _new_enterprise(client, "91320000G2STM04")

    # 合法：绩效跟踪 → 撤销（允许源状态之一）
    _, p_ok = _new_project(client, ent["id"], name="撤销合法", stage="绩效跟踪")
    status, resp = client.request("PUT", f"/api/projects/{p_ok['id']}", {"stage": "撤销"})
    assert status == 200, f"绩效跟踪→撤销 应放行: status={status} {resp}"

    # 非法：已完结 → 撤销（已完结为终态，不得撤销）
    _, p1 = _new_project(client, ent["id"], name="撤销已完结", stage="已完结")
    status, resp = client.request("PUT", f"/api/projects/{p1['id']}", {"stage": "撤销"})
    assert status in (400, 403, 409), f"已完结→撤销 被接受: status={status} {resp}"

    # 非法：撤销后不得再流转（不可恢复终态）
    status, resp = client.request("PUT", f"/api/projects/{p_ok['id']}", {"stage": "已完结"})
    assert status in (400, 403, 409), f"撤销后流转 被接受: status={status} {resp}"


# ===========================================================================
# 4. 非法输入必须拒绝且不写库（任务 4）
#   非法金额（负/超两位小数/NaN/Inf/文本）、非法日期（格式/日历/范围）、
#   非法字典值、企业不存在/停用 → 明确 400/403/409，绝不静默转 NULL。
# ===========================================================================
@pytest.mark.parametrize("amount", [-5, 12.345, float("nan"), float("inf"),
                                    float("-inf"), "abc"])
@pytest.mark.xfail(strict=True, reason=(
    "非法金额被接受：app.clean_payload 对文本 float() 失败后静默置 None（P0-02），"
    "负值/超两位小数/NaN/Inf 直接写入 REAL。契约（PLAN §3.2/G2 目标 5）：金额必须"
    "非负、最多两位小数、不得 NaN/Inf/文本，非法输入必须 400 且不写库，"
    "严禁静默转 NULL。"))
def test_illegal_funding_amount_rejected(tmp_db, client, amount):
    """funding.amount 为负/超两位小数/NaN/Inf/文本 → 400 且不写库。"""
    _, ent = _new_enterprise(client, "91320000G2AMT01")
    _, proj = _new_project(client, ent["id"])
    before = _count_rows(tmp_db, "funding")
    status, resp = client.request(
        "POST", "/api/fundings",
        {"project_id": proj["id"], "amount": amount, "status": "未拨付",
         "source_type": "上级拨付"})
    assert status in (400, 403, 409), f"非法金额被接受: amount={amount!r} status={status} {resp}"
    assert _count_rows(tmp_db, "funding") == before, "非法金额被写入"


@pytest.mark.parametrize("total_amount", [-5, 12.345, float("nan"), "abc"])
@pytest.mark.xfail(strict=True, reason=(
    "非法项目总金额被接受：project.total_amount 与 funding.amount 同属金额，"
    "契约同样要求非负、最多两位小数、不得 NaN/文本（PLAN §3.2）。"))
def test_illegal_project_total_amount_rejected(tmp_db, client, total_amount):
    """project.total_amount 非法 → 400 且不写库。"""
    _, ent = _new_enterprise(client, "91320000G2AMT02")
    before = _count_rows(tmp_db, "project")
    status, resp = client.request(
        "POST", "/api/projects",
        {"name": "非法总金额项目", "enterprise_id": ent["id"], "level": "省级",
         "category": "科技成果转化", "total_amount": total_amount,
         "start_date": "2024-01-01", "end_date": "2024-12-31", "stage": "已立项"})
    assert status in (400, 403, 409), (
        f"非法总金额被接受: total_amount={total_amount!r} status={status} {resp}")
    assert _count_rows(tmp_db, "project") == before, "非法金额被写入"


def test_valid_two_decimal_amount_accepted(client):
    """边界对照（绿）：两位小数是合法上限，必须被接受（不弱化断言）。"""
    _, ent = _new_enterprise(client, "91320000G2AMT03")
    _, proj = _new_project(client, ent["id"])
    status, resp = client.request(
        "POST", "/api/fundings",
        {"project_id": proj["id"], "amount": 12.34, "status": "未拨付",
         "source_type": "上级拨付"})
    assert status == 200, f"两位小数金额被拒: status={status} {resp}"


@pytest.mark.parametrize("field,value", [
    ("start_date", "2024/01/01"),   # 格式错误：分隔符错误
    ("start_date", "20240101"),     # 格式错误：无分隔符
    ("start_date", "2024-02-30"),   # 日历错误：2 月无 30 日
    ("start_date", "2024-13-01"),   # 日历错误：13 月不存在
    ("end_date", "2024-1-1"),       # 格式错误：月份/日非两位
])
@pytest.mark.xfail(strict=True, reason=(
    "非法日期被接受：app 对 start_date/end_date 无任何格式/日历校验。契约"
    "（PLAN §3.2）：日期必须为有效 YYYY-MM-DD（含日历有效性），否则 400 且不写库。"))
def test_illegal_project_date_rejected(tmp_db, client, field, value):
    """项目日期格式/日历非法 → 400 且不写库。"""
    _, ent = _new_enterprise(client, "91320000G2DAT01")
    before = _count_rows(tmp_db, "project")
    payload = {"name": "非法日期项目", "enterprise_id": ent["id"], "level": "省级",
               "category": "科技成果转化", "total_amount": 100,
               "start_date": "2024-01-01", "end_date": "2024-12-31", "stage": "已立项"}
    payload[field] = value
    status, resp = client.request("POST", "/api/projects", payload)
    assert status in (400, 403, 409), f"非法日期被接受: {field}={value!r} status={status} {resp}"
    assert _count_rows(tmp_db, "project") == before, "非法日期被写入"


@pytest.mark.xfail(strict=True, reason=(
    "日期范围未校验：start_date 晚于 end_date 被接受。契约（PLAN §3.2）："
    "开始日期不得晚于结束日期（相等允许），否则 400 且不写库。"))
def test_illegal_project_date_range_rejected(tmp_db, client):
    """start_date > end_date → 400 且不写库。"""
    _, ent = _new_enterprise(client, "91320000G2DAT02")
    before = _count_rows(tmp_db, "project")
    status, resp = client.request(
        "POST", "/api/projects",
        {"name": "日期颠倒项目", "enterprise_id": ent["id"], "level": "省级",
         "category": "科技成果转化", "total_amount": 100,
         "start_date": "2024-12-31", "end_date": "2024-01-01", "stage": "已立项"})
    assert status in (400, 403, 409), f"开始晚于结束被接受: status={status} {resp}"
    assert _count_rows(tmp_db, "project") == before, "非法日期被写入"


def test_valid_start_equals_end_date_accepted(client):
    """边界对照（绿）：开始日期等于结束日期合法（『不得晚于』允许相等）。"""
    _, ent = _new_enterprise(client, "91320000G2DAT03")
    status, resp = client.request(
        "POST", "/api/projects",
        {"name": "同日项目", "enterprise_id": ent["id"], "level": "省级",
         "category": "科技成果转化", "total_amount": 100,
         "start_date": "2024-06-01", "end_date": "2024-06-01", "stage": "已立项"})
    assert status == 200, f"开始=结束被拒: status={status} {resp}"


@pytest.mark.parametrize("field,value", [
    ("plan_date", "2024/06/01"),    # 格式错误
    ("plan_date", "2024-06-31"),    # 日历错误：6 月无 31 日
    ("actual_date", "2024.06.01"),  # 格式错误
    ("actual_date", "2024-02-30"),  # 日历错误
])
@pytest.mark.xfail(strict=True, reason=(
    "资金日期未校验：funding.plan_date/actual_date 非法值被接受。契约（PLAN §3.2）："
    "所有日期字段必须为有效 YYYY-MM-DD，否则 400 且不写库。"))
def test_illegal_funding_date_rejected(tmp_db, client, field, value):
    """资金计划/实拨日期格式、日历非法 → 400 且不写库。"""
    _, ent = _new_enterprise(client, "91320000G2DAT04")
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
@pytest.mark.xfail(strict=True, reason=(
    "非法字典值被接受：app 对 level/category/funding_source/node_type/"
    "enterprise_type/district 无字典校验（P0-02 同类问题）。契约（PLAN §3.2）："
    "这些字段必须引用 dict_item 中存在的取值，非法值必须 400 且不写库。"))
def test_illegal_dict_value_rejected(tmp_db, client, case):
    """各枚举字段引用不存在的字典项 → 400 且不写库。"""
    kind, field, bad = case
    _, ent = _new_enterprise(client, "91320000G2DIC01")
    _, proj = _new_project(client, ent["id"])
    before = _count_rows(tmp_db, "project") + _count_rows(tmp_db, "funding")

    if kind == "enterprise":
        status, resp = client.request(
            "POST", "/api/enterprises",
            {"name": "非法字典企业", "credit_code": "91320000G2DIC02", field: bad})
    elif kind == "project":
        status, resp = client.request(
            "POST", "/api/projects",
            {"name": "非法字典项目", "enterprise_id": ent["id"], field: bad,
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
    assert _count_rows(tmp_db, "project") + _count_rows(tmp_db, "funding") == before, (
        "携带非法字典值的记录被写入")


def _disable_dict_item(client, dict_type, value):
    """通过 API 停用指定字典项（is_active=0）。"""
    _, items = client.request("GET", f"/api/dict?type={dict_type}")
    row = next((i for i in items if i.get("value") == value), None)
    assert row is not None, f"字典项 {dict_type}/{value} 未找到: {items}"
    status, resp = client.request("PUT", f"/api/dict/{row['id']}", {"is_active": 0})
    assert status == 200, f"停用字典项失败: status={status} {resp}"


@pytest.mark.xfail(strict=True, reason=(
    "停用字典项仍可用于新增：停用后 POST 项目/资金不校验 is_active。契约"
    "（PLAN §3.2）：停用字典项仍可显示历史值，但不得再用于新增或修改，"
    "违者 400 且不写库。"))
def test_disabled_dict_item_rejected(client):
    """停用 level/funding_source 后，新增项目/资金不得再引用 → 400。"""
    _, ent = _new_enterprise(client, "91320000G2DIC03")
    _, proj = _new_project(client, ent["id"])

    # 停用『省级』后新增 level=省级 的项目必须被拒
    _disable_dict_item(client, "level", "省级")
    status, resp = client.request(
        "POST", "/api/projects",
        {"name": "引用停用层级项目", "enterprise_id": ent["id"], "level": "省级",
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
    """对照基线（绿）：企业不存在时项目不得写入（SQLite 外键兜底）。

    当前实现未捕获 IntegrityError（连接重置折叠为 599），故只断言「非 2xx +
    不写库」——证明底层约束存在；『必须返回明确 400 与可读错误』见
    test_nonexistent_enterprise_clear_error（xfail）。"""
    before = _count_rows(tmp_db, "project")
    status, resp = client.request(
        "POST", "/api/projects",
        {"name": "孤儿项目", "enterprise_id": 999999})
    assert status >= 400, f"不存在企业的项目竟被接受: status={status} {resp}"
    assert _count_rows(tmp_db, "project") == before, "外键约束未生效，项目被写入"


@pytest.mark.xfail(strict=True, reason=(
    "企业不存在时错误不明确：sqlite3.IntegrityError 未捕获 → 连接重置 → 599/"
    "connection failed。契约（PLAN G2 目标 5）：企业不存在必须返回明确 400 "
    "与可读错误信息，绝不允许连接重置或静默行为。"))
def test_nonexistent_enterprise_clear_error(client):
    """企业不存在 → 明确 400 + 可读 error（当前 599/connection failed）。"""
    status, resp = client.request(
        "POST", "/api/projects",
        {"name": "孤儿项目", "enterprise_id": 999999})
    assert status == 400, f"应返回明确 400，实际 {status}：{resp}"
    assert resp.get("error") not in (None, "connection failed"), (
        f"错误信息不可读: {resp}")


@pytest.mark.xfail(strict=True, reason=(
    "企业停用/软删除未实现：enterprise 表尚无停用标记列（is_active/deleted_at），"
    "『停用企业不得承接新项目』的契约无法表达与验证（PLAN §3.2『存在且未删除的"
    "承担企业』；软删除属 G3 范围）。实现后本测试应验证：停用企业承接新项目被拒。"))
def test_disabled_enterprise_rejected(tmp_db, client):
    """停用企业不得承接新项目（当前无停用机制 → 预期失败）。"""
    conn = db_conn(tmp_db)
    try:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(enterprise)")}
    finally:
        conn.close()
    if not ({"is_active", "status", "deleted_at"} & cols):
        pytest.fail(
            "enterprise 表缺少停用/软删除标记列（is_active/status/deleted_at），"
            "企业停用语义尚未实现，测试无法继续。")

    _, ent = _new_enterprise(client, "91320000G2OFF01")
    conn = db_conn(tmp_db)
    try:
        conn.execute("UPDATE enterprise SET is_active=0 WHERE id=?", (ent["id"],))
        conn.commit()
    finally:
        conn.close()
    status, resp = client.request(
        "POST", "/api/projects",
        {"name": "停用企业项目", "enterprise_id": ent["id"], "level": "省级",
         "category": "科技成果转化", "total_amount": 100,
         "start_date": "2024-01-01", "end_date": "2024-12-31", "stage": "已立项"})
    assert status in (400, 403, 409), f"停用企业承接新项目被接受: status={status} {resp}"


@pytest.mark.xfail(strict=True, reason=(
    "数据库层约束未实施：schema.sql 目前没有金额、日期、字典或状态机 CHECK/"
    "触发器，直接 SQLite INSERT 可绕过 API 校验。契约（PLAN G2 工作项 4/"
    "验收）：数据库约束必须保护直接 SQL/迁移路径，非法值必须抛 IntegrityError，"
    "并且不得留下任何记录。"))
def test_direct_sqlite_invalid_writes_are_rejected(tmp_db, client):
    """直接 SQLite 路径也不可绕过核心不变量（只连接 pytest 临时库）。

    这不是 API 的替身测试：显式以 db_conn(tmp_db) 对临时数据库执行 INSERT，
    验证未来的 CHECK/触发器会在数据库边界拒绝负金额、假日期、非法字典和
    非法阶段。每次尝试都回滚，既使当前基线缺少约束而写入成功，也不会污染
    后续断言；正式 data/project.db 从未打开。
    """
    _, ent = _new_enterprise(client, "91320000G2SQL01", "直写约束企业")
    _, proj = _new_project(client, ent["id"], name="直写约束项目", project_no="P-G2-SQL")
    conn = db_conn(tmp_db)
    try:
        before_funding = conn.execute("SELECT COUNT(*) FROM funding").fetchone()[0]
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO funding (project_id, source_type, amount, plan_date, status) "
                "VALUES (?, ?, ?, ?, ?)",
                (proj["id"], "乱写来源", -1, "2024-02-30", "随便写"),
            )
        conn.rollback()
        assert conn.execute("SELECT COUNT(*) FROM funding").fetchone()[0] == before_funding

        before_project = conn.execute("SELECT COUNT(*) FROM project").fetchone()[0]
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO project (name, project_no, enterprise_id, level, category, "
                "start_date, end_date, stage) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("直写非法状态", "P-G2-SQL-BAD", ent["id"], "省级", "科技成果转化",
                 "2024-12-31", "2024-01-01", "随便写的阶段"),
            )
        conn.rollback()
        assert conn.execute("SELECT COUNT(*) FROM project").fetchone()[0] == before_project
    finally:
        conn.close()


# ===========================================================================
# 5. 同一临时样本：API / UI 数据端点 / MCP 三口径逐项相同（任务 5）
#   UI 数据端点即前端页面实际调用的 HTTP 端点（/api/projects 列表、
#   /api/dashboard 工作台、/api/projects/{id} 详情）；MCP 层 monkeypatch
#   mcp_server.DB_PATH → tmp_db（安全注入，绝不触碰正式库）。
# ===========================================================================
@pytest.mark.xfail(strict=True, reason=(
    "跨层口径未统一：app.py 与 mcp_server.py 各自复制 SQL（mcp_server.list_projects "
    "的 funded_total 无状态过滤），且均无 planned_total/disbursed_total/received_total "
    "字段（P0-01 同类问题）。契约（PLAN §3.4/G2 验收）：同一临时样本下，API 详情、"
    "UI 列表/工作台端点、MCP 查询层返回的 three 个口径必须逐项相同且等于 PLAN §3.1 "
    "期望值。"))
def test_money_totals_consistent_across_api_ui_mcp(tmp_db, client, monkeypatch):
    """同一份样本：API 详情/列表/工作台 与 MCP list_projects/get_project 逐项一致。"""
    import mcp_server

    # MCP 默认从模块级 DB_PATH（正式库）取数 —— 显式重定向到 tmp_db，安全注入
    monkeypatch.setattr(mcp_server, "DB_PATH", str(tmp_db))

    pid, expected = _seed_money_sample(client)

    # —— 逐层取数（UI 数据端点即前端页面调用的 HTTP 端点）——
    _, detail = client.request("GET", f"/api/projects/{pid}")     # API/UI 项目详情
    _, listing = client.request("GET", "/api/projects")           # UI 项目列表端点
    _, dash = client.request("GET", "/api/dashboard")             # UI 工作台端点
    mcp_list = mcp_server.list_projects()                         # MCP 列表查询
    mcp_detail = mcp_server.get_project(pid)                      # MCP 详情查询

    layers = {
        "API/UI 项目详情 /api/projects/{id}": detail,
        "UI 列表端点 /api/projects": listing[0],
        "UI 工作台端点 /api/dashboard": dash,
        "MCP list_projects()": mcp_list[0],
        "MCP get_project()": mcp_detail,
    }

    # —— 各层与期望值逐项比对（当前字段缺失 → KeyError → 预期失败）——
    for name, layer in layers.items():
        for key, want in expected.items():
            got = layer[key]
            assert got == want, f"{name} 的 {key} 应等于 {want}，实际 {got}"

    # —— 层间交叉比对：三口径在所有层必须完全一致 ——
    for key in expected:
        values = {layer[key] for layer in layers.values()}
        assert len(values) == 1, f"{key} 在各层取值不一致: {values}"

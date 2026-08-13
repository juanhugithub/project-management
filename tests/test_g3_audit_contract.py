# -*- coding: utf-8 -*-
"""G3 契约测试：归档、软删除与审计（测试先行）。

权威来源：PLAN.md §3.3、§5 G3，以及 docs/migrations/迁移清单.md 的
M003/M004 已确认设计。本文件只使用 conftest 提供的临时数据库；全部断言
均为 strict xfail，待 G3 业务实现完成后应移除 xfail 并转为普通回归测试。

刻意不覆盖尚未进入 G3 的 Excel 导入和备份恢复，也不引入操作者角色、撤销
授权、多用户权限等尚未确认的规则。
"""

import pytest

from conftest import db_conn


_seq = {"n": 0}


def _new_enterprise(client):
    """构造一个满足 G2 字典/关联约束的承担企业，始终在临时库中创建。"""
    _seq["n"] += 1
    status, enterprise = client.request(
        "POST",
        "/api/enterprises",
        {
            "name": f"G3测试企业-{_seq['n']}",
            "credit_code": f"91320000G3{_seq['n']:06d}",
            "enterprise_type": "高新技术企业",
            "district": "开发区",
        },
    )
    assert status == 200, f"创建测试企业失败: status={status}, body={enterprise}"
    return enterprise


def _new_project(client, enterprise_id, *, start_date="2024-01-01"):
    """构造一个可同时挂接资金、节点并可按开始年度归档的合法项目。"""
    _seq["n"] += 1
    status, project = client.request(
        "POST",
        "/api/projects",
        {
            "name": f"G3测试项目-{_seq['n']}",
            "project_no": f"G3-P-{_seq['n']:04d}",
            "enterprise_id": enterprise_id,
            "level": "省级",
            "category": "科技成果转化",
            "total_amount": 100,
            "start_date": start_date,
            "end_date": "2024-12-31",
            "stage": "已立项",
        },
    )
    assert status == 200, f"创建测试项目失败: status={status}, body={project}"
    return project


def _new_child(client, resource, project_id):
    """创建一条资金或节点记录，返回其 API 响应对象。"""
    payload = {"project_id": project_id}
    if resource == "fundings":
        payload.update({"source_type": "上级拨付", "amount": 10, "status": "未拨付"})
    else:
        payload.update({"node_type": "申报", "plan_date": "2024-03-01", "status": "待办"})
    status, row = client.request("POST", f"/api/{resource}", payload)
    assert status == 200, f"创建测试{resource}失败: status={status}, body={row}"
    return row


def _audit_rows(tmp_db, sql, params=()):
    """只读临时库的审计记录；缺表本身即表示 G3 契约尚未实现。"""
    conn = db_conn(tmp_db)
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


@pytest.mark.xfail(strict=True, reason=(
    "G3 尚未将年度归档集中到 services 写入口：当前项目 POST 未检查归档年度。"
    "契约（PLAN §3.3/§5 G3）：归档年度必须同时拒绝项目、资金、节点的创建、"
    "修改、删除；已实现的局部 PUT/DELETE 拦截不能替代完整覆盖。"
))
def test_archived_year_blocks_project_funding_and_node_all_mutations(client):
    """归档 2024 后，三类对象的 POST/PUT/DELETE 必须全部返回 403。"""
    enterprise = _new_enterprise(client)
    project = _new_project(client, enterprise["id"])
    funding = _new_child(client, "fundings", project["id"])
    node = _new_child(client, "nodes", project["id"])

    status, body = client.request("PUT", "/api/config", {"archived_years": ["2024"]})
    assert status == 200, f"设置归档年度失败: status={status}, body={body}"

    attempts = [
        ("项目创建", "POST", "/api/projects", {
            "name": "归档年项目", "project_no": "G3-ARCHIVE-POST",
            "enterprise_id": enterprise["id"], "start_date": "2024-06-01"}),
        ("项目修改", "PUT", f"/api/projects/{project['id']}", {"name": "不得修改"}),
        ("项目删除", "DELETE", f"/api/projects/{project['id']}", None),
        ("资金创建", "POST", "/api/fundings", {
            "project_id": project["id"], "source_type": "上级拨付", "amount": 1, "status": "未拨付"}),
        ("资金修改", "PUT", f"/api/fundings/{funding['id']}", {"amount": 11}),
        ("资金删除", "DELETE", f"/api/fundings/{funding['id']}", None),
        ("节点创建", "POST", "/api/nodes", {
            "project_id": project["id"], "node_type": "立项", "status": "待办"}),
        ("节点修改", "PUT", f"/api/nodes/{node['id']}", {"status": "已完成"}),
        ("节点删除", "DELETE", f"/api/nodes/{node['id']}", None),
    ]
    for label, method, path, payload in attempts:
        actual, response = client.request(method, path, payload)
        assert actual == 403, f"{label}未被归档规则拒绝: status={actual}, body={response}"


@pytest.mark.xfail(strict=True, reason=(
    "G3 尚未实施 M003：当前 DELETE 物理删除 project，默认 API/MCP 也没有过滤 "
    "is_deleted。契约（PLAN §3.3/迁移清单 M003）：删除必须保留记录并设置 "
    "is_deleted/deleted_at，默认 API 和 MCP 查询均不可返回该记录。"
))
def test_soft_deleted_project_is_retained_but_hidden_from_api_and_mcp(tmp_db, client, monkeypatch):
    """项目删除必须软删除；HTTP 和 MCP 的默认列表、详情均不得泄漏它。"""
    import mcp_server

    monkeypatch.setattr(mcp_server, "DB_PATH", str(tmp_db))
    monkeypatch.setattr(mcp_server, "BASE_DIR", str(tmp_db.parent))
    enterprise = _new_enterprise(client)
    project = _new_project(client, enterprise["id"])

    status, body = client.request("DELETE", f"/api/projects/{project['id']}")
    assert status == 200, f"删除测试项目失败: status={status}, body={body}"

    # M003 冻结字段证明这是软删除而非“列表层隐藏的硬删除”。
    row = _audit_rows(
        tmp_db, "SELECT id, is_deleted, deleted_at FROM project WHERE id=?", (project["id"],)
    )
    assert len(row) == 1, "删除后项目物理消失；G3 要求软删除并保留恢复依据"
    assert row[0]["is_deleted"] == 1 and row[0]["deleted_at"], "项目未标记为软删除"

    api_status, api_list = client.request("GET", "/api/projects")
    assert api_status == 200
    assert project["id"] not in {item["id"] for item in api_list}, "默认 API 列表泄漏已删除项目"
    detail_status, _ = client.request("GET", f"/api/projects/{project['id']}")
    assert detail_status == 404, "默认 API 详情仍可读取已删除项目"

    assert project["id"] not in {item["id"] for item in mcp_server.list_projects()}, "MCP 列表泄漏已删除项目"
    assert mcp_server.get_project(project["id"]).get("error"), "MCP 详情仍可读取已删除项目"


@pytest.mark.xfail(strict=True, reason=(
    "G3 尚未实施 M004 audit_log。契约（PLAN §5 G3/迁移清单 M004）：创建、"
    "修改、软删除、归档、解除归档均须留下带对象、动作、时间、操作者和前后摘要的"
    "可读审计记录；解除归档还必须保留理由。"
))
def test_high_risk_operations_write_complete_audit_records(tmp_db, client):
    """五类 G3 高风险操作必须逐项留下完整、可读的审计证据。"""
    enterprise = _new_enterprise(client)
    project = _new_project(client, enterprise["id"])
    project_id = project["id"]

    status, body = client.request("PUT", f"/api/projects/{project_id}", {"name": "已修改项目"})
    assert status == 200, f"修改测试项目失败: status={status}, body={body}"
    status, body = client.request("DELETE", f"/api/projects/{project_id}")
    assert status == 200, f"软删除测试项目失败: status={status}, body={body}"
    status, body = client.request("PUT", "/api/config", {"archived_years": ["2024"]})
    assert status == 200, f"归档失败: status={status}, body={body}"
    status, body = client.request(
        "PUT", "/api/config", {"archived_years": [], "reason": "G3 测试解除归档"}
    )
    assert status == 200, f"解除归档失败: status={status}, body={body}"

    rows = _audit_rows(
        tmp_db,
        "SELECT ts, operator, action, object_type, object_id, before_summary, after_summary, reason "
        "FROM audit_log WHERE (object_type='project' AND object_id=?) "
        "OR action IN ('archive', 'unarchive')",
        (project_id,),
    )
    actions = [row["action"] for row in rows]
    for action in ("create", "update", "delete", "archive", "unarchive"):
        assert actions.count(action) == 1, f"高风险操作 {action} 应恰有一条审计记录: {actions}"
    for row in rows:
        assert row["ts"] and row["operator"] and row["object_type"], f"审计记录不可读: {dict(row)}"
    project_actions = [row for row in rows if row["object_type"] == "project"]
    assert all(row["before_summary"] or row["after_summary"] for row in project_actions), "项目审计缺少前后摘要"
    unarchive = next(row for row in rows if row["action"] == "unarchive")
    assert unarchive["reason"] == "G3 测试解除归档", "解除归档审计未保存理由"


@pytest.mark.xfail(strict=True, reason=(
    "G3 尚未提供受约束的恢复路径。契约（PLAN §3.3/§5 G3、迁移清单 M003）："
    "恢复软删除资金时，归档年度必须先拒绝；解除归档后若所属项目仍被删除，"
    "引用完整性仍必须拒绝恢复，且记录保持删除状态。"
))
def test_restore_rejects_archived_year_and_deleted_parent(tmp_db, client):
    """恢复必须同时受归档规则和有效父项目引用约束，不能复活孤儿资金。"""
    enterprise = _new_enterprise(client)
    project = _new_project(client, enterprise["id"])
    funding = _new_child(client, "fundings", project["id"])

    status, _ = client.request("DELETE", f"/api/fundings/{funding['id']}")
    assert status == 200, "构造已删除资金失败"
    status, _ = client.request("PUT", "/api/config", {"archived_years": ["2024"]})
    assert status == 200, "构造归档年度失败"
    status, body = client.request("POST", f"/api/fundings/{funding['id']}/restore", {"reason": "测试恢复"})
    assert status == 403, f"归档年度仍允许恢复资金: status={status}, body={body}"

    status, _ = client.request("PUT", "/api/config", {"archived_years": [], "reason": "测试解除归档"})
    assert status == 200, "解除归档失败"
    status, _ = client.request("DELETE", f"/api/projects/{project['id']}")
    assert status == 200, "构造已删除父项目失败"
    status, body = client.request("POST", f"/api/fundings/{funding['id']}/restore", {"reason": "测试恢复"})
    assert status == 409, f"父项目已删除仍允许恢复资金: status={status}, body={body}"

    row = _audit_rows(tmp_db, "SELECT is_deleted FROM funding WHERE id=?", (funding["id"],))
    assert len(row) == 1 and row[0]["is_deleted"] == 1, "被拒绝恢复后资金删除状态被改变"

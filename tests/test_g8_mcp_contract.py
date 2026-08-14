# -*- coding: utf-8 -*-
"""G8 MCP 版本化业务契约验收。

高阶工具的目标是向 Agent 提供可直接复核的业务事实，而不是暴露 SQLite 表。所有
测试只建立临时库，且同时检查软删除、年度归档和金额口径不会从新工具中泄露或漂移。
"""

import sqlite3

import mcp_server


EXPECTED_G8_TOOLS = {
    "get_project_fact_sheet",
    "list_acceptance_risks",
    "get_funding_execution_dataset",
    "list_projects_missing_identity",
    "list_composite_risks",
}
HISTORICAL_TOOLS = {
    "list_projects", "get_project", "list_enterprises", "get_enterprise",
    "list_fundings", "list_nodes", "get_reminders", "get_stats",
    "get_funding_check", "search",
}


def _seed(tmp_db, monkeypatch):
    """构造一个可见风险项目及归档/软删除对照项目。"""
    monkeypatch.setattr(mcp_server, "DB_PATH", str(tmp_db))
    conn = sqlite3.connect(tmp_db)
    try:
        conn.executemany(
            "INSERT INTO enterprise(name,credit_code,district) VALUES(?,?,?)",
            [("可见企业", "91320000G800000001", "开发区"),
             ("归档企业", "91320000G800000002", "高新区"),
             ("删除企业", "91320000G800000003", "花桥")],
        )
        conn.execute("INSERT INTO project(name,project_no,enterprise_id,total_amount,start_date,stage) VALUES('可见风险项目','G8-OPEN',1,100,'2025-01-01','待验收')")
        conn.execute("INSERT INTO project(name,project_no,identity_status,enterprise_id,total_amount,start_date,stage) VALUES('编号待补项目',NULL,'人工编号待补',1,50,'2025-01-01','实施中')")
        conn.execute("INSERT INTO project(name,project_no,enterprise_id,total_amount,start_date,stage) VALUES('归档项目','G8-ARCHIVE',2,200,'2024-01-01','待验收')")
        conn.execute("INSERT INTO project(name,project_no,enterprise_id,total_amount,start_date,stage,is_deleted) VALUES('删除项目','G8-DELETED',3,300,'2025-01-01','待验收',1)")
        conn.executemany(
            "INSERT INTO funding(project_id,source_type,amount,plan_date,actual_date,status) VALUES(?,?,?,?,?,?)",
            [(1, "上级拨付", 10, "2025-01-01", None, "未拨付"),
             (1, "本级配套", 20, "2025-01-02", "2025-01-03", "已拨付"),
             (1, "本级自付", 30, None, "2025-01-04", "已到账"),
             (3, "上级拨付", 200, "2024-01-01", "2024-01-02", "已到账")],
        )
        conn.execute("INSERT INTO node(project_id,node_type,plan_date,status) VALUES(1,'验收','2999-01-01','待办')")
        conn.execute("INSERT INTO node(project_id,node_type,plan_date,status) VALUES(3,'验收','2999-01-01','待办')")
        conn.execute("UPDATE system_config SET value='2024' WHERE key='archived_years'")
        conn.commit()
    finally:
        conn.close()


def _assert_envelope(result):
    """所有业务数据集必须带齐可追溯公共字段。"""
    assert result["contract_version"] == "1.0"
    assert result["generated_at"]
    assert isinstance(result["filters"], dict)
    assert result["data_scope"]["archived_projects"] == "excluded"
    assert result["money_semantics"]["unit"] == "万元"
    assert "data" in result


def test_g8_registers_exact_new_read_only_business_tools(tmp_db, monkeypatch):
    """G8 只增加五个公共业务工具，名称中不得出现写入动作。"""
    _seed(tmp_db, monkeypatch)
    tools = set(mcp_server.mcp._tool_manager._tools)
    assert tools - HISTORICAL_TOOLS == EXPECTED_G8_TOOLS
    assert not {name for name in tools if any(word in name for word in ("create", "update", "delete", "restore", "import"))}


def test_g8_fact_sheet_and_funding_dataset_share_visible_facts_and_money(tmp_db, monkeypatch):
    """项目事实包和资金执行表对同一项目必须给出相同金额、且隐藏归档/删除项目。"""
    _seed(tmp_db, monkeypatch)
    fact = mcp_server.get_project_fact_sheet(1)
    dataset = mcp_server.get_funding_execution_dataset(year="2025", district="开发区")
    _assert_envelope(fact)
    _assert_envelope(dataset)
    project = fact["data"]["project"]
    row = dataset["data"]["items"][0]
    assert project["project_no"] == row["project_no"] == "G8-OPEN"
    assert {key: project[key] for key in ("planned_total", "disbursed_total", "received_total")} == {"planned_total": 30.0, "disbursed_total": 50.0, "received_total": 30.0}
    assert {key: row[key] for key in ("planned_total", "disbursed_total", "received_total")} == {"planned_total": 30.0, "disbursed_total": 50.0, "received_total": 30.0}
    assert [item["project_no"] for item in dataset["data"]["items"]] == ["G8-OPEN", None]
    assert mcp_server.get_project_fact_sheet(3)["data"]["found"] is False


def test_g8_risk_datasets_are_deterministic_and_do_not_leak_archived_data(tmp_db, monkeypatch):
    """验收、编号和复合风险都只包含当前可见项目，并写明触发原因。"""
    _seed(tmp_db, monkeypatch)
    acceptance = mcp_server.list_acceptance_risks(days=365000, district="开发区")
    missing = mcp_server.list_projects_missing_identity(district="开发区")
    composite = mcp_server.list_composite_risks(days=365000, district="开发区")
    for result in (acceptance, missing, composite):
        _assert_envelope(result)
    assert [item["project_no"] for item in acceptance["data"]["items"]] == ["G8-OPEN"]
    assert [item["name"] for item in missing["data"]["items"]] == ["编号待补项目"]
    by_no = {item["project_no"]: item["reasons"] for item in composite["data"]["items"]}
    assert "存在验收或结题临期/逾期节点" in by_no["G8-OPEN"]
    assert "资金合计与项目总金额不一致" in by_no["G8-OPEN"]
    assert "项目编号待补" in by_no[None]
    assert "G8-ARCHIVE" not in by_no

# -*- coding: utf-8 -*-
"""G7 MCP 只读一致性验收。

测试直接调用 MCP 工具函数，但把其数据库路径指向 pytest 临时库，确保验收不触碰
正式台账。这里关注 MCP 的对外事实：只读工具集合、共享资金口径，以及软删除和
年度归档数据不会默认出现在 AI 查询结果中。
"""

import sqlite3

import mcp_server


def _seed(tmp_db, monkeypatch):
    """建立一条可见项目、一条软删除项目和一条归档项目的最小对照数据。"""
    monkeypatch.setattr(mcp_server, "DB_PATH", str(tmp_db))
    conn = sqlite3.connect(tmp_db)
    try:
        conn.execute(
            "INSERT INTO enterprise(name,credit_code,district) VALUES('可见企业','91320000G700000001','开发区')"
        )
        conn.execute(
            "INSERT INTO enterprise(name,credit_code,district) VALUES('已归档企业','91320000G700000002','高新区')"
        )
        conn.execute(
            "INSERT INTO enterprise(name,credit_code,district,is_deleted) VALUES('已删除企业','91320000G700000003','花桥',1)"
        )
        conn.execute(
            "INSERT INTO project(name,project_no,enterprise_id,total_amount,start_date,stage) VALUES('可见项目','G7-OPEN',1,100,'2025-01-01','已立项')"
        )
        conn.execute(
            "INSERT INTO project(name,project_no,enterprise_id,total_amount,start_date,stage) VALUES('归档项目','G7-ARCHIVE',2,200,'2024-01-01','已立项')"
        )
        conn.execute(
            "INSERT INTO project(name,project_no,enterprise_id,total_amount,start_date,stage,is_deleted) VALUES('删除项目','G7-DELETED',3,300,'2025-01-01','已立项',1)"
        )
        conn.executemany(
            "INSERT INTO funding(project_id,source_type,amount,plan_date,actual_date,status) VALUES(?,?,?,?,?,?)",
            [
                (1, '上级拨付', 10, '2025-01-02', None, '未拨付'),
                (1, '本级配套', 20, '2025-01-03', '2025-01-04', '已拨付'),
                (1, '本级自付', 30, None, '2025-01-05', '已到账'),
                (2, '上级拨付', 200, '2024-01-01', '2024-01-02', '已到账'),
            ],
        )
        conn.execute("INSERT INTO node(project_id,node_type,plan_date,status) VALUES(1,'验收','2025-02-01','待办')")
        conn.execute("INSERT INTO node(project_id,node_type,plan_date,status) VALUES(2,'验收','2024-02-01','待办')")
        conn.execute("UPDATE system_config SET value='2024' WHERE key='archived_years'")
        conn.commit()
    finally:
        conn.close()


def test_g7_mcp_registers_read_only_query_tools_only(tmp_db, monkeypatch):
    """工具名称不含业务写动词，避免 AI 侧获得隐式增删改能力。"""
    _seed(tmp_db, monkeypatch)
    tools = set(mcp_server.mcp._tool_manager._tools)
    assert tools == {
        'list_projects', 'get_project', 'list_enterprises', 'get_enterprise',
        'list_fundings', 'list_nodes', 'get_reminders', 'get_stats',
        'get_funding_check', 'search',
    }
    assert not {name for name in tools if any(word in name for word in ('create', 'update', 'delete', 'restore', 'import'))}


def test_g7_project_list_and_detail_use_shared_funding_totals(tmp_db, monkeypatch):
    """列表与详情的计划、已拨、已到账金额必须等于共享查询定义。"""
    _seed(tmp_db, monkeypatch)
    project = mcp_server.list_projects()[0]
    detail = mcp_server.get_project(project['id'])
    expected = {'planned_total': 30.0, 'disbursed_total': 50.0, 'received_total': 30.0}
    assert {key: project[key] for key in expected} == expected
    assert {key: detail[key] for key in expected} == expected
    assert [funding['id'] for funding in detail['fundings']] == [1, 2, 3]


def test_g7_deleted_and_archived_records_are_hidden_from_all_relevant_tools(tmp_db, monkeypatch):
    """AI 默认只看当前可见数据；归档和软删除项目不得从任何关联查询泄露。"""
    _seed(tmp_db, monkeypatch)
    assert [item['project_no'] for item in mcp_server.list_projects()] == ['G7-OPEN']
    assert mcp_server.get_project(2)['error'] == '项目不存在或当前不可见'
    assert [item['project_id'] for item in mcp_server.list_fundings()] == [1, 1, 1]
    assert [item['project_id'] for item in mcp_server.list_nodes()] == [1]
    assert [item['project_no'] for item in mcp_server.search('项目')['projects']] == ['G7-OPEN']
    assert [item['name'] for item in mcp_server.search('企业')['enterprises']] == ['可见企业']
    enterprises = mcp_server.list_enterprises()
    assert [(item['name'], item['project_count'], item['total_amount_sum']) for item in enterprises] == [('可见企业', 1, 100.0)]
    assert [item['key'] for item in mcp_server.get_stats('year')] == ['2025']
    assert [item['id'] for item in mcp_server.get_funding_check()] == [1]


def test_g7_missing_or_hidden_project_returns_readable_error(tmp_db, monkeypatch):
    """无效和不可见项目使用统一可读错误，不向调用方暴露数据库异常。"""
    _seed(tmp_db, monkeypatch)
    assert mcp_server.get_project(999) == {'error': '项目不存在或当前不可见'}
    assert mcp_server.get_enterprise(2) == {'error': '企业不存在或当前不可见'}

# -*- coding: utf-8 -*-
"""G0 基线冒烟测试（必须全部「绿」）

作用：
1. 证明测试基础设施本身可靠：临时库可建、API 可端到端调用、合法数据
   链路完整 —— 这样 test_regressions.py 中的 xfail 才能被信任为
   「真实复现业务缺陷」，而不是「测试写错了」。
2. 提供对照基线：外键约束（不存在 enterprise_id 被拒）证明 SQLite 外键
   在 API 路径确实生效，从而把「未关联企业项目被接受」这类缺陷精确
   定位为业务校验缺失而非约束缺失。
"""

import sqlite3

from conftest import db_conn


def test_tmp_db_has_full_schema(tmp_db):
    """临时库包含全部 6 张表与 31 条种子字典数据。"""
    conn = sqlite3.connect(str(tmp_db))
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"enterprise", "project", "funding", "node",
            "dict_item", "system_config"} <= tables, f"缺表: {tables}"
    n = conn.execute("SELECT COUNT(*) FROM dict_item").fetchone()[0]
    assert n == 31, f"种子字典应为 31 条，实际 {n}"
    conn.close()


def test_api_dict_returns_seed_values(client):
    """GET /api/dict 返回可用的种子字典（证明 HTTP 链路通）。"""
    status, data = client.request("GET", "/api/dict")
    assert status == 200, f"dict 接口异常: {status}"
    assert len(data.get("level", [])) == 4
    assert data.get("funding_source") == ["上级拨付", "本级配套", "本级自付"]


def test_valid_enterprise_project_roundtrip(client):
    """合法企业 + 合法项目：创建、详情查询、字段完整（最小闭环可用）。"""
    status, ent = client.request(
        "POST", "/api/enterprises",
        {"name": "甲公司", "credit_code": "91320000TEST01",
         "enterprise_type": "高新技术企业", "district": "开发区"})
    assert status == 200, f"建企业失败: {status} {ent}"
    eid = ent["id"]

    status, proj = client.request(
        "POST", "/api/projects",
            {"name": "示范项目", "enterprise_id": eid, "level": "省级",
             "category": "科技成果转化", "total_amount": 100,
             "start_date": "2024-01-01", "end_date": "2024-12-31",
             "stage": "已立项", "identity_status": "人工编号待补"})
    assert status == 200, f"建项目失败: {status} {proj}"
    pid = proj["id"]
    assert proj["total_amount"] == 100

    status, detail = client.request("GET", f"/api/projects/{pid}")
    assert status == 200
    assert detail["enterprise"]["name"] == "甲公司"
    assert detail["stage"] == "已立项"


def test_foreign_key_rejects_nonexistent_enterprise(client):
    """对照基线：SQLite 外键在 API 路径生效。

    给一个不存在的 enterprise_id（999999），外键约束应拒绝写入。
    当前实现未捕获 sqlite3.IntegrityError（连接被重置 → 折叠为 599），
    因此断言「非 2xx」即视为约束生效。
    该对照证明：系统不是完全没有约束，而是缺『enterprise_id 为空的
    项目必须拒绝』这类业务校验（见 test_regressions.py 中 P0-02 用例）。
    """
    status, _ = client.request(
        "POST", "/api/projects", {"name": "孤儿项目", "enterprise_id": 999999})
    assert status >= 400, f"不存在的外键企业竟被接受: status={status}"

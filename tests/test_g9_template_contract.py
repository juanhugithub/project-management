# -*- coding: utf-8 -*-
"""G9 模板任务和衍生稿契约：每项断言都只使用临时 SQLite 数据库。"""
import json
import sqlite3

import pytest

from conftest import db_conn


def _sample(client):
    """构造同时覆盖资金季度口径和验收风险的最小可复算事实样本。"""
    status, enterprise = client.request("POST", "/api/enterprises", {
        "name": "G9模板企业", "credit_code": "91320000G900000001",
        "enterprise_type": "高新技术企业", "district": "开发区",
    })
    assert status == 200
    status, project = client.request("POST", "/api/projects", {
        "name": "G9模板项目", "project_no": "G9-001", "enterprise_id": enterprise["id"],
        "level": "省级", "category": "科技成果转化", "total_amount": 100,
        "start_date": "2025-01-01", "end_date": "2025-12-31", "stage": "待验收",
    })
    assert status == 200
    for funding in (
        {"amount": 60, "source_type": "上级拨付", "status": "已到账", "plan_date": "2025-02-01", "actual_date": "2025-03-01"},
        {"amount": 40, "source_type": "本级配套", "status": "未拨付", "plan_date": "2025-04-01"},
    ):
        status, _ = client.request("POST", "/api/fundings", {"project_id": project["id"], **funding})
        assert status == 200
    status, _ = client.request("POST", "/api/nodes", {
        "project_id": project["id"], "node_type": "验收", "status": "待办", "plan_date": "2025-06-15",
    })
    assert status == 200
    return project["id"]


def test_g9_explicit_migration_accepts_fresh_schema(tmp_path):
    """全新 schema 已包含 G9 表时，显式迁移仍需记录 005 而不重复失败。"""
    from migrations import apply
    from pathlib import Path

    conn = sqlite3.connect(tmp_path / "fresh-g9.db")
    try:
        conn.executescript(Path(__file__).resolve().parents[1].joinpath("schema.sql").read_text(encoding="utf-8"))
        apply(conn)
        assert conn.execute("SELECT version FROM schema_migration WHERE version='005_g9_templates.sql'").fetchone()
        assert conn.execute("SELECT name FROM sqlite_master WHERE name='derivative_draft'").fetchone()
    finally:
        conn.close()


def test_template_directory_exposes_two_versioned_contracts():
    """模板发现和字段模式来自明确的版本化文件，不能由数据库列名临时推断。"""
    from ledger.templates import get_template_schema, list_reporting_templates

    templates = list_reporting_templates()
    assert {(item["template_id"], item["version"]) for item in templates} == {
        ("quarterly_funding_execution", "1.0.0"), ("acceptance_risk_list", "1.0.0")
    }
    schema = get_template_schema("quarterly_funding_execution", "1.0.0")
    assert [item["name"] for item in schema["columns"]][:4] == ["project_no", "project_name", "enterprise_name", "district"]


def test_quarterly_dataset_is_deterministic_and_uses_fixed_money_semantics(tmp_db, client):
    """相同事实与参数必须返回同一行、同一快照哈希及截至季度末的三资金口径。"""
    from ledger.templates import build_template_dataset

    _sample(client)
    conn = db_conn(tmp_db)
    try:
        first = build_template_dataset(conn, "quarterly_funding_execution", {"year": 2025, "quarter": 1, "district": "开发区"})
        second = build_template_dataset(conn, "quarterly_funding_execution", {"district": "开发区", "quarter": 1, "year": 2025})
    finally:
        conn.close()
    assert first == second
    assert first["money_unit"] == "万元"
    assert first["rows"] == [{
        "project_id": 1, "project_no": "G9-001", "project_name": "G9模板项目", "enterprise_name": "G9模板企业",
        "district": "开发区", "total_amount": 100.0, "planned_total": 60.0, "disbursed_total": 60.0, "received_total": 60.0,
    }]


def test_acceptance_risk_dataset_is_traceable_to_project_and_explicit_date(tmp_db, client):
    """风险原因只来自阶段或验收节点日期，且结果带回可追溯项目标识。"""
    from ledger.templates import build_template_dataset

    project_id = _sample(client)
    conn = db_conn(tmp_db)
    try:
        dataset = build_template_dataset(conn, "acceptance_risk_list", {"reference_date": "2025-06-01", "days": 30})
    finally:
        conn.close()
    assert dataset["source_project_ids"] == [project_id]
    assert dataset["rows"][0]["risk_reason"] == "验收节点临期"
    assert dataset["rows"][0]["acceptance_plan_date"] == "2025-06-15"


def test_filled_template_validation_rejects_unknown_and_missing_required_fields():
    """填表校验不做猜测补齐：未知列和缺少必填事实都必须返回精确错误。"""
    from ledger.templates import validate_filled_template

    result = validate_filled_template("quarterly_funding_execution", [{"project_name": "缺少编号", "extra": "不得存在"}])
    assert not result["valid"]
    assert {item["field"] for item in result["errors"]} >= {"project_no", "extra"}


def test_derivative_draft_persists_full_provenance_without_changing_project_facts(tmp_db, client):
    """衍生稿登记必须完整保存版本、参数、快照、来源项目、模型、状态及导出位置。"""
    from ledger.templates import build_template_dataset, register_derivative_draft

    project_id = _sample(client)
    conn = db_conn(tmp_db)
    try:
        dataset = build_template_dataset(conn, "quarterly_funding_execution", {"year": 2025, "quarter": 2})
        draft = register_derivative_draft(conn, dataset, "agent-x/model-y", "已确认", r"exports\\g9.xlsx", "季度报表初稿")
        stored = conn.execute("SELECT * FROM derivative_draft WHERE id=?", (draft["id"],)).fetchone()
        project = conn.execute("SELECT name FROM project WHERE id=?", (project_id,)).fetchone()
    finally:
        conn.close()
    assert stored["template_id"] == "quarterly_funding_execution"
    assert stored["template_version"] == "1.0.0"
    assert json.loads(stored["mcp_parameters_json"]) == {"quarter": 2, "year": 2025}
    assert stored["dataset_snapshot_hash"] == dataset["snapshot_hash"]
    assert json.loads(stored["source_project_ids_json"]) == [project_id]
    assert stored["agent_model"] == "agent-x/model-y" and stored["human_status"] == "已确认"
    assert stored["export_path"] == r"exports\\g9.xlsx" and stored["confirmed_at"]
    assert project["name"] == "G9模板项目", "登记衍生稿不应改变正式项目事实"


def test_template_parameter_errors_are_explicit(tmp_db):
    """未提供确定性时间参数或非法季度时，系统必须拒绝而非用当前日期兜底。"""
    from ledger.templates import TemplateError, build_template_dataset

    conn = db_conn(tmp_db)
    try:
        with pytest.raises(TemplateError, match="year"):
            build_template_dataset(conn, "quarterly_funding_execution", {"quarter": 1})
        with pytest.raises(TemplateError, match="quarter"):
            build_template_dataset(conn, "quarterly_funding_execution", {"year": 2025, "quarter": 5})
        with pytest.raises(TemplateError, match="reference_date"):
            build_template_dataset(conn, "acceptance_risk_list", {"days": 30})
    finally:
        conn.close()

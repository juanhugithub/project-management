# -*- coding: utf-8 -*-
"""G4 可控 Excel 导入契约测试（测试先行）。

权威来源：PLAN.md §3.4、§5 G4，及 ADR-0001 决策二和迁移清单 M005。
本文件故意只面向尚待实现的 ``imports.controlled.ImportWorkflow`` 公共边界：

    parse_and_stage(file_name, file_bytes, rows, field_map_version) -> batch
    preview(batch_id) -> {"rows": [...], "summary": {...}}
    confirm(batch_id) -> {"status": "committed", ...}

``rows`` 是解析器产出的标准化行，令本契约聚焦 G4 的状态机和事务边界，而非
Excel 库本身。每个测试均为 strict xfail；G4 实现完成后应先移除 xfail，再以
同一临时库验证真实实现。不得把这些测试改接到旧的逐行直接写库函数。
"""

import hashlib
import json

import pytest

from conftest import db_conn


def _workflow(tmp_db, tmp_path):
    """取得 G4 工作流；模块不存在本身即说明 G4 契约尚未落地。"""
    from imports.controlled import ImportWorkflow

    return ImportWorkflow(database_path=str(tmp_db), archive_dir=tmp_path / "imports")


def _row(*, name="G4项目", credit_code="91320000G400000001", project_no="G4-001"):
    """构造已标准化的有效导入行；身份字段均显式提供，避免名称推断。"""
    return {
        "enterprise_name": "G4测试企业",
        "credit_code": credit_code,
        "enterprise_type": "高新技术企业",
        "district": "开发区",
        "project_name": name,
        "project_no": project_no,
        "level": "省级",
        "category": "科技成果转化",
        "total_amount": 100,
        "start_date": "2024-01-01",
        "end_date": "2024-12-31",
        "stage": "已立项",
    }


def _counts(tmp_db):
    """只读临时库，检查确认前/失败后没有正式写入。"""
    conn = db_conn(tmp_db)
    try:
        return {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("enterprise", "project")
        }
    finally:
        conn.close()


def test_parse_and_stage_produces_deterministic_preview_without_formal_writes(tmp_db, tmp_path):
    """解析后的每行先进入暂存，确认前不得创建企业或项目。"""
    workflow = _workflow(tmp_db, tmp_path)
    before = _counts(tmp_db)
    source = b"G4 controlled import fixture"
    batch = workflow.parse_and_stage("g4.xlsx", source, [_row()], "g4-v1")

    preview = workflow.preview(batch["id"])
    assert preview["rows"] == [{"row_no": 1, "conclusion": "new_enterprise,new_project", "error": None}]
    assert preview["summary"] == {"new_enterprise": 1, "new_project": 1, "blocking": 0}
    assert _counts(tmp_db) == before, "暂存预览阶段向 enterprise/project 正式表写入"


def test_blocking_row_cannot_be_confirmed_and_leaves_zero_formal_writes(tmp_db, tmp_path):
    """存在字段错误、缺失身份或归档冲突时，确认请求必须被拒绝。"""
    workflow = _workflow(tmp_db, tmp_path)
    before = _counts(tmp_db)
    batch = workflow.parse_and_stage(
        "bad.xlsx", b"one invalid row", [_row(project_no=None)], "g4-v1"
    )
    preview = workflow.preview(batch["id"])
    assert preview["rows"][0]["conclusion"] == "missing_identity"
    with pytest.raises(workflow.ConfirmationBlocked):
        workflow.confirm(batch["id"])
    assert _counts(tmp_db) == before, "有阻断行仍在确认提交前写入正式表"


def test_empty_project_batch_is_rejected_before_staging(tmp_db, tmp_path):
    """没有有效数据行时不得创建可被误认为成功的空导入批次。"""
    from ledger.errors import DomainError

    workflow = _workflow(tmp_db, tmp_path)
    with pytest.raises(DomainError, match="没有可导入的数据行"):
        workflow.parse_and_stage("empty.xlsx", b"empty workbook", [], "excel-v1")

    conn = db_conn(tmp_db)
    try:
        assert conn.execute("SELECT COUNT(*) FROM import_batch").fetchone()[0] == 0
    finally:
        conn.close()


def test_enterprise_identity_is_credit_code_never_automatic_name_merge(tmp_db, tmp_path):
    """同名不同码不可自动合并；缺码同名行只能待 HUMAN 显式处置。"""
    workflow = _workflow(tmp_db, tmp_path)
    batch = workflow.parse_and_stage(
        "identity.xlsx", b"identity", [_row(credit_code="91320000G400000011"),
                                           _row(name="另一项目", credit_code="91320000G400000012"),
                                           _row(name="缺码项目", credit_code=None)], "g4-v1")
    rows = workflow.preview(batch["id"])["rows"]
    assert [row["conclusion"] for row in rows] == [
        "new_enterprise,new_project", "new_enterprise,new_project", "missing_identity"
    ]
    assert _counts(tmp_db) == {"enterprise": 0, "project": 0}


def test_duplicate_key_detected_and_missing_project_number_never_auto_posted(tmp_db, tmp_path):
    """同一业务键为重复；无项目编号仅暂存为 missing_identity，不能自动入账。"""
    workflow = _workflow(tmp_db, tmp_path)
    repeated = workflow.parse_and_stage("repeated.xlsx", b"repeated", [_row(), _row()], "g4-v1")
    repeated_rows = workflow.preview(repeated["id"])["rows"]
    assert [row["conclusion"] for row in repeated_rows] == ["new_enterprise,new_project", "duplicate"]
    assert repeated_rows[1]["error"] == "项目编号/文号与承担企业组合在文件内重复"

    first = workflow.parse_and_stage("first.xlsx", b"first", [_row()], "g4-v1")
    workflow.confirm(first["id"])
    duplicate = workflow.parse_and_stage("again.xlsx", b"again", [_row()], "g4-v1")
    no_number = workflow.parse_and_stage("blank.xlsx", b"blank", [_row(project_no=None)], "g4-v1")
    assert workflow.preview(duplicate["id"])["rows"][0]["conclusion"] == "duplicate"
    assert workflow.preview(no_number["id"])["rows"][0]["conclusion"] == "missing_identity"
    assert _counts(tmp_db)["project"] == 1


def test_confirm_failure_rolls_back_entire_batch_without_orphan_enterprise(tmp_db, tmp_path):
    """项目插入故障发生在企业插入之后时，整个批次必须回滚。"""
    workflow = _workflow(tmp_db, tmp_path)
    batch = workflow.parse_and_stage("rollback.xlsx", b"rollback", [_row()], "g4-v1")
    conn = db_conn(tmp_db)
    try:
        conn.execute("CREATE TRIGGER reject_g4_project BEFORE INSERT ON project "
                     "BEGIN SELECT RAISE(ABORT, 'forced G4 project failure'); END")
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(Exception, match="forced G4 project failure"):
        workflow.confirm(batch["id"])
    assert _counts(tmp_db) == {"enterprise": 0, "project": 0}, "提交失败遗留企业或半条项目"


def test_confirm_preserves_all_supported_template_fields(tmp_db, tmp_path):
    """确认入库必须完整保留模板中的企业联系信息和项目扩展字段。"""
    workflow = _workflow(tmp_db, tmp_path)
    row = _row()
    row.update({
        "qualifications": "高新资质",
        "enterprise_contact_person": "张三",
        "enterprise_contact_phone": "0512-12345678",
        "enterprise_address": "测试路1号",
        "match_ratio": 1,
        "leader": "李四",
        "project_contact_phone": "13800000000",
        "project_note": "完整字段",
    })
    batch = workflow.parse_and_stage("full.xlsx", b"full fields", [row], "excel-v1")
    workflow.confirm(batch["id"])

    conn = db_conn(tmp_db)
    try:
        enterprise = conn.execute(
            "SELECT qualifications,contact_person,contact_phone,address FROM enterprise WHERE credit_code=?",
            (row["credit_code"],),
        ).fetchone()
        project = conn.execute(
            "SELECT match_ratio,leader,contact_phone,note FROM project WHERE project_no=?",
            (row["project_no"],),
        ).fetchone()
    finally:
        conn.close()
    assert tuple(enterprise) == ("高新资质", "张三", "0512-12345678", "测试路1号")
    assert tuple(project) == (1.0, "李四", "13800000000", "完整字段")


def test_import_batch_persists_sha_metadata_staging_and_commit_audit(tmp_db, tmp_path):
    """批次必须保存文件 SHA、映射版本、暂存行及带 source_batch 的确认审计。"""
    workflow = _workflow(tmp_db, tmp_path)
    source = b"immutable G4 source bytes"
    batch = workflow.parse_and_stage("source.xlsx", source, [_row()], "g4-v1")
    workflow.confirm(batch["id"])
    conn = db_conn(tmp_db)
    try:
        stored = conn.execute(
            "SELECT file_sha256, file_name, field_map_version, status FROM import_batch WHERE id=?",
            (batch["id"],),
        ).fetchone()
        staged = conn.execute("SELECT row_no, raw_json FROM import_staging WHERE batch_id=?", (batch["id"],)).fetchall()
        audit = conn.execute(
            "SELECT action, source_batch FROM audit_log WHERE source_batch=?", (str(batch["id"]),)
        ).fetchall()
    finally:
        conn.close()
    assert tuple(stored) == (hashlib.sha256(source).hexdigest(), "source.xlsx", "g4-v1", "committed")
    assert len(staged) == 1 and staged[0]["row_no"] == 1 and json.loads(staged[0]["raw_json"])["project_no"] == "G4-001"
    assert any(row["action"] == "import_confirm" for row in audit), "确认提交缺少来源批次审计"

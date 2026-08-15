"""G4 受控导入：解析结果先暂存，经 HUMAN token 确认后才原子入账。"""
import hashlib
import json
import shutil
import sqlite3
from pathlib import Path

from ledger.errors import DomainError
from ledger import services
from migrations import apply as apply_migrations


class ConfirmationBlocked(DomainError):
    """预览存在阻断行时拒绝确认，确保正式业务表保持不变。"""


class ImportWorkflow:
    """每个工作流明确绑定一个数据库；构造时只对该目标库显式补齐迁移。"""
    ConfirmationBlocked = ConfirmationBlocked

    def __init__(self, database_path, archive_dir, apply_schema=True):
        self.database_path = str(database_path)
        self.archive_dir = Path(archive_dir)
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        if apply_schema:
            # 测试临时库和维护者明确指定的目标库才允许执行迁移；应用服务绝不迁移正式库。
            with self._conn() as conn:
                apply_migrations(conn)

    def _conn(self):
        conn = sqlite3.connect(self.database_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @staticmethod
    def _text(value):
        return value.strip() if isinstance(value, str) and value.strip() else (None if value == "" else value)

    def _conclusion(self, conn, row):
        code = self._text(row.get("credit_code"))
        number = self._text(row.get("project_no"))
        if not code or not number:
            return "missing_identity", "统一社会信用代码和项目编号/文号均为自动入账必填项"
        if not self._text(row.get("enterprise_name")) or not self._text(row.get("project_name")):
            return "field_error", "企业名称和项目名称必填"
        enterprise = conn.execute("SELECT id FROM enterprise WHERE credit_code=? AND is_deleted=0", (code,)).fetchone()
        if enterprise and conn.execute("SELECT 1 FROM project WHERE project_no=? AND enterprise_id=? AND is_deleted=0", (number, enterprise['id'])).fetchone():
            return "duplicate", None
        start = self._text(row.get("start_date"))
        if start and start[:4] in services.archived_years(conn):
            return "archived_conflict", "该年度项目已归档"
        return ("new_enterprise,new_project" if not enterprise else "new_project"), None

    def parse_and_stage(self, file_name, file_bytes, rows, field_map_version):
        """保存不可覆盖的原始文件并逐行写暂存，不触碰 enterprise/project。"""
        digest = hashlib.sha256(file_bytes).hexdigest()
        safe_name = Path(file_name).name or "upload.xlsx"
        archive_path = self.archive_dir / f"{digest}-{safe_name}"
        if not archive_path.exists():
            archive_path.write_bytes(file_bytes)
        with self._conn() as conn:
            with conn:
                cur = conn.execute("INSERT INTO import_batch(file_name,file_sha256,field_map_version,archive_path,status) VALUES(?,?,?,?, 'staged')", (safe_name, digest, field_map_version, str(archive_path)))
                batch_id = cur.lastrowid
                for row_no, raw in enumerate(rows, 1):
                    normalized = {key: self._text(value) for key, value in raw.items()}
                    conclusion, error = self._conclusion(conn, normalized)
                    conn.execute("INSERT INTO import_staging(batch_id,row_no,raw_json,conclusion,error) VALUES(?,?,?,?,?)", (batch_id, row_no, json.dumps(normalized, ensure_ascii=False, sort_keys=True), conclusion, error))
        return {"id": batch_id}

    def parse_enterprises_and_stage(self, file_name, file_bytes, rows):
        """暂存企业专用工作簿；确认前不写 enterprise 正式表。"""
        digest = hashlib.sha256(file_bytes).hexdigest()
        safe_name = Path(file_name).name or "企业导入.xlsx"
        archive_path = self.archive_dir / f"{digest}-{safe_name}"
        if not archive_path.exists():
            archive_path.write_bytes(file_bytes)
        seen_codes = set()
        with self._conn() as conn:
            # 企业类型和区镇沿用系统配置字典，预览阶段就明确指出不匹配值。
            allowed_values = {}
            for item in conn.execute(
                "SELECT dict_type,value FROM dict_item WHERE dict_type IN ('enterprise_type','district') AND is_active=1"
            ):
                allowed_values.setdefault(item["dict_type"], set()).add(item["value"])
            with conn:
                cursor = conn.execute(
                    "INSERT INTO import_batch(file_name,file_sha256,field_map_version,archive_path,status) "
                    "VALUES(?,?,?,?, 'staged')",
                    (safe_name, digest, "enterprise-v1", str(archive_path)),
                )
                batch_id = cursor.lastrowid
                for row_no, raw in enumerate(rows, 1):
                    normalized = {key: self._text(value) for key, value in raw.items()}
                    name = normalized.get("name")
                    code = normalized.get("credit_code")
                    if not name or not code:
                        conclusion, error = "missing_identity", "企业名称和统一社会信用代码均为必填项"
                    elif code in seen_codes or conn.execute(
                        "SELECT 1 FROM enterprise WHERE credit_code=? AND is_deleted=0", (code,)
                    ).fetchone():
                        conclusion, error = "duplicate", "统一社会信用代码已存在或在文件内重复"
                    else:
                        invalid = []
                        if normalized.get("enterprise_type") and normalized["enterprise_type"] not in allowed_values.get("enterprise_type", set()):
                            invalid.append("企业类型不在系统启用选项中")
                        if normalized.get("district") and normalized["district"] not in allowed_values.get("district", set()):
                            invalid.append("区镇不在系统启用选项中")
                        if invalid:
                            conclusion, error = "field_error", "；".join(invalid)
                        else:
                            conclusion, error = "new_enterprise", None
                            seen_codes.add(code)
                    conn.execute(
                        "INSERT INTO import_staging(batch_id,row_no,raw_json,conclusion,error) VALUES(?,?,?,?,?)",
                        (batch_id, row_no, json.dumps(normalized, ensure_ascii=False, sort_keys=True), conclusion, error),
                    )
        return {"id": batch_id}

    def preview_enterprises(self, batch_id):
        """返回企业导入的逐行结论和汇总，供页面人工确认。"""
        with self._conn() as conn:
            batch = conn.execute(
                "SELECT id FROM import_batch WHERE id=? AND field_map_version='enterprise-v1'", (batch_id,)
            ).fetchone()
            if not batch:
                raise DomainError("企业导入批次不存在")
            rows = conn.execute(
                "SELECT row_no,conclusion,error FROM import_staging WHERE batch_id=? ORDER BY row_no", (batch_id,)
            ).fetchall()
        result_rows = [dict(row) for row in rows]
        return {
            "rows": result_rows,
            "summary": {
                "new_enterprise": sum(row["conclusion"] == "new_enterprise" for row in rows),
                "blocking": sum(row["conclusion"] != "new_enterprise" for row in rows),
            },
        }

    def confirm_enterprises(self, batch_id):
        """人工确认后在一个事务中创建全部企业，并记录来源批次。"""
        enterprise_fields = (
            "name", "credit_code", "enterprise_type", "district", "qualifications",
            "contact_person", "contact_phone", "address", "note",
        )
        with self._conn() as conn:
            batch = conn.execute(
                "SELECT * FROM import_batch WHERE id=? AND field_map_version='enterprise-v1'", (batch_id,)
            ).fetchone()
            if not batch:
                raise DomainError("企业导入批次不存在")
            if batch["status"] != "staged":
                raise DomainError("企业导入批次不是待确认状态")
            rows = conn.execute(
                "SELECT * FROM import_staging WHERE batch_id=? ORDER BY row_no", (batch_id,)
            ).fetchall()
            if not rows or any(row["conclusion"] != "new_enterprise" for row in rows):
                raise ConfirmationBlocked("企业导入存在阻断项，不能确认提交")
            with conn:
                for staged in rows:
                    row = json.loads(staged["raw_json"])
                    payload = {field: row.get(field) for field in enterprise_fields if row.get(field) is not None}
                    enterprise = services.create(conn, "enterprise", payload, commit=False)
                    conn.execute(
                        "UPDATE audit_log SET source_batch=? "
                        "WHERE object_type='enterprise' AND object_id=? AND source_batch IS NULL",
                        (str(batch_id), enterprise["id"]),
                    )
                conn.execute(
                    "UPDATE import_batch SET status='committed', committed_at=datetime('now','localtime') WHERE id=?",
                    (batch_id,),
                )
                conn.execute(
                    "INSERT INTO audit_log(ts,operator,action,object_type,object_id,source_batch,note) "
                    "VALUES(datetime('now','localtime'),'local-user','import_confirm','import_batch',?,?,?)",
                    (batch_id, str(batch_id), batch["file_sha256"]),
                )
        return {"status": "committed", "id": batch_id, "enterprise_count": len(rows)}

    def preview(self, batch_id):
        with self._conn() as conn:
            batch = conn.execute("SELECT id FROM import_batch WHERE id=?", (batch_id,)).fetchone()
            if not batch:
                raise DomainError("导入批次不存在")
            rows = conn.execute("SELECT row_no,conclusion,error FROM import_staging WHERE batch_id=? ORDER BY row_no", (batch_id,)).fetchall()
        result_rows = [{"row_no": row['row_no'], "conclusion": row['conclusion']} for row in rows]
        return {"rows": result_rows, "summary": {"new_enterprise": sum(row['conclusion'] == 'new_enterprise,new_project' for row in rows), "new_project": sum(row['conclusion'] in ('new_enterprise,new_project', 'new_project') for row in rows), "blocking": sum(row['conclusion'] not in ('new_enterprise,new_project', 'new_project') for row in rows)}}

    def confirm(self, batch_id):
        """HUMAN 确认入口：所有企业、项目、审计与批次状态同一事务提交。"""
        with self._conn() as conn:
            batch = conn.execute("SELECT * FROM import_batch WHERE id=?", (batch_id,)).fetchone()
            if not batch:
                raise DomainError("导入批次不存在")
            if batch['status'] != 'staged':
                raise DomainError("导入批次不是待确认状态")
            rows = conn.execute("SELECT * FROM import_staging WHERE batch_id=? ORDER BY row_no", (batch_id,)).fetchall()
            if any(row['conclusion'] not in ('new_enterprise,new_project', 'new_project') for row in rows):
                raise ConfirmationBlocked("存在阻断行，不能确认提交")
            try:
                with conn:
                    for staged in rows:
                        row = json.loads(staged['raw_json'])
                        enterprise = conn.execute("SELECT * FROM enterprise WHERE credit_code=? AND is_deleted=0", (row['credit_code'],)).fetchone()
                        if enterprise is None:
                            enterprise_payload = {"name": row['enterprise_name'], "credit_code": row['credit_code'], "enterprise_type": row.get('enterprise_type'), "district": row.get('district')}
                            enterprise = services.create(conn, 'enterprise', enterprise_payload, commit=False)
                            enterprise_id = enterprise['id']
                        else:
                            enterprise_id = enterprise['id']
                        project_payload = {"name": row['project_name'], "project_no": row['project_no'], "enterprise_id": enterprise_id, "level": row.get('level'), "category": row.get('category'), "total_amount": row.get('total_amount'), "start_date": row.get('start_date'), "end_date": row.get('end_date'), "stage": row.get('stage')}
                        project = services.create(conn, 'project', project_payload, commit=False)
                        conn.execute("UPDATE audit_log SET source_batch=? WHERE object_type IN ('enterprise','project') AND object_id IN (?,?) AND source_batch IS NULL", (str(batch_id), enterprise_id, project['id']))
                    conn.execute("UPDATE import_batch SET status='committed', committed_at=datetime('now','localtime') WHERE id=?", (batch_id,))
                    conn.execute("INSERT INTO audit_log(ts,operator,action,object_type,object_id,source_batch,note) VALUES(datetime('now','localtime'),'local-user','import_confirm','import_batch',?,?,?)", (batch_id, str(batch_id), batch['file_sha256']))
            except Exception:
                # 失败状态须保持 staged，方便 HUMAN 查看原因并重试；没有任何业务写入会残留。
                raise
        return {"status": "committed", "id": batch_id}

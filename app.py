#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""科技项目全生命周期台账系统 — 后端（Python 标准库，零第三方依赖）

双击 start.bat 启动，浏览器访问 http://127.0.0.1:8765
提供：静态文件服务 + JSON API（企业/项目/资金/节点/字典 的增删改查）
"""

import json
import os
import sqlite3
import threading
import webbrowser
import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from ledger.errors import DomainError
from ledger import queries, services
from ledger import security

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data", "project.db")
SCHEMA_PATH = os.path.join(BASE_DIR, "schema.sql")
STATIC_DIR = os.path.join(BASE_DIR, "static")
HOST = "127.0.0.1"
PORT = 8765

# 各表允许写入的字段（白名单，防注入、防脏数据）
FIELDS = {
    "enterprise": ["name", "credit_code", "enterprise_type", "qualifications", "district",
                   "contact_person", "contact_phone", "address", "note"],
    "project": ["name", "project_no", "level", "category", "enterprise_id", "total_amount",
                "start_date", "end_date", "stage", "match_ratio", "leader", "contact_phone", "note"],
    "funding": ["project_id", "source_type", "amount", "batch", "plan_date", "actual_date", "status", "note"],
    "node": ["project_id", "node_type", "plan_date", "actual_date", "status", "has_major_change", "note"],
    "dict": ["dict_type", "value", "sort_order", "is_active"],
}

NUMERIC_FIELDS = {"total_amount", "amount", "match_ratio"}
INT_FIELDS = {"enterprise_id", "project_id", "has_major_change", "is_active", "sort_order"}

MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".ico": "image/x-icon",
}


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    if not os.path.exists(DB_PATH):
        conn = get_db()
        with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
            conn.executescript(f.read())
        conn.commit()
        conn.close()
    else:
        # 老库兼容仅确保归档配置存在；结构迁移必须由维护人员显式调用 migrations.apply。
        conn = get_db()
        conn.executescript(
            "CREATE TABLE IF NOT EXISTS system_config ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " key TEXT UNIQUE NOT NULL,"
            " value TEXT);"
            "INSERT OR IGNORE INTO system_config (key, value) VALUES ('archived_years', '');"
        )
        conn.commit()
        conn.close()


def clean_row(row):
    """sqlite3.Row -> dict"""
    return dict(row) if row is not None else None


def clean_payload(body, table):
    """只保留白名单字段；空字符串转 None；数值/整数字段做类型转换。"""
    out = {}
    allowed = FIELDS[table]
    for k, v in (body or {}).items():
        if k not in allowed:
            continue
        if isinstance(v, str):
            v = v.strip()
            if v == "":
                v = None
        elif k in NUMERIC_FIELDS and v is not None:
            try:
                v = float(v)
            except (TypeError, ValueError):
                v = None
        elif k in INT_FIELDS and v is not None:
            try:
                v = int(v)
            except (TypeError, ValueError):
                v = None
        out[k] = v
    return out


class Handler(BaseHTTPRequestHandler):
    server_version = "ProjectLedger/1.0"

    # ---------- 基础工具 ----------
    def _read_body(self):
        """每个请求只读取一次请求体，使鉴权拒绝后的连接也能正常收尾。"""
        if hasattr(self, "_parsed_request_body"):
            return self._parsed_request_body
        length = int(self.headers.get("Content-Length", 0))
        if not length:
            self._parsed_request_body = {}
            return self._parsed_request_body
        raw = self.rfile.read(length)
        try:
            self._parsed_request_body = json.loads(raw.decode("utf-8"))
        except Exception:
            self._parsed_request_body = {}
        return self._parsed_request_body

    def _send(self, status, obj, headers=None):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    def _ok(self, obj):
        self._send(200, obj)

    def _err(self, status, message):
        self._send(status, {"error": message})

    def _request_user(self):
        """从 HttpOnly 会话 Cookie 提取当前用户，API 不接受客户端伪造身份字段。"""
        raw_cookie = self.headers.get("Cookie", "")
        for item in raw_cookie.split(";"):
            key, sep, value = item.strip().partition("=")
            if key == "ledger_session" and sep:
                return security.user_for_token(value)
        return None

    def _require_role(self, *roles):
        """统一角色门禁：未登录 401，已登录但越权 403。"""
        if not self.current_user:
            self._err(401, "请先登录")
            return False
        if self.current_user["role"] not in roles:
            self._err(403, "当前角色无此操作权限")
            return False
        return True

    def _is_sensitive_action(self, resource, method, parts):
        """归档、恢复、导入是高影响操作，仅管理员可执行。"""
        return (
            resource == "config" and method == "PUT"
            or resource == "import" and method == "POST"
            or method == "POST" and len(parts) > 1 and parts[-1] == "restore"
        )

    # ---------- 路由 ----------
    def do_GET(self):
        self._route("GET")

    def do_POST(self):
        self._route("POST")

    def do_PUT(self):
        self._route("PUT")

    def do_DELETE(self):
        self._route("DELETE")

    def _route(self, method):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        parts = [p for p in path.split("/") if p]
        qs = parse_qs(parsed.query)

        # 静态文件 / 首页
        if method == "GET" and (path == "/" or path.startswith("/static/") or "." in parts[-1] if parts else False):
            self._serve_static(path)
            return

        # API
        if parts and parts[0] == "api":
            self._api(method, parts[1:], qs)
        else:
            self._serve_static("/")

    def _serve_static(self, path):
        if path == "/" or path == "":
            path = "/index.html"
        if path.startswith("/static/"):
            rel = path[len("/static/"):]
        else:
            rel = path.lstrip("/")
        # 防目录穿越
        file_path = os.path.normpath(os.path.join(STATIC_DIR, rel))
        if not file_path.startswith(STATIC_DIR):
            self._err(403, "forbidden")
            return
        if not os.path.isfile(file_path):
            self._err(404, "not found")
            return
        ext = os.path.splitext(file_path)[1].lower()
        content_type = MIME.get(ext, "application/octet-stream")
        with open(file_path, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    # ---------- API 分发 ----------
    def _api(self, method, parts, qs):
        # 必须先消费写请求体：若鉴权直接返回 401/403 而残留请求体，Windows 关闭
        # 套接字时会发送 RST，客户端便可能在已记录 403 后仍收到 ConnectionAbortedError。
        if method in ("POST", "PUT", "DELETE"):
            self._read_body()
        if not parts:
            self._err(404, "no api resource")
            return
        resource = parts[0]

        # 登录是唯一不需要既有会话的 API，其余读写一律先做身份认证。
        if resource == "auth":
            self._api_auth(method, parts[1:])
            return
        self.current_user = self._request_user()
        if not self.current_user:
            self._err(401, "请先登录")
            return
        if self._is_sensitive_action(resource, method, parts[1:]) and not self._require_role("admin"):
            return
        # 查阅员绝不写入；编辑员可做日常台账维护，但不能越过上面的敏感操作门禁。
        if method in ("POST", "PUT", "DELETE") and not self._require_role("admin", "editor"):
            return
        operator_token = security.set_current_operator(self.current_user["username"])
        try:
            self._dispatch_api(method, resource, parts[1:], qs)
        finally:
            security.reset_current_operator(operator_token)

    def _dispatch_api(self, method, resource, parts, qs):

        if resource == "dict":
            self._api_dict(method, parts, qs)
        elif resource == "enterprises":
            self._api_enterprise(method, parts, qs)
        elif resource == "projects":
            self._api_project(method, parts, qs)
        elif resource == "fundings":
            self._api_funding(method, parts, qs)
        elif resource == "nodes":
            self._api_node(method, parts, qs)
        elif resource == "reminders":
            self._api_reminders(method, parts, qs)
        elif resource in ("stats", "statistics"):
            self._api_stats(method, parts, qs)
        elif resource == "funding-check":
            self._api_funding_check(method, parts, qs)
        elif resource == "import":
            self._api_import(method, parts, qs)
        elif resource == "template":
            self._api_template(method, parts, qs)
        elif resource == "dashboard":
            self._api_dashboard(method, parts, qs)
        elif resource == "funding-plan":
            self._api_funding_plan(method, parts, qs)
        elif resource == "config":
            self._api_config(method, parts, qs)
        else:
            self._err(404, "unknown resource")

    def _api_auth(self, method, parts):
        """最小本地登录：成功后仅以 HttpOnly Cookie 建立会话。"""
        if method != "POST" or parts != ["login"]:
            self._err(405, "method not allowed")
            return
        body = self._read_body()
        token, user = security.login(body.get("username"), body.get("password"))
        if not token:
            self._err(401, "用户名或密码错误")
            return
        self._send(200, {"user": user}, {"Set-Cookie": f"ledger_session={token}; HttpOnly; SameSite=Strict; Path=/"})

    # ---------- 归档工具 ----------
    def _archived_years(self, conn):
        row = conn.execute("SELECT value FROM system_config WHERE key='archived_years'").fetchone()
        if not row or not row["value"]:
            return set()
        return {y.strip() for y in row["value"].split(",") if y.strip()}

    def _is_archived_project(self, conn, project_id):
        if not project_id:
            return False
        row = conn.execute("SELECT start_date FROM project WHERE id=?", (project_id,)).fetchone()
        if not row or not row["start_date"]:
            return False
        return row["start_date"][:4] in self._archived_years(conn)

    # ---------- 首页工作台 ----------
    def _api_dashboard(self, method, parts, qs):
        if method != "GET":
            self._err(405, "method not allowed"); return
        conn = get_db()
        try:
            totals = queries.dashboard(conn)
            project_count = conn.execute("SELECT COUNT(*) c FROM project").fetchone()["c"]
            enterprise_count = conn.execute("SELECT COUNT(*) c FROM enterprise").fetchone()["c"]
            funded_total = conn.execute("SELECT COALESCE(SUM(amount),0) a FROM funding WHERE status='已到账'").fetchone()["a"]
            plan_total = conn.execute("SELECT COALESCE(SUM(amount),0) a FROM funding WHERE plan_date IS NOT NULL").fetchone()["a"]
            overdue_funding = conn.execute(
                "SELECT COUNT(*) c, COALESCE(SUM(amount),0) a FROM funding "
                "WHERE plan_date IS NOT NULL AND plan_date < date('now','localtime') "
                "AND (actual_date IS NULL OR actual_date='')").fetchone()
            overdue_nodes = conn.execute(
                "SELECT COUNT(*) c FROM node WHERE status!='已完成' AND plan_date IS NOT NULL "
                "AND julianday(plan_date) < julianday(date('now','localtime'))").fetchone()["c"]
            due30_nodes = conn.execute(
                "SELECT COUNT(*) c FROM node WHERE status!='已完成' AND plan_date IS NOT NULL "
                "AND julianday(plan_date) BETWEEN julianday(date('now','localtime')) "
                "AND julianday(date('now','localtime'))+30").fetchone()["c"]
            by_level = [clean_row(r) for r in conn.execute(
                "SELECT COALESCE(level,'未设置') AS key, COUNT(*) AS count FROM project "
                "GROUP BY level ORDER BY count DESC").fetchall()]
            by_category = [clean_row(r) for r in conn.execute(
                "SELECT COALESCE(category,'未设置') AS key, COUNT(*) AS count FROM project "
                "GROUP BY category ORDER BY count DESC").fetchall()]
            self._ok({
                **totals,
                "project_count": project_count,
                "enterprise_count": enterprise_count,
                "funded_total": round(funded_total, 2),
                "plan_total": round(plan_total, 2),
                "overdue_funding_count": overdue_funding["c"],
                "overdue_funding_amount": round(overdue_funding["a"], 2),
                "overdue_nodes": overdue_nodes,
                "due30_nodes": due30_nodes,
                "by_level": by_level,
                "by_category": by_category,
            })
        finally:
            conn.close()

    # ---------- 资金拨付执行度 ----------
    def _api_funding_plan(self, method, parts, qs):
        if method != "GET":
            self._err(405, "method not allowed"); return
        conn = get_db()
        try:
            rows = conn.execute(
                "SELECT f.id, f.project_id, f.source_type, f.amount, f.plan_date, f.actual_date, f.status, "
                "p.name AS project_name, p.level AS project_level, p.start_date "
                "FROM funding f JOIN project p ON f.project_id=p.id "
                "WHERE f.plan_date IS NOT NULL ORDER BY f.plan_date, f.id").fetchall()
            today = datetime.date.today().isoformat()
            items = []
            summary = {"total_plan": 0.0, "total_paid": 0.0, "overdue_count": 0, "overdue_amount": 0.0}
            for r in rows:
                d = clean_row(r)
                d["is_overdue"] = bool(d["plan_date"] and d["plan_date"] < today and not d["actual_date"])
                items.append(d)
                summary["total_plan"] += d["amount"] or 0
                if d["status"] == "已到账":
                    summary["total_paid"] += d["amount"] or 0
                if d["is_overdue"]:
                    summary["overdue_count"] += 1
                    summary["overdue_amount"] += d["amount"] or 0
            summary["total_plan"] = round(summary["total_plan"], 2)
            summary["total_paid"] = round(summary["total_paid"], 2)
            summary["overdue_amount"] = round(summary["overdue_amount"], 2)
            summary["execution_rate"] = round(summary["total_paid"] / summary["total_plan"], 4) if summary["total_plan"] else 0
            self._ok({"items": items, "summary": summary})
        finally:
            conn.close()

    # ---------- 系统配置 ----------
    def _api_config(self, method, parts, qs):
        conn = get_db()
        try:
            if method == "GET":
                rows = conn.execute("SELECT key, value FROM system_config").fetchall()
                out = {}
                for r in rows:
                    if r["key"] == "archived_years":
                        out[r["key"]] = [y for y in (r["value"] or "").split(",") if y.strip()]
                    else:
                        out[r["key"]] = r["value"]
                self._ok(out)
            elif method == "PUT":
                body = self._read_body()
                years = (body or {}).get("archived_years")
                if not isinstance(years, list):
                    self._err(400, "archived_years must be list"); return
                services.set_archived_years(conn, years, (body or {}).get("reason"))
                self._ok({"saved": True})
            else:
                self._err(405, "method not allowed")
        finally:
            conn.close()

    # ---------- 下载导入模板 ----------
    def _api_template(self, method, parts, qs):
        if method != "GET":
            self._err(405, "method not allowed"); return
        import subprocess
        import sys
        path = os.path.join(BASE_DIR, "导入模板.xlsx")
        if not os.path.exists(path):
            subprocess.run([sys.executable, os.path.join(BASE_DIR, "make_template.py")],
                           cwd=BASE_DIR, check=False)
        if not os.path.exists(path):
            self._err(500, "模板生成失败"); return
        with open(path, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        self.send_header("Content-Disposition", 'attachment; filename="import_template.xlsx"')
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    # ---------- Excel 导入 ----------
    def _api_import(self, method, parts, qs):
        if method == "GET" and len(parts) == 1:
            from imports.controlled import ImportWorkflow
            try:
                workflow = ImportWorkflow(DB_PATH, os.path.join(BASE_DIR, "imports", "archive"), apply_schema=False)
                self._ok(workflow.preview(int(parts[0])))
            except (DomainError, ValueError, sqlite3.Error) as exc:
                self._err(400, str(exc))
            return
        if method == "POST" and len(parts) == 2 and parts[1] == "confirm":
            from imports.controlled import ImportWorkflow
            try:
                workflow = ImportWorkflow(DB_PATH, os.path.join(BASE_DIR, "imports", "archive"), apply_schema=False)
                self._ok(workflow.confirm(int(parts[0])))
            except DomainError as exc:
                self._err(409, str(exc))
            except (ValueError, sqlite3.Error) as exc:
                self._err(400, str(exc))
            return
        if method != "POST" or parts:
            self._err(405, "method not allowed"); return
        try:
            import base64
            import io
            from openpyxl import load_workbook
        except ImportError:
            self._err(500, "未安装 openpyxl，请先运行: pip install openpyxl"); return
        body = self._read_body()
        b64 = body.get("data") or ""
        try:
            raw = base64.b64decode(b64)
        except Exception:
            self._err(400, "文件内容无法解码"); return
        try:
            wb = load_workbook(io.BytesIO(raw), data_only=True)
        except Exception as e:
            self._err(400, f"Excel 解析失败: {e}"); return
        try:
            from import_excel import normalized_rows
            from imports.controlled import ImportWorkflow
        except ImportError:
            self._err(500, "缺少 import_excel.py"); return
        try:
            workflow = ImportWorkflow(DB_PATH, os.path.join(BASE_DIR, "imports", "archive"), apply_schema=False)
            result = workflow.parse_and_stage(body.get("name") or "upload.xlsx", raw, normalized_rows(wb), "excel-v1")
            result["preview"] = workflow.preview(result["id"])
        except (DomainError, sqlite3.Error) as e:
            self._err(400, f"导入暂存失败: {e}"); return
        self._ok(result)

    # ---------- 字典 ----------
    def _api_dict(self, method, parts, qs):
        conn = get_db()
        try:
            if method == "GET":
                if parts and parts[0] == "types":
                    rows = conn.execute("SELECT DISTINCT dict_type FROM dict_item ORDER BY dict_type").fetchall()
                    self._ok([r["dict_type"] for r in rows])
                    return
                dict_type = qs.get("type", [None])[0]
                all_items = qs.get("all", ["0"])[0] == "1"
                if dict_type:
                    sql = "SELECT * FROM dict_item WHERE dict_type=?"
                    if not all_items:
                        sql += " AND is_active=1"
                    rows = conn.execute(sql + " ORDER BY sort_order, id", (dict_type,)).fetchall()
                    self._ok([clean_row(r) for r in rows])
                else:
                    rows = conn.execute(
                        "SELECT dict_type, value FROM dict_item WHERE is_active=1 ORDER BY dict_type, sort_order, id"
                    ).fetchall()
                    grouped = {}
                    for r in rows:
                        grouped.setdefault(r["dict_type"], []).append(r["value"])
                    self._ok(grouped)
            elif method == "POST" and not parts:
                body = clean_payload(self._read_body(), "dict")
                if not body.get("dict_type") or not body.get("value"):
                    self._err(400, "dict_type and value are required"); return
                dup = conn.execute(
                    "SELECT id FROM dict_item WHERE dict_type=? AND value=?",
                    (body["dict_type"], body["value"])).fetchone()
                if dup:
                    self._err(400, "该取值已存在"); return
                cur = conn.execute(
                    "INSERT INTO dict_item (dict_type, value, sort_order, is_active) VALUES (?,?,?,1)",
                    (body["dict_type"], body["value"], body.get("sort_order") or 0))
                conn.commit()
                row = conn.execute("SELECT * FROM dict_item WHERE id=?", (cur.lastrowid,)).fetchone()
                self._ok(clean_row(row))
            elif method == "PUT" and len(parts) == 1:
                did = int(parts[0])
                body = clean_payload(self._read_body(), "dict")
                if not body:
                    self._err(400, "no fields"); return
                sets = ", ".join(f"{k}=?" for k in body)
                conn.execute(f"UPDATE dict_item SET {sets} WHERE id=?", [*body.values(), did])
                conn.commit()
                row = conn.execute("SELECT * FROM dict_item WHERE id=?", (did,)).fetchone()
                self._ok(clean_row(row))
            elif method == "DELETE" and len(parts) == 1:
                did = int(parts[0])
                # 停用而非删除，保护历史引用
                conn.execute("UPDATE dict_item SET is_active=0 WHERE id=?", (did,))
                conn.commit()
                self._ok({"disabled": did})
            else:
                self._err(405, "method not allowed")
        except DomainError as exc:
            self._err(403 if '已归档' in str(exc) else 409 if '父项目' in str(exc) else 400, str(exc))
        except ValueError:
            self._err(400, "invalid id")
        finally:
            conn.close()

    # ---------- 提醒 ----------
    def _api_reminders(self, method, parts, qs):
        if method != "GET":
            self._err(405, "method not allowed"); return
        conn = get_db()
        try:
            days = int(qs.get("days", ["30"])[0])
            rows = conn.execute(
                "SELECT n.id, n.project_id, n.node_type, n.plan_date, n.actual_date, n.status, n.note, "
                "p.name AS project_name, p.level AS project_level, "
                "(julianday(n.plan_date) - julianday(date('now','localtime'))) AS days_left "
                "FROM node n JOIN project p ON n.project_id = p.id "
                "WHERE n.status != '已完成' AND n.plan_date IS NOT NULL "
                "AND (julianday(n.plan_date) - julianday(date('now','localtime'))) <= ? "
                "ORDER BY n.plan_date",
                (days,)
            ).fetchall()
            out = []
            for r in rows:
                d = clean_row(r)
                dl = d.get("days_left")
                if dl is None:
                    d["level"] = "later"
                elif dl < 0:
                    d["level"] = "overdue"
                elif dl <= 7:
                    d["level"] = "red"
                elif dl <= days:
                    d["level"] = "yellow"
                else:
                    d["level"] = "later"
                out.append(d)
            self._ok(out)
        except ValueError:
            self._err(400, "invalid days")
        finally:
            conn.close()

    # ---------- 统计 ----------
    def _api_stats(self, method, parts, qs):
        if method != "GET":
            self._err(405, "method not allowed"); return
        by = qs.get("by", ["category"])[0]
        conn = get_db()
        try:
            scope = self.current_user.get("district_scope")
            scope_sql = " AND e.district=?" if scope else ""
            scope_params = (scope,) if scope else ()
            if by == "district":
                rows = conn.execute(
                    "SELECT COALESCE(e.district,'未设置') AS key, COUNT(p.id) AS count, "
                    "COALESCE(SUM(p.total_amount),0) AS amount "
                    "FROM project p JOIN enterprise e ON p.enterprise_id=e.id "
                    "WHERE p.is_deleted=0 AND e.is_deleted=0" + scope_sql + " GROUP BY e.district ORDER BY count DESC",
                    scope_params,
                ).fetchall()
            elif by == "source":
                rows = conn.execute(
                    "SELECT f.source_type AS key, COUNT(*) AS count, COALESCE(SUM(f.amount),0) AS amount "
                    "FROM funding f JOIN project p ON f.project_id=p.id JOIN enterprise e ON p.enterprise_id=e.id "
                    "WHERE f.is_deleted=0 AND p.is_deleted=0 AND e.is_deleted=0" + scope_sql + " GROUP BY f.source_type ORDER BY amount DESC",
                    scope_params).fetchall()
            elif by == "enterprise":
                rows = conn.execute(
                    "SELECT COALESCE(e.name,'未关联') AS key, COUNT(p.id) AS count, "
                    "COALESCE(SUM(p.total_amount),0) AS amount "
                    "FROM project p LEFT JOIN enterprise e ON p.enterprise_id=e.id "
                    "GROUP BY p.enterprise_id ORDER BY amount DESC").fetchall()
            elif by == "year":
                rows = conn.execute(
                    "SELECT substr(p.start_date,1,4) AS key, COUNT(*) AS count, "
                    "COALESCE(SUM(p.total_amount),0) AS amount "
                    "FROM project p GROUP BY substr(p.start_date,1,4) ORDER BY key").fetchall()
            elif by == "stage":
                rows = conn.execute(
                    "SELECT p.stage AS key, COUNT(*) AS count, COALESCE(SUM(p.total_amount),0) AS amount "
                    "FROM project p GROUP BY p.stage ORDER BY count DESC").fetchall()
            else:
                col = by if by in ("level", "category") else "category"
                rows = conn.execute(
                    f"SELECT p.{col} AS key, COUNT(*) AS count, COALESCE(SUM(p.total_amount),0) AS amount "
                    f"FROM project p GROUP BY p.{col} ORDER BY count DESC").fetchall()
            out = []
            for r in rows:
                d = clean_row(r)
                d["key"] = d.get("key") or "未设置"
                out.append(d)
            self._ok(out)
        finally:
            conn.close()

    # ---------- 资金勾稽核对 ----------
    def _api_funding_check(self, method, parts, qs):
        if method != "GET":
            self._err(405, "method not allowed"); return
        conn = get_db()
        try:
            rows = conn.execute(
                "SELECT p.id, p.name, p.total_amount, p.match_ratio, "
                "COALESCE(SUM(CASE WHEN f.source_type='上级拨付' THEN f.amount ELSE 0 END),0) AS sum_up, "
                "COALESCE(SUM(CASE WHEN f.source_type='本级配套' THEN f.amount ELSE 0 END),0) AS sum_match, "
                "COALESCE(SUM(CASE WHEN f.source_type='本级自付' THEN f.amount ELSE 0 END),0) AS sum_self "
                "FROM project p LEFT JOIN funding f ON f.project_id=p.id "
                "GROUP BY p.id ORDER BY p.id").fetchall()
            out = []
            for r in rows:
                d = clean_row(r)
                d["sum_all"] = d["sum_up"] + d["sum_match"] + d["sum_self"]
                issues = []
                if d["total_amount"] is not None and abs(d["sum_all"] - d["total_amount"]) > 0.005:
                    issues.append("资金合计与项目总金额不一致")
                if d["match_ratio"] and d["sum_up"]:
                    expected = d["sum_up"] * d["match_ratio"]
                    d["match_expected"] = round(expected, 2)
                    if abs(d["sum_match"] - expected) > 0.005:
                        issues.append("本级配套与应配额不一致")
                d["issues"] = issues
                d["ok"] = len(issues) == 0
                out.append(d)
            self._ok(out)
        finally:
            conn.close()

    # ---------- 企业 ----------
    def _api_enterprise(self, method, parts, qs):
        conn = get_db()
        try:
            if method == "GET" and not parts:
                rows = conn.execute(
                    "SELECT e.*, "
                    "(SELECT COUNT(*) FROM project p WHERE p.enterprise_id=e.id AND p.is_deleted=0) AS project_count, "
                    "(SELECT COALESCE(SUM(p.total_amount),0) FROM project p WHERE p.enterprise_id=e.id AND p.is_deleted=0) AS total_amount_sum "
                    "FROM enterprise e WHERE e.is_deleted=0 ORDER BY e.id DESC"
                ).fetchall()
                self._ok([clean_row(r) for r in rows])
            elif method == "GET" and len(parts) == 1:
                eid = int(parts[0])
                ent = conn.execute("SELECT * FROM enterprise WHERE id=? AND is_deleted=0", (eid,)).fetchone()
                if not ent:
                    self._err(404, "enterprise not found"); return
                projects = conn.execute(
                    "SELECT * FROM project WHERE enterprise_id=? AND is_deleted=0 ORDER BY id DESC", (eid,)
                ).fetchall()
                result = clean_row(ent)
                result["projects"] = [clean_row(r) for r in projects]
                self._ok(result)
            elif method == "POST" and not parts:
                payload = clean_payload(self._read_body(), "enterprise")
                if not payload.get("name"):
                    self._err(400, "name is required"); return
                self._ok(services.create(conn, "enterprise", payload))
            elif method == "PUT" and len(parts) == 1:
                eid = int(parts[0])
                payload = clean_payload(self._read_body(), "enterprise")
                if not payload:
                    self._err(400, "no fields"); return
                self._ok(services.update(conn, "enterprise", eid, payload))
            elif method == "DELETE" and len(parts) == 1:
                eid = int(parts[0])
                services.soft_delete(conn, "enterprise", eid, self._read_body().get("reason"))
                self._ok({"deleted": eid})
            elif method == "POST" and len(parts) == 2 and parts[1] == "restore":
                self._ok(services.restore(conn, "enterprise", int(parts[0]), self._read_body().get("reason")))
            else:
                self._err(405, "method not allowed")
        except DomainError as exc:
            self._err(403 if '已归档' in str(exc) else 409 if '父项目' in str(exc) else 400, str(exc))
        except ValueError:
            self._err(400, "invalid id")
        finally:
            conn.close()

    # ---------- 项目 ----------
    def _build_filter_cond(self, field, op, val):
        """高级筛选：字段/运算符/值 -> (sql片段, 参数)。非法组合返回 None。"""
        if val is None or (isinstance(val, str) and val.strip() == ""):
            return None
        colmap = {
            "name": "p.name", "project_no": "p.project_no", "level": "p.level",
            "category": "p.category", "stage": "p.stage", "enterprise_id": "p.enterprise_id",
            "enterprise_name": "e.name", "district": "e.district",
            "total_amount": "p.total_amount", "match_ratio": "p.match_ratio",
            "start_date": "p.start_date", "end_date": "p.end_date",
            "leader": "p.leader", "contact_phone": "p.contact_phone",
        }
        col = colmap.get(field)
        if not col:
            return None
        if op == "eq":
            return (f"{col}=?", val)
        if op == "contains":
            return (f"{col} LIKE ?", f"%{val}%")
        if op == "gt":
            return (f"{col} > ?", val)
        if op == "gte":
            return (f"{col} >= ?", val)
        if op == "lt":
            return (f"{col} < ?", val)
        if op == "lte":
            return (f"{col} <= ?", val)
        return None

    def _api_project(self, method, parts, qs):
        conn = get_db()
        try:
            if method == "GET" and not parts:
                where, params = [], []
                for key, col in [("level", "p.level"), ("category", "p.category"),
                                 ("stage", "p.stage"), ("enterprise_id", "p.enterprise_id")]:
                    v = qs.get(key, [None])[0]
                    if v:
                        where.append(f"{col}=?")
                        params.append(v)
                # 区镇（挂在承担企业上）
                v = qs.get("district", [None])[0]
                if v:
                    where.append("e.district=?")
                    params.append(v)
                q = qs.get("q", [None])[0]
                if q:
                    where.append("(p.name LIKE ? OR p.project_no LIKE ? OR e.name LIKE ?)")
                    like = f"%{q}%"
                    params += [like, like, like]
                # 高级筛选（JSON 数组：[{field, op, value}, ...] AND 组合）
                filters_raw = qs.get("filters", [None])[0]
                if filters_raw:
                    try:
                        for cond in json.loads(filters_raw):
                            built = self._build_filter_cond(
                                cond.get("field"), cond.get("op"), cond.get("value"))
                            if built:
                                where.append(built[0])
                                params.append(built[1])
                    except (ValueError, TypeError):
                        pass
                requested_district = qs.get("district", [None])[0]
                scoped_district = self.current_user.get("district_scope")
                if scoped_district and requested_district and requested_district != scoped_district:
                    self._ok([]); return
                self._ok(queries.project_list(conn, {
                    "level": qs.get("level", [None])[0], "category": qs.get("category", [None])[0],
                    "stage": qs.get("stage", [None])[0], "enterprise_id": qs.get("enterprise_id", [None])[0],
                    "district": scoped_district or requested_district, "query": qs.get("q", [None])[0]}))
            elif method == "GET" and len(parts) == 1:
                pid = int(parts[0])
                result = queries.project_detail(conn, pid)
                if not result:
                    self._err(404, "project not found"); return
                self._ok(result)
            elif method == "POST" and not parts:
                payload = clean_payload(self._read_body(), "project")
                if not payload.get("name"):
                    self._err(400, "name is required"); return
                self._ok(services.create(conn, "project", payload))
            elif method == "PUT" and len(parts) == 1:
                pid = int(parts[0])
                if self._is_archived_project(conn, pid):
                    self._err(403, "该年度项目已归档，禁止修改"); return
                payload = clean_payload(self._read_body(), "project")
                if not payload:
                    self._err(400, "no fields"); return
                self._ok(services.update(conn, "project", pid, payload))
            elif method == "DELETE" and len(parts) == 1:
                pid = int(parts[0])
                if self._is_archived_project(conn, pid):
                    self._err(403, "该年度项目已归档，禁止删除"); return
                services.soft_delete(conn, "project", pid, self._read_body().get("reason"))
                self._ok({"deleted": pid})
            elif method == "POST" and len(parts) == 2 and parts[1] == "restore":
                self._ok(services.restore(conn, "project", int(parts[0]), self._read_body().get("reason")))
            else:
                self._err(405, "method not allowed")
        except DomainError as exc:
            self._err(403 if '已归档' in str(exc) else 409 if '父项目' in str(exc) else 400, str(exc))
        except ValueError:
            self._err(400, "invalid id")
        finally:
            conn.close()

    # ---------- 资金 ----------
    def _api_funding(self, method, parts, qs):
        self._api_child("funding", method, parts, qs)

    # ---------- 节点 ----------
    def _api_node(self, method, parts, qs):
        self._api_child("node", method, parts, qs)

    def _api_child(self, table, method, parts, qs):
        conn = get_db()
        try:
            if method == "GET" and not parts:
                pid = qs.get("project_id", [None])[0]
                if pid:
                    rows = conn.execute(f"SELECT * FROM {table} WHERE project_id=? AND is_deleted=0 ORDER BY id", (int(pid),)).fetchall()
                else:
                    rows = conn.execute(f"SELECT * FROM {table} WHERE is_deleted=0 ORDER BY id").fetchall()
                self._ok([clean_row(r) for r in rows])
            elif method == "POST" and not parts:
                payload = clean_payload(self._read_body(), table)
                if not payload.get("project_id"):
                    self._err(400, "project_id is required"); return
                if self._is_archived_project(conn, payload["project_id"]):
                    self._err(403, "该项目已归档，禁止新增"); return
                self._ok(services.create(conn, table, payload))
            elif method == "PUT" and len(parts) == 1:
                rid = int(parts[0])
                row = conn.execute(f"SELECT project_id FROM {table} WHERE id=?", (rid,)).fetchone()
                if row and self._is_archived_project(conn, row["project_id"]):
                    self._err(403, "该项目已归档，禁止修改"); return
                payload = clean_payload(self._read_body(), table)
                if not payload:
                    self._err(400, "no fields"); return
                self._ok(services.update(conn, table, rid, payload))
            elif method == "DELETE" and len(parts) == 1:
                rid = int(parts[0])
                row = conn.execute(f"SELECT project_id FROM {table} WHERE id=?", (rid,)).fetchone()
                if row and self._is_archived_project(conn, row["project_id"]):
                    self._err(403, "该项目已归档，禁止删除"); return
                services.soft_delete(conn, table, rid, self._read_body().get("reason"))
                self._ok({"deleted": rid})
            elif method == "POST" and len(parts) == 2 and parts[1] == "restore":
                self._ok(services.restore(conn, table, int(parts[0]), self._read_body().get("reason")))
            else:
                self._err(405, "method not allowed")
        except DomainError as exc:
            self._err(403 if '已归档' in str(exc) else 409 if '父项目' in str(exc) else 400, str(exc))
        except ValueError:
            self._err(400, "invalid id")
        finally:
            conn.close()

    # ---------- 日志 ----------
    def log_message(self, fmt, *args):
        print(f"[{self.command}] {self.path} " + (fmt % args))


def main():
    init_db()
    try:
        import backup
        backup.auto_backup_if_needed()
    except Exception:
        pass
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    url = f"http://{HOST}:{PORT}"
    print(f"科技项目台账已启动：{url}")
    print("按 Ctrl+C 停止")
    # 自动打开浏览器（延迟，避免和启动抢）
    threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")


if __name__ == "__main__":
    main()

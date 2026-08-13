# -*- coding: utf-8 -*-
"""G6 安全与权限契约测试（测试先行）。

本文件冻结 G6 的对外 HTTP 约定，当前系统尚未实现认证与授权，因此每项均为
strict xfail。G6 落地时，应先移除对应 xfail，再以同一临时库完成真实回归。

约定：
1. ``POST /api/auth/login`` 接受 username/password，成功后返回 HttpOnly 会话 Cookie；
2. 角色固定为 admin（管理员）、editor（编辑员）、viewer（查阅员）；
3. viewer 只读，editor 不能执行导入、归档和恢复，admin 才能执行敏感动作；
4. 用户的 district_scope 是可见数据边界，列表和统计都必须遵守该边界。
"""

import http.client
import json

import pytest

from conftest import db_conn


def _request_with_headers(client, method, path, body=None, headers=None):
    """使用真实 HTTP 客户端发送带会话 Cookie 的请求，避免用测试替身绕过 Handler。"""
    conn = http.client.HTTPConnection("127.0.0.1", client.port, timeout=10)
    try:
        data = None
        request_headers = dict(headers or {})
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        conn.request(method, path, body=data, headers=request_headers)
        response = conn.getresponse()
        raw = response.read().decode("utf-8")
        return response.status, json.loads(raw) if raw else {}, dict(response.getheaders())
    finally:
        conn.close()


def _login(client, username, password):
    """登录并提取服务端会话；Cookie 缺失即代表会话契约未满足。"""
    status, body, headers = _request_with_headers(
        client, "POST", "/api/auth/login", {"username": username, "password": password}
    )
    assert status == 200, f"登录失败: status={status}, body={body}"
    assert body["user"]["username"] == username
    cookie = headers.get("Set-Cookie")
    assert cookie and "HttpOnly" in cookie, "登录成功但未下发 HttpOnly 会话 Cookie"
    return {"Cookie": cookie.split(";", 1)[0]}


def _create_project(client, headers, *, number, district):
    """通过管理员会话创建带区镇归属的项目，为数据范围断言准备真实业务数据。"""
    status, enterprise, _ = _request_with_headers(client, "POST", "/api/enterprises", {
        "name": f"G6企业-{district}-{number}",
        "credit_code": f"91320000G6{number:010d}",
        "enterprise_type": "高新技术企业",
        "district": district,
    }, headers)
    assert status == 200, f"创建企业失败: {enterprise}"
    status, project, _ = _request_with_headers(client, "POST", "/api/projects", {
        "name": f"G6项目-{district}-{number}",
        "project_no": f"G6-{number}",
        "enterprise_id": enterprise["id"],
        "level": "省级",
        "category": "科技成果转化",
        "total_amount": 100,
        "start_date": "2024-01-01",
        "end_date": "2024-12-31",
        "stage": "已立项",
    }, headers)
    assert status == 200, f"创建项目失败: {project}"
    return project


def test_g6_unauthenticated_requests_are_rejected_before_read_or_write(client):
    """未登录者不能读取项目/统计，也不能修改归档或发起导入。"""
    attempts = [
        ("GET", "/api/projects", None),
        ("GET", "/api/statistics", None),
        ("PUT", "/api/config", {"archived_years": ["2024"]}),
        ("POST", "/api/import", {"file_name": "unauthenticated.xlsx", "rows": []}),
    ]
    for method, path, body in attempts:
        status, response, _ = _request_with_headers(client, method, path, body)
        assert status == 401, f"未登录请求未被 401 拒绝: {method} {path}, body={response}"


def test_g6_roles_reject_viewer_and_editor_sensitive_operations(client):
    """查阅员只读；编辑员不能导入、归档、解除归档或恢复删除数据。"""
    viewer = _login(client, "g6-viewer", "g6-viewer-password")
    editor = _login(client, "g6-editor", "g6-editor-password")
    viewer_status, viewer_response, _ = _request_with_headers(
        client, "POST", "/api/enterprises", {"name": "越权企业"}, viewer
    )
    assert viewer_status == 403, f"viewer 被允许写入: {viewer_response}"
    for method, path, body in [
        ("PUT", "/api/config", {"archived_years": ["2024"]}),
        ("POST", "/api/import", {"file_name": "role.xlsx", "rows": []}),
        ("POST", "/api/projects/1/restore", {"reason": "无权恢复"}),
    ]:
        status, response, _ = _request_with_headers(client, method, path, body, editor)
        assert status == 403, f"editor 被允许执行敏感操作 {path}: {response}"


def test_g6_audit_uses_authenticated_operator_instead_of_fixed_local_user(tmp_db, client):
    """每个写操作的审计 operator 必须等于已认证用户，而不是固定占位标识。"""
    admin = _login(client, "g6-admin", "g6-admin-password")
    _create_project(client, admin, number=1, district="开发区")
    conn = db_conn(tmp_db)
    try:
        row = conn.execute(
            "SELECT operator, action FROM audit_log WHERE object_type='project' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()
    assert row and row["operator"] == "g6-admin", f"审计操作者不可追溯: {dict(row) if row else None}"
    assert row["operator"] != "local-user", "审计仍使用固定 local-user 占位符"


def test_g6_project_list_and_statistics_only_return_authorized_district_scope(client):
    """区镇查阅员只能看到授权区镇的项目，统计金额与数量也不得汇入越权项目。"""
    admin = _login(client, "g6-admin", "g6-admin-password")
    allowed = _create_project(client, admin, number=2, district="开发区")
    hidden = _create_project(client, admin, number=3, district="高新区")
    reader = _login(client, "g6-devzone-viewer", "g6-viewer-password")

    status, projects, _ = _request_with_headers(client, "GET", "/api/projects", headers=reader)
    assert status == 200
    visible_ids = {project["id"] for project in projects}
    assert allowed["id"] in visible_ids and hidden["id"] not in visible_ids, "项目列表泄漏区镇外数据"

    status, statistics, _ = _request_with_headers(client, "GET", "/api/statistics?by=district", headers=reader)
    assert status == 200
    assert {item["key"] for item in statistics} == {"开发区"}, "统计结果包含未授权区镇"

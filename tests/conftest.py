# -*- coding: utf-8 -*-
"""pytest 公共夹具（G0 基线，2026-08-13）

职责（三条硬约束，对应 PLAN G0-2「以独立临时数据库运行测试」）：

1. 临时数据库隔离：
   将 app.DB_PATH 重定向到 pytest 的临时目录，所有测试写库都发生在
   临时库里，绝不触碰正式库 data/project.db（正式库路径由本模块
   读取 app 的原始模块常量得到，测试期间不随 monkeypatch 改变）。

2. 端到端 HTTP 客户端：
   在后台线程启动真实的 http.server（复用 app.Handler），用标准库
   http.client 发送真实 HTTP 请求，完整复现浏览器 → app.py 的调用路径，
   使失败复现测试能真实打到当前业务代码（而非测试替身）。

3. 会话级哈希守卫：
   pytest 会话开始前记录正式库 data/project.db 的 SHA-256，会话结束后
   再次计算并对比。任何测试若直接或间接改动正式库，会话结束时立即
   报错退出——保证「测试执行过程不得改变正式数据库文件的哈希值」
   （PLAN G0 验收）这条红线在每一次测试运行中都被自动验证。
"""

import hashlib
import http.client
import json
import os
import sqlite3
import sys
import threading
from http.server import ThreadingHTTPServer

import pytest

# 项目根目录（tests/ 的上一级）——保证 `import app` 等模块可直接导入
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ["LEDGER_AUTH_ENABLED"] = "1"
import app  # noqa: E402  （必须在 sys.path 就绪后导入）


# ---------------------------------------------------------------------------
# 会话级守卫：正式库 SHA-256 前后对比
# ---------------------------------------------------------------------------
# 注意：必须用 app 模块常量在「被 monkeypatch 之前」的原始值，
#       这里在模块导入时立即取值，测试运行中 app.DB_PATH 被重定向也不受影响。
OFFICIAL_DB = os.path.join(app.BASE_DIR, "data", "project.db")

_official_sha_before = None


def _sha256(path):
    """计算文件 SHA-256（分块读取，避免一次性载入大文件）。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def pytest_sessionstart(session):
    """记录正式库的会话前哈希。"""
    global _official_sha_before
    if os.path.exists(OFFICIAL_DB):
        _official_sha_before = _sha256(OFFICIAL_DB)


def pytest_sessionfinish(session, exitstatus):
    """会话结束后校验正式库哈希未变，变了则直接报错。"""
    if os.path.exists(OFFICIAL_DB):
        after = _sha256(OFFICIAL_DB)
        if _official_sha_before is not None and after != _official_sha_before:
            raise AssertionError(
                "测试会话期间正式库 data/project.db 被改动！\n"
                f"  会话前 SHA-256: {_official_sha_before}\n"
                f"  会话后 SHA-256: {after}\n"
                "  违反 PLAN G0 验收：测试不得改变正式数据库文件哈希。"
            )


# ---------------------------------------------------------------------------
# 夹具：临时数据库
# ---------------------------------------------------------------------------
@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """把 app.DB_PATH 指向临时目录，并基于真实 schema.sql 建库。

    返回临时库路径（pathlib.Path）。测试结束自动清理（tmp_path 生命周期）。
    """
    db_path = tmp_path / "test_ledger.db"
    monkeypatch.setattr(app, "DB_PATH", str(db_path))
    # SCHEMA_PATH 保持指向真实 schema.sql，保证测试库结构与正式库一致
    app.init_db()
    return db_path


# ---------------------------------------------------------------------------
# 极简 HTTP 客户端
# ---------------------------------------------------------------------------
class SimpleClient:
    """针对 app.Handler 的极简 JSON HTTP 客户端。

    用法：client.request("POST", "/api/projects", {...json body...})
    返回 (status, parsed_json)。
    服务端线程异常（如未捕获的 sqlite3.IntegrityError 导致连接被重置）
    统一折叠为 (599, {"error": "connection failed"})，让测试可以断言
    「非 2xx」而不至于被底层异常中断。
    """

    def __init__(self, port):
        self.port = port
        # 既有 G0-G5 回归测试描述的是业务规则而非匿名访问，因此统一以管理员会话
        # 调用，避免登录门禁掩盖原有领域断言。G6 的匿名断言使用独立原生 HTTP
        # 辅助函数，不经过本客户端，仍会真实得到 401。
        self._cookie = self._login_as_admin()

    def _login_as_admin(self):
        """启动夹具时建立一次管理员会话，并将 Cookie 自动附加到旧测试请求。"""
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            body = json.dumps({"username": "g6-admin", "password": "g6-admin-password"}).encode("utf-8")
            conn.request("POST", "/api/auth/login", body=body, headers={"Content-Type": "application/json"})
            response = conn.getresponse()
            response.read()
            assert response.status == 200, "测试管理员登录失败"
            return response.getheader("Set-Cookie").split(";", 1)[0]
        finally:
            conn.close()

    def request(self, method, path, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            data = None
            headers = {"Cookie": self._cookie}
            if body is not None:
                data = json.dumps(body, ensure_ascii=False).encode("utf-8")
                headers["Content-Type"] = "application/json"
            conn.request(method, path, body=data, headers=headers)
            resp = conn.getresponse()
            raw = resp.read().decode("utf-8")
            try:
                parsed = json.loads(raw) if raw else {}
            except ValueError:
                parsed = {"raw": raw}
            return resp.status, parsed
        except (http.client.HTTPException, ConnectionError, OSError):
            # 服务端线程异常导致连接被重置：折叠为 599，保留「被拒绝」语义
            return 599, {"error": "connection failed"}
        finally:
            conn.close()


@pytest.fixture
def client(tmp_db):
    """在后台线程启动真实 app 服务，返回 SimpleClient。"""
    server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    yield SimpleClient(port)
    server.shutdown()
    thread.join(timeout=5)
    server.server_close()


# ---------------------------------------------------------------------------
# 通用辅助：查询临时库（测试内断言数据库实际写入情况用）
# ---------------------------------------------------------------------------
def db_conn(db_path):
    """打开临时库连接（Row 工厂），测试用完后自行 close。"""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn

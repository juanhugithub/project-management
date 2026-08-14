# -*- coding: utf-8 -*-
"""G8N 远程 MCP 边界契约：仅在进程内请求，不启动监听端口或公网服务。"""

import asyncio
import json

import httpx
import pytest

from remote_mcp import RemoteMCPConfigurationError, create_application, load_config


def _request(app, method, path="/mcp", **kwargs):
    """用 ASGI 传输验证拒绝路径，避免测试启动真实端口或公网服务。"""
    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8001") as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(run())


def _config(tmp_path, **extra):
    values = {
        "REMOTE_MCP_BIND": "127.0.0.1",
        "REMOTE_MCP_API_TOKEN": "a" * 43,
        "REMOTE_MCP_AUDIT_LOG": str(tmp_path / "mcp-access.jsonl"),
    }
    values.update(extra)
    return load_config(values)


def test_public_bind_rejects_missing_tls_or_strong_token(tmp_path):
    """公网绑定不可因漏配 TLS 标记或弱 Token 而启动。"""
    with pytest.raises(RemoteMCPConfigurationError, match="TLS"):
        _config(tmp_path, REMOTE_MCP_BIND="0.0.0.0")
    with pytest.raises(RemoteMCPConfigurationError, match="随机"):
        _config(tmp_path, REMOTE_MCP_BIND="0.0.0.0", REMOTE_MCP_TLS_TERMINATED="1", REMOTE_MCP_PUBLIC_HOST="mcp.example.test", REMOTE_MCP_API_TOKEN="short")


def test_remote_mcp_rejects_missing_or_wrong_token(tmp_path):
    """配置了 API Token 后，未经认证的 MCP 请求绝不能进入工具服务。"""
    app = create_application(_config(tmp_path))
    assert _request(app, "GET").status_code == 401
    assert _request(app, "GET", headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_public_mcp_requires_https_proxy_header_before_mcp_request(tmp_path):
    """公网模式只接受反向代理明确声明的 HTTPS 请求。"""
    config = _config(tmp_path, REMOTE_MCP_BIND="0.0.0.0", REMOTE_MCP_TLS_TERMINATED="1", REMOTE_MCP_PUBLIC_HOST="mcp.example.test")
    app = create_application(config)
    headers = {"Authorization": "Bearer " + "a" * 43}
    assert _request(app, "GET", headers=headers).status_code == 426


def test_remote_mcp_discovers_only_read_tools_and_audits_tool_name(tmp_path):
    """远程承载的是原有全只读工具；审计行不含调用参数或 Token。"""
    async def run():
        app = create_application(_config(tmp_path))
        headers = {
            "Authorization": "Bearer " + "a" * 43,
            "X-Client-Id": "report-agent-a",
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        initialize = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "contract-test", "version": "1"}}}
        async with app.app.router.lifespan_context(app.app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8001") as client:
                response = await client.post("/mcp", json=initialize, headers=headers)
                assert response.status_code == 200
                listed = await client.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}, headers=headers)
                assert listed.status_code == 200
                payload = listed.json()
                names = {tool["name"] for tool in payload["result"]["tools"]}
                assert {"list_reporting_templates", "build_template_dataset", "validate_filled_template"} <= names
                assert not any(any(word in name.lower() for word in ("create", "update", "delete", "write", "register")) for name in names)
                call = {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "list_reporting_templates", "arguments": {"secret": "must-not-appear"}}}
                assert (await client.post("/mcp", json=call, headers=headers)).status_code == 200

    asyncio.run(run())
    audit_lines = (tmp_path / "mcp-access.jsonl").read_text(encoding="utf-8").splitlines()
    audit = json.loads(audit_lines[-1])
    assert audit["tool"] == "list_reporting_templates" and audit["client"] == "report-agent-a"
    assert "secret" not in audit_lines[-1] and "a" * 43 not in audit_lines[-1]

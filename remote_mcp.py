#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""科技项目台账的 Streamable HTTP MCP 入口。

此模块只负责网络边界、认证与最小审计；业务工具仍只在 ``mcp_server`` 中声明。
默认仅监听回环地址。要暴露到公网，必须由 HTTPS 反向代理终止 TLS，并同时明确
设置非回环绑定地址、强 API Token 和 ``REMOTE_MCP_TLS_TERMINATED=1``。
"""

import hmac
import json
import os
import re
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable

import uvicorn
from mcp.server.transport_security import TransportSecuritySettings

BASE_DIR = Path(__file__).resolve().parent
LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}
TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43,}$")


class RemoteMCPConfigurationError(ValueError):
    """远程 MCP 的网络配置不满足上线安全条件。"""


@dataclass(frozen=True)
class RemoteMCPConfig:
    """启动配置；API Token 仅从环境变量读取，绝不写入仓库或审计日志。"""

    bind: str
    port: int
    api_token: str | None
    tls_terminated: bool
    public_host: str | None
    audit_log: Path

    @property
    def public_bind(self) -> bool:
        """非回环绑定即视为会接收外部网络流量。"""
        return self.bind.lower() not in LOOPBACK_HOSTS


def load_config(env: dict[str, str] | None = None) -> RemoteMCPConfig:
    """读取并校验环境变量，拒绝以不完整安全条件启动公网服务。"""
    values = os.environ if env is None else env
    bind = values.get("REMOTE_MCP_BIND", "127.0.0.1").strip()
    token = values.get("REMOTE_MCP_API_TOKEN", "").strip() or None
    try:
        port = int(values.get("REMOTE_MCP_PORT", "8001"))
    except ValueError as error:
        raise RemoteMCPConfigurationError("REMOTE_MCP_PORT 必须是整数") from error
    if not 1 <= port <= 65535:
        raise RemoteMCPConfigurationError("REMOTE_MCP_PORT 必须在 1 至 65535 之间")

    config = RemoteMCPConfig(
        bind=bind,
        port=port,
        api_token=token,
        tls_terminated=values.get("REMOTE_MCP_TLS_TERMINATED") == "1",
        public_host=values.get("REMOTE_MCP_PUBLIC_HOST", "").strip() or None,
        audit_log=Path(values.get("REMOTE_MCP_AUDIT_LOG", BASE_DIR / "data" / "mcp_access.log")),
    )
    if config.public_bind:
        if "REMOTE_MCP_BIND" not in values:
            raise RemoteMCPConfigurationError("公网部署必须显式设置 REMOTE_MCP_BIND")
        if not config.tls_terminated:
            raise RemoteMCPConfigurationError("公网部署必须设置 REMOTE_MCP_TLS_TERMINATED=1")
        if not config.public_host:
            raise RemoteMCPConfigurationError("公网部署必须设置 REMOTE_MCP_PUBLIC_HOST")
        if not token or not TOKEN_PATTERN.fullmatch(token):
            raise RemoteMCPConfigurationError(
                "公网部署必须设置至少 43 位 URL-safe 随机 REMOTE_MCP_API_TOKEN"
            )
    return config


class AccessAuditLog:
    """仅保存工具名、客户端标识和 UTC 时间，刻意不记录参数、Token 或台账数据。"""

    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()

    def append(self, tool_name: str, client_id: str) -> None:
        record = {
            "at": datetime.now(timezone.utc).isoformat(),
            "tool": tool_name,
            "client": client_id[:128],
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


def _headers(scope: dict) -> dict[str, str]:
    return {key.decode("latin-1").lower(): value.decode("latin-1") for key, value in scope["headers"]}


def _tool_name(body: bytes) -> str | None:
    """只提取 MCP tools/call 的工具名，不读取或持久化任何 arguments。"""
    try:
        request = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if request.get("method") != "tools/call":
        return None
    name = request.get("params", {}).get("name")
    return name if isinstance(name, str) else "unknown"


async def _read_body(receive: Callable[[], Awaitable[dict]]) -> bytes:
    chunks: list[bytes] = []
    while True:
        message = await receive()
        if message["type"] != "http.request":
            return b"".join(chunks)
        chunks.append(message.get("body", b""))
        if not message.get("more_body", False):
            return b"".join(chunks)


def _replay_body(body: bytes) -> Callable[[], Awaitable[dict]]:
    sent = False

    async def receive() -> dict:
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    return receive


class RemoteSecurityBoundary:
    """在 MCP ASGI 应用外建立认证、TLS 代理校验和工具访问审计边界。"""

    def __init__(self, app: Callable, config: RemoteMCPConfig, audit_log: AccessAuditLog):
        self.app = app
        self.config = config
        self.audit_log = audit_log

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = _headers(scope)
        if self.config.public_bind and headers.get("x-forwarded-proto", "").lower() != "https":
            await self._reject(send, 426, b"HTTPS reverse proxy header is required")
            return
        if self.config.api_token:
            supplied = headers.get("authorization", "")
            expected = f"Bearer {self.config.api_token}"
            if not hmac.compare_digest(supplied, expected):
                await self._reject(send, 401, b"MCP API token is required", {b"www-authenticate": b"Bearer"})
                return

        body = await _read_body(receive)
        tool = _tool_name(body)
        if tool is not None:
            # 客户端标识由接入方配置；不退化为 IP，避免把网络身份写入审计文件。
            self.audit_log.append(tool, headers.get("x-client-id", "anonymous"))
        await self.app(scope, _replay_body(body), send)

    @staticmethod
    async def _reject(send: Callable, status: int, body: bytes, extra: dict[bytes, bytes] | None = None) -> None:
        headers = [(b"content-type", b"text/plain; charset=utf-8"), (b"cache-control", b"no-store")]
        headers.extend((extra or {}).items())
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": body})


def create_application(config: RemoteMCPConfig | None = None) -> RemoteSecurityBoundary:
    """创建 Streamable HTTP 应用，工具集合复用既有且仅有只读的 MCP 声明。"""
    from mcp_server import create_streamable_http_app

    active_config = config or load_config()
    transport_security = None
    if active_config.public_bind:
        host = active_config.public_host
        transport_security = TransportSecuritySettings(
            allowed_hosts=[host, f"{host}:443"],
            allowed_origins=[f"https://{host}"],
        )
    return RemoteSecurityBoundary(
        create_streamable_http_app(transport_security, remote=True), active_config, AccessAuditLog(active_config.audit_log)
    )


def main() -> None:
    """运行 HTTP 服务；真实公网发布前仍需按部署文档配置反向代理和防火墙。"""
    config = load_config()
    uvicorn.run(create_application(config), host=config.bind, port=config.port, proxy_headers=False)


if __name__ == "__main__":
    main()

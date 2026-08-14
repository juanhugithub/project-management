# G8N：远程 MCP 安全部署

本服务通过 MCP Streamable HTTP 提供现有**全部只读**项目、企业、资金、风险和模板工具，供合规 Agent 进行文字起草与表格填报。它不提供任何正式台账写入、导入确认或衍生稿登记工具。

## 安全边界

- 默认只监听 `127.0.0.1:8001`，不接受网络客户端。
- 公网绑定必须显式设置 `REMOTE_MCP_BIND`、`REMOTE_MCP_PUBLIC_HOST`、`REMOTE_MCP_TLS_TERMINATED=1` 以及至少 43 位 URL-safe 随机 `REMOTE_MCP_API_TOKEN`；漏任一项即拒绝启动。
- 公网模式每个请求必须同时携带 `Authorization: Bearer <token>` 和由可信反向代理写入的 `X-Forwarded-Proto: https`。缺失或非 HTTPS 请求会被拒绝。
- 审计日志默认写入 `data/mcp_access.log`，每行只含 UTC 时间、工具名与 `X-Client-Id`；不写 Token、工具参数、项目数据或客户端 IP。
- MCP 返回数据仍执行软删除和年度归档过滤。模板数据集也复用该可见性边界。

API Token 请在目标主机生成，不要保存在仓库、批处理文件、文档截图或 Agent 提示词中：

```text
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

## 本机启动

仅供同机 Agent 使用时，可不设置 Token：

```text
cd /d "E:\Reasonix WorkSpace\科技项目台账"
python -X utf8 remote_mcp.py
```

建议即使本机联调也设置 Token：

```text
set REMOTE_MCP_API_TOKEN=<本机随机Token>
python -X utf8 remote_mcp.py
```

MCP 地址为 `http://127.0.0.1:8001/mcp`。生产环境不得直接将此 HTTP 地址暴露给互联网。

## 公网部署示例（仅示例，不在本项目中自动执行）

在服务进程环境中设置：

```text
REMOTE_MCP_BIND=0.0.0.0
REMOTE_MCP_PORT=8001
REMOTE_MCP_PUBLIC_HOST=mcp.example.gov.cn
REMOTE_MCP_TLS_TERMINATED=1
REMOTE_MCP_API_TOKEN=<使用 secrets.token_urlsafe(32) 生成的值>
REMOTE_MCP_AUDIT_LOG=D:\mcp-audit\access.jsonl
```

反向代理负责对外监听和 TLS 终止，并将 `X-Forwarded-Proto: https` 传给后端。MCP 进程使用非回环绑定时，防火墙只能允许反向代理访问该端口；`REMOTE_MCP_PUBLIC_HOST` 同时作为 SDK 的 Host 白名单，不能填 IP 或未知域名。

Nginx 参考配置：

```nginx
location /mcp {
    proxy_pass http://127.0.0.1:8001/mcp;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Client-Id $http_x_client_id;
    proxy_set_header Authorization $http_authorization;
    proxy_set_header Connection "";
    proxy_buffering off;
}
```

反向代理必须覆盖而非信任外部传入的 `X-Forwarded-Proto`，并在自身完成证书校验、访问控制和请求大小限制。示例不是可直接上线的完整防火墙或证书配置。

Docker 示例仅用于隔离运行环境，数据库和审计目录必须使用受控宿主机卷，不能打入镜像：

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements-mcp.txt .
RUN pip install --no-cache-dir -r requirements-mcp.txt
COPY . .
CMD ["python", "-X", "utf8", "remote_mcp.py"]
```

## Agent 接入规则

Agent 通过 `tools/list` 发现只读工具，其中包括 `list_reporting_templates`、`get_template_schema`、`build_template_dataset` 与 `validate_filled_template`。Agent 可以据此生成报告或填写表格，但不得把生成稿当作正式台账事实；任何正式变更仍须在既有人工确认流程中完成。

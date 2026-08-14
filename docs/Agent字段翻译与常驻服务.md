# Agent 字段翻译与常驻服务

## 开机常驻

安装版会为当前 Windows 用户写入“科技项目台账”开机启动项，启动命令带有 `--resident`，只启动后台 HTTP 服务，不自动弹出浏览器。卸载程序时应同时清理该启动项；数据目录和数据库不删除。

源码环境可执行：

```text
python resident_service.py install
python resident_service.py remove
python resident_service.py run
```

## 字段翻译

Agent 先调用 `get_standard_field_dictionary` 了解标准字段，再调用 `suggest_field_mapping(headers)` 生成候选。出现 `manual_review` 时由人工确认目标字段，随后把确认后的 `mapping` 传给 `translate_external_rows(rows, mapping)`。

翻译结果只是标准化数据集，不会直接写入项目、企业、资金或节点表。正式入账仍通过网页导入预览和人工确认完成。

## 网络边界

本地服务常驻不等于公网可达。手机远程访问需要在本机前放置 HTTPS 反向代理或国内 VPS 反向隧道，并使用 Token；不上传数据库，也不开放 SQLite 文件端口。电脑关机后，手机无法访问本地唯一事实源。

当前不启用公网隧道。无需购买 VPS 或域名时，优先使用同一台电脑上的本地 MCP stdio 接入，或让本机 Agent 访问 `http://127.0.0.1:8001/mcp`。公网部署配置文件和代码会保留，后续只需补齐 VPS、域名和证书配置。

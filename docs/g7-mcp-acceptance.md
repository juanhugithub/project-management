# G7 MCP 只读一致性验收

## 范围

- MCP 仅注册十个查询工具：项目、企业、资金、节点、提醒、统计、勾稽和搜索。
- 不提供新增、修改、删除、恢复、导入或归档等写工具。
- 项目列表与项目详情复用 `ledger.queries` 的 `planned_total`、`disbursed_total`、`received_total` 资金口径。

## 可见性规则

- `is_deleted=1` 的企业、项目、资金和节点不返回。
- `system_config.archived_years` 中项目开始年度的数据默认不返回。
- 资金、节点、提醒、统计、勾稽、企业聚合和搜索均通过其所属项目应用同一可见性规则。
- 不存在、软删除或归档项目统一返回“项目不存在或当前不可见”，避免把底层 SQL 异常泄露给 MCP 调用方。

## 验收命令

```text
python -X utf8 -m pytest tests/test_g7_mcp_contract.py -q
python -X utf8 -m pytest -q
python -X utf8 scripts/check.py
```

所有测试仅使用 pytest 创建的临时 SQLite 数据库；正式 `data/project.db` 不执行迁移或写入。

# G9 模板任务与衍生稿契约

模板是面向 Agent 的版本化业务协议，而不是 SQLite 表结构的镜像。当前固定提供：

- `quarterly_funding_execution@1.0.0`：季度资金执行表；以资金计划日期和实际日期截至季度末计算计划、已拨、已到账额。
- `acceptance_risk_list@1.0.0`：验收风险清单；以待验收阶段或未完成验收节点的明确日期判定风险。

`ledger.templates.build_template_dataset` 的参数、行顺序、字段和快照哈希均为确定性结果。返回中包含 `source_project_ids` 与 `snapshot_hash`；模型必须以此为文字或表格工作的事实依据。

`validate_filled_template` 只校验模板字段和必填项，不会猜测、补齐或改写 Agent 输出。`register_derivative_draft` 仅写入衍生稿登记，并保存模板版本、MCP 参数、数据快照哈希、来源项目、Agent/模型、人工状态和导出路径；它不写入正式项目台账。

当前数据层不开放任何 MCP 或 HTTP 路由，路由集成属于 G8/G9 的其他明确所有者。

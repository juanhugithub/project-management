# G8：版本化 MCP 业务契约

## 目标

MCP 是科技项目台账面向 Agent 的公共只读业务接口，而不是 SQLite 表的镜像。Agent 可据此生成汇报、说明和表格草稿，但不能通过 MCP 写入正式台账。

## 公共结果信封（v1.0）

所有 G8 业务工具返回下列外层字段：

- `contract_version`：当前为 `1.0`；未来不兼容调整将提升主版本。
- `generated_at`：本次取数生成时间，带本机时区偏移。
- `filters`：调用方实际使用的筛选条件。
- `data_scope`：默认仅包括未软删除且未归档年度的项目及关联事实。
- `money_semantics`：金额单位、精度，以及计划/已拨/到账的确定义。
- `data`：本工具的业务事实数据。

金额单位均为万元；`planned_total` 是有应拨日期的资金金额合计，`disbursed_total` 是状态为已拨付或已到账的合计，`received_total` 是已到账合计。

## G8 工具

| 工具 | 用途 | 主要输入 |
|---|---|---|
| `get_project_fact_sheet` | 单项目事实包，含企业、资金、节点和统一金额口径 | `project_id` |
| `list_acceptance_risks` | 验收/结题临期或逾期清单 | `days`、`district` |
| `get_funding_execution_dataset` | 可直接用于资金执行表的项目行和汇总 | `year`、`district`、`level` |
| `list_projects_missing_identity` | 项目编号待补治理清单 | `district` |
| `list_composite_risks` | 验收风险、编号待补和资金勾稽不一致的组合清单 | `days`、`district` |

旧有原子查询工具继续保留兼容期。任何返回项目的数据集都不包含软删除项目或年度归档项目；未找到或不可见项目的事实包返回 `data.found=false`，而不泄露底层记录。

## 远程承载边界

本阶段只定义 stdio MCP 的业务契约，未新增网络监听、网络认证、令牌或公网服务。后续 **G8N** 负责远程承载、访问认证、传输加密、限流和运维部署；即使转为互联网访问，G8 工具仍保持只读。

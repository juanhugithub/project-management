# 版本化 SQLite 迁移设计（G1）

本文件是迁移实施契约，不执行迁移，也不修改正式库。正式 `data/project.db` 当前仍为 `user_version=0` 的基线库；G2 获授权后才可以实现并执行迁移。

## 版本与完成标记

- `PRAGMA user_version` 保存已成功应用的最高连续迁移号。
- 新增 `schema_migration`：`migration_no INTEGER PRIMARY KEY`、`name TEXT NOT NULL`、`applied_at TEXT NOT NULL`、`report_sha256 TEXT NOT NULL`。完成标记与结构变更在同一事务提交，禁止仅更新其中之一。
- 迁移文件按固定编号、不可修改：`M001_money_cents`、`M002_project_business_key_and_state`、`M003_soft_delete_and_audit`、`M004_import_batches_and_operation_config`。已发布迁移绝不重写；新增修正必须使用新编号。

## 目标结构与迁移次序

| 迁移 | 内容 | 前置预检 |
|---|---|---|
| M001 | 金额真值改为非负整数分；展示层统一换算万元 | 金额可精确换算为两位小数 |
| M002 | 项目必须有企业、企业信用代码非空唯一、项目 `(project_no, enterprise_id)` 唯一；加入状态合法性与流转保护 | 无企业、空编号自动入账、重复组合键、非法阶段必须逐条列出 |
| M003 | 企业/项目/资金/节点增加 `is_deleted`、`deleted_at`、`deleted_reason`；新建 `audit_log` | 现有引用和归档记录完整 |
| M004 | 新建 `import_batch`、`import_staging_row`、`system_operation_config` | 无未决导入批次冲突 |

`audit_log` 至少记录：对象类型/ID、操作、操作者、时间、来源批次、理由、前后摘要。
`import_batch` 保存原文件 SHA-256、原文件名、映射版本、状态和汇总；`import_staging_row` 保存行号、原始数据、校验结论。
`system_operation_config` 保存迁移和高风险操作所需的明确配置；它不替代审计日志。

## 执行协议

1. 先对正式库执行 `.vibe/evidence/g1-preflight-check.py`；完整性、外键、哈希守卫和所有阻断项必须通过。否则停止并输出报告，绝不自动修改数据。
2. 用 SQLite online backup API 制作带 SHA-256 的只读可验证快照；在副本演练成功前不得对正式库执行迁移。
3. 每个迁移在单一 `BEGIN IMMEDIATE` 事务中执行：验证当前 `user_version` 与 `schema_migration` 连续性 → DDL/DML → 再校验 → 写迁移报告摘要与完成标记 → 设置 `user_version` → `COMMIT`。
4. 任一步失败必须 `ROLLBACK`，并输出迁移号、失败检查、事务是否回滚、正式库前后 SHA-256；不得部分提交、不得跳过迁移、不得静默降级。

## 升级、回滚和不可降级恢复

- **升级：** 只能按编号连续执行；每一步都生成独立报告，且先在副本上通过完整性/外键/关键查询验证。
- **失败回滚：** 未提交时使用事务回滚，保留失败报告；不把任何失败版本写入完成标记。
- **已提交迁移不可降级：** SQLite DDL 不提供可靠通用降级。恢复方法是停止服务，保留当前库，使用迁移前在线备份恢复到副本，执行 `integrity_check`、关键表计数和抽样查询；仅由 HUMAN 决定是否以已验证副本替换正式库。恢复本身必须记录审计与操作报告。

## 禁止自动处理

不自动补项目编号、不按名称合并企业/项目、不自动修正金额或日期、不删除重复记录、不恢复中止/撤销项目、不改变归档年度。任何预检违规均进入 HUMAN 决策清单。

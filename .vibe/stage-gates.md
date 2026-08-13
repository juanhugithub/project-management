# Stage Gates

## Current phase

**G0 已完成（2026-08-13），下一授权阶段 G1，等待 HUMAN 三项决策**：
PLAN.md 已获确认，「确认后第一项实施任务」（G0-1 至 G0-4：Git 基线、tests/、
失败复现测试、scripts/check.py）及 .vibe 治理同步均已交付并通过验收
（`python scripts/check.py` 全部通过、正式库哈希不变）。
**注意：G1~G7 尚未开始，不得视为已完成。** 原「阶段 1–5」为历史演进记录，
phase-5-harden（备份/Excel 导入/错误处理）功能已实现，标记为 completed；
其遗留缺陷（P0-01~P0-04，见 tests/test_regressions.py 6 项 xfail(strict=True)）
按 PLAN 归属 G2/G3/G4 修复，须先经 G1 决策后授权，故 G1 保持 pending、
不进入 G2。当前 task-graph 无 in_progress 任务。

## Entry evidence（阶段 1–2 起点）

- 用户确认全部关键决策：本地轻量工具、单人、A 方案、第一版含 MCP、官方 `mcp` SDK、字段清单（删信用等级/增区镇/增联系人手机号/增重大事项变更）、类别可配置。

## Exit conditions

- **阶段 1**：能启动的空系统 + 5 张表 + 31 条种子数据 + 查询层。✅
- **阶段 2**：一条「录入→查全貌」端到端链路可用。✅
- **阶段 3**：全部 6 个视图可用（提醒/勾稽/报表/画像/配置）。✅
- **阶段 4**：AI 工具通过只读 MCP 读库填表。✅
- **阶段 5**：备份/Excel 导入/错误处理，可日常使用。

## Completed evidence

- 数据库：`schema.sql` 建 5 表 + 31 条种子（category 3 / district 11 / enterprise_type 4 / funding_source 3 / level 4 / node_type 6）✓
- 后端 `app.py`：语法 `py_compile` 通过 ✓；API 端到端测试 15 项全部通过（14 PASS + 1 项测试断言写错复核 PASS）✓
- 前端 `static/`：`node --check` 通过 ✓；首页/静态资源 HTTP 200 ✓
- 干净库重建：企业 0 / 项目 0 / 字典 31 ✓
- 治理文件：charter / acceptance / domain-model / architecture / task-graph 就绪 ✓
- **阶段 3 验证**：提醒分级（overdue/red/yellow，30 天外过滤，排除已完成）✓；资金勾稽核对（正常/异常双测）✓；统计 6 维度（level/category/stage/year/enterprise/source）✓；配置管理（新增/重复拦截/停用/启用）✓；企业画像接口 ✓；阶段 3 测试 19 项中 18 PASS + 1 项（yellow 未覆盖，补 15 天后节点后 ALL PASS）✓
- **阶段 4 验证**：mcp_server.py 10 个只读工具（list_projects/get_project/list_enterprises/get_enterprise/list_fundings/list_nodes/get_reminders/get_stats/get_funding_check/search）经官方 mcp SDK 客户端连接测试，无任何写工具，各工具调用返回正确（ALL PASS）✓；MCP 接入指南已交付 ✓
- **迭代验证（2026-08-13）**：① 首页工作台（/api/dashboard 聚合 + 卡片 + 待办）✓；② 资金拨付执行度（/api/funding-plan，应拨vs实拨 + 该拨未拨，语义修正：仅"已过期"计逾期，今天到期不算）✓；③ 年度归档冻结（system_config + 配置界面归档/解除 + 后端 403 拦截 + 前端禁用，12 项测试 10 PASS + 2 项语义修正后 ALL PASS）✓；④ 自动备份（启动时每日一次，实测生成）✓；⑤ Excel 导入升级单表自动拆分 + 下载模板 + 拖拽导入 ✓；⑥ 高级筛选/区镇筛选/导出当前结果 ✓；⑦ start.bat/backup.bat GBK 编码修复（双击打不开问题）✓

## Blockers and open decisions

- **已复现问题（P0-01 ~ P0-04，对应 tests/test_regressions.py 6 项 xfail(strict=True)）**：
  - P0-01 资金口径分歧（dashboard 的 funded_total 只算『已到账』，项目列表
    的 funded_total 算全部资金，同一字段两种语义）；
  - P0-02 非法金额文本静默转 NULL、任意阶段可写入、无承担企业项目可写入；
  - P0-03 归档年度仍可新建项目（PUT/DELETE 已拦，POST 未拦）；
  - P0-04 Excel 导入逐行写入、部分提交。
  上述问题按 PLAN 归属 G2/G3/G4 修复，本轮（G0）只复现、不修复。
- 待用户确认：各字典初始种子值是否够用（可自助增补，不阻塞）。
- 待用户确认：附件/文档关联能力是否纳入（暂不含，不阻塞）。
- G1 起需 HUMAN 确认的三项决策：资金记录是否拆分计划/实际、项目业务唯一键、
  状态机流转规则（PLAN §4 G1）。

## Next authorized phase

G1（领域契约确认与迁移设计）。G0 已验收通过（`python scripts/check.py` 与
vibe 校验全部通过、正式库哈希不变）；当前等待 HUMAN 确认 G1 三项决策，
确认后方可进入 G1 实施。

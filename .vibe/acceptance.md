# Acceptance Contract

> 验收项详见 `../设计方案.md` 第 3 节（A1–A8），本文件为执行与验证记录。

## Golden-path scenario

录入企业 → 录入项目（选承担企业/层级/类型/阶段）→ 录入资金（来源/金额/批次/到账）→ 录入节点（类型/计划时间）→ 查看项目详情全貌（企业+资金+节点+下一节点）→ 筛选/搜索 → （阶段 3 起）提醒、勾稽、统计 → （阶段 4 起）AI 读库填表。

## Functional acceptance

| # | 标准 | 状态 |
|---|---|---|
| A1 | 项目全貌几秒可查 | ✅ 阶段2 已实现（详情接口含企业+资金+节点） |
| A2 | 企业画像 | ✅ 列表含项目数/累计金额；详情接口含项目列表 |
| A3 | 资金勾稽对得上、汇总不出错 | ✅ 勾稽核对面板存在（详情页 fund-check + /api/funding-check）；⚠️ P0-01 口径统一属 G2 |
| A4 | 节点到期主动提醒不漏 | ✅ 提醒视图（overdue/红/黄分级，30/60/90/365 天窗口） |
| A5 | 单文件备份即恢复 | 🔜 部分实现（backup.py 一键/自动备份已存在）；在线备份校验、恢复演练属 G5 |
| A6 | 低配电脑流畅 | ✅ 技术选型保证（标准库+SQLite+原生JS） |
| A7 | MCP 只读出口 | ✅ 工具已实现（10 个只读工具，mcp_server.py）；G7 契约测试与口径统一待补 |
| A8 | 配置界面自助增/停用 | ✅ 配置管理视图（新增/停用/启用，停用不影响历史） |

## Quality requirements

- **确定性**：资金勾稽、节点提醒为纯规则计算，无 AI 参与、无启发式。
- **性能**：启动 1~2 秒、内存几十 MB、点击瞬时响应（A6）。
- **数据安全**：纯本地存储；MCP 只读不写（A7）。
- **可维护**：标准库、零依赖核心，好交接。

## Safety and irreversible operations

- 删除项目：级联删除其资金/节点记录（前端二次确认）。
- 删除企业：其下项目 `enterprise_id` 置空（保留项目）。
- 配置字典值：只**停用**（`is_active=0`）不物理删除，保护历史引用。
- 以上均为用户主动操作，前端均有确认。

## Verification commands

```bash
cd "E:/Reasonix WorkSpace/科技项目台账"
python scripts/check.py            # G0 统一检查：Python/Node 语法 + pytest + SQLite 只读完整性 + SHA 守卫 + .vibe 校验
python -m py_compile app.py        # 后端语法（check.py 已含，保留历史）
node --check static/app.js         # 前端语法（check.py 已含，保留历史）
python app.py                      # 启动 → 浏览器 http://127.0.0.1:8765
```

API 冒烟：临时测试脚本覆盖 企业/项目/资金/节点 CRUD + 详情 + 筛选 + 更新 + 删除（15 项，14 PASS + 1 项断言写错复核 PASS）。

## Required evidence

- 数据库：5 张表 + 31 条种子数据（已验证）。
- 端到端 API 测试：15 项全部通过（含复核）。
- 语法检查：`py_compile` / `node --check` 均通过。
- 干净库已重建（企业 0 / 项目 0 / 字典 31），交付用户从零录入。
- **G0（2026-08-13）**：Git 基线已建；tests/ 冒烟基线 4 项绿 + 失败复现 6 项
  xfail（P0-01~P0-04）；scripts/check.py 全项通过；正式库 SHA-256 前后一致
  （7cc1e320…d087c4）。

# Reuse Survey（复用边界调查）

> 记录日期：2026-08-13
> 结论先行：**本轮（G0 基线）及 G1–G7 全部实施阶段均不进行技术栈替换**，
> 继续复用现有 SQLite + Python 标准库 + 原生前端的组合。本文件给出边界与依据。

## Capability boundary

- 需要的能力边界：单人、本地、离线的科技项目台账 —— 企业/项目/资金/节点
  四类实体 CRUD、资金勾稽核对、节点提醒、统计报表、企业画像、配置字典、
  Excel 导入、备份、只读 MCP 出口。
- 明确不在边界内：多人协作、账号权限、网络/云同步、移动端、外部系统对接、
  附件管理（charter.md Non-goals 与设计方案 §2.2）。
- 复用对象 = 现有技术栈三件套：
  1. **SQLite**（单文件数据库，`schema.sql` 建表，`data/project.db` 单文件）；
  2. **Python 标准库**（`http.server` + `sqlite3`，`app.py` 后端）；
  3. **原生 HTML/JS/CSS**（`static/`，无框架无构建）。
  另有唯一第三方运行时依赖：官方 `mcp` SDK（MCP 只读出口，用户已确认）。

## Contract-derived criteria

从契约（charter.md Success metrics / 设计方案 §3 验收 A1–A8）推导出的复用判据：

| 判据 | 契约出处 | 现有技术栈是否满足 |
|---|---|---|
| 低配办公电脑流畅（启动 1~2 秒、内存几十 MB） | A6 / 设计方案 §7.1 | ✅ 标准库+SQLite+原生 JS 无重运行时 |
| 单文件即备份、可恢复 | A5 | ✅ SQLite 单文件（可恢复性验证属 G5） |
| 全程离线、无 CDN/外网依赖 | 设计方案 §7.1 / Non-goals | ✅ 原生前端零外部资源 |
| 好交接、双击即用、依赖极少 | 设计方案 §7.1「零第三方依赖核心」 | ✅ 仅 mcp SDK 一个第三方依赖 |
| 数据量几十~上百条、勾稽/提醒为确定性规则 | A3/A4、charter Assumptions | ✅ SQLite 完全胜任 |
| 只读 MCP 出口 | A7 | ✅ 官方 mcp SDK（已装） |

## Survey scope, budget, and stop condition

- **本轮（G0）范围**：不进行任何技术栈调查、对比试验或替换尝试。G0 的
  全部工作（Git 基线、测试、失败复现、检查脚本、治理同步）都在现有技术栈
  内完成。
- **预算**：0 工时投入技术栈评估（评审结论：现有组合满足全部契约判据，
  无评估必要）。
- **停止条件 / 触发重审**：出现以下任一情况才允许重新启动技术栈调查——
  1. 数据量预期超过 SQLite 单机合理容量（万条级，本工具需求之外）；
  2. 出现多人协作/网络访问/云同步等新契约（charter Non-goals 变更）；
  3. 需要界面级复杂交互/可视化，原生 JS 维护成本显著失控；
  4. HUMAN 明确要求更换技术栈。

## Sources and queries

- 依据来源：
  - `设计方案.md` §2.2 非目标、§7.1 技术选型与理由、§7 性能与资源约束；
  - `PLAN.md` §1.2 明确不做（「不为了修复问题引入 Flask、React、ORM、
    独立数据库服务等技术栈替换」）；
  - `.vibe/charter.md` Constraints and budgets（核心零第三方依赖、金额单位、
    日期格式、阶段预算）。
- 已完成的评估记录（此前设计阶段）：设计方案 §7.1 对比了大框架
  （Flask/Django/Vue/React）与本方案，结论是「单人、离线、数据量小，
  框架带来的依赖安装和维护成本大于收益」。

## Candidate evidence

候选替代方案及否决理由（沿用设计方案 §7.1 结论，本轮不再重复验证）：

| 候选 | 否决理由 |
|---|---|
| Flask / Django（Web 框架） | 引入第三方 Web 依赖与维护面；标准库 http.server 已满足单用户本地场景 |
| Vue / React + 构建链 | 需要 Node 构建/打包，破坏「双击即用、离线、无 CDN」边界；数据量小无需 SPA 框架 |
| ORM（SQLAlchemy 等） | 单文件 SQLite + 少量表，手写 SQL 清晰可控；ORM 增加学习/交接成本 |
| 独立数据库服务（PostgreSQL/MySQL） | 违反「单文件即备份」「零配置」；单人本地场景严重过度设计 |
| Electron / Tauri 桌面壳 | 资源占用高、违反 A6 低配流畅与轻量约束（设计方案 §7.1 明确规避） |

## Adopt, extend, or build decision

- **决策：Adopt（继续采用）+ Extend（在现有技术栈内扩展）**。
  - SQLite / Python 标准库 / 原生前端：继续采用，不替换；
  - 数据层演进方向为「受控迁移」（PLAN §6：`schema.sql` 从一次性建表转为
    受控迁移框架），仍基于 SQLite 实现，不更换引擎；
  - 业务规则以新增 `ledger/` 领域层承载（PLAN G2），仍为 Python 标准库。
- 明确不采用的技术栈替换：见 Candidate evidence 四行，全部维持否决。

## Verification and unresolved risks

- 验证方式：
  - `python scripts/check.py`（G0 统一检查）覆盖 Python/Node 语法、pytest、
    SQLite 完整性、.vibe 校验 —— 技术栈保持的可行性由该检查持续守护；
  - `PLAN.md` §7 验收矩阵的每项验收均在现有技术栈内完成。
- 未决风险：
  - 若未来契约扩展到多人/网络/大数据量，本决策需重审（见 stop condition）；
  - SQLite 并发写能力有限，但单人本地场景无并发压力，不构成当前风险；
  - `mcp` SDK 版本演进可能带来接口变动，属依赖管理风险，非技术栈替换理由。

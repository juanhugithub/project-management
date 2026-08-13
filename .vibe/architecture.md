# Architecture

> 详细架构见 `../设计方案.md` 第 7、8 节。

## Direct-product or tool-first decision

**tool-first**：为「科技项目台账」这一**持续使用、重复性高、一致性敏感**的工作构建专用生产工具（而非一次性脚本或通用表格）。数据量虽小，但资金勾稽、节点提醒、跨系统填表等需求对一致性和确定性要求高，值得一个小型专用系统。

## Components and responsibilities

| 组件 | 职责 |
|---|---|
| `schema.sql` | 基线 5 张表定义 + 31 条种子数据；G2 起仅能经版本化迁移改变结构 |
| `docs/migrations/` | 迁移号、前置预检、事务、完成标记、回滚和恢复的实施契约 |
| `app.py` | 标准库后端：静态文件 + JSON API（企业/项目/资金/节点/字典 CRUD） |
| `static/` | 前端 SPA（原生 HTML/JS/CSS，无框架无 CDN） |
| `start.bat` | 双击启动入口（检查 Python → 运行 app.py） |
| `mcp_server.py`（阶段4） | 只读 MCP server（官方 `mcp` SDK），AI 工具读库入口 |
| `data/project.db` | SQLite 单文件（拷贝即备份） |
| `.vibe/` | 项目治理（契约/验收/领域/架构/任务/进度） |

## External component boundaries

- 系统外部边界仅两处：**浏览器**（HTTP/JSON，127.0.0.1 本地）与 **AI 工具**
  （MCP stdio 只读查询）。除此之外不对外暴露任何接口。
- 浏览器/前端仅依赖标准浏览器能力（fetch、DOM），无 CDN、无外部字体、
  无第三方 JS 库 —— 离线可用是硬边界（设计方案 §7.1）。
- MCP 出口依赖官方 `mcp` SDK（requirements-mcp.txt），是唯一的第三方
  运行时依赖；只读不写（mcp_server.py 不注册任何写工具）。
- Python 后端与数据层零第三方依赖（Python 标准库 + SQLite）。
- 本轮（G0）明确**不进行任何技术栈替换**：不引入 Flask/Django/React/Vue、
  不引入 ORM、不更换数据库引擎（详见 reuse-survey.md）。

## G1 迁移边界

迁移先在副本演练，正式库仅在 HUMAN 授权后按连续编号升级；`user_version` 与
`schema_migration` 完成标记必须在同一事务提交。失败一律回滚；已提交的 SQLite
结构变更不承诺通用降级，恢复只能使用迁移前已验证备份并由 HUMAN 决定替换。完整
协议见 `../docs/migrations/README.md`，已确认领域契约见 `../docs/decisions/0001-g1-domain-contract.md`。

## Data flow and interfaces

```
浏览器 ─HTTP(JSON)─▶ app.py ─SQL─▶ SQLite(project.db)
Codex/WorkBuddy ─MCP(stdio)─▶ mcp_server.py(只读) ─SQL─▶ SQLite
```

- 端口 8765，仅绑定 127.0.0.1（本地访问）
- API 字段白名单校验，防止脏数据/注入

## Solver routing

| 任务 | 求解器 |
|---|---|
| 台账增删改查、筛选、统计 | SQL（确定性） |
| 资金勾稽核对、节点到期提醒 | 确定性规则（阶段3） |
| 读库填表、汇报初稿 | LLM（只读 MCP，初稿人工核对；阶段4） |

核心原则：**账房（钱/勾稽/提醒）用确定性规则，嘴（填表/文字）用 AI 只读**。

## Deterministic validation points

- 字段白名单（app.py `FIELDS`）+ 类型转换（数值/整数）
- 勾稽核对：Σ来源 vs 总金额（阶段3）
- 节点提醒阈值（阶段3）
- MCP 只读：不注册任何写工具（阶段4）

## Security and irreversible side effects

- 本地运行、127.0.0.1 绑定、不联网不上云 → 无外泄面
- 删除类操作：前端二次确认 + 数据库外键策略（CASCADE / SET NULL）
- MCP 只读不写：AI 无法修改台账
- 备份：SQLite 单文件拷贝（阶段5 加一键备份脚本）

## Integration strategy

- 阶段1-2（已完成）：骨架 + 最小闭环（本架构已落地）
- 阶段3：提醒/勾稽/报表/画像/配置界面（前端 + 后端查询扩展）
- 阶段4：`mcp_server.py`（官方 `mcp` SDK，只读工具）
- 阶段5：备份脚本、Excel 导入、错误处理

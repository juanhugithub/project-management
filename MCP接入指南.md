# 科技项目台账 — MCP 接入指南（AI 读库填表）

> 目的：让 Codex / WorkBuddy / Claude 等支持 MCP 的 AI 工具读取台账数据，按其他科室的表格要求自动填表。
> **安全边界：MCP 出口只读不写。** AI 只能查询，不能修改台账；台账的增删改永远走浏览器界面。
> AI 填出的表格是**初稿**，金额、日期、信用代码等关键字段务必人工核对后再交。

## 1. 前提

- Python 3.8+（已装）
- 安装 MCP 依赖（一次性）：

```bash
pip install -r "E:\Reasonix WorkSpace\科技项目台账\requirements-mcp.txt"
```

- 台账数据库存在（双击 `start.bat` 启动过一次即自动建库）。

## 2. 对接方式（通用 stdio 协议）

MCP server 通过 **stdio** 与 AI 客户端通信，任何支持 MCP 的客户端都可以把下面这条命令注册为 MCP server：

```
命令：python
参数：["E:\\Reasonix WorkSpace\\科技项目台账\\mcp_server.py"]
```

## 3. 具体客户端配置

### 3.1 Codex CLI

方式一（命令添加）：

```bash
codex mcp add 科技项目台账 -- python "E:\Reasonix WorkSpace\科技项目台账\mcp_server.py"
```

方式二（编辑 `~/.codex/config.toml` 或项目 `.codex/config.toml`）：

```toml
[mcp_servers.科技项目台账]
command = "python"
args = ["E:\\Reasonix WorkSpace\\科技项目台账\\mcp_server.py"]
```

### 3.2 其他 MCP 客户端（WorkBuddy、Claude Desktop 等）

在客户端的 MCP server 配置中新增一个 **stdio** 类型 server：

- `command`: `python`
- `args`: `["E:\\Reasonix WorkSpace\\科技项目台账\\mcp_server.py"]`

> 提示：各客户端配置入口不同，但本质都是填上面这一对 command/args。

## 4. AI 可用的工具（全部只读）

| 工具 | 说明 |
|---|---|
| `list_projects(level, category, stage, query)` | 项目列表（按层级/类型/阶段/关键词过滤，含企业名、已到位资金） |
| `get_project(project_id)` | 单个项目全貌（基本信息 + 企业 + 资金明细 + 节点明细） |
| `list_enterprises(district, enterprise_type)` | 企业列表（含项目数、累计金额） |
| `get_enterprise(enterprise_id)` | 企业画像（含承担的全部项目） |
| `list_fundings(project_id)` | 资金拨付明细（来源/金额/批次/到账） |
| `list_nodes(project_id)` | 项目节点（计划/实际时间、状态、重大变更） |
| `get_reminders(days)` | 节点到期提醒（逾期/红/黄分级） |
| `get_stats(by)` | 统计（类型/层级/阶段/年度/企业/资金来源） |
| `get_funding_check()` | 资金勾稽核对（来源合计 vs 总金额 vs 配套应配额） |
| `search(keyword)` | 跨企业/项目全局搜索 |

## 5. 典型用法示例（对话指令）

> 例 1：填"××年度省科技项目执行情况表"
> 「读取台账中所有『省级』项目的名称、承担企业、总金额、当前阶段、下一节点，按这个表格的列填好：…（粘贴空表）」

> 例 2：核对资金
> 「调用 get_funding_check，把勾稽不一致的项目列出来」

> 例 3：写汇报
> 「统计今年立项的项目按层级、类型汇总，帮我写一段汇报初稿」

## 6. 验证接入成功

在 AI 客户端里问一句：「列出你从科技项目台账 MCP 能用的工具」，应看到 10 个查询工具，且**没有任何"创建/修改/删除"类工具**。若出现写工具，说明配置错了，立即停用并检查。

# Domain Model

> 详细设计见 `../设计方案.md` 第 4、5 节。

## Entities and value objects

- **enterprise**（企业）：name, credit_code(唯一), enterprise_type, qualifications, district, contact_person, contact_phone, address, note
- **project**（项目）：name, project_no, level, category, enterprise_id(外键), total_amount, start_date, end_date, stage, match_ratio, leader, contact_phone, note
- **funding**（资金）：project_id(外键), source_type, amount, batch, plan_date, actual_date, status, note
- **node**（节点）：project_id(外键), node_type, plan_date, actual_date, status, has_major_change, note
- **dict_item**（配置/字典）：dict_type, value, sort_order, is_active

## Relationships and ownership

```
enterprise 1 ──承担── N project 1 ──包含── N funding / N node
```

- project 删除 → funding/node 级联删除（CASCADE）
- enterprise 删除 → project.enterprise_id 置空（SET NULL）

## Invariants

- funding/node 必须挂在一个 project 下
- project 应有承担企业（可允许未关联，但设计上以有为准）
- stage 只能按状态机流转：申报中→已立项→实施中→待验收→已验收→绩效跟踪→已完结（+异常态 中止/撤销）
- source_type 只能取 dict_item.funding_source 定义值

## Operations and state transitions

- 生命周期状态机见上；节点 plan_date/actual_date 决定提醒（阶段3）
- 资金勾稽：应到位 ≈ Σ上级 + Σ配套 + Σ自付；本级配套 = 上级拨付 × match_ratio（阶段3核对）

## Mechanisms and content

| | 内容 | 处理 |
|---|---|---|
| 机制（稳定） | 实体关系、状态机、勾稽规则 | 写死在代码/表结构 |
| 内容（易变） | level/category/funding_source/node_type/district/enterprise_type 的取值清单 | `dict_item` 配置表，自助增/停用 |

- 新增：配置界面加一条 → 下拉框即时生效
- 停用：is_active=0 → 不出现在下拉框，历史数据（存文本值）不受影响
- 改名：政务数据不追溯篡改历史，用「停用旧 + 新增新」实现

## Invalid states

- 资金/节点无 project_id
- stage 非法取值（不在状态机）
- 枚举字段取值不在 dict_item（允许历史遗留，但下拉框不出现）
- 金额为负

## Intermediate representation

- 数据库 schema 即唯一事实源（`schema.sql`）
- JSON API 为读写接口（白名单字段校验）
- MCP（阶段4）为只读查询接口

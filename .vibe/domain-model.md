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

- G3 起删除采用软删除；在此之前不得以删除企业制造无承担企业项目。

## Invariants

- funding/node 必须挂在一个 project 下
- project 必须关联存在且未删除的承担企业；企业信用代码是企业业务身份。
- 项目业务唯一键是“项目编号/文号 + 企业信用代码”；编号非空时以 `(project_no, enterprise_id)` 实现等价唯一约束，无编号记录不得自动入账。
- funding 是不拆分的单记录：amount 为计划/批准金额，plan_date 为应拨日期，actual_date 为实际拨付日期，status 为拨付/到账状态。
- stage 正常链只能相邻前进：申报中→已立项→实施中→待验收→已验收→绩效跟踪→已完结；中止仅从已立项/实施中/待验收进入且不可恢复；撤销只能人工显式进入且不可恢复。
- source_type 只能取 dict_item.funding_source 定义值

## Operations and state transitions

- 正常状态不得回退或跳跃；已完结、中止、撤销均无出边。撤销的授权条件由未来 HUMAN 决定，不阻塞本契约。
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
- 枚举字段取值不在 dict_item
- 金额为负

## Intermediate representation

- 数据库 schema 即唯一事实源（`schema.sql`）
- JSON API 为读写接口（白名单字段校验）
- MCP（阶段4）为只读查询接口

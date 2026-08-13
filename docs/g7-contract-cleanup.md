# G7：旧契约收口记录

日期：2026-08-13

## 已完成收口

- 旧版 `import_excel.import_workbook` 不再允许直接向企业和项目表逐行写入。
  该入口现在明确抛出“已废弃”错误，调用方必须使用 G4 `ImportWorkflow`
  的“暂存、预览、人工确认”流程。因此含错误行的工作簿不可能再留下部分数据。
- 已归档年份的项目创建和既有项目修改均由 G3 服务层阻断，回归测试已从
  strict xfail 转为正常通过。
- 工作台和项目列表使用统一的 `planned_total`、`disbursed_total`、
  `received_total` 三项资金口径，回归测试已从旧 `funded_total` 争议转为
  三项精确值验证。

## 明确保留的业务阻塞

以下两项仍为 strict xfail，G7 不改变其业务代码或数据库结构：

1. 无“项目编号/文号”的人工项目录入。受控导入已按项目编号加企业信用代码
   阻断自动入账，但手工录入是否必须一律拒绝，或进入待确认队列，仍需要业务
   决策和对应流程设计。
2. 企业停用。当前只有软删除语义，没有独立的企业“停用”状态、维护入口和
   审计规则；不能把软删除误写成停用功能。

## 验证

```text
python -X utf8 -m pytest tests/test_regressions.py tests/test_g2_contract.py -q
```

结果：50 passed，2 xfailed。

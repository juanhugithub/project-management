#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""G8 MCP 公共业务契约。

这里定义的是面向 Agent 的稳定结果外壳，而不是 SQLite 表结构的转发。业务工具
只把已确认的台账事实放入 data；筛选条件、数据可见范围和金额口径同时返回，确保
报告、文字和表格可以追溯到一次确定的取数。
"""

from datetime import datetime


CONTRACT_VERSION = "1.0"
MONEY_SEMANTICS = {
    "unit": "万元",
    "precision": "最多两位小数",
    "planned_total": "资金记录中应拨日期不为空的金额合计",
    "disbursed_total": "状态为已拨付或已到账的金额合计",
    "received_total": "状态为已到账的金额合计",
}


def envelope(data, filters=None, data_scope=None):
    """将业务事实包装为 G8 统一信封，避免 Agent 猜测查询口径。"""
    return {
        "contract_version": CONTRACT_VERSION,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "filters": filters or {},
        "data_scope": data_scope or {
            "visibility": "仅返回未软删除且未归档年度的项目及关联事实",
            "archived_projects": "excluded",
            "soft_deleted_records": "excluded",
        },
        "money_semantics": MONEY_SEMANTICS,
        "data": data,
    }

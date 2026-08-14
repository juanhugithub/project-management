# D13 首次启动诊断

`diagnostics.py` 是安装器、桌面“诊断报告”入口和人工排障共用的只读检查。
它不会创建、迁移、修复、备份或覆盖正式数据库。

## 运行

在安装后的程序目录执行：

```text
python diagnostics.py
python diagnostics.py --json
```

安装器应先写入本机路径配置、或设置 `LEDGER_HOME` 为稳定数据根目录，再运行诊断。路径
没有 C 盘假设：`LEDGER_HOME` 优先；其次读取安装器写入的
`LEDGER_PATHS_CONFIG`（或默认 `config/runtime-paths.json`）中的 `ledger_home`。例如：

```text
%LOCALAPPDATA%\科技项目台账
```

未设置时，安装运行时由 `runtime_paths.get_runtime_paths()` 使用当前用户的本机配置或
`LOCALAPPDATA` 默认目录；报告会同时显示实际安装目录、运行时根目录和数据目录。

## 报告内容

- 应用 `VERSION`、实际安装目录、运行时根目录与数据目录；
- 正式库是否存在、`integrity_check`、外键违规数和已应用迁移；
- 备份目录、备份数量和最近备份；
- 本地网页端口 `8765` 与远程 MCP 端口 `8001` 是否已被占用；
- 本机 MCP 是否由 `LEDGER_LOCAL_MCP_ENABLED=1` 明确启用，以及配置和 Token 文件是否已就绪。

报告永不输出 Token 内容。本机 MCP 默认关闭；只有用户主动启用后，安装器才应生成
`config/local_mcp.token` 或指定 `LEDGER_LOCAL_MCP_TOKEN_FILE`。

## 首次启动验收

1. 用全新的 `LEDGER_HOME` 运行诊断：应显示“正式库未初始化”，且目录不被创建。
2. 完成安装初始化后重跑：完整性必须为 `ok`，外键违规为 `0`，并显示迁移版本。
3. 创建并验证一次备份后重跑：应显示至少一个备份及最近备份路径。
4. 若 `8765` 已被其他程序使用，安装器必须停止启动并展示端口占用；不得尝试强制结束其他程序。

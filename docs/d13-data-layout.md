# D13：本机数据目录与代码目录分离

安装目录只包含程序代码、静态资源、模板、`schema.sql` 与 `migrations/`。台账正式库和所有
会变化的材料均不写入安装目录，因此代码更新或重装不会覆盖数据。

## 运行目录选择

程序按以下顺序选择运行目录：

1. `LEDGER_HOME` 环境变量；
2. 安装器写入的路径配置文件；如需自定义配置文件位置，可设置 `LEDGER_PATHS_CONFIG`；
3. 默认 `%LOCALAPPDATA%\\科技项目台账`。

安装器配置文件内容为 UTF-8 JSON：

```json
{"ledger_home": "D:\\科技项目台账数据"}
```

未指定 `LEDGER_PATHS_CONFIG` 时，安装器将该文件写到
`%LOCALAPPDATA%\\科技项目台账\\config\\runtime-paths.json`。该引导文件只保存所选
数据根目录，允许数据目录放在 D 盘、移动盘或单位规定的其他位置。

## 目录结构

```text
<运行目录>
  data/project.db       正式 SQLite 数据库
  backups/              在线备份
  imports/archive/      导入原件
  config/               本机配置与密钥
  logs/                 MCP 访问审计日志
  reports/              首次迁移报告等可核验记录
```

## 首次安装与旧数据

首次启动时，如果新运行目录没有正式库、安装目录仍有旧 `data/`，程序会复制整个旧 `data/`
目录到新位置，校验 SQLite 完整性、外键和数据库 SHA-256 后生成
`reports/runtime-data-migration-*.json`。旧目录不会删除、移动或改写。

如新 `data/` 目录已存在但没有 `project.db`，程序会停止并提示人工检查，绝不尝试覆盖。
这项复制不执行任何数据库结构迁移；既有正式库在日常应用启动时也不会执行 SQL 结构修改。

## 验证

```text
set LEDGER_HOME=D:\科技项目台账数据
python -X utf8 -m pytest tests/test_d13_runtime_paths.py -q
python -X utf8 scripts/check.py
```

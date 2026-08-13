# G5：备份与恢复验证

## 创建备份

在项目根目录运行：

```text
python backup.py create
```

该命令只读 `data/project.db`，通过 SQLite backup API 在 `backups/` 生成带时间标识的备份文件，并立即执行 `integrity_check` 与 `foreign_key_check`。

可指定其他源库或输出位置：

```text
python backup.py create --source data/project.db --backup-dir backups
```

## 验证恢复能力

对既有备份运行：

```text
python backup.py verify backups/project_YYYYMMDD_HHMMSS_ffffff.db
```

该命令将备份恢复到系统临时目录后执行 SQLite 完整性和外键检查。它不覆盖正式库，不修改原备份文件。

## 验收边界

- 自动化测试只使用临时数据库。
- 正式库仅作为只读备份源，并由 SHA-256 前后对比守卫。
- 本阶段提供“备份可创建、备份可恢复验证”的闭环；真正将备份覆盖回正式库属于人工运维动作，未提供自动覆盖命令。

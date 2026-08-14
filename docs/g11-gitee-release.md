# G11：Gitee 私有仓库发布与本地安全更新

## 责任边界

Gitee 私有仓库只保存代码和经审计的发布说明。`data/`、`backups/`、导入原件、密钥和本机配置不是发布物，更新器也会在执行前检查 Git 跟踪清单。

仓库由单位管理员在 Gitee 创建私有仓库并配置成员；本项目不保存账号、令牌或远程地址。发布人员将已验收提交推送到 `stable` 分支。

## 人工更新

```text
python updater.py check
python updater.py update
```

`check` 仅拉取 `origin/stable` 的元数据，展示当前/稳定版本、提交差异和是否可快进。`update` 的顺序固定为：发布清单守卫、检查稳定版本、SQLite online backup、`git merge --ff-only origin/stable`、`python scripts/check.py` 健康检查。

健康检查失败时，更新器仅回退代码到更新前提交；不会覆盖、降级或迁移数据库。更新前备份会保留，是否恢复正式库始终由人工决定。

## 数据库变更

G11 不执行数据库迁移。后续版本如含迁移，必须另行显示迁移清单、备份结果和人工确认入口；不得借代码热更新自动改动正式库。

## 发布前检查

```text
python -X utf8 -m pytest -q
python -X utf8 scripts/check.py
git ls-files
```

发布前确认跟踪清单中没有 `data/`、备份、导入原件、`.env`、证书或私钥。

# D13 安装版人工热更新

安装版不依赖 Git。它从 Gitee 的 HTTPS 发布清单读取最新版本，下载完整安装器并核验 SHA-256；校验成功后，安装器只在既有 `program_root` 下新增版本目录，并重新生成桌面/开始菜单启动入口。

## 发布物

每次发布上传两个文件：`台账安装器.exe` 和 `release-manifest.json`。清单格式如下：

```json
{
  "version": "0.2.0",
  "installer_url": "https://gitee.com/.../台账安装器.exe",
  "installer_sha256": "安装器文件的 SHA-256",
  "notes": ["本次改动说明"]
}
```

构建后可用 `build_release.write_release_manifest()` 生成清单。发布包只包含程序、运行时与静态资源；不得包含 `data/`、`backups/`、导入原件、`config/`、密钥或本机路径。

## 首次安装与更新

首次安装时由维护人员传入发布清单地址：

```text
台账安装器.exe install --program-root "D:\项目台账\app" --data-root "E:\项目台账数据" --config-root "E:\项目台账配置" --manifest-url "https://.../release-manifest.json"
```

三个目录均可自行选择，不固定在 C 盘。之后使用“更新科技项目台账”入口即可；它读取保存在独立配置目录的发布清单地址。

更新器不创建备份、不执行数据库迁移、不写入 `data_root`。若下载、SHA 校验或新安装器失败，旧程序版本、启动记录和数据均保留。旧版本不会被自动删除，须由人工确认后使用卸载入口移除。

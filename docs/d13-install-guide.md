# 科技项目台账 Windows 安装说明

## 适用范围

本安装包面向 Windows 当前用户安装，不要求安装 Python、Git 或 pip。安装时可分别选择程序目录和数据目录，均可选择任意盘符；以下仅为建议默认值，不代表必须安装到 C 盘。程序版本安装到：

```text
%LOCALAPPDATA%\科技项目台账\app\<版本号>
```

正式数据库、备份和导入原件位于用户选择的数据根目录下；本机配置另存于用户选择的配置目录（在程序目录之外）。安装器会将两项选择写入 `install_locations.json`，供更新与卸载使用：

```text
<数据根目录>\data
<数据根目录>\backups
<数据根目录>\imports
<配置目录>\install_locations.json
<配置目录>\runtime-paths.json（含 ledger_home，启动器通过 LEDGER_PATHS_CONFIG 使用）
```

## 安装与使用

双击发布的 `台账安装器.exe`。安装完成后，从桌面或开始菜单中的“科技项目台账”启动。备份、诊断和卸载入口与主程序同时创建。

若单位策略禁止从用户目录运行程序，安装会失败；请将诊断结果交给单位 IT 采用受管安装方式，不要尝试绕过单位策略。

## 更新与卸载

每个版本安装到用户选择的程序目录下的独立版本目录，安装器不会覆盖同版本程序。更新只能更换程序版本，不能删除、覆盖或重建既有数据库。

卸载入口只删除指定的 `<程序目录>\<版本号>` 程序目录；数据根目录与配置目录永远保留。重新安装后可继续使用已有数据。

## 构建发布包（维护人员）

在项目根目录执行：

```text
python -X utf8 build_release.py
```

输出为 `release\台账安装器.exe`。发布前执行：

```text
python -X utf8 -m pytest tests/test_d13_packaging_contract.py -q
python -X utf8 scripts/check.py
```

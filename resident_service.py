"""科技项目台账常驻启动入口。

默认使用当前用户注册表 Run 项，电脑登录后启动后台服务；数据目录仍由
runtime_paths 决定。它不创建云副本，也不改变数据库事实。
"""
import argparse
import os
import sys
import winreg


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "科技项目台账"


def _command():
    executable = sys.executable
    if executable.lower().endswith("python.exe"):
        return f'"{executable}" "{os.path.join(os.path.dirname(__file__), "app.py")}" --resident'
    return f'"{executable}" --resident'


def install_startup():
    """为当前 Windows 用户写入开机启动项。"""
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, _command())


def remove_startup():
    """移除本程序的当前用户开机启动项。"""
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        try:
            winreg.DeleteValue(key, APP_NAME)
        except FileNotFoundError:
            pass


def main():
    parser = argparse.ArgumentParser(description="科技项目台账常驻服务管理")
    parser.add_argument("action", choices=["install", "remove", "run"])
    args = parser.parse_args()
    if args.action == "install":
        install_startup()
        print("已启用当前用户开机启动")
    elif args.action == "remove":
        remove_startup()
        print("已移除当前用户开机启动")
    else:
        from app import main as app_main
        app_main(open_browser=False)


if __name__ == "__main__":
    main()

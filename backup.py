#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一键备份 / 自动备份：把 data/project.db 复制到 backups/（带时间戳），自动保留最近 30 份。

用法：
  手动：  python backup.py
  自动：  python backup.py --auto   （每天最多一次，当天已有备份则跳过）
  程序内：from backup import auto_backup_if_needed; auto_backup_if_needed()
"""

import datetime
import os
import shutil
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(BASE_DIR, "data", "project.db")
BAK_DIR = os.path.join(BASE_DIR, "backups")
KEEP = 30


def do_backup(keep=KEEP):
    """执行一次备份，返回备份文件路径；数据库不存在返回 None。"""
    if not os.path.exists(SRC):
        return None
    os.makedirs(BAK_DIR, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = os.path.join(BAK_DIR, f"project_{ts}.db")
    shutil.copy2(SRC, dst)

    files = sorted(f for f in os.listdir(BAK_DIR)
                   if f.startswith("project_") and f.endswith(".db"))
    removed = 0
    for f in files[:-keep]:
        os.remove(os.path.join(BAK_DIR, f))
        removed += 1
    return dst


def auto_backup_if_needed(keep=KEEP):
    """每天最多一次：当天已有备份则跳过，否则执行备份。返回备份路径或 None。"""
    if not os.path.exists(SRC):
        return None
    os.makedirs(BAK_DIR, exist_ok=True)
    today = datetime.datetime.now().strftime("%Y%m%d")
    if any(f.startswith(f"project_{today}") for f in os.listdir(BAK_DIR)):
        return None
    return do_backup(keep=keep)


def main():
    auto = "--auto" in sys.argv
    if auto:
        dst = auto_backup_if_needed()
        if dst:
            print(f"[OK] 自动备份完成：{dst}")
        else:
            print("[INFO] 今天已备份过，跳过")
        return 0
    dst = do_backup()
    if dst is None:
        print("[提示] 尚未找到数据库文件（data/project.db），请先双击 start.bat 启动过一次。")
        return 1
    size_kb = os.path.getsize(dst) // 1024
    files = [f for f in os.listdir(BAK_DIR) if f.startswith("project_") and f.endswith(".db")]
    print(f"[OK] 备份完成：{dst}（{size_kb} KB）")
    print(f"当前共保留 {len(files)} 份备份（自动保留最近 {KEEP} 份）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

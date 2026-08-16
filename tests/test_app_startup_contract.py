# -*- coding: utf-8 -*-
"""主程序启动边界测试：端口冲突不得初始化或改写正式数据。"""

import app


def test_port_conflict_stops_before_database_initialization(monkeypatch):
    """已有监听者时，启动应给出提示并在 init_db 前退出。"""
    messages = []
    monkeypatch.setattr(app, "stop_previous_installed_versions", lambda: [])
    monkeypatch.setattr(app, "_port_is_occupied", lambda: True)
    monkeypatch.setattr(app, "_show_startup_error", messages.append)

    def fail_if_database_is_touched():
        raise AssertionError("端口冲突时不应初始化数据库")

    monkeypatch.setattr(app, "init_db", fail_if_database_is_touched)

    assert app.main(open_browser=False) == 1
    assert messages == [app.PORT_CONFLICT_MESSAGE]


def test_windows_and_unix_address_in_use_errors_are_recognized():
    """绑定竞态产生的系统错误必须进入统一的端口冲突处理。"""
    assert app._is_address_in_use(OSError(10048, "address already in use"))

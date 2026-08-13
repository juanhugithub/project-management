"""G6 本地会话与数据范围定义。

本系统定位为局域网单机台账，用户清单直接固化为本地初始账号；会话只保存在
进程内存中，服务重启即失效。这样不引入额外账户表迁移，也让权限边界在 HTTP
入口集中生效。
"""
from contextvars import ContextVar
from secrets import token_urlsafe
from threading import Lock


# 用户名是可追溯审计主体；测试账号同时作为初始可用本地账号。
USERS = {
    "g6-admin": {"password": "g6-admin-password", "role": "admin", "district_scope": None},
    "g6-editor": {"password": "g6-editor-password", "role": "editor", "district_scope": None},
    "g6-viewer": {"password": "g6-viewer-password", "role": "viewer", "district_scope": None},
    "g6-devzone-viewer": {"password": "g6-viewer-password", "role": "viewer", "district_scope": "开发区"},
}

_sessions = {}
_sessions_lock = Lock()
_operator = ContextVar("ledger_operator", default="local-user")


def login(username, password):
    """校验本地账号并签发不可预测会话令牌。"""
    user = USERS.get(username)
    if not user or user["password"] != password:
        return None, None
    token = token_urlsafe(32)
    public_user = {"username": username, "role": user["role"], "district_scope": user["district_scope"]}
    with _sessions_lock:
        _sessions[token] = public_user
    return token, public_user


def user_for_token(token):
    """返回会话主体；令牌不存在时直接按未登录处理。"""
    with _sessions_lock:
        return _sessions.get(token)


def current_operator():
    """供领域服务写审计时取得当前 HTTP 请求的操作者。"""
    return _operator.get()


def set_current_operator(username):
    """由 HTTP Handler 在一个请求的整个业务调用期间设置审计主体。"""
    return _operator.set(username)


def reset_current_operator(token):
    """请求结束后恢复上下文，避免线程复用时串写操作者。"""
    _operator.reset(token)

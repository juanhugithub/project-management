class DomainError(Exception):
    """可直接映射为 HTTP 400 的业务输入错误。"""

"""
自定义异常类
"""


class TwitterError(Exception):
    """Twitter API 基础异常"""
    def __init__(self, msg: str):
        super().__init__(msg)
        self.message = msg


class AccountSuspendedError(TwitterError):
    """账号被冻结"""
    pass


class AccountNotFoundError(TwitterError):
    """账号不存在"""
    pass


class LoginFailedError(TwitterError):
    """登录失败"""
    pass


class PasswordResetRequiredError(TwitterError):
    """需要重置密码"""
    pass


class EmailMismatchError(TwitterError):
    """邮箱不匹配 - 需要改密"""
    pass


class TwoFARequiredError(TwitterError):
    """需要2FA验证"""
    pass


class CloudflareError(TwitterError):
    """Cloudflare 拦截"""
    pass


class NoRetryError(TwitterError):
    """不可重试的错误"""
    pass


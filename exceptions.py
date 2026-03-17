"""
Gemini 浏览器自动化 - 自定义异常体系
"""


class BrowserException(Exception):
    """浏览器自动化异常基类"""
    pass


class BrowserCrashedException(BrowserException):
    """浏览器崩溃异常 - 触发自动重启"""
    pass


class TimeoutException(BrowserException):
    """操作超时异常 - 触发重试"""
    pass


class NetworkException(BrowserException):
    """网络错误异常 - 触发重试"""
    pass


class ElementNotFoundError(BrowserException):
    """页面元素未找到异常 - 触发重试"""
    pass


class LoginRequiredException(BrowserException):
    """需要登录异常 - 中断流程，提示用户"""
    pass


class MessageSendFailedError(BrowserException):
    """消息发送失败异常"""
    pass


class ResponseTimeoutError(BrowserException):
    """响应获取超时异常"""
    pass


# ============================================================================
# 文件上传相关异常（新增）
# ============================================================================


class FileUploadException(BrowserException):
    """文件上传异常基类"""
    pass


class FileNotFoundError(FileUploadException):
    """文件不存在异常"""
    def __init__(self, file_path: str):
        super().__init__(f"文件不存在: {file_path}")


class FileSizeError(FileUploadException):
    """文件大小超限异常"""
    def __init__(self, file_name: str, file_size_mb: float, limit_mb: float):
        super().__init__(
            f"文件过大: {file_name}\n"
            f"当前大小: {file_size_mb:.2f} MB\n"
            f"限制大小: {limit_mb:.2f} MB"
        )


class FileTypeError(FileUploadException):
    """文件类型不支持异常"""
    def __init__(self, file_name: str, supported_types: str = None):
        msg = f"文件类型不支持: {file_name}"
        if supported_types:
            msg += f"\n支持的类型: {supported_types}"
        super().__init__(msg)


class FileUploadError(FileUploadException):
    """通用文件上传失败异常"""
    def __init__(self, message: str):
        super().__init__(f"文件上传失败: {message}")


# ============================================================================
# API 相关异常
# ============================================================================


class APIException(Exception):
    """API 异常基类"""
    pass


class APIKeyNotFoundError(APIException):
    """未找到 API Key 异常"""
    def __init__(self, message: str = "未配置任何 API Key"):
        super().__init__(message)


class APIKeyInvalidError(APIException):
    """API Key 无效异常"""
    def __init__(self, key_hint: str = ""):
        hint = f" (Key: {key_hint}...)" if key_hint else ""
        super().__init__(f"API Key 无效{hint}")


class APIRateLimitError(APIException):
    """API 速率限制异常"""
    def __init__(self, retry_after: int = None):
        msg = "API 请求频率超限"
        if retry_after:
            msg += f"，建议 {retry_after} 秒后重试"
        super().__init__(msg)
        self.retry_after = retry_after


class APIQuotaExceededError(APIException):
    """API 配额用尽异常"""
    def __init__(self, key_hint: str = ""):
        hint = f" (Key: {key_hint}...)" if key_hint else ""
        super().__init__(f"API 配额已用尽{hint}")


class APINetworkError(APIException):
    """API 网络错误异常"""
    def __init__(self, message: str = "网络连接失败"):
        super().__init__(f"API 网络错误: {message}")


class APIServerError(APIException):
    """API 服务器错误异常 (5xx)"""
    def __init__(self, status_code: int = None):
        msg = "API 服务器错误"
        if status_code:
            msg += f" (HTTP {status_code})"
        super().__init__(msg)
        self.status_code = status_code


class APIResponseError(APIException):
    """API 响应解析错误异常"""
    def __init__(self, message: str = "无法解析响应"):
        super().__init__(f"API 响应错误: {message}")


class AllKeysExhaustedError(APIException):
    """所有 API Key 都不可用异常"""
    def __init__(self, message: str = "所有 API Key 均不可用，请检查配置或稍后重试"):
        super().__init__(message)


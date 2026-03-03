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


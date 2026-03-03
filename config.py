"""
Gemini 浏览器自动化 - 配置管理
"""

import argparse
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Optional
import os
from dotenv import load_dotenv


logger = logging.getLogger(__name__)


def get_system_proxy() -> Optional[Dict[str, str]]:
    """
    获取系统代理设置
    
    Returns:
        如果启用代理，返回 {"server": "http://proxy_address:port"}
        否则返回 None
    """
    try:
        import winreg
        
        # 打开注册表
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 
                           r"Software\Microsoft\Windows\CurrentVersion\Internet Settings") as key:
            # 检查是否启用代理
            proxy_enable, _ = winreg.QueryValueEx(key, "ProxyEnable")
            
            if proxy_enable:
                # 获取代理服务器地址
                proxy_server, _ = winreg.QueryValueEx(key, "ProxyServer")
                logger.info(f"检测到系统代理: {proxy_server}")
                
                # 处理代理格式（可能包含多个代理，格式如 "http=127.0.0.1:15715;https=127.0.0.1:15715"）
                if "=" in proxy_server:
                    # 分割多个代理
                    proxies = {}
                    for proxy in proxy_server.split(";"):
                        if "=" in proxy:
                            protocol, addr = proxy.split("=", 1)
                            proxies[protocol] = addr
                    
                    # 优先使用 http 代理
                    if "http" in proxies:
                        return {"server": f"http://{proxies['http']}"}
                    elif "https" in proxies:
                        return {"server": f"http://{proxies['https']}"}
                    else:
                        return {"server": f"http://{list(proxies.values())[0]}"}
                else:
                    # 单个代理地址
                    return {"server": f"http://{proxy_server}"}
            else:
                logger.info("系统代理未启用")
                return None
                
    except Exception as e:
        logger.warning(f"获取系统代理失败: {e}")
        return None


@dataclass
class BrowserConfig:
    """浏览器配置"""
    headless: bool = True  # v1.1 改进：默认使用 headless 模式
    profile_dir: str = "./profiles"
    timeout: int = 30
    retry_count: int = 3
    check_interval: float = 0.3
    language: str = "zh-CN"
    timezone: str = "Asia/Tokyo"
    # 浏览器路径配置（默认使用已安装的 Chrome）
    browser_path: Optional[str] = r"C:\Program Files\Google\Chrome\Application\chrome.exe"  # 默认使用 Chrome
    # 代理配置
    proxy: Optional[Dict[str, str]] = None  # 例如：{"server": "http://127.0.0.1:15715"}


@dataclass
class GeminiConfig:
    """Gemini 相关配置"""
    base_url: str = "https://gemini.google.com"
    response_timeout: int = 300  # 响应最长等待时间（秒）

    # DOM 选择器配置
    input_selectors: List[str] = None

    # 文件上传配置（新增）
    upload_button_selectors: List[str] = None
    file_input_selectors: List[str] = None
    upload_complete_selectors: List[str] = None
    upload_timeout: int = 30  # 文件上传超时（秒）
    upload_retry_count: int = 2  # 文件上传重试次数

    # 文件大小限制（字节）
    max_file_sizes: Dict[str, int] = None

    # 支持的文件类型
    supported_file_types: Dict[str, List[str]] = None

    def __post_init__(self):
        if self.input_selectors is None:
            self.input_selectors = [
                'div[role="textbox"]',                    # 最可靠
                'textarea[placeholder*="Ask Gemini"]',    # 备用
                'rich-textarea',                          # 最后备用
            ]

# 上传按钮选择器（优先级排列）
        if self.upload_button_selectors is None:
            self.upload_button_selectors = [
                # 第 1 层：data-test-id（最可靠）
                'button[data-test-id="hidden-local-file-upload-button"]',
                'button[data-test-id="hidden-local-image-upload-button"]',
                # 第 2 层：aria-label
                'button[aria-label*="打开文件上传菜单"]',
                'button[aria-label*="upload file"]',
                'button[aria-label*="上传文件"]',
                'button[aria-label*="Upload file"]',
                'button[aria-label*="上传"]',
                'button[aria-label*="Upload"]',
                'button[aria-label*="attach"]',
                'button[aria-label*="Attach"]',
                'button[aria-label*="附加"]',
                'button[aria-label*="image"]',
                'button[aria-label*="Image"]',
                'button[aria-label*="file"]',
                'button[aria-label*="File"]',
                # 第 3 层：class 属性
                'button[class*="upload-button"]',
                'button[class*="upload-card-button"]',
                'button[class*="uploader"]',
                'button[class*="attach"]',
                'button[class*="Attach"]',
                'button[class*="image"]',
                'button[class*="Image"]',
                'button[class*="file"]',
                'button[class*="File"]',
                'button[class*="clip"]',
                'button[mat-icon-button]',
                # 第 4 层：通用选择器
                'div[class*="uploader-button-container"] button',
                'div[class*="file-uploader"] button',
            ]

        # 文件输入框选择器（隐藏的 input[type="file"]）
        if self.file_input_selectors is None:
            self.file_input_selectors = [
                'input[type="file"]',
                'input[type="file"][accept*="image"]',
                'input[type="file"][accept*="pdf"]',
                'input[class*="upload"]',
            ]

        # 上传完成标志选择器
        if self.upload_complete_selectors is None:
            self.upload_complete_selectors = [
                # 图片预览相关
                'img[alt*="preview"]',
                'img[alt*="Preview"]',
                'img[class*="preview"]',
                'img[class*="Preview"]',
                'img[class*="thumbnail"]',
                'img[class*="Thumbnail"]',
                # 文件名显示相关
                'div[class*="filename"]',
                'div[class*="file-name"]',
                'span[class*="filename"]',
                'span[class*="file-name"]',
                # 附件相关
                '[class*="attachment"]',
                '[class*="Attachment"]',
                '[class*="attached-file"]',
                '[class*="attached"]',
                # 发送按钮可用（表示文件已准备好）
                'button[aria-label*="Send"]:not([disabled])',
                'button[aria-label*="发送"]:not([disabled])',
                # 其他可能的标志
                '[class*="upload-complete"]',
                '[class*="file-loaded"]',
            ]

        # 文件大小限制（单位：字节）
        if self.max_file_sizes is None:
            self.max_file_sizes = {
                'image': 20 * 1024 * 1024,    # 20 MB
                'pdf': 50 * 1024 * 1024,      # 50 MB
                'text': 10 * 1024 * 1024,     # 10 MB
                'video': 100 * 1024 * 1024,   # 100 MB
                'data': 20 * 1024 * 1024,     # 20 MB
            }

        # 支持的文件类型
        if self.supported_file_types is None:
            self.supported_file_types = {
                'image': ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'],
                'pdf': ['.pdf'],
                'text': ['.txt', '.doc', '.docx', '.md'],
                'video': ['.mp4', '.webm', '.mov', '.avi', '.mkv'],
                'data': ['.csv', '.json', '.xlsx', '.xls'],
            }


class Config:
    """统一配置管理"""

    def __init__(self):
        load_dotenv()
        
        # 自动获取系统代理
        proxy = get_system_proxy()
        
        self.browser = BrowserConfig(
            proxy=proxy
        )
        self.gemini = GeminiConfig()
        self._validate_profile_dir()

    def _validate_profile_dir(self):
        """验证并创建 Profile 目录"""
        profile_path = Path(self.browser.profile_dir)
        profile_path.mkdir(parents=True, exist_ok=True)

    def from_args(self, args: argparse.Namespace) -> None:
        """从命令行参数覆盖配置"""
        # v1.1 改进：处理 headless 和 no-headless 参数
        if hasattr(args, 'headless') and hasattr(args, 'no_headless'):
            logger.info(f"参数值: headless={args.headless}, no_headless={args.no_headless}")
            logger.info(f"BrowserConfig 默认值: headless={self.browser.headless}")
            
            if args.headless:
                self.browser.headless = True
                logger.info("已显式设置 headless=True")
            elif args.no_headless:
                self.browser.headless = False
                logger.info("已显式设置 headless=False")
            else:
                # 如果都没有指定，使用 BrowserConfig 的默认值（True）
                logger.info("未指定 headless 参数，使用 BrowserConfig 默认值")
            
            logger.info(f"最终 headless 值: {self.browser.headless}")
            
        elif hasattr(args, 'headless'):
            # 只有 --headless，没有 --no-headless，显式设置为 True
            if args.headless:
                self.browser.headless = True
                logger.info("已显式设置 headless=True")
        elif hasattr(args, 'no_headless'):
            # 只有 --no-headless，显式设置为 False
            if args.no_headless:
                self.browser.headless = False
                logger.info("已显式设置 headless=False")

        if hasattr(args, 'profile') and args.profile:
            self.browser.profile_dir = args.profile
            self._validate_profile_dir()

        if hasattr(args, 'timeout') and args.timeout:
            self.browser.timeout = args.timeout
            self.gemini.response_timeout = args.timeout * 10  # 响应超时更长

        if hasattr(args, 'retry') and args.retry:
            self.browser.retry_count = args.retry

        # 浏览器路径：命令行参数 > 环境变量 > 默认值
        if hasattr(args, 'browser_path') and args.browser_path:
            self.browser.browser_path = args.browser_path
            logger.debug(f"已配置使用已安装的浏览器: {args.browser_path}")
        elif not self.browser.browser_path and os.getenv("BROWSER_PATH"):
            self.browser.browser_path = os.getenv("BROWSER_PATH")
            logger.debug(f"使用环境变量 BROWSER_PATH: {os.getenv('BROWSER_PATH')}")

        if hasattr(args, 'retry') and args.retry:
            self.browser.retry_count = args.retry

    def get_anti_detection_args(self) -> List[str]:
        """获取反检测启动参数"""
        # 对于已安装的浏览器，使用更少的启动参数，避免影响文件上传
        if self.browser.browser_path:
            return [
                "--no-first-run",
                "--no-default-browser-check",
                f"--lang={self.browser.language}",
            ]
        else:
            # Playwright 自带的 Chromium，使用优化后的反检测参数
            # 移除了可能影响文件上传的参数，添加文件上传支持
            return [
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",  # 可能导致某些问题，先注释掉
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-extensions",  # 移除：可能影响文件上传
                "--disable-component-extensions-with-background-pages",  # 移除：可能影响文件上传
                "--allow-file-access-from-files",  # 添加：允许文件访问
                "--disable-features=VizDisplayCompositor",  # 添加：可能提高稳定性
                f"--lang={self.browser.language}",
            ]


# 全局配置实例
config = Config()

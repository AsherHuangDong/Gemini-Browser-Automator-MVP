"""
Gemini 浏览器自动化核心类
"""

import asyncio
import logging
from pathlib import Path
from typing import AsyncGenerator, Optional, Callable, Any, Dict
import json
import random
import string

from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from exceptions import (
    BrowserException,
    BrowserCrashedException,
    TimeoutException,
    ElementNotFoundError,
    LoginRequiredException,
    MessageSendFailedError,
    ResponseTimeoutError,
    FileUploadException,
    FileNotFoundError,
    FileSizeError,
    FileTypeError,
    FileUploadError,
)
from config import config
from file_uploader import FileValidator, FileUploadUI

# MutationObserver 流式响应（Tier 2 优化 - 推荐！）
try:
    from mutation_observer_stream import stream_response_mutation_observer
    MUTATION_OBSERVER_AVAILABLE = True
except ImportError:
    MUTATION_OBSERVER_AVAILABLE = False
    logger.debug("MutationObserver 模块不可用")


logger = logging.getLogger(__name__)


class GeminiBrowser:
    """
    Gemini 浏览器自动化核心类
    负责浏览器生命周期、页面交互、流式输出等
    """

    def __init__(
        self,
        headless: bool = True,  # v1.1 改进：默认使用 headless 模式
        profile_dir: str = "./profiles",
        timeout: int = 30,
        retry_count: int = 3,
        check_interval: float = 0.01,  # ⚡⚡ 超激进：0.01 秒（10ms，比原来快 30 倍）
    ):
        """初始化浏览器配置"""
        self.headless = headless
        self.profile_dir = Path(profile_dir)
        self.timeout = timeout
        self.retry_count = retry_count
        self.check_interval = check_interval

        # Playwright 对象
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.context: Optional[BrowserContext] = None
        self._playwright = None

        # 运行状态
        self._running = False
        self._crashed = False
        self._background_tasks = set()

    async def launch(self) -> None:
        """
        启动浏览器（v1.1 改进）
        
        1. 初始化 Playwright
        2. 使用反检测参数启动 Chromium
        3. 加载或创建 Profile
        4. 打开新 Page 并导航到 Gemini
        5. 检查登录状态（v1.1：优先 headless，失败则 fallback 到 headful）
        """
        try:
            logger.debug(f"正在启动浏览器... (headless={self.headless})")

            # 启动浏览器
            await self._launch_browser()

            # 检查登录状态（v1.1 改进）
            is_logged_in = await self.ensure_logged_in()

            if not is_logged_in:
                # headless 模式下登录失败，fallback 到 headful
                if self.headless:
                    logger.warning("headless 模式下登录检查失败，切换到 headful 模式...")
                    await self._fallback_to_headful_login()
                else:
                    # 已经是 headful 模式，直接抛出异常
                    raise LoginRequiredException("未登录，请在浏览器窗口中完成登录")

        except Exception as e:
            logger.error(f"浏览器启动失败: {e}", exc_info=True)
            await self._safe_cleanup()
            raise BrowserException(f"浏览器启动失败: {e}")

    async def _launch_browser(self) -> None:
        """
        启动浏览器的核心逻辑（可被 fallback 复用）
        
        1. 初始化 Playwright
        2. 使用反检测参数启动 Chromium
        3. 加载或创建 Profile
        4. 打开新 Page 并导航到 Gemini
        """
        try:
            # 初始化 Playwright
            if not self._playwright:
                self._playwright = await async_playwright().start()

            # 启动浏览器
            launch_args = config.get_anti_detection_args()

            # 构建启动参数
            launch_kwargs = {
                "headless": self.headless,
                "args": launch_args
            }

            # 如果配置了浏览器路径，使用已安装的浏览器
            if config.browser.browser_path:
                logger.debug(f"使用已安装的浏览器: {config.browser.browser_path}")
                launch_kwargs["executable_path"] = config.browser.browser_path
            else:
                logger.debug("使用 Playwright 自带的 Chromium")

            self.browser = await self._playwright.chromium.launch(**launch_kwargs)

            # 创建 Browser Context（持久化配置）
            profile_state_file = self.profile_dir / "storage_state.json"

            # 完全不设置 viewport，让浏览器自适应窗口大小
            context_kwargs = {
                "locale": config.browser.language,
                "timezone_id": config.browser.timezone,
            }
            logger.debug("不设置 viewport，让浏览器自适应窗口大小")

            # 添加代理配置（如果存在）
            if config.browser.proxy:
                context_kwargs["proxy"] = config.browser.proxy
                logger.info(f"✓ 使用代理: {config.browser.proxy}")

            # 如果存在保存的 storage，则加载
            if profile_state_file.exists():
                try:
                    with open(profile_state_file, "r", encoding='utf-8') as f:
                        storage_state = json.load(f)
                    context_kwargs["storage_state"] = storage_state
                    logger.debug(f"✓ 已加载保存的登录态 (文件: {profile_state_file}, cookies: {len(storage_state.get('cookies', []))})")
                except Exception as e:
                    logger.warning(f"加载保存的登录态失败: {e}")

            self.context = await self.browser.new_context(**context_kwargs)

            # 设置事件监听器
            self.browser.on("disconnected", self._on_browser_disconnected)

            # 打开新页面
            self.page = await self.context.new_page()
            self.page.set_default_timeout(self.timeout * 1000)

            # 导航到 Gemini（v1.1 改进：添加页面加载重试）
            await self._navigate_to_gemini_with_retry()

            # 减少等待时间（从 2 秒减少到 1 秒）
            await asyncio.sleep(1)

            self._running = True
            self._crashed = False
            logger.debug("浏览器启动成功")

        except Exception as e:
            logger.error(f"浏览器启动失败: {e}", exc_info=True)
            raise BrowserException(f"浏览器启动失败: {e}")

    async def _navigate_to_gemini_with_retry(self, max_retries: int = 3) -> None:
        """
        导航到 Gemini，支持重试（v1.1 改进）
        
        Args:
            max_retries: 最大重试次数
        """
        for attempt in range(max_retries):
            try:
                logger.debug(f"正在导航到 Gemini (尝试 {attempt + 1}/{max_retries})...")
                await self.page.goto(config.gemini.base_url, wait_until="domcontentloaded")
                
                # 减少等待时间：networkidle 改为更短的超时
                logger.debug("等待页面稳定...")
                try:
                    await self.page.wait_for_load_state("networkidle", timeout=5000)
                except Exception:
                    # networkidle 超时不是致命错误，继续
                    logger.debug("networkidle 超时，继续...")
                
                # 减少额外等待时间（从 3 秒减少到 1 秒）
                await asyncio.sleep(1)
                
                logger.debug("✓ 已成功导航到 Gemini")
                return
                
            except Exception as e:
                logger.warning(f"导航失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    logger.debug(f"等待 {2 ** attempt} 秒后重试...")
                    await asyncio.sleep(2 ** attempt)
                else:
                    raise BrowserException(f"导航到 Gemini 失败（已重试 {max_retries} 次）: {e}")

    async def _save_login_state(self) -> None:
        """保存当前登录态到文件"""
        if not self.context:
            logger.warning("Context 未初始化，无法保存登录态")
            return

        try:
            storage_state = await self.context.storage_state()
            profile_state_file = self.profile_dir / "storage_state.json"
            self.profile_dir.mkdir(parents=True, exist_ok=True)

            # 检查关键 cookies
            key_cookie_names = ['SID', '__Secure-1PSID', '__Secure-3PSID', 'NID']
            cookies = storage_state.get('cookies', [])
            found_key_cookies = [c for c in cookies if c['name'] in key_cookie_names]

            logger.debug(f"准备保存登录态:")
            logger.debug(f"  Cookies 总数: {len(cookies)}")
            logger.debug(f"  关键登录 cookies: {len(found_key_cookies)}")
            if found_key_cookies:
                logger.debug(f"  关键 cookies: {[c['name'] for c in found_key_cookies]}")

            with open(profile_state_file, "w", encoding='utf-8') as f:
                json.dump(storage_state, f, indent=2)

            logger.debug(f"✓ 已保存登录态到: {profile_state_file}")
            logger.debug(f"  文件大小: {profile_state_file.stat().st_size} 字节")
        except Exception as e:
            logger.warning(f"保存登录态失败: {e}")

    async def close(self) -> None:
        """优雅关闭浏览器"""
        logger.debug("正在关闭浏览器...")

        # 保存当前登录态
        if self.context:
            try:
                await self._save_login_state()
            except Exception as e:
                logger.warning(f"关闭时保存登录态失败: {e}")

        # 取消所有后台任务
        for task in self._background_tasks:
            if not task.done():
                task.cancel()

        await self._safe_cleanup()
        self._running = False
        logger.debug("浏览器已关闭")

    async def _safe_cleanup(self) -> None:
        """安全清理资源"""
        try:
            if self.page:
                await self.page.close()
        except Exception:
            pass

        try:
            if self.context:
                await self.context.close()
        except Exception:
            pass

        try:
            if self.browser:
                await self.browser.close()
        except Exception:
            pass

        try:
            if self._playwright:
                await self._playwright.stop()
        except Exception:
            pass

    def _on_browser_disconnected(self):
        """浏览器断开连接回调"""
        logger.warning("浏览器已断开连接")
        self._crashed = True

    async def go_to_gemini(self) -> None:
        """导航到 Gemini 官网"""
        if not self.page:
            raise BrowserException("页面未初始化")

        try:
            await self.page.goto(config.gemini.base_url, wait_until="domcontentloaded")
            logger.debug("已导航到 Gemini 官网")
        except PlaywrightTimeoutError:
            raise TimeoutException("导航到 Gemini 官网超时")

    async def ensure_logged_in(self) -> bool:
        """
        确保已登录
        检查登录状态，未登录则等待用户手动登录
        返回 True 表示已登录
        """
        if not self.page:
            raise BrowserException("页面未初始化")

        try:
            logger.debug("正在检查登录状态...")

            # 减少等待时间（从 3 秒减少到 1 秒）
            await asyncio.sleep(1)

            # 执行多重登录检查（v1.1 改进）
            is_logged_in = await self._check_login_status_v11()

            if is_logged_in:
                logger.debug("✓ 登录检查通过，确认已登录")
                # 保存登录态
                await self._save_login_state()
                return True
            else:
                # 未登录，需要手动登录
                logger.warning("⚠ 检测到未登录")
                return False

        except LoginRequiredException:
            raise
        except Exception as e:
            logger.error(f"检查登录状态异常: {e}", exc_info=True)
            raise LoginRequiredException(f"检查登录状态失败: {e}")

    async def _check_login_status_v11(self) -> bool:
        """
        v1.1 更严格的登录检查（优化版）
        
        检查条件：
        主要条件：输入框 locator 可见且 enabled（如果找到，就认为已登录）
        辅助条件 A: URL 不含登录关键词（accounts.google.com / SignIn / ServiceLogin）
        
        改进：
        1. 只要找到输入框就立即返回，不检查其他条件（速度优先）
        2. 减少超时时间（从 2000 改为 500）
        3. 移除慢速检查（页面文本检查）
        
        返回 True 表示已登录
        """
        logger.info("开始执行登录检查...")

        # 主要条件：检查输入框（找到就立即返回）
        for selector in config.gemini.input_selectors:
            try:
                element = self.page.locator(selector)
                # 减少超时时间（从 2000 改为 500）
                is_visible = await element.is_visible(timeout=500)
                is_enabled = await element.is_enabled()
                
                if is_visible and is_enabled:
                    logger.info(f"✓ 登录检查通过：找到可用输入框 ({selector})")
                    return True
            except Exception as e:
                logger.debug(f"输入框检查失败 ({selector}): {e}")
                continue
        
        # 如果没找到输入框，检查 URL（快速判断）
        current_url = self.page.url
        logger.info(f"当前 URL: {current_url}")
        login_keywords = ['accounts.google.com', 'signin', 'service login']
        url_has_login_keyword = any(keyword.lower() in current_url.lower() for keyword in login_keywords)
        
        if url_has_login_keyword:
            logger.warning(f"✗ 登录检查失败：URL 包含登录关键词 ({current_url})")
        else:
            logger.warning(f"✗ 登录检查失败：未找到输入框 (URL: {current_url})")
        
        return False

    async def _fallback_to_headful_login(self) -> None:
        """
        Fallback 流程：从 headless 切换到 headful 模式进行手动登录
        
        步骤：
        1. 关闭当前上下文和浏览器
        2. 重新以 headful 模式启动同一个 profile_dir
        3. 弹出浏览器窗口，打印清晰指令
        4. 等待用户登录后按 Enter
        5. 重新检查登录状态
        """
        logger.warning("\n" + "="*70)
        logger.warning("检测到登录态失效（或首次使用）")
        logger.warning("="*70)
        
        # 关闭当前浏览器
        logger.debug("关闭当前浏览器...")
        await self._safe_cleanup()
        self._running = False
        self._crashed = False
        
        # 重新以 headful 模式启动
        logger.debug("以 headful 模式重新启动浏览器...")
        self.headless = False  # 强制使用 headful 模式
        
        # 重新启动浏览器
        await self._launch_browser()
        
        # 打印清晰指令
        logger.warning("\n" + "="*70)
        logger.warning("已打开浏览器窗口，请在其中完成 Google 账号登录")
        logger.warning("（可能需要两步验证）")
        logger.warning("")
        logger.warning("登录成功并看到 Gemini 聊天界面后，在此终端按 Enter 键继续...")
        logger.warning("="*70 + "\n")
        
        # 等待用户按 Enter
        try:
            input("已成功登录？请按 ENTER 继续...")
        except EOFError:
            # 非交互环境，无法等待用户输入
            logger.warning("非交互环境，无法等待用户输入")
            raise LoginRequiredException(
                "检测到未登录，但在非交互环境中无法进行手动登录。\n"
                "请在交互环境中运行，或删除 profile 文件夹后重新运行。"
            )
        
        # 重新检查登录状态
        logger.debug("正在重新检查登录状态...")
        await asyncio.sleep(3)
        
        is_logged_in = await self._check_login_status_v11()
        
        if is_logged_in:
            logger.debug("✓ 登录检查通过")
            # 保存登录态
            await self._save_login_state()
            logger.info("✓ 登录态已刷新，下次可 headless 运行")
        else:
            logger.error("✗ 登录似乎未成功")
            raise LoginRequiredException(
                "登录似乎未成功，请检查：\n"
                "1. 账号是否正确\n"
                "2. 网络连接是否正常\n"
                "3. 是否完成了 Google 的验证流程\n"
                "4. 删除 profile 文件夹后重试"
            )

    async def _health_check(self) -> None:
        """
        健康检查（v1.1 改进）
        
        在每次 chat() 前执行，确保会话仍然有效
        如果检测到 session 失效，触发重新登录流程
        """
        logger.debug("执行健康检查...")
        
        # 尝试定位输入框
        input_found = False
        for selector in config.gemini.input_selectors:
            try:
                element = self.page.locator(selector)
                is_visible = await element.is_visible(timeout=3000)
                is_enabled = await element.is_enabled()
                
                if is_visible and is_enabled:
                    input_found = True
                    logger.debug("✓ 健康检查通过")
                    break
            except Exception:
                continue
        
        if not input_found:
            logger.warning("⚠ 健康检查失败：未找到输入框")
            logger.warning("可能的原因：session 失效或页面结构变化")
            logger.warning("继续尝试发送消息...")
            
            # 不再触发重新登录，因为文件上传后输入框可能暂时不可用

    async def send_message(self, prompt: str) -> None:
        """
        发送消息到 Gemini
        1. 健康检查（v1.1 改进）
        2. 定位输入框
        3. 填入文本
        4. 提交消息
        """
        if not self.page:
            raise BrowserException("页面未初始化")

        try:
            # 健康检查（v1.1 改进）
            await self._health_check()

            # 定位输入框（按优先级尝试）
            input_locator = None
            for selector in config.gemini.input_selectors:
                try:
                    element = self.page.locator(selector)
                    await element.wait_for(timeout=5000)
                    input_locator = element
                    logger.debug(f"找到输入框: {selector}")
                    break
                except PlaywrightTimeoutError:
                    continue

            if not input_locator:
                raise ElementNotFoundError("未能找到 Gemini 输入框")

            # 点击输入框
            await input_locator.click()
            await asyncio.sleep(0.2)

            # 填入文本
            await input_locator.fill(prompt)
            logger.debug(f"已填入文本: {prompt[:50]}...")

            # 延迟后提交
            await asyncio.sleep(0.5)

            # 按 Enter 提交
            await self.page.keyboard.press("Enter")
            logger.debug("消息已发送")

            # 等待响应开始
            await asyncio.sleep(1)

        except PlaywrightTimeoutError as e:
            raise TimeoutException(f"发送消息超时: {e}")
        except Exception as e:
            if isinstance(e, (ElementNotFoundError, TimeoutException)):
                raise
            logger.error(f"发送消息失败: {e}")
            raise MessageSendFailedError(f"发送消息失败: {e}")

    async def stream_response(self) -> AsyncGenerator[str, None]:
        """
        流式获取 Gemini 生成的回复

        优化方案（优先级排列）：
        1. **Tier 2: MutationObserver** - 延迟 ~300ms（推荐）
        2. **Tier 1: 轮询方案** - 延迟 ~1s（备用）

        会根据可用性自动选择合适的方案
        """
        if not self.page:
            raise BrowserException("页面未初始化")

        try:
            logger.debug("正在获取 Gemini 回复...")

            # ✅ Tier 2: 尝试 MutationObserver 事件驱动方案（推荐！）
            if MUTATION_OBSERVER_AVAILABLE:
                try:
                    import time
                    start_time = time.time()
                    logger.debug("尝试 MutationObserver 事件驱动方案...")
                    # 这里需要获取响应容器元素
                    # 先尝试常用的选择器
                    response_selectors = [
                        "structured-content-container.model-response-text:last-of-type",
                        "message-content:last-of-type",
                        "div.markdown.markdown-main-panel",
                        "div[data-message-author-role='model']:last-of-type",
                    ]

                    response_element = None
                    for selector in response_selectors:
                        try:
                            element = self.page.locator(selector)
                            if await element.count() > 0:
                                response_element = element
                                logger.debug(f"✓ 找到响应元素: {selector}")
                                break
                        except:
                            continue

                    if response_element:
                        async for chunk in stream_response_mutation_observer(
                            self.page, response_element
                        ):
                            yield chunk
                        elapsed = time.time() - start_time
                        logger.debug(f"✓ MutationObserver 方案成功，耗时: {elapsed:.2f}s")
                        return
                    else:
                        elapsed = time.time() - start_time
                        logger.debug(
                            f"⚠ 未找到响应元素（耗时 {elapsed:.2f}s），跳过 MutationObserver，使用轮询..."
                        )
                except Exception as e:
                    elapsed = time.time() - start_time
                    logger.debug(f"MutationObserver 方案失败（耗时 {elapsed:.2f}s）: {e}，回退到轮询...")

            # 如果 MutationObserver 不可用或失败，使用轮询方案
            import time
            polling_start_time = time.time()
            logger.debug("使用轮询方案获取响应...")


            # 以更长的时间等待响应开始生成（Gemini 服务器响应需要时间）
            logger.debug("等待响应开始生成（最长 10 秒）...")

            # 尝试等待消息容器出现，等待更长时间
            try:
                await self.page.wait_for_selector(
                    "div[role='region'] >> text=I am Gemini, "
                    "div.message-content, "
                    "div[data-message-author-role='model']",
                    timeout=10000  # 增加到 10 秒
                )
                logger.debug("✓ 检测到响应容器已出现")
            except PlaywrightTimeoutError:
                logger.debug("⚠ 响应容器未立即出现，直接开始轮询...")
                # 额外等待 3 秒，给 AI 更多时间生成回复
                logger.debug("额外等待 3 秒...")
                await asyncio.sleep(3)

            # 多个响应容器选择器（优先级排列）
            # 针对 Gemini 3 Flash 的新界面 - 查找聊天区域内的最新 AI 回复
            # KEY FIX: 优先在 main 标签内查找，避免选到侧边栏或菜单
            response_selectors = [
                # 优先级 0: 根据实际 DOM 结构（2024 年后的 Gemini UI）
                "structured-content-container.model-response-text:last-of-type",  # 新 UI 响应内容容器
                "message-content:last-of-type",                                   # 消息内容组件
                "div.markdown.markdown-main-panel",                               # 包含实际回复文本的 div
                # 优先级1: 查找 main 标签内的最后一个消息（最准确，main = 主聊天区）
                "main div[class*='message']:last-of-type",              # main 中最后一条消息
                "main > div:last-child",                                 # main 最后一个直接子元素
                "main div[data-message-author-role='model']:last-of-type",  # main 中最后的 AI 消息
                # 优先级1.5: 查找任何包含内容的 main 子元素（新增）
                "main [role='presentation']:last-of-type",               # main 中最后一个 presentation 元素
                "main div[class*='response']:last-of-type",              # main 中最后一个响应相关元素
                # 优先级2: 查找明确是聊天消息的容器
                "div[class*='conversation'] div[class*='message']:last-child",  # 对话中最后一条消息
                "div[class*='chat'] div[class*='message']:last-of-type",  # 聊天区最后一条
                # 优先级2.5: 通用选择器（新增）
                "[data-message-author-role='assistant']:last-of-type",   # 助手消息
                "[data-message-author-role='ai']:last-of-type",          # AI 消息
                # 优先级3: 查找最后一条包含实际内容的消息
                "div[data-message-author-role='model']:last-of-type",    # 最后的 AI 消息
                # 优先级3.5: 最宽松的选择器（新增）
                "main > div[class]:last-of-type",                        # main 中最后一个有 class 的 div
                "main [class*='container']:last-of-type",                # main 中最后一个容器
                # 优先级4: 备用方案（可能包含历史，需要过滤）
                "div[class*='message-list'] > div:last-child",          # 消息列表最后一条
                "div[data-message-author-role='model']",                # 标准 Gemini 数据属性
            ]

            response_selector = None
            response_element = None

            # 尝试找到响应容器
            for i, selector in enumerate(response_selectors):
                try:
                    logger.debug(f"尝试选择器 #{i+1}/{len(response_selectors)}: {selector}")
                    elements = await self.page.locator(selector).all()
                    if elements:
                        # 从最后一个元素开始往前检查，跳过系统消息和短内容
                        for element_idx in range(len(elements) - 1, max(-1, len(elements) - 3)):
                            response_element = elements[element_idx]
                            response_selector = selector
                            text_content = await response_element.inner_text()

                            # 打印前100个字符用于调试
                            preview = text_content[:100].replace('\n', ' ')
                            logger.debug(f"✓ 找到响应容器（选择器 #{i+1}），包含文本长度: {len(text_content)}")
                            logger.debug(f"  预览: {preview}...")

                            # 首先检查系统消息：上传文件后的"成功执行"类型消息
                            if any(keyword in text_content for keyword in ['成功执行了', '处理中', '上传中']):
                                logger.debug(f"  ⚠ 系统消息提示，AI 可能还在处理，等待实际回复...")
                                response_element = None
                                response_selector = None
                                continue

                            # 检查长度：如果太短，直接跳过（可能是系统消息）
                            if len(text_content) < 30:
                                logger.debug(f"  ⚠ 内容太短（{len(text_content)} 字符），可能是系统消息，继续尝试...")
                                response_element = None
                                response_selector = None
                                continue

                            # 检查是否是真实的 AI 回复（不是聊天菜单或历史）
                            lines = text_content.split('\n')
                            long_lines = sum(1 for line in lines if len(line.strip()) > 20)
                            short_lines = sum(1 for line in lines if len(line.strip()) < 20 and len(line.strip()) > 0)

                            # 计算平均行长
                            non_empty_lines = [line.strip() for line in lines if line.strip()]
                            avg_line_length = sum(len(line) for line in non_empty_lines) / len(non_empty_lines) if non_empty_lines else 0

                            # 计算"Gemini 说"出现次数（用于检测历史内容）
                            gemini_marker_count = text_content.count("Gemini 说")

                            # 菜单检测器：侧边栏菜单（大量短行）
                            is_menu = (
                                short_lines > 10 and long_lines < 3 and
                                avg_line_length < 20 and
                                len(text_content) < 300
                            )

                            # 聊天历史检测器（改进版）
                            # 检测特征：多个标题列表，没有连贯的文本
                            is_chat_history = (
                                # 特征1: 多个对话标记
                                (gemini_marker_count > 2 or text_content.count("你说") > 1) or
                                # 特征2: 大量重复的标题或短行（历史列表）
                                (short_lines > 15 and avg_line_length < 30) or
                                # 特征3: 包含多个对话标题但无实际回复内容
                                (len(text_content) > 200 and len(text_content) < 800 and
                                 not any(keyword in text_content for keyword in ['是', '可以', '为', '的', '了', '我', '你', '它']))
                            )

                            # 真实回复检测器（单个新回复）
                            is_real_response = (
                                # 特征1: 足够长的文本
                                len(text_content) > 80 or
                                # 特征2: 至少有 2 行长内容
                                long_lines >= 2 or
                                # 特征3: 平均行长 > 20 字
                                avg_line_length > 20 or
                                # 特征4: 包含常见回复词汇
                                any(keyword in text_content for keyword in ['是', '可以', '为', '的', '了', '我', '你', '它', '这个', '那个', '图片', '文件'])
                            )

                            logger.debug(f"  分析: 长行={long_lines}, 短行={short_lines}, 平均={avg_line_length:.1f}, Gemini标记={gemini_marker_count}, 菜单={is_menu}, 历史={is_chat_history}, 真实={is_real_response}")

                            if is_menu:
                                logger.debug(f"  ⚠ 确认是侧边栏菜单，继续尝试下一个...")
                                response_element = None
                                response_selector = None
                                continue

                            if is_chat_history:
                                logger.debug(f"  ⚠ 确认是聊天历史列表（{gemini_marker_count} 个Gemini标记），继续尝试下一个...")
                                response_element = None
                                response_selector = None
                                continue

                            if not is_real_response:
                                logger.debug(f"  ⚠ 内容太短或不像 AI 回复，继续尝试...")
                                response_element = None
                                response_selector = None
                                continue

                            # 找到有效的响应，跳出循环
                            break

                        # 如果找到了有效的响应，跳出外层循环
                        if response_selector and response_element:
                            break

                except Exception as e:
                    logger.debug(f"✗ 选择器 #{i+1} 失败: {e}")
                    continue

            # 如果第一轮都失败了，使用 JavaScript 查找最新的 AI 回复
            if not response_selector or not response_element:
                logger.debug("第一轮选择器都失败了，使用 JavaScript 查找最新的 AI 回复...")

                try:
                    # 使用通用的 JavaScript 方法扫描所有包含文本的容器
                    js_result = await self.page.evaluate('''() => {
                        const candidates = [];

                        // 策略 1: 检查所有 div 元素，找最长的内容（排除系统消息）
                        document.querySelectorAll('div, section, article').forEach((el) => {
                            const text = el.innerText || '';
                            const directText = el.childNodes
                                .filter(node => node.nodeType === 3)
                                .map(node => node.textContent)
                                .join('');

                            // 条件：足够长（>100字符），不是系统消息，不在菜单中
                            if (text.length > 100 &&
                                !text.includes('成功执行') &&
                                !text.includes('查询') &&
                                !text.includes('处理中') &&
                                el.closest('aside') === null &&
                                el.closest('nav') === null) {

                                candidates.push({
                                    element: el,
                                    text: text,
                                    length: text.length,
                                    className: el.className,
                                    dataAttrs: Object.keys(el.dataset).join(',')
                                });
                            }
                        });

                        // 按文本长度排序（最长的通常是最新的回复）
                        candidates.sort((a, b) => b.length - a.length);

                        if (candidates.length > 0) {
                            // 返回前 3 个最长的候选
                            return {
                                found: true,
                                candidates: candidates.slice(0, 3).map(c => ({
                                    length: c.length,
                                    className: c.className.substring(0, 80),
                                    dataAttrs: c.dataAttrs,
                                    text: c.text.substring(0, 100)
                                })),
                                best: {
                                    length: candidates[0].length,
                                    text: candidates[0].text.substring(0, 150)
                                }
                            };
                        }

                        return { found: false };
                    }''')

                    if js_result.get('found'):
                        logger.debug(f"✓ 找到 {len(js_result.get('candidates', []))} 个可能的 AI 回复容器")
                    else:
                        logger.debug("✗ JavaScript 扫描也没有找到足够长的内容")

                except Exception as e:
                    logger.debug(f"JavaScript 扫描失败: {e}")

            # 如果仍然失败，等待更长时间后重试
            if not response_selector or not response_element:
                logger.debug("JavaScript 查找也失败了，等待 5 秒后重试选择器...")
                await asyncio.sleep(5)

                # 重试一次
                for i, selector in enumerate(response_selectors[:3]):  # 只重试前 3 个性能最好的选择器
                    try:
                        logger.debug(f"重试选择器 #{i+1}: {selector}")
                        elements = await self.page.locator(selector).all()
                        if elements:
                            response_element = elements[-1]
                            response_selector = selector
                            text_content = await response_element.inner_text()
                            logger.debug(f"✓ 重试成功！找到响应容器，长度: {len(text_content)}")

                            # 验证内容长度
                            if len(text_content) < 30:
                                logger.debug(f"重试结果内容太短（{len(text_content)} 字符），继续...")
                                continue

                            # 验证不是系统消息
                            if any(keyword in text_content for keyword in ['成功执行', '查询']):
                                logger.debug(f"重试结果是系统消息，继续...")
                                continue

                            break
                    except Exception as e:
                        logger.debug(f"重试选择器 #{i+1} 失败: {e}")

            if not response_selector or not response_element:
                # 所有方法都失败，尝试调试：获取更详细的页面结构
                logger.error(f"所有方法都失败了，获取详细页面结构...")
                try:
                    # 获取更详细的页面 HTML 结构
                    page_info = await self.page.evaluate("""
                    () => {
                        const info = {
                            title: document.title,
                            url: document.location.href,
                            mainElement: null,
                            regions: [],
                            allMessages: [],
                            messages: document.querySelectorAll('[role="region"]').length
                        };

                        // 检查 main
                        if (document.querySelector('main')) {
                            info.mainElement = {
                                className: document.querySelector('main').className,
                                childCount: document.querySelector('main').children.length,
                                innerHTML: document.querySelector('main').innerHTML.substring(0, 500)
                            };
                        }

                        // 检查所有 region
                        document.querySelectorAll('[role="region"]').forEach((region, idx) => {
                            info.regions.push({
                                index: idx,
                                className: region.className,
                                textLength: region.innerText.length,
                                text: region.innerText.substring(0, 150)
                            });
                        });

                        // 查找所有可能是消息的容器
                        ['div', 'section', 'article'].forEach(tag => {
                            document.querySelectorAll(tag).forEach(el => {
                                const text = el.innerText || '';
                                if (text.length > 20 && text.length < 5000) {
                                    info.allMessages.push({
                                        tag: tag,
                                        className: el.className,
                                        textLength: text.length
                                    });
                                }
                            });
                        });

                        return info;
                    }
                    """)

                    logger.error(f"页面标题: {page_info.get('title')}")
                    logger.error(f"页面 URL: {page_info.get('url')}")
                    logger.error(f"Main 元素: {page_info.get('mainElement')}")
                    logger.error(f"Region 数量: {len(page_info.get('regions', []))}")
                    if page_info.get('regions'):
                        logger.error(f"第一个 Region 信息: {page_info['regions'][0]}")

                except Exception as debug_error:
                    logger.error(f"调试获取详细信息失败: {debug_error}", exc_info=True)

                raise ResponseTimeoutError(
                    "无法找到响应容器。可能原因：\n"
                    "1. Gemini 响应生成缓慢（已等待 40+ 秒）\n"
                    "2. 页面 HTML 结构与预期不同\n"
                    "3. 网络连接问题\n"
                    "4. 文件上传后需要手动确认或等待\n\n"
                    "请尝试：\n"
                    "1. 在浏览器中检查是否有确认按钮需要点击\n"
                    "2. 刷新页面后重试\n"
                    "3. 查看日志中的详细信息"
                )

            logger.debug(f"使用选择器: {response_selector}")

            # 最终验证：确保选择的不是聊天历史或菜单
            try:
                final_text = await response_element.inner_text()
                lines = final_text.split('\n')
                short_lines = sum(1 for line in lines if len(line.strip()) < 20 and len(line.strip()) > 0)
                long_lines = sum(1 for line in lines if len(line.strip()) >= 20)
                non_empty_lines = [line.strip() for line in lines if line.strip()]
                avg_line_length = sum(len(line) for line in non_empty_lines) / len(non_empty_lines) if non_empty_lines else 0

                # 检查系统消息关键词
                system_keywords = ['成功执行', '查询', '上传', '处理中', '请稍候']
                is_system_message = any(keyword in final_text for keyword in system_keywords)

                # 最终检查：如果看起来像菜单、历史列表或系统消息，拒绝使用
                is_invalid = (
                    is_system_message or  # 系统消息
                    (short_lines > 15 and avg_line_length < 30) or  # 菜单/历史列表
                    (len(final_text) > 200 and len(final_text) < 800 and
                     not any(keyword in final_text for keyword in ['是', '可以', '为', '的', '我', '图片', '文件']))  # 标题列表
                )

                if is_invalid:
                    logger.debug(f"⚠ 最终验证失败：选中的元素看起来无效")
                    logger.debug(f"   文本长度: {len(final_text)}, 短行: {short_lines}, 长行: {long_lines}, 平均: {avg_line_length:.1f}")
                    if is_system_message:
                        logger.debug(f"   检测到系统消息，说明 AI 还在生成回复中...")
                    logger.debug(f"   文本预览: {final_text[:200]}...")

                    # 当检测到系统消息时，增加等待时间，因为这意味着 AI 还在处理
                    wait_time = 8 if is_system_message else 3
                    logger.debug(f"等待 {wait_time} 秒后重新选择响应容器...")
                    await asyncio.sleep(wait_time)

                    # 重新尝试选择响应容器
                    retry_count = 0
                    max_retries = 5  # 增加重试次数（从 3 改为 5）
                    found_valid = False

                    while retry_count < max_retries and not found_valid:
                        retry_count += 1
                        logger.debug(f"重新选择响应容器（尝试 {retry_count}/{max_retries}）...")

                        for idx, selector in enumerate(response_selectors[:10]):  # 尝试更多选择器（从 5 改为 10）
                            try:
                                elements = await self.page.locator(selector).all()
                                if elements:
                                    # 从最后开始往前找，确保是最新的消息
                                    for element_idx in range(len(elements) - 1, -1, -1):
                                        retry_element = elements[element_idx]
                                        retry_text = await retry_element.inner_text()

                                        # 严格过滤系统消息：如果包含"成功执行"关键字，直接跳过
                                        if any(keyword in retry_text for keyword in ['成功执行了', '处理中', '上传中']):
                                            logger.debug(f"跳过系统消息: {retry_text[:50]}...")
                                            continue

                                        # 降低验证要求：只需要 10 个字符（从 30 改为 10）
                                        if len(retry_text) >= 10:
                                            response_element = retry_element
                                            response_selector = selector
                                            logger.debug(f"✓ 重新选择成功！找到有效响应容器（选择器 #{idx+1}），长度: {len(retry_text)}")
                                            found_valid = True
                                            break
                            except Exception as e:
                                logger.debug(f"重试选择器失败: {e}")

                        if found_valid:
                            break
                        elif retry_count < max_retries:
                            logger.debug(f"等待 5 秒后继续重试...")
                            await asyncio.sleep(5)  # 增加等待时间（从 3 改为 5）

                    # 如果重试后仍然无效，才抛出异常
                    if not found_valid:
                        current_text = await response_element.inner_text() if response_element else ""
                        if len(current_text) < 30 or any(keyword in current_text for keyword in ['成功执行', '处理中']):
                            raise ResponseTimeoutError(
                                "未能找到正确的响应容器。可能原因：\n"
                                "1. 上传文件后，AI 回复生成缓慢\n"
                                "2. 页面结构与预期不同\n"
                                "3. 网络连接问题导致 AI 未生成回复\n\n"
                                "请尝试：\n"
                                "1. 检查浏览器中是否有 AI 回复显示\n"
                                "2. 等待更长时间后重试\n"
                                "3. 刷新页面后重试"
                            )
                    else:
                        logger.debug(f"✓ 重试成功，使用新选中的响应容器")
            except ResponseTimeoutError:
                raise
            except Exception as e:
                logger.warning(f"最终验证失败，继续尝试流式输出: {e}")

            last_text = ""
            no_change_count = 0
            max_no_change_cycles = 1  # ⚡⚡ 超激进：1 次检查无变化则认为完成（约 10ms）
            check_count = 0
            max_checks = 3000  # 最多检查 3000 次 * 0.01s = 30 秒（增加超时时间）

            while check_count < max_checks:
                check_count += 1
                try:
                    # 获取当前响应文本
                    try:
                        current_text = await response_element.inner_text()

                        # ✅ 多轮对话优化：如果包含多个"Gemini说"，只保留最后一个之后的内容
                        # 这样可以确保在多轮对话中只输出最新的回复
                        gemini_marker_count = current_text.count("Gemini 说")
                        if gemini_marker_count > 1:  # 只有当有多个标记时才需要过滤
                            last_gemini_pos = current_text.rfind("Gemini 说")
                            if last_gemini_pos >= 0:
                                # 提取从最后一个"Gemini说"之后的内容
                                latest_response = current_text[last_gemini_pos + len("Gemini 说"):].strip()
                                # 只在有实质内容时使用（长度 > 10）
                                if len(latest_response) > 10:
                                    old_length = len(current_text)
                                    current_text = latest_response
                                    logger.debug(f"多轮对话：发现 {gemini_marker_count} 个标记，提取最新回复。原始长度: {old_length} -> {len(current_text)}")

                    except Exception as e:
                        logger.debug(f"获取响应文本失败: {e}，重试...")
                        no_change_count += 1
                        await asyncio.sleep(self.check_interval)
                        continue

                    # 提取新增部分
                    if current_text != last_text:
                        new_part = current_text[len(last_text):]
                        if new_part:
                            yield new_part
                            logger.debug(f"收到新内容，长度: {len(new_part)}")
                        last_text = current_text
                        no_change_count = 0  # 重置计数器
                    else:
                        no_change_count += 1
                        if no_change_count % 5 == 0:  # 每隔 5 次打印一次
                            logger.debug(f"无变化续计 ({no_change_count}/{max_no_change_cycles})")

                    # 检查完成条件
                    # 方案1：检测复制按钮（最可靠）
                    try:
                        # 只在响应容器内查找复制按钮，避免误检其他区域的按钮
                        copy_buttons = response_element.locator(
                            "button[aria-label*='Copy'], button[aria-label*='复制'], "
                            "button[title*='Copy'], button[title*='复制'], "
                            "button:has-text('Copy'), button:has-text('复制')"
                        )
                        count = await copy_buttons.count()
                        if count > 0:
                            first_button = copy_buttons.first
                            try:
                                is_visible = await first_button.is_visible(timeout=500)
                                if is_visible:
                                    # 额外检查：确保内容已经足够长
                                    if len(current_text) > 50:
                                        logger.debug("✓ 检测到复制按钮且内容足够长，回复生成完成")
                                        break
                                    else:
                                        logger.debug(f"检测到复制按钮但内容太短（{len(current_text)} 字符），继续等待...")
                            except Exception:
                                pass
                    except Exception as e:
                        logger.debug(f"检查复制按钮出错: {e}")

                    # 方案2：连续无变化则认为完成
                    if no_change_count >= max_no_change_cycles:
                        logger.debug(f"✓ 连续 {max_no_change_cycles} 次无变化，认为生成完成")
                        break

                    # 等待下一次检查
                    await asyncio.sleep(self.check_interval)

                except Exception as e:
                    logger.debug(f"获取响应文本异常（检查 #{check_count}）: {e}")
                    await asyncio.sleep(self.check_interval)
                    continue

            if check_count >= max_checks:
                logger.warning(f"⚠ 达到最大检查次数 ({max_checks})，停止")

            polling_elapsed = time.time() - polling_start_time
            logger.debug(f"✓ 响应生成完成，总长度: {len(last_text)} 字符，检查次数: {check_count}，轮询耗时: {polling_elapsed:.2f}s")

        except ResponseTimeoutError:
            raise
        except Exception as e:
            logger.error(f"流式输出失败: {e}", exc_info=True)
            raise ResponseTimeoutError(f"流式输出失败: {e}")

    async def chat(self, prompt: str) -> str:
        """
        完整聊天流程
        1. 发送消息
        2. 流式输出并实时打印回复
        3. 返回完整文本
        """
        full_response = ""

        try:
            # 等待页面稳定（特别是文件上传后）
            logger.debug("等待页面稳定...")
            await asyncio.sleep(1)

            # 发送消息
            await self._execute_with_retry(
                self.send_message, prompt, max_retries=self.retry_count
            )

            logger.debug("消息已发送，开始接收回复...")
            print("\n[Gemini] ", end="", flush=True)  # 实时输出提示

            # 流式输出
            async for chunk in self.stream_response():
                print(chunk, end="", flush=True)
                full_response += chunk

            print()  # 换行

            return full_response

        except Exception as e:
            logger.error(f"聊天失败: {e}")
            raise

    async def upload_file(self, file_path: str) -> Dict[str, Any]:
        """
        上传文件到 Gemini

        Args:
            file_path: 文件路径（支持相对路径和绝对路径）

        Returns:
            上传结果字典：
            {
                'success': bool,
                'file_name': str,
                'file_type': str,
                'file_size': int,
                'file_size_mb': float,
                'upload_time': float,  # 上传耗时（秒）
                'preview_visible': bool,
                'ready_for_chat': bool,  # 是否已准备好继续聊天
                'message': str  # 错误或成功消息
            }

        Raises:
            FileNotFoundError: 文件不存在
            FileSizeError: 文件大小超限
            FileTypeError: 文件类型不支持
            FileUploadError: 上传过程失败
            BrowserException: 浏览器未初始化
        """
        if not self.page:
            raise BrowserException("页面未初始化")

        import time
        start_time = time.time()

        try:
            # 1. 参数规范化：转换为绝对路径
            file_path_obj = Path(file_path).resolve()
            logger.debug(f"开始上传文件: {file_path_obj}")

            # 2. 文件验证
            validator = FileValidator(
                config_file_types=config.gemini.supported_file_types,
                config_max_sizes=config.gemini.max_file_sizes
            )
            validation_result = validator.validate(str(file_path_obj))
            logger.debug(f"✓ 文件验证通过: {validation_result['file_name']}")

            # 3. 初始化 UI 交互器
            ui = FileUploadUI(
                page=self.page,
                config_selectors={
                    'upload_button': config.gemini.upload_button_selectors,
                    'file_input': config.gemini.file_input_selectors,
                    'upload_complete': config.gemini.upload_complete_selectors,
                },
                timeout=config.gemini.upload_timeout
            )

            # 4. 执行上传（通过重试机制）
            upload_result = await self._execute_with_retry(
                self._perform_upload,
                ui,
                str(file_path_obj),
                max_retries=config.gemini.upload_retry_count
            )

            # 5. 计算耗时
            elapsed_time = time.time() - start_time
            upload_result['upload_time'] = elapsed_time

            # 6. 构建返回结果
            is_ready = upload_result.get('ready_for_chat', True)
            warning = upload_result.get('warning', '')

            if not is_ready:
                # 文件未真正上传成功
                result = {
                    'success': False,
                    'file_name': validation_result['file_name'],
                    'file_type': validation_result['file_type'],
                    'file_size': validation_result['file_size'],
                    'file_size_mb': validation_result['file_size_mb'],
                    'upload_time': elapsed_time,
                    'preview_visible': upload_result.get('preview_visible', False),
                    'ready_for_chat': False,
                    'message': f"✗ 文件 '{validation_result['file_name']}' 上传可能失败（{elapsed_time:.2f}秒）"
                }
                if warning:
                    result['message'] += f"\n原因: {warning}"
                logger.warning(f"文件上传可能失败: {result['message']}")
            else:
                # 文件上传成功
                result = {
                    'success': True,
                    'file_name': validation_result['file_name'],
                    'file_type': validation_result['file_type'],
                    'file_size': validation_result['file_size'],
                    'file_size_mb': validation_result['file_size_mb'],
                    'upload_time': elapsed_time,
                    'preview_visible': upload_result.get('preview_visible', False),
                    'ready_for_chat': True,
                    'message': f"✓ 文件 '{validation_result['file_name']}' 上传成功（{elapsed_time:.2f}秒）"
                }
                logger.debug(f"✓ 文件上传完成: {result['message']}")

            return result

        except FileUploadException as e:
            # 文件验证异常（FileNotFoundError, FileSizeError, FileTypeError）
            elapsed_time = time.time() - start_time
            logger.error(f"文件检验失败: {e}")
            raise

        except Exception as e:
            # 其他异常转换为 FileUploadError
            elapsed_time = time.time() - start_time
            logger.error(f"文件上传失败: {e}", exc_info=True)
            raise FileUploadError(str(e))

    async def _perform_upload(self, ui: FileUploadUI, file_path: str) -> Dict[str, Any]:
        """
        执行文件上传 (使用 Playwright 的 filechooser 事件)

        这是 Playwright 处理文件选择器的标准方法：
        0. 预处理：聚焦输入框，确保上传按钮可见
        1. 启动文件选择器事件监听
        2. 点击上传按钮
        3. 等待文件选择器事件触发
        4. 设置文件路径
        5. 关闭文件选择器并提交

        Args:
            ui: FileUploadUI 实例
            file_path: 文件绝对路径

        Returns:
            上传操作结果字典
        """
        try:
            logger.debug("正在执行文件上传...")

            # 步骤 0: 清理状态 - 关闭任何可能打开的菜单
            logger.debug("步骤 0: 清理页面状态...")
            try:
                # 点击页面其他地方关闭可能打开的菜单
                await self.page.click('body', force=True)
                await asyncio.sleep(0.2)

                # 清理文件输入框的状态
                file_inputs = await self.page.locator('input[type="file"]').all()
                if file_inputs:
                    logger.debug(f"清理 {len(file_inputs)} 个文件输入框")
                    for file_input in file_inputs:
                        try:
                            await file_input.evaluate('el => el.value = ""')
                        except:
                            pass

                logger.debug("激活输入框...")
                for selector in config.gemini.input_selectors:
                    try:
                        input_box = self.page.locator(selector)
                        if await input_box.count() > 0:
                            await input_box.click()
                            await asyncio.sleep(0.2)
                            break
                    except:
                        continue

                logger.debug("✓ 已清理页面状态")
            except Exception as e:
                logger.debug(f"清理页面状态失败: {e}")

            # 步骤 1: 查找上传按钮
            logger.debug("步骤 1: 查找上传按钮...")
            upload_button = await ui.find_upload_button()

            if not upload_button:
                # 备用方案：尝试直接触发文件选择器
                logger.warning("⚠ 未找到上传按钮，尝试备用方案...")
                try:
                    # 尝试找到所有文件输入框并直接设置文件
                    all_file_inputs = await self.page.locator('input[type="file"]').all()
                    if all_file_inputs:
                        logger.debug(f"找到 {len(all_file_inputs)} 个文件输入框，尝试直接设置文件")
                        await all_file_inputs[0].set_input_files(file_path)
                        logger.debug("✓ 文件已直接设置到输入框（备用方案）")
                    else:
                        raise FileUploadError(
                            "未找到上传按钮和文件输入框。这可能是因为：\n"
                            "1. 页面结构已变化，需要更新选择器\n"
                            "2. 当前页面不支持文件上传\n"
                            "3. 需要先进入聊天界面\n"
                            "4. 建议：在浏览器中手动点击输入框，然后重新尝试上传"
                        )
                except Exception as e:
                    raise FileUploadError(
                        f"未找到上传按钮，备用方案也失败: {e}\n"
                        "建议：在浏览器中手动点击输入框，然后重新尝试上传"
                    )

# 步骤 2: 使用 Playwright 的 filechooser 事件拦截（不弹出选择器）
            logger.debug("步骤 2: 使用 filechooser 事件拦截文件选择器...")

            try:
                # 启动事件监听任务
                event_task = asyncio.create_task(
                    self.page.wait_for_event('filechooser')
                )

                # 点击上传按钮
                logger.debug("点击上传按钮...")
                await upload_button.click()
                logger.debug("✓ 已点击上传按钮")

                # 等待菜单渲染
                await asyncio.sleep(1.0)

                # 根据文件类型选择上传选项
                file_type = file_path_obj.suffix.lower()
                logger.debug(f"文件类型: {file_type}")

                # 根据文件类型选择不同的上传选项文本
                if file_type in ['.mp4', '.webm', '.mov', '.avi', '.mkv']:
                    # 视频文件
                    upload_option_texts = ["上传视频", "Upload video", "选择视频"]
                elif file_type in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp']:
                    # 图片文件
                    upload_option_texts = ["上传图片", "Upload image", "选择图片"]
                elif file_type in ['.pdf']:
                    # PDF 文件
                    upload_option_texts = ["上传 PDF", "Upload PDF", "选择 PDF"]
                else:
                    # 其他文件（文本、数据等）
                    upload_option_texts = ["上传文件", "Upload file", "选择文件"]

                logger.debug(f"查找上传选项: {upload_option_texts}")

                # 查找并点击相应的上传选项
                upload_option_clicked = False
                for option_text in upload_option_texts:
                    try:
                        upload_option = self.page.get_by_text(option_text).first
                        if await upload_option.count() > 0:
                            logger.debug(f"✓ 找到上传选项: {option_text}")
                            await upload_option.click()
                            logger.debug(f"✓ 已点击上传选项: {option_text}")
                            upload_option_clicked = True
                            await asyncio.sleep(0.5)
                            break
                    except Exception as e:
                        logger.debug(f"查找上传选项 '{option_text}' 失败: {e}")
                        continue

                if not upload_option_clicked:
                    # 备用方法：使用 data-test-id
                    logger.debug("尝试使用 data-test-id 查找上传选项...")
                    try:
                        upload_option = self.page.locator('button[data-test-id="local-images-files-uploader-button"]')
                        if await upload_option.count() > 0:
                            logger.debug("✓ 通过 data-test-id 找到上传文件选项")
                            await upload_option.click()
                            logger.debug("✓ 已点击上传文件选项")
                            upload_option_clicked = True
                            await asyncio.sleep(0.5)
                    except Exception as e:
                        logger.debug(f"data-test-id 方法失败: {e}")

                if not upload_option_clicked:
                    logger.warning(f"⚠ 未找到任何上传选项，尝试直接触发文件选择器")

                # 等待 filechooser 事件触发
                try:
                    file_chooser = await asyncio.wait_for(event_task, timeout=10.0)
                    logger.debug("✓ 文件选择器事件已触发（已被拦截）")

                    # 设置文件路径（这不会弹出选择器，因为事件已被拦截）
                    logger.debug(f"设置文件路径: {file_path}")
                    await file_chooser.set_files(file_path)
                    logger.debug("✓ 文件已设置（文件选择器被拦截，未弹出）")

                except asyncio.TimeoutError:
                    # 取消事件监听任务
                    if not event_task.done():
                        event_task.cancel()
                        try:
                            await event_task
                        except asyncio.CancelledError:
                            pass

                    # 文件选择器事件超时，尝试备用方案
                    logger.warning("⚠ 文件选择器事件超时，尝试备用方案...")
                    
                    # 备用方案：直接查找文件输入框并设置
                    file_inputs = await self.page.locator('input[type="file"]').all()
                    if file_inputs:
                        logger.debug(f"备用方案：找到 {len(file_inputs)} 个文件输入框")
                        await file_inputs[-1].set_input_files(file_path)
                        logger.debug("✓ 文件已通过备用方案设置")
                    else:
                        raise FileUploadError(
                            "等待文件选择器超时，且未找到文件输入框。\n"
                            "可能的原因：\n"
                            "1. 点击的按钮未正确触发文件选择器\n"
                            "2. 页面结构已变化\n"
                            "3. 页面使用了非标准的文件上传方式"
                        )

            except FileUploadError:
                raise
            except Exception as chooser_error:
                logger.error(f"处理文件选择器失败: {chooser_error}", exc_info=True)
                raise FileUploadError(f"处理文件选择器失败: {chooser_error}")

            # 步骤 3: 等待文件处理
            logger.debug("步骤 3: 等待文件处理...")
            await asyncio.sleep(5)  # 增加等待时间（从 0.5 秒增加到 5 秒）

            # 步骤 4: 验证文件是否已加载到页面
            logger.debug("步骤 4: 验证文件是否已加载...")
            file_loaded = await ui.check_file_loaded()

            if file_loaded:
                logger.debug("✓ 文件已在页面中检测到")
            else:
                logger.debug("ℹ 文件输入框中未检测到文件，但可能已通过其他方式处理")

            # 步骤 5: 等待上传完成
            logger.debug("步骤 5: 等待上传完成...")
            upload_complete = await ui.wait_for_upload_complete(
                timeout=config.gemini.upload_timeout
            )

            if not upload_complete:
                logger.warning("⚠ 未检测到明确的上传完成标志")
                logger.warning("⚠ 文件可能只是设置到了输入框，但没有真正上传到服务器")
                logger.warning("⚠ 建议：在浏览器中手动检查文件是否已显示在聊天输入框中")

                # 最后一次尝试：检查页面上是否真的有新的文件元素
                try:
                    attachments = await self.page.locator('[class*="attachment"], [class*="attached-file"]').count()
                    preview_images = await self.page.locator('img[class*="preview"], img[class*="thumbnail"]').count()
                    file_names = await self.page.locator('div[class*="filename"], span[class*="filename"]').count()

                    logger.debug(f"最后一次检查: 附件={attachments}, 预览={preview_images}, 文件名={file_names}")

                    if attachments > 0 or preview_images > 0 or file_names > 0:
                        logger.debug("✓ 最终检查发现文件元素，认为上传可能成功")
                        upload_complete = True
                    else:
                        logger.error("✗ 最终检查未发现任何文件元素，上传可能失败")
                        # 不抛出异常，但标记为未准备好
                        return {
                            'preview_visible': False,
                            'ready_for_chat': False,
                            'warning': '文件可能未成功上传，请在浏览器中手动检查'
                        }
                except Exception as e:
                    logger.error(f"最终检查失败: {e}")
                    return {
                        'preview_visible': False,
                        'ready_for_chat': False,
                        'warning': f'文件上传验证失败: {e}'
                    }

            logger.debug("✓ 文件上传完成")

            # 额外等待，让页面完全稳定（特别是 headless 模式）
            logger.debug("额外等待 2 秒，让页面完全稳定...")
            await asyncio.sleep(2)

            return {
                'preview_visible': upload_complete,
                'ready_for_chat': upload_complete  # 只有真正上传完成才标记为准备好
            }

        except FileUploadError:
            raise
        except Exception as e:
            logger.error(f"上传过程异常: {e}", exc_info=True)
            raise FileUploadError(str(e))

    async def _execute_with_retry(
        self, func: Callable, *args, max_retries: int = None, **kwargs
    ) -> Any:
        """
        通用重试装饰器

        重试策略：
        - 第 1 次失败：延迟 1 秒重试
        - 第 2 次失败：延迟 2 秒重试
        - 第 3 次失败：延迟 4 秒重试（指数退避）
        - 所有重试失败：抛出异常
        """
        if max_retries is None:
            max_retries = self.retry_count

        last_exception = None

        for attempt in range(max_retries + 1):
            try:
                return await func(*args, **kwargs)

            except BrowserCrashedException as e:
                logger.error(f"浏览器已崩溃，尝试重启...")
                # 浏览器崩溃，触发重启
                await self.launch()
                if attempt < max_retries:
                    await asyncio.sleep(2)
                    continue
                raise

            except (TimeoutException, ElementNotFoundError, MessageSendFailedError):
                last_exception = e
                if attempt < max_retries:
                    # 指数退避
                    delay = 2 ** attempt  # 1, 2, 4, 8...
                    logger.warning(f"操作失败，{delay}秒后重试（{attempt + 1}/{max_retries}）: {e}")
                    await asyncio.sleep(delay)
                    continue
                raise

            except Exception as e:
                last_exception = e
                if attempt < max_retries:
                    delay = 2 ** attempt
                    logger.warning(f"未知错误，{delay}秒后重试（{attempt + 1}/{max_retries}）: {e}")
                    await asyncio.sleep(delay)
                    continue
                raise

        if last_exception:
            raise last_exception

    def _get_random_user_agent(self) -> str:
        """获取随机现代 User Agent"""
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
        ]
        return random.choice(user_agents)

    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self.launch()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器退出"""
        await self.close()
        return False

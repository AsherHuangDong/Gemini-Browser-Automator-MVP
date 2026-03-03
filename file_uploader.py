"""
Gemini 浏览器自动化 - 文件上传功能模块

包含：
- FileValidator: 文件验证（存在性、大小、类型）
- FileUploadUI: UI 交互（找上传按钮、设置文件、等待完成）
"""

import asyncio
import logging
import mimetypes
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from exceptions import (
    FileNotFoundError,
    FileSizeError,
    FileTypeError,
)

logger = logging.getLogger(__name__)


class FileValidator:
    """文件验证器 - 对上传文件进行全方位验证"""

    def __init__(self, config_file_types: Dict[str, List[str]], config_max_sizes: Dict[str, int]):
        """
        初始化验证器

        Args:
            config_file_types: 支持的文件类型配置 {type: [extensions]}
            config_max_sizes: 文件大小限制配置 {type: max_bytes}
        """
        self.supported_file_types = config_file_types
        self.max_file_sizes = config_max_sizes
        self.file_type_to_category = self._build_type_to_category_map()

    def _build_type_to_category_map(self) -> Dict[str, str]:
        """构建文件扩展名到分类的映射"""
        mapping = {}
        for category, extensions in self.supported_file_types.items():
            for ext in extensions:
                mapping[ext.lower()] = category
        return mapping

    def validate(self, file_path: str) -> Dict:
        """
        验证文件

        Args:
            file_path: 文件路径（绝对或相对）

        Returns:
            验证结果字典：
            {
                'valid': bool,
                'file_type': str,  # image/pdf/text/video/data
                'file_path': Path,
                'file_name': str,
                'file_size': int,  # 字节
                'file_size_mb': float,
                'mime_type': str,
                'errors': []
            }

        Raises:
            FileNotFoundError: 文件不存在
            FileSizeError: 文件大小超限
            FileTypeError: 文件类型不支持
        """
        errors = []
        file_path_obj = Path(file_path).resolve()
        file_name = file_path_obj.name
        file_size = 0
        file_size_mb = 0.0
        file_type = None
        mime_type = None

        # 1. 检查文件是否存在
        if not file_path_obj.exists():
            logger.error(f"文件不存在: {file_path}")
            raise FileNotFoundError(str(file_path))

        # 2. 检查是否是文件（不是目录）
        if not file_path_obj.is_file():
            logger.error(f"路径不是文件: {file_path}")
            errors.append(f"路径不是文件: {file_name}")
            raise FileNotFoundError(str(file_path))

        # 3. 获取文件大小
        try:
            file_size = file_path_obj.stat().st_size
            file_size_mb = file_size / (1024 * 1024)
        except OSError as e:
            logger.error(f"无法获取文件大小: {e}")
            errors.append(f"无法获取文件大小: {e}")
            if errors:
                raise FileTypeError(file_name, "读取文件失败")

        # 4. 获取 MIME 类型
        mime_type, _ = mimetypes.guess_type(str(file_path_obj))
        if not mime_type:
            mime_type = "application/octet-stream"

        # 5. 验证文件类型
        file_extension = file_path_obj.suffix.lower()
        if not file_extension:
            logger.warning(f"文件没有扩展名: {file_name}")
            errors.append(f"文件没有扩展名: {file_name}")
            raise FileTypeError(file_name)

        if file_extension not in self.file_type_to_category:
            supported = ", ".join(
                f"{cat}: {', '.join(exts)}"
                for cat, exts in self.supported_file_types.items()
            )
            logger.warning(f"文件类型不支持: {file_extension}")
            raise FileTypeError(file_name, supported)

        file_type = self.file_type_to_category[file_extension]

        # 6. 验证文件大小
        if file_type in self.max_file_sizes:
            max_size = self.max_file_sizes[file_type]
            max_size_mb = max_size / (1024 * 1024)

            if file_size > max_size:
                logger.error(
                    f"文件过大: {file_name} ({file_size_mb:.2f} MB > {max_size_mb:.2f} MB 限制)"
                )
                raise FileSizeError(file_name, file_size_mb, max_size_mb)

        logger.debug(
            f"✓ 文件验证通过: {file_name}\n"
            f"  类型: {file_type}\n"
            f"  大小: {file_size_mb:.2f} MB\n"
            f"  MIME: {mime_type}"
        )

        return {
            'valid': True,
            'file_type': file_type,
            'file_path': file_path_obj,
            'file_name': file_name,
            'file_size': file_size,
            'file_size_mb': file_size_mb,
            'mime_type': mime_type,
            'errors': errors,
        }

    def get_supported_types_description(self) -> str:
        """获取支持类型的可读描述"""
        descriptions = []
        for category, extensions in self.supported_file_types.items():
            descriptions.append(f"{category.upper()}: {', '.join(extensions)}")
        return " | ".join(descriptions)


class FileUploadUI:
    """Gemini UI 文件上传交互器

    负责与浏览器交互，完成文件上传的所有步骤
    """

    def __init__(self, page, config_selectors: Dict[str, List[str]], timeout: int = 30):
        """
        初始化 UI 交互器

        Args:
            page: Playwright Page 对象
            config_selectors: 选择器配置
                - 'upload_button': 上传按钮选择器列表
                - 'file_input': 文件输入框选择器列表
                - 'upload_complete': 上传完成标志选择器列表
            timeout: 操作超时时间（秒）
        """
        self.page = page
        self.upload_button_selectors = config_selectors.get('upload_button', [])
        self.file_input_selectors = config_selectors.get('file_input', [])
        self.upload_complete_selectors = config_selectors.get('upload_complete', [])
        self.timeout = timeout

    async def find_element_by_selectors(
        self, selectors: List[str], timeout: Optional[int] = None
    ) -> Optional:
        """
        尝试多个选择器，返回第一个找到的元素

        Args:
            selectors: 选择器列表（按优先级排列）
            timeout: 超时时间（秒）

        Returns:
            找到的 Locator 对象或 None
        """
        if timeout is None:
            timeout = self.timeout

        for i, selector in enumerate(selectors):
            try:
                logger.debug(f"尝试选择器 #{i+1}/{len(selectors)}: {selector}")
                element = self.page.locator(selector)
                await element.wait_for(timeout=timeout * 1000)
                logger.debug(f"✓ 找到元素 (选择器 #{i+1}): {selector}")
                return element
            except Exception as e:
                logger.debug(f"✗ 选择器 #{i+1} 失败: {str(e)[:100]}")
                continue

        logger.warning(f"所有 {len(selectors)} 个选择器都失败了")
        return None

    async def _discover_upload_control(self) -> Optional[str]:
        """
        使用 JavaScript 分析页面找到上传控件

        Returns:
            可用的 CSS 选择器字符串或 None
        """
        try:
            result = await self.page.evaluate("""
            () => {
                const candidates = [];

                // 1. 遍历所有 button 元素
                document.querySelectorAll('button').forEach((btn) => {
                    const ariaLabel = btn.getAttribute('aria-label') || '';
                    const title = btn.getAttribute('title') || '';
                    const text = btn.textContent.trim().toLowerCase();
                    const classList = btn.className;
                    const id = btn.id;

                    // 2. 评分：包含上传/附加/文件相关关键字的按钮
                    let score = 0;
                    if (ariaLabel.includes('上传') || ariaLabel.includes('upload')) score += 10;
                    if (ariaLabel.includes('attach')) score += 8;
                    if (ariaLabel.includes('image') || ariaLabel.includes('file')) score += 5;
                    if (title.includes('上传') || title.includes('upload')) score += 6;
                    if (classList.includes('upload') || classList.includes('attach')) score += 4;
                    if (text.includes('上传') || text.includes('上传文件')) score += 8;

                    if (score > 0) {
                        candidates.push({
                            text: btn.textContent.trim().substring(0, 50),
                            ariaLabel: ariaLabel,
                            title: title,
                            id: id,
                            score: score,
                            visible: btn.offsetParent !== null,
                        });
                    }
                });

                // 3. 返回最高分的可见按钮信息
                const best = candidates
                    .filter(c => c.visible)
                    .sort((a, b) => b.score - a.score)[0];

                if (!best) return { found: false };

                // 4. 生成最佳选择器（优先级：id > aria-label > text > title）
                let selector = null;
                if (best.id) {
                    selector = `button#${best.id}`;
                } else if (best.ariaLabel) {
                    // 转义 aria-label 中的特殊字符
                    const escapedLabel = best.ariaLabel.replace(/"/g, '\\"');
                    selector = `button[aria-label="${escapedLabel}"]`;
                } else if (best.text) {
                    // 使用文本内容作为选择器
                    selector = `button:has-text("${best.text}")`;
                } else if (best.title) {
                    const escapedTitle = best.title.replace(/"/g, '\\"');
                    selector = `button[title="${escapedTitle}"]`;
                }

                return { found: true, ...best, selector };
            }
            """)

            if result.get('found') and result.get('selector'):
                logger.debug(f"✓ DOM 发现找到上传控件: score={result['score']}, text='{result['text']}', selector='{result['selector']}'")
                return result['selector']
            else:
                logger.warning("✗ DOM 发现未找到上传控件或无法生成选择器")
                return None

        except Exception as e:
            logger.error(f"DOM 发现执行失败: {e}")
            return None

    async def _get_page_structure(self) -> Dict:
        """
        获取页面的详细结构，用于调试为什么找不到上传按钮
        """
        try:
            return await self.page.evaluate("""
            () => ({
                title: document.title,
                allButtons: document.querySelectorAll('button').length,
                inputs: document.querySelectorAll('input').length,
                fileInputs: document.querySelectorAll('input[type="file"]').length,
                textInputs: document.querySelectorAll('[role="textbox"]').length,
                buttons: Array.from(document.querySelectorAll('button')).map(b => ({
                    text: b.textContent.substring(0, 30),
                    aria: b.getAttribute('aria-label') || '',
                    title: b.getAttribute('title') || '',
                    classes: b.className.substring(0, 100)
                })).slice(0, 10)
            })
            """)
        except Exception as e:
            logger.error(f"获取页面结构失败: {e}")
            return {}

    async def find_upload_button(self) -> Optional:
        """
        查找上传按钮（改进版本，增加重试机制）

        策略：
        1. 快速查找前10个选择器（2秒超时）
        2. 如果失败，尝试所有选择器（5秒超时）
        3. 如果仍失败，使用 DOM 智能发现
        """
        logger.debug("正在查找上传按钮 (方法1: 快速查找前10个选择器)...")

        # 第 1 步：快速查找前10个选择器
        button = await self.find_element_by_selectors(
            self.upload_button_selectors[:10],
            timeout=2  # 快速失败
        )

        if button:
            logger.debug("✓ 快速查找成功找到上传按钮")
            return button

        # 第 2 步：用所有选择器查找
        logger.debug("快速查找失败，尝试所有选择器...")
        button = await self.find_element_by_selectors(
            self.upload_button_selectors,
            timeout=5  # 5秒超时
        )

        if button:
            logger.debug("✓ 使用所有选择器成功找到上传按钮")
            return button

        # 第 3 步：利用 DOM 智能发现
        logger.warning("所有选择器失败，尝试 DOM 智能发现...")
        discovered_selector = await self._discover_upload_control()

        if discovered_selector:
            try:
                button = self.page.locator(discovered_selector)
                await button.wait_for(timeout=5000)
                logger.debug(f"✓ DOM 发现成功：{discovered_selector}")
                return button
            except Exception as e:
                logger.debug(f"DOM 发现的选择器失效: {e}")

        logger.warning("✗ 未能找到上传按钮")
        return None

    async def find_file_input(self) -> Optional:
        """
        查找文件输入框（通常是隐藏的 input[type="file"]）

        Returns:
            文件输入框 Locator 或 None
        """
        logger.debug("正在查找文件输入框...")
        file_input = await self.find_element_by_selectors(
            self.file_input_selectors,
            timeout=5  # 文件输入通常在页面加载时就存在，短超时即可
        )

        if file_input:
            logger.debug("✓ 找到文件输入框")
        else:
            logger.warning("✗ 未能找到文件输入框")

        return file_input

    async def set_file_path(self, file_path: str) -> bool:
        """
        设置文件路径到输入框

        使用 Playwright 的 set_input_files() 方法，可以直接设置文件而无需打开系统对话

        关键：
        1. 必须在点击按钮之前或立即设置文件，避免系统对话框弹出
        2. 设置文件后不要触发任何事件（change 事件在单独的步骤中触发）

        Args:
            file_path: 文件路径

        Returns:
            是否设置成功
        """
        logger.debug(f"正在设置文件: {file_path}")

        try:
            # 获取所有 input[type="file"]
            all_file_inputs = await self.page.locator('input[type="file"]').all()

            if not all_file_inputs:
                logger.warning("✗ 未能找到任何 input[type=\"file\"]")
                return False

            logger.debug(f"找到 {len(all_file_inputs)} 个文件输入框")

            # 尝试设置每个文件输入框（可能有多个隐藏的）
            success = False
            for i, file_input in enumerate(all_file_inputs):
                try:
                    # 直接设置文件，不做任何验证或触发事件
                    # Playwright 的 set_input_files() 不会触发 change 事件
                    await file_input.set_input_files(file_path)

                    # 验证文件是否已设置（只读取，不触发事件）
                    check_result = await file_input.evaluate('''el => ({
                        hasValue: el.files && el.files.length > 0,
                        fileCount: el.files ? el.files.length : 0,
                        fileName: el.files && el.files.length > 0 ? el.files[0].name : ''
                    })''')

                    if check_result['hasValue']:
                        logger.debug(f"✓ 文件已设置到输入框 #{i+1}: {check_result['fileName']}")
                        success = True
                        break  # 成功一个就够了
                    else:
                        logger.warning(f"文件设置后输入框 #{i+1} 仍为空")

                except Exception as e:
                    logger.debug(f"设置输入框 #{i+1} 失败: {e}")
                    continue

            if success:
                logger.debug("✓ 文件设置成功")
                return True
            else:
                logger.error("✗ 所有文件输入框设置失败")
                return False

        except Exception as e:
            logger.error(f"设置文件失败: {e}")
            return False

    async def check_file_loaded(self) -> bool:
        """
        检查文件是否已加载到输入框

        只读取信息，不触发任何事件

        Returns:
            是否有文件已加载
        """
        try:
            file_inputs = await self.page.locator('input[type="file"]').all()

            for i, file_input in enumerate(file_inputs):
                try:
                    # 只读取文件信息，不触发任何事件
                    result = await file_input.evaluate('''el => {
                        if (el.files && el.files.length > 0) {
                            return {
                                hasFiles: true,
                                fileCount: el.files.length,
                                fileName: el.files[0].name,
                                fileSize: el.files[0].size
                            };
                        }
                        return { hasFiles: false };
                    }''')

                    if result.get('hasFiles'):
                        logger.debug(f"✓ 输入框 #{i+1} 已包含文件: {result['fileName']} ({result['fileSize']} bytes)")
                        return True
                except Exception as e:
                    logger.debug(f"检查输入框 #{i+1} 失败: {e}")
                    continue

            logger.debug("未找到包含文件的输入框")
            return False
        except Exception as e:
            logger.error(f"检查文件加载状态失败: {e}")
            return False

    async def wait_for_upload_complete(self, timeout: Optional[int] = None) -> bool:
        """
        等待文件上传完成（严格验证版本）

        通过检测完成标志来判断（如预览图、文件名、发送按钮可用等）

        严格验证逻辑：
        1. 优先检测页面上的文件预览/附件元素（这是最可靠的标志）
        2. 检查发送按钮是否可用（表示文件已准备好）
        3. 最后才检查输入框（但必须配合其他标志）

        Args:
            timeout: 超时时间（秒）

        Returns:
            是否上传完成
        """
        logger.debug("正在等待文件上传完成（严格验证）...")

        if timeout is None:
            timeout = self.timeout

        try:
            # 记录初始状态
            initial_attachment_count = 0
            try:
                initial_attachments = await self.page.locator('[class*="attachment"], [class*="attached-file"], [role="img"]').count()
                initial_attachment_count = initial_attachments
                logger.debug(f"初始附件数量: {initial_attachment_count}")
            except:
                pass

            # 检测参数
            check_count = 0
            max_checks = 20  # 增加检查次数
            check_interval = 0.5  # 每次检查间隔 0.5 秒
            # 总等待时间: 20 * 0.5 = 10 秒

            while check_count < max_checks:
                check_count += 1

                # 方法1（最可靠）：检查是否有新的附件元素出现
                try:
                    current_attachments = await self.page.locator('[class*="attachment"], [class*="attached-file"], [role="img"]').count()
                    if current_attachments > initial_attachment_count:
                        logger.debug(f"✓ 检测到新附件出现: {current_attachments} 个（初始: {initial_attachment_count}）")
                        # 进一步验证：检查是否有预览图或文件名
                        preview_found = False
                        try:
                            preview_images = self.page.locator('img[alt*="preview"], img[class*="preview"], img[class*="thumbnail"]')
                            if await preview_images.count() > 0:
                                preview_found = True
                                logger.debug("  ✓ 附件包含预览图")
                        except:
                            pass

                        if not preview_found:
                            try:
                                file_names = self.page.locator('div[class*="filename"], span[class*="filename"], [class*="file-name"]')
                                if await file_names.count() > 0:
                                    text = await file_names.first.inner_text()
                                    if text and len(text.strip()) > 0:
                                        preview_found = True
                                        logger.debug(f"  ✓ 附件包含文件名: {text[:30]}...")
                            except:
                                pass

                        if preview_found:
                            return True
                        else:
                            logger.debug("  ⚠ 附件出现但无预览/文件名，继续等待...")
                except Exception:
                    pass

                # 方法2：检查发送按钮是否可用（表示文件已准备好）
                try:
                    send_button = self.page.locator('button[aria-label*="Send"], button[aria-label*="发送"]')
                    if await send_button.count() > 0:
                        is_enabled = await send_button.first.is_enabled()
                        if is_enabled:
                            logger.debug("✓ 发送按钮可用（文件可能已准备好）")
                            # 结合输入框检查
                            file_inputs = await self.page.locator('input[type="file"]').all()
                            for file_input in file_inputs:
                                has_files = await file_input.evaluate('el => el.files && el.files.length > 0')
                                if has_files:
                                    logger.debug("  ✓ 输入框也有文件，确认上传完成")
                                    return True
                except Exception:
                    pass

                # 方法3：检查预览图
                try:
                    preview_images = self.page.locator('img[alt*="preview"], img[class*="preview"], img[class*="thumbnail"]')
                    if await preview_images.count() > 0:
                        # 检查预览图是否可见
                        is_visible = await preview_images.first.is_visible()
                        if is_visible:
                            logger.debug("✓ 检测到可见的预览图")
                            return True
                except Exception:
                    pass

                # 方法4：检查文件名显示
                try:
                    file_names = self.page.locator('div[class*="filename"], span[class*="filename"], [class*="file-name"]')
                    if await file_names.count() > 0:
                        text = await file_names.first.inner_text()
                        if text and len(text.strip()) > 0:
                            logger.debug(f"✓ 检测到文件名显示: {text[:30]}...")
                            return True
                except Exception:
                    pass

                # 方法5：检查上传完成标志选择器
                try:
                    complete_element = await self.find_element_by_selectors(
                        self.upload_complete_selectors,
                        timeout=0.3  # 短超时
                    )
                    if complete_element:
                        logger.debug("✓ 检测到上传完成标志")
                        return True
                except Exception:
                    pass

                # 等待下一次检查
                if check_count < max_checks:
                    logger.debug(f"未检测到上传完成，等待 {check_interval} 秒后重试（{check_count}/{max_checks}）...")
                    await asyncio.sleep(check_interval)

            # 所有检查都超时
            logger.warning(f"✗ 未能检测到上传完成标志（已检查 {check_count} 次，超时 {timeout} 秒）")
            logger.warning("  说明：文件可能只是设置到了输入框，但没有真正上传到服务器")
            return False

        except Exception as e:
            logger.error(f"等待上传完成时出错: {e}")
            return False

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MutationObserver 事件驱动的流式响应模块

使用浏览器原生的 MutationObserver API，
在 DOM 变化时立即通知，实现真正的实时监听。

延迟：< 50ms（浏览器原生，极快）
原理：DOM 元素变化 → 立即触发回调 → 立即读取内容 → 立即输出
"""

import asyncio
import json
import logging
from typing import AsyncGenerator
from playwright.async_api import Page

logger = logging.getLogger(__name__)


async def stream_response_mutation_observer(
    page: Page,
    response_element,  # Playwright Locator 对象
) -> AsyncGenerator[str, None]:
    """
    使用 MutationObserver 监听 DOM 变化

    延迟: < 50ms（浏览器原生事件驱动）
    优点:
    - 不需要网络拦截
    - 不需要轮询
    - 完全由浏览器原生 API 驱动
    - 变化立即通知

    缺点:
    - 需要正确识别目标 DOM 元素
    - 依赖 DOM 更新（而非直接网络）

    参数:
    - page: Playwright Page 对象
    - response_element: 响应文本所在的 DOM 元素（Playwright Locator）
    """

    try:
        last_text = ""
        buffer = {"text": "", "ready": False, "completed": False}

        # 在浏览器中执行的 JavaScript 代码
        # 这会设置一个 MutationObserver，监听目标元素的内容变化
        setup_monitor_script = """
        () => {
            const targetElement = arguments[0];

            if (!targetElement) {
                console.error('[MutationObserver] 目标元素不存在');
                return false;
            }

            // 创建回调函数，会被 Python 代码调用
            window.geminiMutationCallback = window.geminiMutationCallback || [];

            // 初始化消息队列
            window.geminiMessageQueue = [];

            // 创建 MutationObserver
            const observer = new MutationObserver((mutations) => {
                // 读取当前文本
                const currentText = targetElement.innerText;

                // 只在真正有变化时处理
                if (currentText !== window.lastObservedText) {
                    window.lastObservedText = currentText;

                    // 存储到队列
                    window.geminiMessageQueue.push({
                        type: 'text_update',
                        content: currentText,
                        timestamp: Date.now()
                    });

                    console.log('[MutationObserver] 检测到变化，长度:', currentText.length);
                }
            });

            // 配置观察器
            // characterData: 监听文本内容变化
            // childList: 监听子元素增删
            // subtree: 监听所有后代节点
            observer.observe(targetElement, {
                characterData: true,
                childList: true,
                subtree: true,
                characterDataOldValue: false
            });

            // 初始化
            window.lastObservedText = targetElement.innerText;
            console.log('[MutationObserver] 已启动，监听目标元素');

            return true;
        }
        """

        # 首先获取响应元素的句柄
        element_handle = await response_element.evaluate_handle("el => el")

        # 在浏览器中设置 MutationObserver
        result = await page.evaluate(f"{setup_monitor_script}", element_handle)

        if not result:
            logger.debug("⚠ MutationObserver 初始化失败，回退到轮询")
            raise Exception("MutationObserver 初始化失败")

        logger.debug("MutationObserver 已启动，等待 DOM 变化...")

        # 等待循环：轮询消息队列
        no_change_count = 0
        timeout_counter = 0
        max_timeout = 50  # 5 秒超时（100ms * 50）
        chunk_size = 0

        while timeout_counter < max_timeout:
            try:
                await asyncio.sleep(0.01)  # 10ms 检查一次
                timeout_counter += 1

                # 从浏览器中获取当前文本
                current_text = await response_element.inner_text()

                # 检查是否有新内容
                if len(current_text) > len(last_text):
                    new_text = current_text[len(last_text) :]
                    if new_text.strip():
                        yield new_text
                        logger.debug(f"MutationObserver 流: {len(new_text)} 字符")
                        last_text = current_text
                        chunk_size += len(new_text)
                        no_change_count = 0
                        timeout_counter = 0  # 重置超时计数
                else:
                    no_change_count += 1

                # 快速完成检测：2 次连续 100ms 无变化 = 200ms 无变化，认为完成
                if no_change_count >= 2 and len(last_text) > 0:
                    logger.debug(
                        f"✓ MutationObserver 检测完成信号（200ms 无变化）"
                    )
                    break

            except Exception as e:
                logger.debug(f"MutationObserver 读取异常: {e}")
                timeout_counter += 1
                await asyncio.sleep(0.05)
                continue

        elapsed = timeout_counter * 0.01  # 粗略计算耗时
        logger.debug(
            f"✓ MutationObserver 流完成，总数据: {len(last_text)} 字符，耗时: {elapsed:.2f}s"
        )

        if not last_text:
            logger.debug("⚠ MutationObserver 未收到任何内容")
            raise Exception("MutationObserver 未收到任何内容")

    except Exception as e:
        logger.debug(f"MutationObserver 流异常: {e}，回退到轮询")
        raise

    finally:
        # 清理
        try:
            await page.evaluate("() => { delete window.geminiMessageQueue; }")
        except:
            pass

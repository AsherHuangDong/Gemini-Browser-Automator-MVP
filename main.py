"""
Gemini 浏览器自动化 MVP - CLI 入口
"""

import asyncio
import logging
import argparse
import sys
from pathlib import Path
from typing import Optional

from gemini_browser import GeminiBrowser
from exceptions import (
    LoginRequiredException,
    BrowserException,
    FileUploadException,
    FileNotFoundError as FileNotFoundError_custom,
    FileSizeError,
    FileTypeError,
    FileUploadError,
)
from config import config


# 确保日志目录存在
Path("logs").mkdir(parents=True, exist_ok=True)

# 配置日志（Windows 使用 GBK，其他系统使用 UTF-8）
import sys
file_encoding = "gbk" if sys.platform == "win32" else "utf-8"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/gemini.log", encoding=file_encoding, errors='replace'),
    ],
)

logger = logging.getLogger(__name__)


class GeminiCLI:
    """CLI 交互控制器"""

    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.browser: Optional[GeminiBrowser] = None

        # 应用命令行配置
        config.from_args(args)

        # 创建浏览器实例
        self.browser = GeminiBrowser(
            headless=config.browser.headless,
            profile_dir=config.browser.profile_dir,
            timeout=config.browser.timeout,
            retry_count=config.browser.retry_count,
            check_interval=config.browser.check_interval,
        )

    async def run_interactive(self) -> None:
        """
        交互模式主循环

        1. 初始化并启动浏览器
        2. 提示用户登录（如需要）
        3. REPL 循环：
           - 接收用户输入
           - 发送消息并流式输出回复
           - 循环直到用户退出
        4. 优雅关闭
        """
        try:
            # 启动浏览器
            await self.browser.launch()

            # 确保已登录
            try:
                await self.browser.ensure_logged_in()
            except LoginRequiredException as e:
                logger.error(f"登录失败: {e}")
                return

            logger.debug("开始交互模式，输入 'exit' 或 'quit' 退出")
            print("\n" + "=" * 60)
            print("Gemini 浏览器自动化 MVP")
            print("=" * 60)
            print("提示: 输入 'exit' 或 'quit' 退出")
            print("=" * 60 + "\n")

            # 交互循环
            while True:
                try:
                    prompt = input("\n[Gemini] >> ").strip()

                    # 检查退出命令
                    if prompt.lower() in ["exit", "quit"]:
                        logger.debug("用户主动退出")
                        break

                    # 空输入则继续
                    if not prompt:
                        continue

                    # 命令分派：检查是否为特殊命令
                    if prompt.startswith("/upload "):
                        # 处理文件上传命令
                        file_path = prompt[8:].strip()
                        if not file_path:
                            print("✗ 错误: 请指定文件路径")
                            print("  用法: /upload <file_path>")
                            continue

                        await self._handle_upload_command(file_path)
                        continue

                    # 检查帮助命令
                    if prompt.startswith("/help"):
                        self._print_help()
                        continue

                    # 检查保存登录态命令
                    if prompt.startswith("/save"):
                        try:
                            await self.browser._save_login_state()
                            print("✓ 登录态已保存")
                        except Exception as e:
                            print(f"✗ 保存失败: {e}")
                        continue

                    # 普通聊天消息
                    logger.debug(f"用户输入: {prompt[:50]}...")
                    response = await self.browser.chat(prompt)

                    logger.debug(f"回复已生成，长度: {len(response)}")

                except KeyboardInterrupt:
                    logger.debug("捕获到键盘中断")
                    break
                except BrowserException as e:
                    logger.error(f"浏览器异常: {e}")
                    break
                except Exception as e:
                    logger.error(f"未预期的异常: {e}", exc_info=True)
                    break

        except LoginRequiredException as e:
            logger.error(f"登录失败: {e}")
        except KeyboardInterrupt:
            logger.debug("捕获到键盘中断")
        except Exception as e:
            logger.error(f"交互模式异常: {e}", exc_info=True)

    async def run_single_query(self, query: str) -> None:
        """
        单次查询模式

        1. 启动浏览器
        2. 发送查询
        3. 打印完整回复
        4. 关闭浏览器
        """
        try:
            # 启动浏览器
            await self.browser.launch()

            # 确保已登录
            try:
                await self.browser.ensure_logged_in()
            except LoginRequiredException as e:
                logger.error(f"登录失败: {e}")
                return

            # 发送查询
            logger.debug(f"发送查询: {query[:50]}...")
            print("\n[Gemini] 正在生成回复...")
            response = await self.browser.chat(query)

            print("\n" + "=" * 60)
            logger.debug(f"查询完成，回复长度: {len(response)}")

        except LoginRequiredException as e:
            logger.error(f"登录失败: {e}")
        except Exception as e:
            logger.error(f"单次查询异常: {e}", exc_info=True)

    async def _handle_upload_command(self, file_path: str) -> None:
        """
        处理 /upload 命令 (改进版本，增强日志和错误建议)

        Args:
            file_path: 用户指定的文件路径
        """
        try:
            print("\n[Gemini] 正在上传文件...")
            logger.debug(f"开始处理上传命令: {file_path}")

            result = await self.browser.upload_file(file_path)

            if result['success']:
                print(f"\n✓ {result['message']}")
                print(f"  文件类型: {result['file_type']}")
                print(f"  文件大小: {result['file_size_mb']:.2f} MB")
                print(f"  上传耗时: {result['upload_time']:.2f} 秒")

                if result['ready_for_chat']:
                    print("\n提示: 文件上传完成，现在可以继续聊天。")
                    print("  例如: '分析这个文件' 或 '这是什么?'")

                logger.debug(f"文件上传成功: {result['file_name']}")

            else:
                print(f"\n✗ 文件上传失败: {result.get('message', '未知错误')}")
                logger.error(f"文件上传失败: {result['message']}")
                # 提供调试建议
                print("\n调试建议:")
                print("  1. 检查浏览器是否仍在运行")
                print("  2. 确认已登录 Gemini")
                print("  3. 尝试刷新页面或重新启动程序")

        except FileNotFoundError_custom as e:
            print(f"\n✗ 文件不存在: {e}")
            logger.error(f"文件不存在: {e}")
            print("\n提示: 请检查文件路径是否正确")

        except FileSizeError as e:
            print(f"\n✗ 文件过大: {e}")
            logger.error(f"文件过大: {e}")
            print("\n提示: 请检查文件大小是否超过限制")

        except FileTypeError as e:
            print(f"\n✗ 不支持的文件类型: {e}")
            logger.error(f"不支持的文件类型: {e}")
            print("\n支持的文件类型:")
            print("  - 图片: jpg, jpeg, png, gif, webp, bmp (最大 20MB)")
            print("  - PDF: pdf (最大 50MB)")
            print("  - 文本: txt, doc, docx, md (最大 10MB)")
            print("  - 视频: mp4, webm, mov, avi, mkv (最大 100MB)")
            print("  - 数据: csv, json, xlsx, xls (最大 20MB)")

        except FileUploadError as e:
            print(f"\n✗ 上传失败: {e}")
            logger.error(f"上传失败: {e}")
            print("\n故障排除:")
            print("  1. 检查网络连接")
            print("  2. 尝试上传小文件测试")
            print("  3. 查看日志了解详细错误: tail -f logs/gemini.log")

        except BrowserException as e:
            print(f"\n✗ 浏览器异常: {e}")
            logger.error(f"浏览器异常: {e}")
            print("\n提示: 请检查浏览器是否仍在运行")

        except Exception as e:
            print(f"\n✗ 未预期的错误: {e}")
            logger.error(f"未预期的错误: {e}", exc_info=True)
            print("\n请检查日志文件获取更多信息")

    def _print_help(self) -> None:
        """打印帮助信息"""
        help_text = """
╔═══════════════════════════════════════════════════════════════╗
║           Gemini 浏览器自动化 MVP - 命令帮助                    ║
╚═══════════════════════════════════════════════════════════════╝

【基本命令】
  exit, quit         - 退出程序
  /help              - 显示此帮助信息
  /save              - 手动保存登录态（用于备份登录状态）

【文件上传】
  /upload <path>     - 上传文件到 Gemini
                       支持的文件类型:
                       - 图片: jpg, jpeg, png, gif, webp, bmp
                       - PDF: pdf
                       - 文本: txt, doc, docx, md
                       - 视频: mp4, webm, mov, avi, mkv
                       - 数据: csv, json, xlsx, xls

                       文件大小限制:
                       - 图片: 20 MB
                       - PDF: 50 MB
                       - 文本: 10 MB
                       - 视频: 100 MB
                       - 数据: 20 MB

【使用示例】
  /upload ./image.jpg
  /upload ~/Downloads/document.pdf
  /upload "C:\\Users\\name\\Desktop\\data.csv"

【上传后】
  上传完成后，可以直接提问关于文件的内容:
  - "分析这个图片"
  - "总结这个文档"
  - "这个数据显示了什么?"

【提示】
  - 首次运行需要手动登录，登录成功后会自动保存登录态
  - 下次启动会自动加载保存的登录态，无需重复登录
  - 如果遇到登录问题，删除 profiles/storage_state.json 后重新登录
  - 使用 /save 命令可以手动保存当前登录状态

═══════════════════════════════════════════════════════════════
"""
        print(help_text)
        logger.debug("用户查看帮助信息")

    async def run(self) -> None:
        """根据命令选择运行模式"""
        if self.args.mode == "interactive":
            await self.run_interactive()
        elif self.args.mode == "query":
            await self.run_single_query(self.args.query)


def create_parser() -> argparse.ArgumentParser:
    """创建命令行参数解析器"""
    parser = argparse.ArgumentParser(
        description="Gemini 浏览器自动化 MVP - 100% 模仿真人聊天",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法：
  # 交互模式（非 headless，第一次运行时手动登录）
  python main.py interactive

  # 交互模式（headless，服务器后台运行）
  python main.py interactive --headless

  # 使用已安装的 Chrome 浏览器（推荐）
  python main.py interactive --browser-path "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"

  # 单次查询
  python main.py query "你好，请介绍一下自己"

  # 自定义 Profile 和超时
  python main.py interactive --profile ./my_profiles --timeout 60

  # 完整示例
  python main.py interactive --headless --profile ./profiles --timeout 120 --retry 5
        """,
    )

    # 命令选择
    subparsers = parser.add_subparsers(
        dest="mode",
        help="运行模式",
        required=True,
    )

    # interactive 模式
    interactive_parser = subparsers.add_parser(
        "interactive",
        help="交互模式 - REPL 循环聊天",
    )

    # query 模式
    query_parser = subparsers.add_parser(
        "query",
        help="单次查询模式",
    )
    query_parser.add_argument(
        "query",
        help="要发送的问题",
    )

    # 共享参数
    for p in [interactive_parser, query_parser]:
        headless_group = p.add_mutually_exclusive_group()
        headless_group.add_argument(
            "--headless",
            action="store_true",
            default=None,
            help="启用 headless 模式（无 GUI 窗口，默认：True）",
        )
        headless_group.add_argument(
            "--no-headless",
            action="store_true",
            default=None,
            help="禁用 headless 模式（显示浏览器窗口）",
        )

        p.add_argument(
            "--profile",
            default="./profiles",
            help="浏览器 Profile 存储目录（默认: ./profiles）",
        )

        p.add_argument(
            "--timeout",
            type=int,
            default=30,
            help="操作超时时间，单位秒（默认: 30）",
        )

        p.add_argument(
            "--retry",
            type=int,
            default=3,
            help="异常重试次数（默认: 3）",
        )

        p.add_argument(
            "--browser-path",
            type=str,
            default=None,
            help="使用已安装的浏览器路径（例如：C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe）",
        )

    return parser


async def main():
    """CLI 主入口"""
    parser = create_parser()

    # 解析参数
    args = parser.parse_args()

    logger.debug(f"启动 Gemini 浏览器自动化 MVP")
    logger.debug(f"运行模式: {args.mode}")
    logger.debug(f"Headless: {args.headless}")
    logger.debug(f"Profile 目录: {args.profile}")

    # 创建 CLI 实例并运行
    cli = GeminiCLI(args)

    try:
        await cli.run()
    except KeyboardInterrupt:
        logger.debug("用户中断程序")
    except Exception as e:
        logger.error(f"程序异常: {e}", exc_info=True)
    finally:
        # 清理资源
        if cli.browser:
            try:
                await cli.browser.close()
            except Exception as e:
                logger.error(f"关闭浏览器失败: {e}")

        logger.debug("程序已退出")


if __name__ == "__main__":
    # 运行异步主程序
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n程序已中止")
        sys.exit(0)
    except Exception as e:
        print(f"致命错误: {e}")
        sys.exit(1)

"""
Gemini 自动化工具 - CLI 入口
默认使用 API 模式，支持多 Key 循环容灾
"""

import asyncio
import logging
import argparse
import sys
import os
from pathlib import Path
from typing import Optional, List, Dict

from gemini_browser import GeminiBrowser
from gemini_api import GeminiAPIClient, APIKeyPool
from exceptions import (
    LoginRequiredException,
    BrowserException,
    APIException,
    APIKeyNotFoundError,
    AllKeysExhaustedError,
)
from config import config


# 确保日志目录存在
Path("logs").mkdir(parents=True, exist_ok=True)

# 配置日志
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


# ============================================================================
# API 模式（默认）
# ============================================================================

class GeminiAPICLI:
    """API 模式 CLI 交互控制器"""

    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.client: Optional[GeminiAPIClient] = None
        self.key_pool: Optional[APIKeyPool] = None
        self.uploaded_files: List[Dict] = []

        config.from_args(args)
        config.api.ensure_keys_loaded()

        if not config.api.api_keys:
            raise APIKeyNotFoundError(
                "未配置 API Key。请通过以下方式之一提供：\n"
                "  1. 创建 api_keys.txt 文件（每行一个 Key）\n"
                "  2. 使用 --keys 参数传入\n"
                "  3. 从 https://aistudio.google.com/apikey 获取 Key"
            )

        self.key_pool = APIKeyPool(
            keys=config.api.api_keys,
            strategy=config.api.rotation_strategy,
            error_threshold=config.api.error_threshold,
            cooldown_seconds=config.api.cooldown_seconds,
        )

        self.client = GeminiAPIClient(
            key_pool=self.key_pool,
            config=config.api,
        )

    def run_interactive(self) -> None:
        """交互模式"""
        logger.debug("开始 API 交互模式")
        print("\n" + "=" * 60)
        print("Gemini API 模式")
        print("=" * 60)
        print(f"模型: {config.api.model}")
        print(f"可用 Key 数: {len(config.api.api_keys)}")
        print("提示: 输入 'exit' 退出，/help 查看命令")
        print("=" * 60 + "\n")

        while True:
            try:
                prompt = input("\n[Gemini] >> ").strip()

                if prompt.lower() in ["exit", "quit"]:
                    break
                if not prompt:
                    continue
                if prompt.startswith("/status"):
                    self._print_pool_status()
                    continue
                if prompt.startswith("/help"):
                    self._print_help()
                    continue
                if prompt.startswith("/upload "):
                    self._handle_upload(prompt[8:].strip())
                    continue
                if prompt.startswith("/files"):
                    self._list_files()
                    continue

                logger.debug(f"用户输入: {prompt[:50]}...")
                print("\n[Gemini] 正在生成回复...\n")

                if self.uploaded_files:
                    last_file = self.uploaded_files[-1]
                    response = self.client.chat_with_file(
                        prompt=prompt,
                        file_uri=last_file.get("file_uri"),
                    )
                else:
                    response = self.client.stream_chat(prompt)

                logger.debug(f"回复完成，长度: {len(response)}")

            except KeyboardInterrupt:
                break
            except AllKeysExhaustedError as e:
                logger.error(f"所有 Key 不可用: {e}")
                print(f"\n✗ 错误: {e}")
            except APIException as e:
                logger.error(f"API 异常: {e}")
                print(f"\n✗ API 错误: {e}")
            except Exception as e:
                logger.error(f"未预期的异常: {e}", exc_info=True)
                print(f"\n✗ 错误: {e}")

    def run_single_query(self, query: str, file_path: str = None) -> None:
        """单次查询（可选文件）"""
        logger.debug(f"发送查询: {query[:50] if query else ''}...")
        
        if file_path:
            print(f"\n[Gemini] 正在上传文件...")
        
        print("\n[Gemini] 正在生成回复...\n")
        try:
            if file_path:
                # 直接传入 file_path，让 chat_with_file 在同一个 key 下完成上传和发送
                result = self.client.chat_with_file(prompt=query or "分析这个文件", file_path=file_path)
                if result:
                    print(result)
            else:
                self.client.stream_chat(query)
            print()
        except AllKeysExhaustedError as e:
            logger.error(f"所有 Key 不可用: {e}")
            print(f"\n✗ 错误: {e}")

    def _handle_upload(self, file_path: str) -> None:
        if not file_path:
            print("✗ 错误: 请指定文件路径")
            return
        try:
            print(f"\n[Gemini] 正在上传文件: {file_path}")
            result = self.client.upload_file(file_path)
            if result.get("success"):
                self.uploaded_files.append(result)
                print(f"\n✓ {result['message']}")
                print(f"  文件名: {result['file_name']}")
                print(f"  文件 URI: {result['file_uri']}")
                print("\n提示: 文件已上传，可直接提问")
            else:
                print(f"\n✗ 上传失败")

        except FileNotFoundError:
            print(f"\n✗ 文件不存在: {file_path}")
        except Exception as e:
            logger.error(f"上传失败: {e}")
            print(f"\n✗ 上传失败: {e}")

    def _list_files(self) -> None:
        print("\n" + "-" * 50)
        print("已上传的文件")
        print("-" * 50)
        if not self.uploaded_files:
            print("（暂无）")
        else:
            for i, f in enumerate(self.uploaded_files, 1):
                print(f"  {i}. {f['file_name']}")
        print("-" * 50)

    def _print_pool_status(self) -> None:
        status = self.key_pool.get_pool_status()
        print("\n" + "-" * 50)
        print("API Key 池状态")
        print("-" * 50)
        print(f"总 Key 数: {status['total_keys']}")
        print(f"可用 Key 数: {status['available_count']}")
        print("\nKey 详情:")
        for key_info in status['keys']:
            print(f"  {key_info['key_hint']}: {key_info['status']} "
                  f"(错误: {key_info['error_count']}, 成功: {key_info['success_count']})")
        print("-" * 50)

    def _print_help(self) -> None:
        print("""
【命令帮助】
  exit, quit         - 退出程序
  /help              - 显示帮助
  /status            - 查看 Key 池状态
  /upload <path>     - 上传文件
  /files             - 列出已上传文件
""")

    def run(self) -> None:
        query = getattr(self.args, 'query', None)
        file_path = getattr(self.args, 'file', None)
        if query or file_path:
            self.run_single_query(query or "分析这个文件", file_path)
        else:
            self.run_interactive()


# ============================================================================
# 浏览器模式
# ============================================================================

class GeminiBrowserCLI:
    """浏览器模式 CLI"""

    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.browser: Optional[GeminiBrowser] = None
        config.from_args(args)
        self.browser = GeminiBrowser(
            headless=config.browser.headless,
            profile_dir=config.browser.profile_dir,
            timeout=config.browser.timeout,
            retry_count=config.browser.retry_count,
            check_interval=config.browser.check_interval,
        )
        self.keep_browser_open = os.getenv("KEEP_BROWSER_OPEN", "false").lower() == "true"

    async def run_interactive(self) -> None:
        try:
            await self.browser.launch()
            await self.browser.ensure_logged_in()

            print("\n" + "=" * 60)
            print("Gemini 浏览器模式")
            print("=" * 60)
            print("提示: 输入 'exit' 退出")
            print("=" * 60 + "\n")

            while True:
                try:
                    prompt = input("\n[Gemini] >> ").strip()
                    if prompt.lower() in ["exit", "quit"]:
                        break
                    if not prompt:
                        continue
                    if prompt.startswith("/upload "):
                        await self._handle_upload(prompt[8:].strip())
                        continue
                    if prompt.startswith("/help"):
                        print("exit - 退出, /upload <path> - 上传文件")
                        continue

                    response = await self.browser.chat(prompt)
                except KeyboardInterrupt:
                    break
                except BrowserException as e:
                    logger.error(f"浏览器异常: {e}")
                    if not self.keep_browser_open:
                        break
        except Exception as e:
            logger.error(f"错误: {e}")

    async def run_single_query(self, query: str, file_path: str = None) -> None:
        try:
            await self.browser.launch()
            await self.browser.ensure_logged_in()
            
            if file_path:
                await self._handle_upload(file_path)
            
            print("\n[Gemini] 正在生成回复...")
            await self.browser.chat(query or "分析这个文件")
        except Exception as e:
            logger.error(f"错误: {e}")

    async def _handle_upload(self, file_path: str) -> None:
        if not file_path:
            print("✗ 错误: 请指定文件路径")
            return
        try:
            result = await self.browser.upload_file(file_path)
            if result['success']:
                print(f"\n✓ 文件上传成功: {result['file_name']}")
        except Exception as e:
            print(f"\n✗ 上传失败: {e}")

    async def run(self) -> None:
        query = getattr(self.args, 'query', None)
        file_path = getattr(self.args, 'file', None)
        if query or file_path:
            await self.run_single_query(query or "分析这个文件", file_path)
        else:
            await self.run_interactive()


# ============================================================================
# CLI 入口
# ============================================================================

def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Gemini 自动化工具 - 默认 API 模式，支持多 Key 容灾",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法：

【API 模式（默认）】
  python main.py                        # 交互模式
  python main.py "你好"                  # 单次查询
  python main.py --file image.png "分析这张图片"  # 文件+查询
  python main.py --keys "key1,key2"     # 指定 API Keys
  python main.py --model gemini-1.5-pro # 指定模型

【浏览器模式】
  python main.py --browser              # 浏览器交互模式
  python main.py --browser "你好"        # 浏览器单次查询
        """,
    )

    # 模式选择
    parser.add_argument("--browser", action="store_true", help="使用浏览器模式")

    # 位置参数：查询（可选）
    parser.add_argument("query", nargs="?", default=None, help="单次查询")

    # 文件上传参数
    parser.add_argument("--file", "-f", type=str, default=None, help="上传文件路径")

    # API 模式参数
    parser.add_argument("--keys", type=str, default=None, help="API Keys（逗号分隔）")
    parser.add_argument("--keys-file", type=str, default="api_keys.txt", help="API Keys 文件")
    parser.add_argument("--model", type=str, default="gemini-2.5-flash", help="模型名称")
    parser.add_argument("--api-timeout", type=int, default=60, help="API 超时（秒）")

    # 浏览器模式参数
    parser.add_argument("--headless", action="store_true", default=None, help="浏览器无头模式")
    parser.add_argument("--no-headless", action="store_true", default=None, help="显示浏览器窗口")
    parser.add_argument("--profile", default="./profiles", help="Profile 目录")
    parser.add_argument("--timeout", type=int, default=30, help="超时时间")
    parser.add_argument("--retry", type=int, default=3, help="重试次数")

    return parser


async def main():
    parser = create_parser()
    args = parser.parse_args()

    logger.debug(f"启动 Gemini 自动化工具")

    try:
        if args.browser:
            cli = GeminiBrowserCLI(args)
            await cli.run()
            if cli.browser and not cli.keep_browser_open:
                try:
                    await cli.browser.close()
                except:
                    pass
        else:
            # 默认 API 模式
            cli = GeminiAPICLI(args)
            cli.run()

    except APIKeyNotFoundError as e:
        print(f"\n✗ 错误: {e}")
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.error(f"程序异常: {e}", exc_info=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n程序已中止")
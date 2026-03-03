# Gemini 浏览器自动化 MVP

用 Playwright 全浏览器自动化方式，实现 100% 模仿浏览器中和 Gemini 聊天。

**版本**: MVP v1.0
**状态**: 可直接运行
**语言**: Python 3.11+

## 核心特性

✅ **持久化登录态** - 使用浏览器 Profile 保存 Cookies 和登录信息，仅需首次手动登录一次
✅ **流式输出** - 实时逐字打印 Gemini 生成的回复（每 300ms 检查一次）
✅ **Headless 支持** - 支持无头模式，可在服务器后台运行
✅ **CLI 交互** - 简单命令行交互，支持交互模式和单次查询
✅ **文件上传** - 支持上传图片、PDF、文本、视频、数据文件（交互模式 `/upload <path>`）
✅ **自动重试** - 超时、网络错误、浏览器崩溃自动恢复
✅ **反检测** - 内置反爬虫参数（禁用自动化标志、随机 UA、真实时区语言）

## 快速开始（3 步）

### 1. 安装环境

```bash
# 克隆或进入项目目录
cd gemini-browser-automator

# 创建虚拟环境（推荐）
python3.11 -m venv venv

# 激活虚拟环境
# Linux / Mac:
source venv/bin/activate
# Windows:
venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 安装 Playwright 浏览器驱动
playwright install chromium
```

### 2. 第一次运行（手动登录）

```bash
# 启动交互模式（会弹出浏览器窗口）
python main.py interactive
```

**登录步骤**:
1. 浏览器窗口弹出，自动打开 Gemini 官网
2. 在浏览器中手动登录你的 Google 账户
3. 登录成功后，回到终端按 ENTER 继续
4. 现在可以开始聊天了！

### 3. 后续使用（自动登录）

程序会自动保存登录态，后续只需直接运行，无需重复登录：

```bash
# 交互模式
python main.py interactive

# 或在服务器上无头运行（用于自动化）
python main.py interactive --headless
```

## 使用示例

### 1. 交互模式（推荐）

```bash
# 启动交互模式，进入聊天循环
python main.py interactive

# 输入提问 (例如)
[Gemini] >> 你好，请介绍一下自己
[Gemini] 正在生成回复...
我是 Google 的 AI 助手 Gemini。
我可以帮助你进行各种对话...

# 继续提问
[Gemini] >> 如何学习 Python？
...

# 退出
[Gemini] >> exit
```

### 2. 单次查询模式

```bash
# 快速获取一个问题的答案
python main.py query "北京今天天气怎么样？"
```

### 3. 文件上传（新增）

```bash
# 启动交互模式
python main.py interactive

# 上传文件命令格式：/upload <文件路径>
[Gemini] >> /upload ./my_image.jpg
[Gemini] 正在上传文件...
✓ 文件 'my_image.jpg' 上传成功（1.23秒）
  文件类型: image
  文件大小: 2.50 MB
  上传耗时: 1.23 秒

提示: 文件上传完成，现在可以继续聊天。
  例如: '分析这个文件' 或 '这是什么?'

# 上传后可直接提问
[Gemini] >> 分析一下这张图片
[Gemini] 正在生成回复...
这张图片显示了...

# 支持的文件类型
# 图片: jpg, jpeg, png, gif, webp, bmp (最大 20MB)
# PDF: pdf (最大 50MB)
# 文本: txt, doc, docx, md (最大 10MB)
# 视频: mp4, webm, mov, avi, mkv (最大 100MB)
# 数据: csv, json, xlsx, xls (最大 20MB)
```

**文件上传支持的命令：**
```bash
[Gemini] >> /upload ./image.jpg          # 相对路径
[Gemini] >> /upload ~/Downloads/doc.pdf  # 家目录
[Gemini] >> /upload /absolute/path/file.csv  # 绝对路径
[Gemini] >> /help                        # 查看帮助信息
[Gemini] >> exit                         # 退出
```

### 4. Headless 模式（服务器后台运行）

```bash
# 无 GUI 窗口，适合自动化脚本
python main.py interactive --headless
```

### 5. 自定义配置

```bash
# 指定 Profile 位置和超时时间
python main.py interactive \
  --profile ./my_profiles \
  --timeout 60 \
  --retry 5

# 所有参数
python main.py interactive --help
```

## 命令行参数说明

### Interactive 模式

```bash
python main.py interactive [OPTIONS]
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--headless` | 启用 headless 模式（无 GUI） | False |
| `--profile <dir>` | Profile 存储目录 | `./profiles` |
| `--timeout <sec>` | 操作超时时间（秒） | 30 |
| `--retry <n>` | 异常重试次数 | 3 |

### Query 模式

```bash
python main.py query <QUESTION> [OPTIONS]
```

| 参数 | 说明 |
|------|------|
| `<QUESTION>` | 要提问的问题（必需） |
| `--headless` | 启用 headless 模式 |
| `--profile <dir>` | Profile 存储目录 |
| `--timeout <sec>` | 操作超时时间 |
| `--retry <n>` | 重试次数 |

## 项目结构

```
gemini-browser-automator/
├── main.py                  # CLI 入口和交互控制器
├── gemini_browser.py        # 核心浏览器自动化类
├── config.py                # 配置管理
├── exceptions.py            # 自定义异常定义
├── file_uploader.py         # 文件上传功能模块（新增）
├── requirements.txt         # Python 依赖
├── README.md                # 本文件
├── profiles/                # 浏览器 Profile（自动创建）
│   └── storage_state.json   # 保存的登录态和 Cookies
└── logs/                    # 日志文件（自动创建）
    └── gemini.log
```

## 工作原理

### 1. 持久化登录态

第一次运行时：
- 浏览器窗口弹出，用户手动登录
- 登录成功后，程序自动保存登录状态到 `./profiles/storage_state.json`
- 下次启动时自动加载该文件，保持登录態

```python
# 自动保存 Cookies 和 Storage
storage_state = await context.storage_state()
with open("profiles/storage_state.json", "w") as f:
    json.dump(storage_state, f)

# 自动加载上次的登录態
context = await browser.new_context(storage_state=storage_state)
```

### 2. 流式输出机制

实时打印 Gemini 生成的回复：
- **MutationObserver** (推荐): 使用浏览器原生 API 监听 DOM 变化，延迟 < 50ms
- **轮询方案** (备用): 每 100ms 检查一次响应容器的文本内容，延迟 ~1s
- 自动检测并选择最佳方案

```python
# MutationObserver 方案（优先）
# 使用浏览器原生 MutationObserver API 监听 DOM 变化
# 在 DOM 变化时立即触发回调，实现真正的实时监听

# 轮询方案（备用）
last_text = ""
while True:
    current_text = await response_container.inner_text()
    new_part = current_text[len(last_text):]

    if new_part:
        print(new_part, end="", flush=True)
        last_text = current_text

    if is_complete():
        break

    await asyncio.sleep(0.1)
```

### 3. 反检测技术

内置多重反检测措施，避免被 Gemini 检测为自动化工具：

- **禁用自动化标志**: `--disable-blink-features=AutomationControlled`
- **真实时区**: `timezone_id="Asia/Tokyo"`
- **真实语言**: `locale="zh-CN"`
- **随机 User Agent**: 每次启动随机选择现代浏览器 UA
- **合理的操作延迟**: 填充文本后延迟 500ms 再提交

### 4. 多轮对话处理

在多轮对话中，DOM 中会累积历史消息内容，导致可能提取的选择器指向错误位置（如聊天历史菜单）。该项目实现了智能的多轮对话处理：

```python
# 核心逻辑：提取最新回复
# 当发现多个 "Gemini 说" 标记时，只保留最后一个之后的内容
if current_text.count("Gemini 说") > 1:
    last_gemini_pos = current_text.rfind("Gemini 说")  # find last occurrence
    latest_response = current_text[last_gemini_pos + len("Gemini 说"):].strip()
    current_text = latest_response  # 只处理最新回复
```

**优势：**
- 第一次、第二次、第N次回复都能正确处理
- 自动过滤聊天历史和侧边栏菜单内容
- 无需手动切换模式或等待页面变化
- 日志中能清晰看到 "多轮对话：发现 N 个标记，提取最新回复"

### 5. 自动重试和恢复

异常处理和恢复策略：

| 异常类型 | 处理方式 | 重试 |
|---------|---------|------|
| 超时/网络错误 | 指数退避重试（1s → 2s → 4s） | 最多 3 次 |
| 浏览器崩溃 | 自动重启浏览器，加载保存的登录态 | 1 次 |
| 元素未找到 | 重试寻找备用选择器 | 最多 3 次 |

## 日志和调试

### 查看日志

```bash
# 实时查看日志
tail -f logs/gemini.log

# Windows
type logs\gemini.log
```

### 调试模式

修改 main.py 中的日志级别（可选）：

```python
logging.basicConfig(
    level=logging.DEBUG,  # 改为 DEBUG 查看详细信息
)
```

## 常见问题

### Q1: 首次运行时一直显示"未登录"

**原因**: 登录页面加载慢或选择器有变化

**解决方案**:
1. 确保浏览器窗口完全打开
2. 手动登录 Google 账户
3. 登录后等待页面完全加载
4. 回到终端按 ENTER 继续

### Q2: 流式输出卡顿或漏字

**原因**: 网络延迟或 PC 性能不足

**解决方案**:
1. 增加超时时间: `--timeout 60`
2. 调整检查间隔（高级）: 编辑 `gemini_browser.py` 中的 `check_interval`

### Q3: Headless 模式下无法登录

**原因**: 首次 headless 运行无法进行手动登录

**解决方案**:
1. 第一次必须用非 headless 模式登录: `python main.py interactive`
2. 登录后可以切换到 headless: `python main.py interactive --headless`

### Q4: "浏览器已崩溃"错误

**原因**: 系统资源不足或 Chromium 进程被杀

**解决方案**:
1. 关闭其他占用内存的程序
2. 增加重试次数: `--retry 5`
3. 查看日志获取更多信息: `tail -f logs/gemini.log`

### Q5: 如何清除登录态重新登录？

**解决方案**:
```bash
# 删除保存的登录题
rm profiles/storage_state.json

# 重新运行（会要求手动登录）
python main.py interactive
```

### Q6: 多轮对话时第二条回复显示聊天菜单而不是 AI 回复

**原因**: 多轮对话时 DOM 中累积历史消息，选择器可能指向聊天菜单列表而非当前回复

**解决方案**:
本项目已内置自动处理机制，请确保：
1. 检查日志中是否显示 `"多轮对话：发现 N 个标记，提取最新回复"` - 说明自动过滤正在工作
2. 如果仍有问题，尝试：
   - 增加超时：`--timeout 60`
   - 查看详细日志：修改 main.py，改为 `logging.DEBUG` 级别
   - 重启浏览器清空缓存：`python main.py interactive`（删除 profiles/storage_state.json 前）

**技术原理**:
- 多轮对话时，程序会寻找所有 "Gemini 说" 标记
- 只提取最后一个 "Gemini 说" 之后的内容，确保是最新回复
- 此机制在 gemini_browser.py:536-549 行

## 系统要求


- **Python**: 3.11 或更高版本
- **操作系统**: Windows / macOS / Linux
- **网络**: 能正常访问 Google Gemini 官网
- **内存**: 至少 500MB（浏览器进程）

```bash
# 检查 Python 版本
python --version  # 需要 >= 3.11
```

## 依赖项

```
playwright==1.48.0      # 浏览器自动化框架
python-dotenv==1.0.0    # 环境变量配置
```

所有依赖都已在 `requirements.txt` 中指定。

## 验收标准（MVP）

✅ 运行 `python main.py interactive` 后可正常聊天
✅ 关闭程序再打开仍保持登录态
✅ 流式输出流畅，无卡顿，逐字打印
✅ Headless=True 在服务器上能正常工作
✅ 超时和网络异常时自动重试并恢复
✅ 浏览器崩溃时自动重启并继续聊天

## 后续扩展点（v2+）

- [ ] 支持多 Profile 轮换（避免账号限制）
- [ ] 集成 stealth_async 增强反检测
- [ ] 支持文件上传和图片分析
- [ ] FastAPI + SSE 流式接口
- [ ] 多轮对话历史保存
- [ ] 支持其他 AI（Claude/ChatGPT/Grok）
- [ ] Docker 部署

## Troubleshooting 故障排除

### 如果遇到问题，请按以下步骤排查：

```bash
# 1. 查看日志
tail -f logs/gemini.log

# 2. 检查网络连接
ping gemini.google.com

# 3. 重新安装 Playwright
pip install --upgrade playwright
playwright install chromium

# 4. 清除 Profile 重新登录
rm profiles/storage_state.json
python main.py interactive

# 5. 提高超时和重试
python main.py interactive --timeout 60 --retry 5
```

## 许可和免责声明

本项目仅供学习和研究使用。请遵守 Google Gemini 的使用条款和隐私政策。

不要用于大规模自动化爬取或滥用服务。

## 贡献和反馈

欢迎报告 Bug 或提交功能建议！

## Support 支持

遇到问题？请查看：
1. 本文件的"常见问题"部分
2. 检查 `logs/gemini.log` 日志文件
3. 提高 `--timeout` 参数试试

祝使用愉快！ 🚀

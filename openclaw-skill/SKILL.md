---
name: gemini-browser-automator
description: 使用 Playwright 自动化与 Google Gemini 聊天，支持持久化登录、流式输出、文件上传和 headless 模式
version: 1.0.0
type: skill
tools:
  bash:
    description: 执行 shell 命令来运行 Gemini 浏览器自动化工具
  read:
    description: 读取配置文件和日志文件
  write:
    description: 修改配置文件或创建新的配置
---

# Gemini 浏览器自动化工具

这个技能帮助你使用 Python Playwright 自动化与 Google Gemini 聊天，实现真正的浏览器自动化操作。

## 主要功能

- **持久化登录态**：首次登录后自动保存登录状态，后续无需重复登录
- **流式输出**：实时逐字打印 Gemini 生成的回复
- **文件上传**：支持上传图片、PDF、文本、视频、数据文件
- **Headless 模式**：支持无头模式，适合服务器后台运行
- **自动重试**：超时、网络错误、浏览器崩溃自动恢复
- **反检测**：内置反爬虫参数，避免被检测为自动化工具

## 使用方法

### 1. 首次使用（手动登录）

```bash
# 克隆或下载项目
cd D:\tools\Gemini-Browser-Automator-MVP

# 安装依赖
pip install -r requirements.txt
playwright install chromium

# 启动交互模式（会弹出浏览器窗口）
python main.py interactive
```

在弹出的浏览器窗口中手动登录 Google 账户，登录成功后回到终端按 ENTER 继续。

### 2. 日常使用（自动登录）

```bash
# 交互模式
python main.py interactive

# 单次查询
python main.py query "你的问题"

# Headless 模式（无 GUI）
python main.py interactive --headless
```

### 3. 文件上传

在交互模式中使用 `/upload` 命令：

```bash
[Gemini] >> /upload ./image.jpg
[Gemini] >> /upload ~/Downloads/doc.pdf
[Gemini] >> /upload /absolute/path/file.csv
```

支持的文件类型：
- 图片：jpg, jpeg, png, gif, webp, bmp（最大 20MB）
- PDF：pdf（最大 50MB）
- 文本：txt, doc, docx, md（最大 10MB）
- 视频：mp4, webm, mov, avi, mkv（最大 100MB）
- 数据：csv, json, xlsx, xls（最大 20MB）

## 命令行参数

### Interactive 模式

```bash
python main.py interactive [OPTIONS]
```

参数说明：
- `--headless`：启用 headless 模式（无 GUI）
- `--profile <dir>`：Profile 存储目录（默认：./profiles）
- `--timeout <sec>`：操作超时时间（秒，默认：30）
- `--retry <n>`：异常重试次数（默认：3）

### Query 模式

```bash
python main.py query <QUESTION> [OPTIONS]
```

参数说明：
- `<QUESTION>`：要提问的问题（必需）
- `--headless`：启用 headless 模式
- `--profile <dir>`：Profile 存储目录
- `--timeout <sec>`：操作超时时间
- `--retry <n>`：重试次数

## 工作流程

1. **启动浏览器**：启动 Chromium 浏览器，加载保存的登录态
2. **登录检查**：检查是否已登录，未登录则提示用户手动登录
3. **消息发送**：将用户输入的文本发送到 Gemini
4. **流式输出**：使用 MutationObserver 实时监听 DOM 变化，逐字输出回复
5. **文件处理**：支持上传文件，使用 Playwright 的 filechooser 事件拦截
6. **异常恢复**：自动处理超时、网络错误等异常情况

## 项目结构

```
Gemini-Browser-Automator-MVP/
├── main.py                  # CLI 入口和交互控制器
├── gemini_browser.py        # 核心浏览器自动化类
├── config.py                # 配置管理
├── exceptions.py            # 自定义异常定义
├── file_uploader.py         # 文件上传功能模块
├── requirements.txt         # Python 依赖
├── profiles/                # 浏览器 Profile（自动创建）
│   └── storage_state.json   # 保存的登录态和 Cookies
└── logs/                    # 日志文件（自动创建）
    └── gemini.log
```

## 常见问题

### Q: 首次运行时一直显示"未登录"
确保浏览器窗口完全打开，手动登录 Google 账户，登录后等待页面完全加载，回到终端按 ENTER 继续。

### Q: 流式输出卡顿或漏字
增加超时时间：`--timeout 60`，或者调整检查间隔。

### Q: Headless 模式下无法登录
首次必须用非 headless 模式登录，登录后可以切换到 headless 模式。

### Q: 如何清除登录态重新登录？
删除保存的登录态文件：`rm profiles/storage_state.json`，然后重新运行。

### Q: 多轮对话时显示错误内容
本项目已内置自动处理机制，如果仍有问题，尝试增加超时或查看详细日志。

## 依赖要求

- Python 3.11+
- 能够访问 Google Gemini 官网的网络
- 至少 500MB 内存

## 系统要求

- Python 3.11 或更高版本
- Windows / macOS / Linux
- 能正常访问 Google Gemini 官网
- 至少 500MB 内存（浏览器进程）

## 调试技巧

查看日志文件：
```bash
# 实时查看日志
tail -f logs/gemini.log

# Windows
type logs\gemini.log
```

修改日志级别为 DEBUG 以查看详细信息：
编辑 `main.py`，将 `level=logging.INFO` 改为 `level=logging.DEBUG`。

## 注意事项

- 首次运行需要手动登录 Google 账户
- 项目仅供学习和研究使用，请遵守 Google Gemini 的使用条款
- 不要用于大规模自动化爬取或滥用服务
- 建议使用虚拟环境来管理依赖
# Gemini 自动化工具

默认使用 Gemini API 模式，支持多 API Key 循环容灾和文件上传。

**版本**: 2.0.0
**语言**: Python 3.11+

## 核心特性

- **API 模式（默认）** - 使用官方 Gemini API，快速稳定
- **多 Key 容灾** - 支持多个 API Key 自动轮换，配额用尽自动切换
- **文件上传** - 支持图片、PDF、视频、音频等文件分析
- **浏览器模式** - 保留 Playwright 浏览器自动化作为备选
- **流式输出** - 实时逐字打印回复

## 快速开始

### 1. 获取 API Key

从 https://aistudio.google.com/apikey 获取免费的 Gemini API Key。

### 2. 配置 API Keys

创建 `api_keys.txt` 文件，每行一个 Key：

```
AIzaSyXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
AIzaSyYYYYYYYYYYYYYYYYYYYYYYYYYYYYYY
```

支持多个 Key，程序会自动轮换使用。

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 运行

```bash
# 交互模式（默认）
python main.py

# 单次查询
python main.py "你好，介绍一下自己"

# 文件+查询
python main.py --file image.png "分析这张图片"
python main.py -f document.pdf "总结这个文档"

# 指定模型
python main.py --model gemini-1.5-pro

# 直接指定 Keys
python main.py --keys "key1,key2,key3"
```

## 使用示例

### 交互模式

```bash
python main.py

[Gemini] >> 你好
[Gemini] 正在生成回复...

你好！我是 Gemini...

[Gemini] >> /upload ./image.png
[Gemini] 正在上传文件: ./image.png
✓ 文件上传成功

[Gemini] >> 分析这张图片
这张图片显示的是...

[Gemini] >> /status
API Key 池状态
--------------------------------------------------
总 Key 数: 3
可用 Key 数: 3
Key 详情:
  AIzaSyX...XXX: healthy (错误: 0, 成功: 5)
--------------------------------------------------

[Gemini] >> exit
```

### 文件分析

```bash
# 分析图片
python main.py --file photo.jpg "描述这张图片"

# 分析 PDF
python main.py -f report.pdf "总结这个报告的要点"

# 分析视频
python main.py --file video.mp4 "这个视频讲了什么"

# 只上传文件（使用默认提示词"分析这个文件"）
python main.py --file document.pdf
```

### 交互命令

| 命令 | 说明 |
|------|------|
| `exit` / `quit` | 退出程序 |
| `/help` | 显示帮助信息 |
| `/status` | 查看 API Key 池状态 |
| `/upload <path>` | 上传文件 |
| `/files` | 列出已上传文件 |

## 命令行参数

### API 模式（默认）

```bash
python main.py [query] [OPTIONS]
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `query` | 单次查询（可选） | - |
| `--file`, `-f` | 上传文件路径 | - |
| `--keys` | API Keys（逗号分隔） | - |
| `--keys-file` | API Keys 文件路径 | api_keys.txt |
| `--model` | 模型名称 | gemini-2.5-flash |
| `--api-timeout` | API 超时时间（秒） | 60 |

### 浏览器模式

```bash
python main.py --browser [query] [OPTIONS]
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `query` | 单次查询（可选） | - |
| `--file`, `-f` | 上传文件路径 | - |
| `--headless` | 无头模式 | True |
| `--no-headless` | 显示浏览器窗口 | - |
| `--profile` | Profile 目录 | ./profiles |
| `--timeout` | 超时时间（秒） | 30 |

## 文件上传

支持上传以下类型的文件：

| 类型 | 扩展名 | 最大大小 |
|------|--------|----------|
| 图片 | jpg, png, gif, webp, bmp | 20 MB |
| PDF | pdf | 50 MB |
| 视频 | mp4, webm, mov, mkv | 100 MB |
| 音频 | mp3, wav, flac, m4a | 50 MB |

## 多 Key 容灾

### 容灾机制

- **自动轮换**：Key 配额用尽或触发限制时自动切换
- **冷却机制**：触发速率限制的 Key 进入 60 秒冷却期
- **状态监控**：使用 `/status` 命令查看所有 Key 状态

### 配置多个 Key

方法一：`api_keys.txt` 文件（推荐）

```
AIzaSyXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
AIzaSyYYYYYYYYYYYYYYYYYYYYYYYYYYYYYY
AIzaSyZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ
```

方法二：命令行参数

```bash
python main.py --keys "key1,key2,key3"
```

## 浏览器模式

如需使用浏览器自动化模式：

```bash
# 交互模式
python main.py --browser

# 单次查询
python main.py --browser "你的问题"

# 文件+查询
python main.py --browser --file image.png "分析这张图片"

# 显示浏览器窗口
python main.py --browser --no-headless
```

首次使用浏览器模式需要手动登录 Google 账户。

## 项目结构

```
Gemini-Browser-Automator-MVP/
├── main.py              # CLI 入口
├── gemini_api.py        # API 客户端 + Key 池管理
├── gemini_browser.py    # 浏览器自动化
├── config.py            # 配置管理
├── exceptions.py        # 异常定义
├── requirements.txt     # 依赖
├── api_keys.txt         # API Keys 配置
├── api_keys.txt.example # 配置示例
├── profiles/            # 浏览器 Profile
└── logs/                # 日志
```

## 常见问题

### Q: 提示"未配置 API Key"

**解决方案**：
1. 创建 `api_keys.txt` 文件
2. 或使用 `--keys` 参数传入

### Q: 所有 Key 都不可用

**解决方案**：
1. 检查 Keys 是否有效
2. 添加更多 Keys
3. 等待冷却期结束

### Q: 如何切换模型

```bash
python main.py --model gemini-1.5-pro
python main.py --model gemini-2.0-flash
```

### Q: 如何查看 Key 池状态

在交互模式中输入 `/status`。

## 依赖

```
playwright>=1.48.0
python-dotenv>=1.0.0
google-genai>=1.0.0
```

## 更新日志

### v2.0.0

- 默认使用 API 模式
- 支持多 API Key 循环容灾
- 支持文件上传（命令行 `--file` 参数）
- 使用 google-genai 新版 SDK
- 流式输出

### v1.3.0

- 添加 KEEP_BROWSER_OPEN 持续模式

### v1.0.0

- 初始版本，浏览器自动化

## 许可证

本项目仅供学习和研究使用。请遵守 Google Gemini API 使用条款。

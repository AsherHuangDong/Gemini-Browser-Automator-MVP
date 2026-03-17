---
name: gemini-automator
description: Gemini 自动化工具，默认使用 API 模式，支持多 API Key 循环容灾、文件上传、浏览器模式备选
version: 2.0.0
type: skill
tools:
  bash:
    description: 执行 shell 命令运行 Gemini 自动化工具
  read:
    description: 读取配置文件和日志
  write:
    description: 修改配置文件
---

# Gemini 自动化工具

默认使用 Gemini API 模式，支持多 API Key 循环容灾和文件上传。

## 核心功能

- **API 模式（默认）**：使用官方 Gemini API，无需浏览器
- **多 Key 容灾**：支持多个 API Key 自动轮换，配额用尽自动切换
- **文件上传**：支持图片、PDF、视频、音频等文件上传分析
- **浏览器模式**：保留 Playwright 浏览器自动化作为备选

## 快速开始

### 1. 配置 API Keys

创建 `api_keys.txt` 文件，每行一个 API Key：

```
AIzaSyXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
AIzaSyYYYYYYYYYYYYYYYYYYYYYYYYYYYYYY
```

从 https://aistudio.google.com/apikey 获取 API Key。

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 使用

```bash
# 交互模式（默认）
python main.py

# 单次查询
python main.py "你的问题"

# 文件+查询
python main.py --file image.png "分析这张图片"
python main.py -f document.pdf "总结这个文档"

# 指定模型
python main.py --model gemini-1.5-pro

# 直接指定 Keys
python main.py --keys "key1,key2,key3"
```

## 文件分析

```bash
# 分析图片
python main.py --file photo.jpg "描述这张图片"

# 分析 PDF
python main.py -f report.pdf "总结这个报告"

# 分析视频
python main.py --file video.mp4 "这个视频讲了什么"
```

支持的文件类型：
- 图片：jpg, png, gif, webp, bmp
- PDF：pdf
- 视频：mp4, webm, mov
- 音频：mp3, wav, flac

## 交互命令

在交互模式中：

| 命令 | 说明 |
|------|------|
| `exit` | 退出程序 |
| `/help` | 显示帮助 |
| `/status` | 查看 API Key 池状态 |
| `/upload <path>` | 上传文件 |
| `/files` | 列出已上传文件 |

## 浏览器模式

如需使用浏览器模式：

```bash
python main.py --browser              # 交互模式
python main.py --browser "问题"       # 单次查询
python main.py --browser --file image.png "分析图片"  # 文件+查询
```

## 在 OpenClaw 中使用

直接运行即可，程序会自动加载 `api_keys.txt` 中的 Keys：

```bash
python main.py
```

## Key 容灾机制

- **自动轮换**：Key 配额用尽时自动切换到下一个
- **冷却机制**：触发速率限制的 Key 进入 60 秒冷却
- **状态监控**：使用 `/status` 命令查看 Key 池状态

## 命令行参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `query` | 单次查询 | - |
| `--file`, `-f` | 上传文件路径 | - |
| `--keys` | API Keys（逗号分隔） | - |
| `--keys-file` | API Keys 文件 | api_keys.txt |
| `--model` | 模型名称 | gemini-2.5-flash |
| `--browser` | 使用浏览器模式 | - |

## 常见问题

### Q: 提示"未配置 API Key"
创建 `api_keys.txt` 文件或使用 `--keys` 参数传入。

### Q: 所有 Key 都不可用
检查 Keys 是否有效，或添加更多 Keys。

### Q: 如何切换模型
使用 `--model` 参数，如 `--model gemini-1.5-pro`。

## 配置文件

| 文件 | 说明 |
|------|------|
| `api_keys.txt` | API Keys 配置（每行一个） |
| `api_keys.txt.example` | 配置示例 |

## 依赖

```
playwright>=1.48.0
python-dotenv>=1.0.0
google-genai>=1.0.0
```
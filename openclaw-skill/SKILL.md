---
name: gemini-browser-automator
description: 使用 Playwright 自动化与 Google Gemini 聊天，支持持久化登录、流式输出、文件上传、自动代理检测、默认 headless 模式和性能优化
version: 1.2.0
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
- **默认 Headless 模式**：默认使用无头模式，99%+ 时间无窗口运行
- **智能登录检测**：严格的登录检查，自动处理登录态失效
- **自动代理检测**：自动检测并使用系统代理，无需手动配置
- **性能优化**：登录检查速度提升 50-70%，快速进入对话
- **流式输出**：实时逐字打印 Gemini 生成的回复
- **文件上传**：支持上传图片、PDF、文本、视频、数据文件
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

# 首次运行（会弹出浏览器窗口要求登录）
python main.py interactive
```

在弹出的浏览器窗口中手动登录 Google 账户，登录成功后回到终端按 ENTER 继续。

**注意**：首次运行需要手动登录，之后会自动使用保存的登录态。

### 2. 日常使用（默认 headless 模式）

```bash
# 交互模式（默认 headless，无窗口）
python main.py interactive

# 单次查询（默认 headless）
python main.py query "你的问题"

# 如果需要查看浏览器（调试用）
python main.py interactive --headless false
```

**v1.1 改进**：
- 默认使用 headless 模式，99%+ 时间无窗口运行
- 只在登录失效时短暂弹出浏览器，手动确认后又恢复长期 headless
- 自动检测并使用系统代理（如 127.0.0.1:15715）

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
- `--headless`：启用/禁用 headless 模式（默认：True，即无窗口）
- `--profile <dir>`：Profile 存储目录（默认：./profiles）
- `--timeout <sec>`：操作超时时间（秒，默认：30）
- `--retry <n>`：异常重试次数（默认：3）

### Query 模式

```bash
python main.py query <QUESTION> [OPTIONS]
```

参数说明：
- `<QUESTION>`：要提问的问题（必需）
- `--headless`：启用/禁用 headless 模式（默认：True）
- `--profile <dir>`：Profile 存储目录
- `--timeout <sec>`：操作超时时间
- `--retry <n>`：重试次数

## 工作流程（v1.2 性能优化）

1. **启动浏览器**：默认以 headless 模式启动 Chromium 浏览器
2. **自动代理检测**：自动检测并使用系统代理（如 127.0.0.1:15715）
3. **快速导航**：使用优化的导航和等待策略
4. **加载登录态**：加载保存的登录态和 Cookies
5. **快速登录检查**（v1.2 优化）：
   - 输入框检查超时从 2 秒减少到 0.5 秒
   - 找到输入框立即返回
   - 移除慢速的页面文本检查
6. **智能 fallback**：
   - 如果 headless 模式下登录失败 → 自动切换到 headful 模式
   - 弹出浏览器窗口，提示用户手动登录
   - 登录成功后保存登录态，下次继续使用 headless 模式
7. **健康检查**：每次发送消息前检查 session 是否有效
8. **消息发送**：将用户输入的文本发送到 Gemini
9. **流式输出**：使用 MutationObserver 实时监听 DOM 变化，逐字输出回复
10. **文件处理**：支持上传文件，使用 Playwright 的 filechooser 事件拦截
11. **异常恢复**：自动处理超时、网络错误等异常情况

**v1.2 性能提升**：
- 登录检查速度提升 50-70%
- 从启动到开始对话的时间缩短约 60%

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
**原因**：首次运行需要手动登录 Google 账户

**解决方案**：
1. 程序会自动弹出浏览器窗口
2. 在浏览器中手动登录 Google 账户
3. 登录后等待页面完全加载
4. 回到终端按 ENTER 继续
5. 之后会自动保存登录态，后续无需重复登录

### Q: 仍然弹出浏览器窗口
**原因**：可能是登录态失效，或者你显式使用了 `--headless false`

**解决方案**：
- 登录态失效是正常的（Google 的 session 有有效期）
- 在浏览器中重新登录后，下次又会恢复 headless 模式
- 如果要一直有窗口，可以使用 `--headless false`

### Q: 连接超时（net::ERR_CONNECTION_TIMED_OUT）
**原因**：网络无法访问 Google

**解决方案**：
- v1.1 已自动检测并使用系统代理
- 确保你的代理正在运行（如 127.0.0.1:15715）
- 检查代理配置是否正确

### Q: 流式输出卡顿或漏字
**原因**：网络延迟或 PC 性能不足

**解决方案**：
- 增加超时时间：`--timeout 60`
- 或者调整检查间隔

### Q: 如何清除登录态重新登录？
**解决方案**：
```bash
# 删除保存的登录态
rm profiles/storage_state.json

# 重新运行（会要求手动登录）
python main.py interactive
```

### Q: 多轮对话时显示错误内容
**原因**：多轮对话时 DOM 中累积历史消息

**解决方案**：
本项目已内置自动处理机制，如果仍有问题：
- 增加超时：`--timeout 60`
- 查看详细日志：修改 main.py，改为 `logging.DEBUG` 级别
- 重启浏览器清空缓存

## 依赖要求

- Python 3.11+
- 能够访问 Google Gemini 官网的网络（或使用代理）
- 至少 500MB 内存

## 系统要求

- Python 3.11 或更高版本
- Windows / macOS / Linux
- 能正常访问 Google Gemini 官网（或通过代理）
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

## v1.1 更新亮点

✅ **默认 Headless 模式**：99%+ 时间无窗口运行
✅ **智能登录检测**：严格的登录检查，自动处理登录态失效
✅ **自动代理检测**：自动检测并使用系统代理
✅ **健康检查**：每次发送消息前检查 session 是否有效
✅ **页面加载重试**：支持最多 3 次重试，使用指数退避
✅ **性能优化**：登录检查速度提升 50-70%，快速进入对话

## v1.2 性能优化亮点

- **登录检查加速**：输入框检查超时从 2 秒减少到 0.5 秒
- **智能返回机制**：找到输入框立即返回，不检查其他条件
- **移除慢速检查**：去除页面文本检查，大幅提升速度
- **减少等待时间**：
  - 登录检查前：从 3 秒减少到 1 秒
  - 导航后：从 5 秒减少到 2 秒
  - networkidle 超时：从 10 秒减少到 5 秒
- **总体提升**：从启动到开始对话的时间缩短约 60%

## 注意事项

- 首次运行需要手动登录 Google 账户
- 登录态有时效性（通常 1-4 周），失效时会短暂弹出浏览器
- 程序会自动检测并使用系统代理
- 项目仅供学习和研究使用，请遵守 Google Gemini 的使用条款
- 不要用于大规模自动化爬取或滥用服务
- 建议使用虚拟环境来管理依赖

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
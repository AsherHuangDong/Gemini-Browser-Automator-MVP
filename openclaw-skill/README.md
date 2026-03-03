# Gemini Browser Automator - OpenClaw Skill

这个 OpenClaw skill 将 Gemini Browser Automator 工具集成到 OpenClaw 中，让你可以在 OpenClaw 中直接使用 Gemini 浏览器自动化功能。

## 安装步骤

### 方法 1：手动复制（推荐）

1. 将 `openclaw-skill` 文件夹复制到你的 OpenClaw skills 目录：

**Windows:**
```bash
xcopy /E /I openclaw-skill "%USERPROFILE%\.openclaw\workspace\skills\gemini-browser-automator"
```

**Linux/Mac:**
```bash
cp -r openclaw-skill ~/.openclaw/workspace/skills/gemini-browser-automator
```

2. 刷新 OpenClaw 或重启 OpenClaw Gateway

### 方法 2：使用 PowerShell（Windows）

```powershell
Copy-Item -Recurse -Force openclaw-skill $env:USERPROFILE\.openclaw\workspace\skills\gemini-browser-automator
```

### 方法 3：使用 Bash（Linux/Mac）

```bash
cp -r openclaw-skill ~/.openclaw/workspace/skills/gemini-browser-automator
```

## 使用方法

安装完成后，在 OpenClaw 中使用：

```
使用 gemini-browser-automator skill
```

然后你就可以：
- 与 Gemini 进行对话
- 上传文件进行分析
- 使用 headless 模式在后台运行

## 功能特性

- 持久化登录态
- 流式输出
- 文件上传（图片、PDF、文本、视频、数据文件）
- Headless 模式
- 自动重试
- 反检测

## 依赖

- Python 3.11+
- Playwright
- 能够访问 Google Gemini 官网

## 注意事项

- 首次使用需要手动登录 Google 账户
- 仅供学习和研究使用
- 请遵守 Google Gemini 的使用条款

## 项目地址

https://github.com/AsherHuangDong/Gemini-Browser-Automator-MVP
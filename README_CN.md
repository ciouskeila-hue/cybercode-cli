# CyberCode CLI — Codex 暗色风格 Web UI 与内置自进化 Agent

[![npm version](https://img.shields.io/npm/v/cybercode-cli.svg)](https://www.npmjs.com/package/cybercode-cli)
[![license](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![deps](https://img.shields.io/badge/依赖-stdlib%2Brequests-28c840)](#)

一个独立的、自包含的 Web UI + Agent 框架，采用 Codex 暗色界面风格。**无外部 Agent 依赖** ——
整个 Agent 核心（LLM 客户端、Agent 循环、9 个原子工具、分层记忆）都内置在
`agent_core.py` 中，从单一目录运行。

## 安装

```bash
npm install -g cybercode-cli
```

然后运行：

```bash
cybercode
```

首次运行时会自动：
1. 查找系统中的 Python 3.11+
2. 如果缺少 `requests` 则自动安装
3. 将内置的 Agent + 技能文件复制到 `~/.cybercode/`
4. 创建 `mykey.json` 模板（填入你的 API Key，或通过网页登录）
5. 启动 Web UI 并自动打开浏览器

## 更新

CyberCode 启动时会自动检查更新。手动更新：

```bash
cybercode update
```

或通过 npm：

```bash
npm update -g cybercode-cli
```

## 诊断

运行 `cybercode doctor` 检查环境：

```bash
cybercode doctor
```

检查 Node.js、Python、`requests` 包、工作目录和 npm 版本。

## 用法

```bash
cybercode                                # 启动 Web UI（默认）
cybercode webui --port 8080              # 自定义端口
cybercode webui --host 0.0.0.0           # 监听所有网络接口
cybercode webui --no-browser             # 不自动打开浏览器
cybercode webui --dir ~/my-agent         # 自定义工作目录
cybercode webui --llm 1                  # 使用第 2 个配置的 LLM
cybercode update                         # 自动更新到最新版本
cybercode doctor                         # 运行诊断
```

### 选项

| 参数 | 说明 |
| :--- | :--- |
| `-p, --port <num>` | 端口号（默认：自动查找 18600 附近的可用端口） |
| `--host <addr>` | 绑定地址（默认：127.0.0.1） |
| `--dir <path>` | 工作目录（默认：~/.cybercode） |
| `--llm <num>` | 启动时使用的 LLM 索引（默认：0） |
| `--no-browser` | 不自动打开浏览器 |
| `-h, --help` | 显示帮助 |
| `-V, --version` | 显示版本号 |

## 致谢与许可

`agent_core.py` 中的 Agent 核心架构参考了
[**GenericAgent**](https://github.com/lsdefine/GenericAgent)（作者 lsdefine，
MIT 许可证，Copyright © 2025 lsdefine）。我们感谢 GenericAgent 项目 ——
其约 100 行的 Agent 循环、9 原子工具设计和分层记忆概念直接启发了本实现。

内置的 HyperFrames 技能（`skills/`）源自
[**HyperFrames**](https://github.com/heygen-com/hyperframes)（HeyGen，
MIT 许可证）。

详见 `LICENSE` 中的完整 MIT 许可证文本，包括 GenericAgent 的版权声明。

## 项目简介

`cybercodewebui.py` 启动一个自包含的 `Agent`（来自 `agent_core.py`），
在 `/` 路径提供 `cybercodewebui.html`，并暴露 JSON + SSE API 供前端调用。
UI 保持 Codex 暗色风格 —— 蓝色径向渐变桌面、红绿灯窗口控件、暗色侧边栏
（含会话列表 + 技能）、居中的 *Let's build* 空状态、药丸状 LLM 切换器、
圆角输入框（支持 Local/Worktree/Cloud 模式）—— 每个控件都已接入内置 Agent。

**独立运行：无 GenericAgent 依赖。** Agent 核心（`agent_core.py`）是从头
实现的，直接打包在本仓库中。你**不需要**安装 GenericAgent。唯一的运行时
依赖是 `requests`（用于 LLM HTTP 客户端），其他全部使用 Python 标准库。

## 文件结构

```
cybercode-cli/
├── package.json       # npm 包配置（bin、文件列表、元数据）
├── bin/
│   └── cli.mjs        # Node.js 启动器（查找 Python、引导启动、打开浏览器）
├── python/
│   ├── agent_core.py       # 自包含 Agent 核心（LLM 客户端 + 循环 + 9 工具 + 记忆）
│   ├── cybercodewebui.py   # 标准库 HTTP 服务器 + SSE + API
│   └── cybercodewebui.html # Codex 暗色 UI（单文件，无需构建）
├── skills/             # HyperFrames 视频技能（12 个文件，来自 HeyGen）
├── templates/
│   └── mykey_template.json  # API Key 模板（首次运行自动复制）
├── LICENSE             # MIT（包含 GenericAgent + HyperFrames 版权声明）
└── README.md           # 英文文档
```

## 手动运行（不使用 npm）

如果你希望直接运行 Python 服务器：

```bash
# 1. 配置你的 LLM（任何 OpenAI 兼容端点）
cat > mykey.json << 'EOF'
{
  "llm1": {
    "apikey": "sk-your-key-here",
    "apibase": "https://api.openai.com",
    "model": "gpt-4o",
    "name": "GPT-4o"
  }
}
EOF

# 2. 安装 requests（唯一依赖）
pip install requests

# 3. 运行
python python/cybercodewebui.py                 # http://127.0.0.1:18600
```

## 支持的 LLM 提供商

任何 OpenAI 兼容的 chat completions 端点都可以使用：
- **OpenAI**（GPT-4o、o1、o3 等）
- **DeepSeek**
- **Kimi / Moonshot**
- **MiniMax**
- **本地模型** 通过 Ollama、LM Studio、vLLM 等
- **Anthropic Claude** 通过 OpenAI 兼容代理
- **l0veyou** 后端（内置登录支持）

## 功能一览

| UI 元素 | 对应功能 |
| :--- | :--- |
| **输入框 + 发送** | `agent.put_task()` → SSE 流式输出 |
| **停止按钮** | `agent.abort()` |
| **新建会话** | `/api/new` → 清空对话历史 |
| **会话列表（侧边栏）** | `/api/sessions` → 扫描日志文件 |
| **点击会话** | `/api/continue` → 恢复该会话 |
| **LLM 切换器** | `/api/llm` → `agent.next_llm(idx)` |
| **技能面板** | `/api/skills` → 列出记忆/SOP 文件 |
| **状态指示灯** | `agent.is_running` 每 4 秒轮询 |
| **工具/文件引用** | 工具标签；`[FILE:path]` → 可点击文件标签 |
| **轮次折叠** | 可折叠的轮次区域 |
| **制作视频按钮** | 注入 HyperFrames 技能前导 + `/video` 命令 |
| **视频画廊** | `/api/videos` → 扫描已渲染的 `.mp4` 文件 |
| **视频播放** | `/api/video/<path>` → 支持 Range 的流式播放 |
| **登录界面** | Web UI 登录（需要 l0veyou 后端） |
| **图片生成** | 内置图片生成面板 |
| **视频生成** | 内置视频生成面板 |

## 9 个原子工具

Agent 核心暴露了 9 个工具（与 GenericAgent 设计理念一致）：

| 工具 | 功能 |
| :--- | :--- |
| `code_run` | 执行 Python 或 Shell 脚本 |
| `file_read` | 读取文件（带行号、关键词搜索） |
| `file_write` | 创建/覆盖/追加文件 |
| `file_patch` | 修补文件中的唯一文本块 |
| `web_scan` | 抓取并简化网页（基于 urllib） |
| `web_execute_js` | 在浏览器中执行 JS（需要 TMWebDriver；优雅降级） |
| `ask_user` | 中断并向用户提问 |
| `update_working_checkpoint` | 短期工作记忆记事本 |
| `start_long_term_update` | 将经验提炼为长期记忆 |

## HyperFrames — 内置视频生成

HyperFrames 技能包（12 个文件）打包在 `skills/` 中。点击侧边栏的
**Make video** 按钮，或输入 `/video <描述>`。Agent 会读取内置技能，
使用 `npx hyperframes` CLI 将 HTML 组合渲染为 `.mp4` 文件。
渲染的视频会出现在侧边栏画廊中，可内联播放。

## API 参考

| 方法 | 路径 | 说明 |
| :--- | :--- | :--- |
| GET | `/` | Web UI |
| GET | `/api/status` | Agent 状态：运行中、LLM、历史 |
| GET | `/api/sessions` | 可恢复的会话（日志文件） |
| GET | `/api/skills` | Agent 记忆/SOP 文件 |
| GET | `/api/messages?path=...` | 回放会话日志中的消息 |
| GET | `/api/hyperframes` | 列出内置 HyperFrames 技能 |
| GET | `/api/hyperframes/<name>` | 原始技能 Markdown |
| GET | `/api/videos` | 已渲染的 `.mp4` 文件 |
| GET | `/api/video/<path>` | 流式播放视频（支持 Range） |
| POST | `/api/chat` | SSE 流：delta / done / error |
| POST | `/api/llm` | 按索引切换 LLM |
| POST | `/api/stop` | 中止当前任务 |
| POST | `/api/new` | 开始新对话 |
| POST | `/api/continue` | 恢复会话 N |
| POST | `/api/btw` | 追问（任务运行时） |

## 许可证

MIT 许可证 —— 详见 `LICENSE`。

[English](README.md) | [中文文档](README_CN.md)

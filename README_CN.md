<div align="center">

# CyberCode

### 免费驱动 GPT-5.5、Claude Opus 4.8、GLM-5.2 的全能 AI Agent 平台

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Self-Contained](https://img.shields.io/badge/Self--Contained-zero%20deps-green.svg)](#)
[![Streaming](https://img.shields.io/badge/Streaming-SSE%20%2B%20FC-orange.svg)](#)

**一个自包含的物理级 AI Agent — 直接调用前沿大模型，自带 9 个系统级工具，能读写文件、执行代码、抓取网页、生成图片与视频。**

[English](README.md)

</div>

> **特别推荐：[Linux.do](https://linux.do)** — 真正的技术人社区。在这里你能找到高质量的 AI 工具分享、开源项目讨论和一手前沿资讯。CyberCode 的诞生离不开 Linux.do 社区的启发与支持，诚邀各位开发者加入这个纯粹、友善、有深度的技术家园。

---

## 这是什么

CyberCode 是一个跑在你本地浏览器里的 AI Agent。它不是套壳聊天框，而是一个**有手有脚的执行者**——能真正操作文件系统、运行脚本、访问网络、生成多媒体内容。

最关键的是：**接入即免费使用 GPT-5.5、Claude Opus 4.8、GLM-5.2、Gemini 3.1 Pro、DeepSeek V4 等前沿模型**，还能免费生成 gpt-image-2 图片和 Nanobanana 视频。所有模型通过统一网关代理，提供干净、用户友好的使用体验。

<div align="center">
<img src="docs/images/ui-real.png" alt="CyberCode 真实运行界面" width="90%">
<p><sub>CyberCode Web 界面 — Codex-dark 风格，左侧模型选择器，右侧技能面板</sub></p>
</div>

---

## 核心能力一览

| 能力 | 说明 |
|------|------|
| **前沿模型免费调用** | GPT-5.5 / Claude Opus 4.8 / GLM-5.2 / Gemini 3.1 Pro / DeepSeek V4 Flash 等 32+ 模型 |
| **免费图片生成** | gpt-image-2（1024×1024 / 竖版 / 横版），支持文生图与图生图编辑 |
| **免费视频生成** | Nanobanana 模型 + HyperFrames HTML 渲染引擎，支持旁白配音（edge-tts） |
| **9 个原子工具** | 代码执行 / 文件读写 / 网页抓取 / JS 执行 / 图片生成 / 视觉理解 / 用户交互 / 记忆管理 |
| **函数调用（FC）** | 支持 OpenAI tools 规范的 function calling，流式与非流式 |
| **三级记忆系统** | L0 元规则 / L1 洞察索引 / L2 稳定事实 / L3 任务 SOP |
| **自包含部署** | 仅需 Python 标准库 + requests，无 LangChain / Playwright / 浏览器二进制依赖 |

---

## 为什么用 CyberCode

市面上大多数 AI 客户端要么是纯聊天框（没有执行能力），要么是笨重的框架（依赖一堆 Node 模块和浏览器内核）。CyberCode 走了一条不同的路：

**把 Agent 做薄，把模型做厚。** 核心只有约 1300 行 Python，但通过统一的 OpenAI 兼容接口接入了三十多个前沿模型。你写一段需求，它自己决定调用哪个工具、读哪个文件、跑哪段代码——整个过程流式输出，你看着它干活。

<div align="center">
<img src="docs/images/architecture.jpg" alt="架构图" width="80%">
<p><sub>架构：Agent Core 居中调度，LLM Client 流式通信，9 工具各司其职</sub></p>
</div>

---

## 内置 32+ 前沿模型

所有模型通过统一网关代理，切换模型只需一次 API 调用。以下是部分模型清单：

### 对话与推理模型

| 模型 | 系列 | 备注 |
|------|------|------|
| `gpt-5.5` | OpenAI GPT | 旗舰对话模型 |
| `gpt-5.4` | OpenAI GPT | 高性价比 |
| `gpt-5-mini` | OpenAI GPT | 轻量快速 |
| `gpt-5.3-codex` | OpenAI Codex | 代码专精 |
| `gpt-4.1` | OpenAI GPT | 经典稳定 |
| `claude-opus-4-8` | Anthropic Claude | 顶配推理 |
| `claude-opus-4-7` | Anthropic Claude | 长文分析 |
| `gemini-3.1-pro-preview` | Google Gemini | 多模态 |
| `gemini-3.5-flash` | Google Gemini | 极速响应 |
| `deepseek-v4-flash` | DeepSeek | 国产顶配 |
| `deepseek-v4-pro` | DeepSeek | 深度推理 |
| `deepseek-r1-14b` | DeepSeek R1 | 推理链 |
| `glm-5.2` | 智谱 GLM | **免费层，支持 FC** |
| `free/glm-5.2` | 智谱 GLM | **默认模型，零成本** |
| `kimi-k2.7` | Moonshot Kimi | 超长上下文 |
| `minimax-m3` | MiniMax | 通用强基 |
| `qwen-2.5-coder-14b` | 阿里通义 | 代码生成 |
| `llama-3.1-8b` | Meta Llama | 开源标杆 |
| `mistral-small-24b` | Mistral | 欧洲旗舰 |

### 多媒体生成模型

| 模型 | 用途 | 调用方式 |
|------|------|----------|
| `gpt-image-2` | 文生图 / 图生图 | 异步 creation-tasks API |
| `codex-gpt-image-2` | 图像编辑 | image-edits 端点 |
| `nanobanana` | 视频生成 | HyperFrames + ffmpeg 合成 |
| `hy-mt1` | 多模态理解 | 视觉问答 |

<div align="center">
<img src="docs/images/media-gen.jpg" alt="多媒体生成" width="90%">
<p><sub>图片生成与视频创作 — 左侧 AI 生图，右侧 HyperFrames 时间轴</sub></p>
</div>

---

## 9 个原子工具

Agent 的工作方式不是"聊天"，而是**调用工具完成任务**。CyberCode 内置 9 个物理级工具，覆盖系统操作的方方面面：

<div align="center">
<img src="docs/images/tools.jpg" alt="9 个原子工具" width="85%">
</div>

| 工具 | 能力 | 示例 |
|------|------|------|
| `tool_code_run` | 执行 Python / Bash / Shell 脚本 | 跑数据分析、装依赖、调系统命令 |
| `tool_file_read` | 读取任意文本文件，支持行号与范围 | 看日志、查源码、读配置 |
| `tool_file_write` | 覆盖 / 追加 / 前插写入文件 | 生成代码、写报告、改配置 |
| `tool_file_patch` | 精确搜索替换文件片段 | 修 bug、重构函数 |
| `tool_web_scan` | 抓取网页并提取正文 | 读文档、爬数据、查资料 |
| `tool_web_execute_js` | 在浏览器里跑 JavaScript | 自动化操作、提取动态内容 |
| `tool_generate_image` | 调用 gpt-image-2 生成图片 | 配图、UI 稿、插画 |
| `tool_view_image` | 视觉理解图片内容 | 看截图找 bug、描述画面 |
| `tool_ask_user` | 向用户提问并等待回答 | 澄清需求、确认危险操作 |

此外还有两个记忆工具：`update_working_checkpoint`（短期笔记）和 `start_long_term_update`（长期经验沉淀），让 Agent 在长任务中不迷路、在重复任务中更聪明。

---

## HyperFrames 视频引擎

CyberCode 内置 HyperFrames 技能集——一个**用 HTML 渲染视频**的框架。你描述想要什么视频，Agent 自动写 HTML 组合（带 `data-*` 时间属性），然后用 GSAP / Lottie / Three.js 做动画，最后 ffmpeg 合成带音频的 MP4。

```
用户："做一个 10 秒的猫咪科普短视频，要有旁白"
  ↓
Agent 决策路径：
  1. 调 gpt-image-2 生成 3 张场景图
  2. 调 edge-tts 合成中文旁白 MP3
  3. 写 HyperFrames HTML 组合（GSAP 时间轴 + 淡入淡出）
  4. ffmpeg 合成 H.264 1920x1080 + AAC 音轨
  5. 自检：视频时长、分辨率、音频存在性 → 100/100
  ↓
输出：cat_video_final.mp4
```

HyperFrames 包含 7 个领域技能，按需加载：

| 技能 | 用途 |
|------|------|
| `hyperframes-core` | HTML 组合作者契约（`data-*` 属性、clips、tracks） |
| `hyperframes-animation` | 原子动画（GSAP / Lottie / Three.js / CSS / WAAPI） |
| `hyperframes-creative` | 创意指导（配色、排版、旁白、节拍） |
| `hyperframes-media` | TTS 配音、背景音乐、字幕、背景去除 |
| `hyperframes-cli` | 开发循环（init / lint / render / publish） |
| `hyperframes-registry` | 注册表组件安装 |
| `general-video` | 通用视频工作流路由 |

---

## 快速开始

### 方式一：npm 一键安装（推荐）

```bash
npm install -g cybercode-cli
```

安装完成后，在终端输入：

```bash
cybercode web
```

终端会显示本地服务地址，浏览器打开即可看到 CyberCode 界面。**无需任何配置**——模型密钥、网关地址、默认参数全部自动就绪，开箱即用。

### 方式二：克隆仓库安装

```bash
git clone https://github.com/ciouskeila-hue/cybercode-cli.git
cd cybercode-cli
python python/cybercodewebui.py
```

同样无需手动配置，启动后浏览器访问 `http://localhost:18600` 即可。

### 开始使用

打开浏览器后，你会看到一个登录界面。你有两种选择：

- **登录 CyberCode 账号**：所有模型（GPT-5.5、Claude Opus 4.8、GLM-5.2 等 32+ 前沿模型）立即可用，图片和视频生成功能也已就绪。支持 GitHub / LinuxDo 一键登录。
- **跳过登录**：点击底部的"跳过登录"链接，使用你自己的 API Key。跳过后不会扫描到任何平台模型，需在设置中手动添加模型（填写 API 地址、模型名、API Key）。

登录后，默认选中 `free/glm-5.2`（零成本模型），你可以随时在左侧模型选择器中切换到其他模型。直接在输入框输入你的需求，Agent 会自动调用工具完成任务。

> **零配置理念**：CyberCode 在启动时自动完成所有底层配置——模型路由、密钥管理、令牌生成全部在后台完成。你作为用户，只需登录账号（或跳过登录后自行配置），剩下的交给系统。

---

## API 接口

CyberCode 暴露一套简洁的 HTTP API，可以集成到其他系统：

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/` | Web UI 页面 |
| `GET` | `/api/status` | 运行状态 + 当前模型 |
| `GET` | `/api/sessions` | 历史会话列表 |
| `GET` | `/api/skills` | 技能文档列表 |
| `GET` | `/api/messages?path=` | 回放某次会话 |
| `GET` | `/api/videos` | 已渲染的 MP4 列表 |
| `GET` | `/api/video/<relpath>` | 视频流（支持 Range） |
| `POST` | `/api/chat` | 发送消息，SSE 流式返回 |
| `POST` | `/api/chat` (video:true) | 视频模式，注入 HyperFrames 前导 |
| `POST` | `/api/llm` | 切换 LLM |
| `POST` | `/api/stop` | 中止当前任务 |
| `POST` | `/api/new` | 开启新会话 |
| `POST` | `/api/continue` | 恢复历史会话 |

---

## 技术栈与开源致谢

CyberCode 的 Agent 核心架构（agent loop 结构、9 工具设计、记忆分层理念、系统 prompt 哲学）源自 **GenericAgent** 项目，由 lsdefine 以 MIT 许可证开源：

- **GenericAgent** — [github.com/lsdefine/GenericAgent](https://github.com/lsdefine/GenericAgent) © 2025 lsdefine

在此之上，CyberCode 做了以下扩展：

- 重写 LLM Client，支持 OpenAI 兼容流式 + 函数调用
- 实现统一网关代理层（模型路由 + 会话令牌）
- 集成 HyperFrames 视频引擎（HTML → ffmpeg 管线）
- 集成 edge-tts 语音合成（自动安装逻辑内置于系统 prompt）
- 构建 Codex-dark 风格 Web UI（i18n 中英双语）
- 零配置自动部署（npm 安装后直接 `cybercode web` 启动）

### 依赖

| 依赖 | 用途 | 是否必须 |
|------|------|----------|
| `requests` | HTTP 请求 | 必须 |
| `ffmpeg` | 视频合成 | 仅视频模式 |
| `edge-tts` | 语音合成 | 仅视频旁白 |
| Python stdlib | 其余一切 | 内置 |

---

## 项目结构

```
cybercode/
├── agent_core.py            # Agent 核心：LLM Client + 9 工具 + agent loop
├── cybercodewebui.py        # Web 服务：HTTP API + SSE 流式 + 代理层
├── cybercodewebui.html      # 前端：Codex-dark UI + i18n + 实时聊天
├── mykey.json               # 模型配置（自动生成，不入库）
├── custom_system_prompt.txt # 自定义系统 prompt（热重载）
├── .auth_token              # 自动生成的令牌（不入库）
├── skills/                  # 14 个技能文档
│   ├── hyperframes.md       # 视频引擎入口
│   ├── hyperframes-core.md  # HTML 组合契约
│   ├── hyperframes-animation.md
│   ├── hyperframes-creative.md
│   ├── hyperframes-media.md
│   ├── hyperframes-cli.md
│   ├── hyperframes-registry.md
│   ├── image-gen.md         # 图片生成 API
│   ├── edge-tts-tts.md      # 语音合成
│   ├── general-video.md     # 通用视频路由
│   ├── motion-graphics.md
│   ├── product-launch-video.md
│   ├── website-to-video.md
│   └── faceless-explainer.md
├── memory/                  # 三级记忆系统
│   ├── global_mem.txt       # L2 稳定事实
│   └── global_mem_insight.txt # L1 洞察索引
├── temp/                    # 工作目录（gitignore）
├── docs/
│   └── images/              # README 演示图片
└── .gitignore
```

---

## 使用示例

### 示例 1：让 Agent 写脚本并执行

```
用户：帮我写一个 Python 脚本，统计当前目录下所有 .py 文件的行数，并按行数排序输出

Agent：
  → tool_file_write: 写 count_lines.py
  → tool_code_run: python count_lines.py
  → 返回结果：agent_core.py 1452 行，cybercodewebui.py 1180 行...
  → tool_file_patch: 发现 bug，修正排序逻辑
  → tool_code_run: 重跑，结果正确
  → 总结：共 3 个 Python 文件，总行数 2632
```

### 示例 2：生成图片并理解内容

```
用户：生成一张赛博朋克风格的猫咪图，然后告诉我图里有什么

Agent：
  → tool_generate_image: prompt="cyberpunk cat, neon lights, digital art"
  → 等待异步任务完成，图片保存到 temp/
  → tool_view_image: 分析生成的图片
  → 返回：一只橘色猫咪，戴着霓虹护目镜，背景是紫色和青色的城市灯光...
```

### 示例 3：抓取网页并提取信息

```
用户：帮我看看 python.org 首页有什么新闻

Agent：
  → tool_web_scan: url="https://python.org", text_only=true
  → 提取正文，过滤导航和页脚
  → 返回：Python 3.13 发布、PEP 7xx 新提案、PyCon 2026 日期公布...
```

### 示例 4：生成带旁白的视频

```
用户：做一个 10 秒的猫咪科普短视频，要有中文旁白

Agent（视频模式，自动注入 HyperFrames 前导）：
  → 生成 3 张场景图（gpt-image-2）
  → 合成中文旁白 MP3（edge-tts）
  → 编写 HTML 组合（GSAP 时间轴 + 淡入淡出 + data-start 音频同步）
  → ffmpeg 合成 H.264 1920x1080 + AAC
  → 自检：时长 10s ✓ 分辨率 1080p ✓ 音频存在 ✓
  → 输出：cat_video_final.mp4
```

---

## 配置项

CyberCode 采用零配置设计，启动时自动完成所有配置。以下环境变量供高级用户调整：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `CYBERCODE_PORT` | `18600` | Web 服务端口 |
| `CYBERCODE_HOST` | `127.0.0.1` | 监听地址 |

### 自动配置机制

CyberCode 在首次启动时自动完成以下工作，用户无需干预：

- 连接模型网关，获取可用模型列表
- 生成会话令牌（`.auth_token`）
- 选择默认模型（`free/glm-5.2`，零成本）
- 初始化记忆系统和工作目录

用户只需登录 CyberCode 账号（或跳过登录后自行配置模型），系统自动处理其余一切。

---

## 常见问题

**Q：真的免费吗？**

是的。CyberCode 默认使用 `free/glm-5.2` 模型，完全免费。登录 CyberCode 账号后，GPT-5.5、Claude Opus 4.8 等前沿模型也可直接使用，具体额度取决于平台政策。你也可以跳过登录，使用自己的 API Key。

**Q：需要翻墙吗？**

不需要。模型网关在国内可直连，开箱即用。

**Q：支持函数调用吗？**

支持。`free/glm-5.2`、`deepseek-v4-flash`、`glm-5.2` 等模型支持 OpenAI tools 规范的 function calling，流式与非流式均可。`gpt-5.4` 等部分模型不支持 FC，此时 Agent 回退到 XML 工具调用解析。

**Q：视频生成需要什么依赖？**

需要 `ffmpeg`（系统 PATH 中可用）和 `edge-tts`（`pip install edge-tts`）。系统 prompt 内置了 edge-tts 自动安装逻辑，首次使用视频模式时 Agent 会自动检测并安装。

**Q：数据会上传吗？**

不会。CyberCode 跑在你本地，所有文件操作、代码执行、记忆存储都在本地磁盘。只有 LLM 推理请求会发送到模型网关。

---

## 开发

### 本地调试

```bash
# 克隆仓库后直接运行
python python/cybercodewebui.py --port 18600 --host 0.0.0.0

# 自定义 LLM 启动序号
python python/cybercodewebui.py --llm_no 4
```

### 自定义系统 Prompt

编辑 `custom_system_prompt.txt`，内容会热重载到每次对话的系统 prompt 开头。适合注入项目特定的约束或领域知识。

### 自定义技能

在 `skills/` 目录下新建 `.md` 文件，Agent 会在 `/api/skills` 中列出并按需加载。

---

## 免责声明

> **请仔细阅读以下条款，使用本软件即表示你已阅读并同意全部内容。**

- **仅供学习与娱乐**：本工具仅用于学习研究和技术探索，不得用于任何商业用途或违法用途。
- **禁止上传个人数据**：请勿将任何个人隐私数据（包括但不限于身份证号、手机号、银行卡号、真实姓名、住址等）输入到系统中。你的输入内容会通过模型网关发送至第三方大模型服务进行推理。
- **内容请勿转发并立即删除**：系统生成的内容可能包含不准确、不完整或不当的信息。请勿将生成内容转发、发布或传播给他人，并在使用后立即删除。对于生成内容的使用及其后果，由你自行承担全部责任。
- **不提供任何保证**：本软件按"现状"提供，不附带任何明示或暗示的保证。作者不对因使用本软件而产生的任何直接或间接损失承担责任。

---

## 许可证

MIT License — 详见 [LICENSE](LICENSE) 文件。

CyberCode 的 Agent 核心架构源自 [GenericAgent](https://github.com/lsdefine/GenericAgent)（© 2025 lsdefine, MIT），在此致谢。

---

<div align="center">

**CyberCode — 让前沿大模型真正动手干活。**

</div>

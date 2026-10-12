# 🌉 Agent Bridge

> **将你的腾讯 WorkBuddy / CodeBuddy（代码助手）积分，无缝转换为标准 OpenAI Responses / Anthropic Messages / Chat Completions API。**

[![Python Version](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/Framework-FastAPI-009688.svg)](https://fastapi.tiangolo.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![AI Generated](https://img.shields.io/badge/Generated%20by-AI%20(Antigravity)-purple.svg)](#-项目声明)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](https://github.com/)

---

### 🤖 项目声明

> [!NOTE]
> **本项目由 AI（Google DeepMind Antigravity）辅助生成并持续迭代维护。**  
> 包括协议双向转换逻辑、流式事件转换器（SSE）、请求体合规与风控指纹清洗引擎（Anti-Fingerprint Sanitizer）、模型别名热重载机制等均由 AI 协同编写并实测验证。

---

## 📖 简介

你开通了腾讯 **WorkBuddy** 或 **CodeBuddy** 的会员/套餐积分，拥有大量的免费或高配模型额度（GLM-5.2/5.3、DeepSeek-V4、Kimi、混元等），但在日常编码中，你更习惯使用 **Codex CLI**、**Claude Code**、**Claude Desktop 桌面端**，或者 **Cherry Studio / Chatbox** 等外部工具。

**Agent Bridge** 就是为此而生的本机轻量代理网关：
- 将客户端的 **Anthropic Messages 协议**（`/v1/messages`）或 **OpenAI 协议**（`/v1/chat/completions`、`/v1/responses`）实时转换为腾讯后端接口。
- **免手动配置 Token**：自动读取本机已登录的桌面端身份凭证，并在过期时自动刷新。
- **内置风控指纹剥离**：彻底解决上游报错 `400 Illegal API invocation from an unapproved channel`，让 Claude 客户端/Agent 模式稳定可用。
- **模型别名与动态热重载**：支持把 `claude-3-7-sonnet`、`claude-sonnet-4-5` 灵活映射到真实的 `glm-5.3` 或 `deepseek-v4-pro`，配置文件即改即生效。

> **提示**：真正执行推理的是腾讯后端账号对应的模型。本桥负责协议转换、登录态中继与提示词合规，**不会凭空变成官方 Claude / GPT 原版模型**。

---

## 🌟 核心特性

- 🔄 **三协议全兼容**
  - **Anthropic Messages API**：兼容 Claude Code CLI、Claude Desktop 客户端（支持 Agent / 3p 模式）、CC Switch。
  - **OpenAI Responses API**：兼容 Codex CLI（`/v1/responses`）。
  - **OpenAI Chat Completions**：兼容 Cherry Studio、Chatbox、NextChat、Cursor 等常规客户端。
- 🛡️ **智能客户端指纹清洗（Anti-Fingerprinting）**
  - 上游风控对非官方客户端请求（如包含 `x-anthropic-billing-header`、`Claude Agent SDK`、`You are Claude Code...` 等样板词）会触发 `11128` 拦截（`Illegal API invocation from an unapproved channel`）。
  - Agent Bridge 内置智能清洗引擎，自动剥离官方指纹与计费标记，完整保留用户实质指令与上下文。
- ⚡ **生态端点完备**
  - 内置客户端开机探活接口（`HEAD /api/hello`）。
  - 内置 token 估算端点（`POST /v1/messages/count_tokens`），杜绝客户端预检报 404。
- 🔥 **配置热重载（Hot Reload）**
  - 修改 `config.toml` 后**无需重启服务**，下一次请求自动生效最新的模型别名映射。
- 🔑 **自动化凭据生命周期**
  - 自动读取桌面端本地凭据（Windows / macOS / Linux）。
  - Token 过期自动调用官方接口 refresh，无需频繁重新登录。
- 🎁 **日常维护命令**
  - 支持一键查询剩余额度（`credits`）与每日自动签到领积分（`checkin`）。

---

## 🏗️ 工作原理

```
┌─────────────────────────────────────────────────────────────┐
│ 客户端层                                                    │
│  - Codex CLI          (POST /v1/responses)                  │
│  - Claude Desktop/Code (POST /v1/messages)                  │
│  - Cherry Studio / 其他 (POST /v1/chat/completions)          │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 本地 Agent Bridge (http://127.0.0.1:8787)                   │
│  ├─ 指纹剥离清洗器 (去除 x-anthropic-billing-header/SDK特征) │
│  ├─ 协议转换与参数规范 (Anthropic / Responses ↔ Chat)      │
│  ├─ 模型别名路由 (claude-sonnet-4-5 → glm-5.3)              │
│  └─ 本地凭证存储 (读取桌面端 auth 或 ~/.agent-bridge)        │
└──────────────────────────────┬──────────────────────────────┘
                               │ POST /v2/chat/completions
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 腾讯云上游服务                                              │
│  copilot.tencent.com / codebuddy.ai / workbuddy.ai          │
│  (扣除你的 CodeBuddy / WorkBuddy 积分套餐)                   │
└─────────────────────────────────────────────────────────────┘
```

---

## 🚀 快速上手

### 环境准备
- **操作系统**：Windows / macOS / Linux
- **Python**：Python 3.10+
- **前置依赖**：本机已登录 **WorkBuddy 或 CodeBuddy 桌面端**（推荐），或通过命令行浏览器授权。

---

### 方法 A：Windows 用户一键启动（推荐）

项目自带 PowerShell 自动化启动脚本，自动检测 Python、创建虚拟环境并安装依赖：

```powershell
# 1. 克隆或下载本项目
git clone https://github.com/your-username/agent-bridge.git
cd agent-bridge

# 2. 运行一键脚本
.\run.ps1
```

---

### 方法 B：手动安装与启动

```bash
# 1. 克隆仓库
git clone https://github.com/your-username/agent-bridge.git
cd agent-bridge

# 2. 创建并激活虚拟环境
# Windows (PowerShell):
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Linux / macOS:
python3 -m venv .venv
source .venv/bin/activate

# 3. 安装依赖（可编辑模式）
pip install -e .

# 4. 启动代理桥服务
python -m agent_bridge serve
```

> **注意**：如果本机没有安装桌面端，或者未登录，先运行以下命令在浏览器中扫码/授权登录：
> ```bash
> python -m agent_bridge login
> ```
> 国际版 CodeBuddy 请加上 `--network global`：
> ```bash
> python -m agent_bridge --network global login
> ```

终端看到如下输出即表示启动成功：
```text
INFO:     Uvicorn running on http://127.0.0.1:8787 (Press CTRL+C to quit)
==== Agent Bridge 运行中 ====
节点     : https://copilot.tencent.com  (cn)
地址     : http://127.0.0.1:8787
凭据状态 : 有效
```

---

### 🔍 健康自检与额度查询

服务启动后，另开一个终端窗口进行验证：

```powershell
# 1. 检查桥健康状态
curl http://127.0.0.1:8787/health

# 2. 查看可用模型列表
curl http://127.0.0.1:8787/v1/models -H "Authorization: Bearer sk-local-bridge"

# 3. 查询当前账号积分余额
python -m agent_bridge credits

# 4. 每日签到领取积分
python -m agent_bridge checkin
```

---

## 💻 客户端接入配置指南

### 1. 接入 Claude Code (CLI)

在启动 Claude Code 的终端中设置环境变量：

**Windows (PowerShell)**：
```powershell
$env:ANTHROPIC_BASE_URL="http://127.0.0.1:8787"
$env:ANTHROPIC_API_KEY="sk-local-bridge"
$env:ANTHROPIC_MODEL="glm-5.2"
claude
```

**macOS / Linux (Bash/Zsh)**：
```bash
export ANTHROPIC_BASE_URL="http://127.0.0.1:8787"
export ANTHROPIC_API_KEY="sk-local-bridge"
export ANTHROPIC_MODEL="glm-5.2"
claude
```

> 也可以将上述变量持久化写入项目提供的 [examples/claude.env.example](examples/claude.env.example)。

---

### 2. 接入 Claude Desktop (官方桌面端) & CC Switch

如果你使用 **CC Switch** 管理 Claude Desktop 配置：

```json
{
  "WorkBuddy": {
    "base_url": "http://127.0.0.1:8787",
    "api_key": "sk-local-bridge",
    "model": "glm-5.2"
  }
}
```

> **关于桌面端的模型选择**：  
> 官方桌面端界面上的模型下拉菜单通常是固定的（例如 `Claude 3.7 Sonnet`、`Claude 3.5 Sonnet` 等）。你**直接在界面上选择 Sonnet 即可**，无需在客户端寻找改名入口。代理桥在收到请求时，会自动通过 `config.toml` 的别名映射为指定的腾讯模型。

---

### 3. 接入 Codex CLI

将 [examples/codex.config.toml](examples/codex.config.toml) 内容合并进你的 Codex 配置文件（Windows: `%USERPROFILE%\.codex\config.toml`，Linux/macOS: `~/.codex/config.toml`）：

```toml
[model_providers.workbuddy]
name = "WorkBuddy via Agent Bridge"
base_url = "http://127.0.0.1:8787/v1"
wire_api = "responses"
env_key = "BRIDGE_API_KEY"

[profiles.workbuddy]
model = "glm-5.2"
model_provider = "workbuddy"
```

运行 Codex：
```powershell
$env:BRIDGE_API_KEY="sk-local-bridge"
codex --profile workbuddy "请分析当前仓库的代码架构"
```

---

### 4. 接入普通 OpenAI 客户端（Cherry Studio / Chatbox / NextChat / Cursor 等）

在任何支持自定义 OpenAI 兼容接口的软件中填入：
- **API Base URL**：`http://127.0.0.1:8787/v1`
- **API Key**：`sk-local-bridge`（需与 `config.toml` 一致，本地防误触鉴权）
- **模型名称**：直接填入腾讯真实模型名，如 `glm-5.2`、`glm-5.3`、`deepseek-v4-pro` 或 `auto`

---

## ⚙️ 配置文件说明 (`config.toml`)

根目录下的 `config.toml` 是代理桥的核心配置文件，支持**热重载**（改动即时生效）：

```toml
# 服务监听地址与端口
host = "127.0.0.1"
port = 8787

# 本地客户端鉴权 Key（与客户端中填写的 API Key 对应）
api_key = "sk-local-bridge"

# 节点选择：cn（国内 CodeBuddy/WorkBuddy）、global（国际 CodeBuddy）、workbuddy（国际 WorkBuddy）
network = "cn"

# 客户端未传模型时的默认回退模型
default_model = "glm-5.2"

# 提示词脱敏与安全压缩（压缩过长系统提示，减少上游敏感词审核误拦）
desensitize = true

# 客户端选择的模型名 → 腾讯后端真实模型的别名映射
[aliases]
"claude"            = "glm-5.2"
"claude-sonnet-4"   = "glm-5.2"
"claude-sonnet-4-5" = "glm-5.3"
"claude-3-5-sonnet" = "glm-5.2"
"claude-3-7-sonnet" = "glm-5.2"
"claude-opus-4"     = "deepseek-v4-pro"
"gpt-5"             = "glm-5.2"
"gpt-5-codex"       = "glm-5.2"
"codex"             = "glm-5.2"
```

### 常用真实后端模型参考

| 腾讯真实模型 ID | 模型特点与适用场景 |
|---|---|
| `glm-5.2` | 默认推荐，编程能力强，响应稳定迅速 |
| `glm-5.3` / `glm-5.3-flash` | GLM 5.3 系列最新代码与推理模型 |
| `deepseek-v4-pro` | 深度推理、长逻辑链、复杂架构设计 |
| `deepseek-v4-flash` | 极速响应，适合轻量级问答和代码补全 |
| `kimi-k2.7` / `kimi-k3` | 超长上下文处理、中文语义与文档理解 |
| `auto` | 腾讯后端根据提示词自动路由最合适模型 |

---

## ❓ 常见问题排查 (FAQ)

### Q1: 客户端报错 `API Error: 400 Illegal API invocation from an unapproved channel`？
- **原因**：腾讯上游网关对未经许可的客户端做通道风控，当检测到带有官方特征（如 `x-anthropic-billing-header`、`Claude Agent SDK`、`You are Claude Code...`）时会拦截。
- **解决**：请确认使用最新版本的 Agent Bridge。本项目已内置专门的 `strip_client_fingerprints` 引擎，会自动在转发前剥离上述特征并保留用户原始意图。

### Q2: 终端运行 `python` 报错 `无法将“python”项识别为 cmdlet、函数...`？
- **原因**：Windows 系统的全局环境变量 `PATH` 中没有注册 Python。
- **解决**：如果你在项目目录内，直接执行 `.\run.ps1` 即可（脚本会自动调用 `.venv` 虚拟环境内的 Python），或者在 PowerShell 中运行 `.\.venv\Scripts\Activate.ps1` 激活虚拟环境。

### Q3: 报错 `401 Unauthorized` / `invalid api key`？
- **本地 401**：客户端配置的 API Key 与 `config.toml` 中的 `api_key` 不匹配。
- **上游 401**：说明腾讯登录凭证已失效。请打开 WorkBuddy / CodeBuddy 桌面端重新登录，或者执行 `python -m agent_bridge login` 重新授权。

### Q4: Claude Code / Claude Desktop 启动时报 404？
- **解决**：Claude 客户端启动时会探测 `HEAD /api/hello` 与 `POST /v1/messages/count_tokens`。本项目已完整实现上述端点，请确保服务已正常启动并监听 `8787` 端口。

---

## 📄 免责声明 (Disclaimer)

1. 本项目仅供个人学习、技术研究与合法拥有的个人订阅额度自用。
2. 本项目与腾讯（Tencent）、WorkBuddy、CodeBuddy、Anthropic、OpenAI 无官方关联，不提供任何商业 API 代理或破解服务。
3. 请严格遵守各平台及产品的使用协议与服务条款，严禁用于任何商业牟利、黑灰产或滥用行为，由此产生的一切后果由使用者自行承担。

---

## 📜 许可证 (License)

本项目基于 [MIT License](LICENSE) 开源。欢迎提交 Issue 与 Pull Request！

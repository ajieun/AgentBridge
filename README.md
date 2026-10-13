# 🌉 Agent Bridge

> **将你的腾讯 WorkBuddy / CodeBuddy（代码助手）积分，无缝转换为标准 OpenAI Responses / Anthropic Messages / Chat Completions API。**

[![Python Version](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/Framework-FastAPI-009688.svg)](https://fastapi.tiangolo.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![AI Generated](<https://img.shields.io/badge/Generated%20by-AI%20(Antigravity)-purple.svg>)](#-项目声明)
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
- **全模型官方映射与动态热重载**：将 WorkBuddy 8 款主流模型（GLM-5.3/5.2/5.1、DeepSeek-V4/Flash、Kimi-K3、MiniMax-M3）无缝映射到 Claude 官方标准模型（Sonnet 3.7/3.5、Opus 3、Haiku 3.5/3、Claude 2.1 等），突破官方桌面端硬编码模型过滤限制，配置文件改动即时生效。

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
│  ├─ 模型别名路由 (claude-3-7-sonnet → glm-5.3)              │
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
git clone https://github.com/ajieun/agent-bridge.git
cd agent-bridge

# 2. 运行一键脚本
.\run.ps1
```

---

### 方法 B：手动安装与启动

```bash
# 1. 克隆仓库
git clone https://github.com/ajieun/agent-bridge.git
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
>
> ```bash
> python -m agent_bridge login
> ```
>
> 国际版 CodeBuddy 请加上 `--network global`：
>
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

# 2. 查看可用模型列表（优先展示已映射的 Claude 官方模型及腾讯原生模型）
curl http://127.0.0.1:8787/v1/models -H "Authorization: Bearer sk-local-bridge"

# 3. 发送对话测试（测试 Claude 3.7 Sonnet 映射到 GLM-5.3 连通性）
curl http://127.0.0.1:8787/v1/messages `
  -H "Content-Type: application/json" `
  -H "x-api-key: sk-local-bridge" `
  -H "anthropic-version: 2023-06-01" `
  -d '{"model":"claude-3-7-sonnet","messages":[{"role":"user","content":"你好"}],"max_tokens":100}'

# 4. 查询当前账号积分余额
python -m agent_bridge credits

# 5. 每日签到领取积分
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

接入 Claude Desktop 桌面端有两种常见方式：

#### 方式 A：通过 CC Switch 管理配置（推荐）

如果你使用 **CC Switch** 管理 Claude 桌面端供应商：

```json
{
  "WorkBuddy": {
    "base_url": "http://127.0.0.1:8787",
    "api_key": "sk-local-bridge",
    "model": "glm-5.2"
  }
}
```

#### 方式 B：通过环境变量直接启动官方客户端

无需借助第三方切换工具，只需在启动 Claude Desktop 前注入网关地址与鉴权 Key 即可：

**Windows (PowerShell)**：
```powershell
$env:ANTHROPIC_BASE_URL="http://127.0.0.1:8787"
$env:ANTHROPIC_API_KEY="sk-local-bridge"
Start-Process "$env:LOCALAPPDATA\Programs\Claude\Claude.exe"
```

**macOS (终端)**：
```bash
ANTHROPIC_BASE_URL="http://127.0.0.1:8787" ANTHROPIC_API_KEY="sk-local-bridge" open -a "Claude"
```

---

#### 🎯 Claude Desktop 原生模型选择指南

> **核心机制**：  
> Claude Desktop 原生客户端在前端代码中**硬编码了 Anthropic 官方模型白名单**（如 Sonnet、Opus、Haiku 等），任何非官方格式的自定义模型名均会被原生界面过滤，无法直接出现在下拉菜单中。  
> 
> 为彻底解决该问题，Agent Bridge 已在配置层与解析层将腾讯 WorkBuddy **全部 8 款主流模型精准映射至官方标准模型 ID**。你在 Claude Desktop 下拉菜单中选择对应的官方模型，即可无缝驱动相应的腾讯模型：

| Claude Desktop 界面选项 | 官方模型 ID (`config.toml` 别名) | 实际调用的腾讯模型 | 特性与适用场景 |
|---|---|---|---|
| **Claude 3.7 Sonnet** | `claude-3-7-sonnet-20250219` / `claude-3-7-sonnet` | `glm-5.3` | 智谱旗舰代码模型，复杂逻辑重构与 Agent 任务 |
| **Claude 3.5 Sonnet** | `claude-3-5-sonnet-20241022` / `claude-3-5-sonnet` | `glm-5.2` | 默认主力模型（夜间折扣），全能开发首选 |
| **Claude 3.5 Sonnet (旧版)** | `claude-3-5-sonnet-20240620` | `glm-5.1` | 稳定版本代码生成与常规问答 |
| **Claude 3 Opus** | `claude-3-opus-20240229` / `claude-3-opus` | `deepseek-v4-pro` | 深度思维链长推理、复杂架构（建议错峰使用） |
| **Claude 3.5 Haiku** | `claude-3-5-haiku-20241022` / `claude-3-5-haiku` | `glm-5.3-flash` | 订阅优先高频轻量模型，极速响应 |
| **Claude 3 Haiku** | `claude-3-haiku-20240307` / `claude-3-haiku` | `deepseek-v4.1-flash` | 原生多模态，x0.11 超低积分消耗，极速补全 |
| **Claude 2.1** | `claude-2.1` | `kimi-k3` | 200K 超长上下文，海量文档与长文本理解 |
| **Claude 2.0 / Instant** | `claude-2.0` / `claude-instant-1.2` | `minimax-m3` | 均衡多语言与低费率通用模型 |

> 💡 **提示**：如果你想调整映射关系（例如希望在桌面端选 `Claude 3.7 Sonnet` 时调用 `DeepSeek-V4-Pro`），只需编辑 `config.toml` 中 `[aliases]` 对应行，**保存即生效，无需重启代理服务**！

---

### 3. 接入 Codex / ChatGPT 桌面客户端与 Codex CLI

OpenAI Codex 客户端（包含 **Codex Desktop 桌面客户端 / ChatGPT Windows 客户端** 以及 **Codex CLI 命令行**）基于 OpenAI 最新 **Responses API**（`/v1/responses`）协议进行通信。Agent Bridge 已经完整实现 Responses 协议双向转换、流式事件适配、官方模型映射、探活路由（HEAD 探测）以及指纹清洗。

---

#### 方案 A：Codex Desktop 桌面客户端（ChatGPT.exe 图形界面）

如果你使用的是 **ChatGPT / Codex Windows 桌面客户端**（`ChatGPT.exe` / Microsoft Store 应用），请按以下步骤配置：

##### 1. 为什么会出现 401 报错且没有模型列表？
> ⚠️ **常见报错**：
> `unexpected status 401 Unauthorized: Incorrect API key provided: sk-local***idge. You can find your API key at https://platform.openai.com/account/api-keys., url: https://api.openai.com/v1/responses`
> 
> **原因分析**：
> 1. 桌面客户端读取了 `auth.json` 中的 `OPENAI_API_KEY: "sk-local-bridge"` 本地 Key。
> 2. 但由于 `config.toml` 缺少全局顶层的 `openai_base_url`（或者把 `model_provider` 误写在 `[projects]` 内部被系统忽略），桌面客户端**默认将请求发往了 OpenAI 官方服务器**（`api.openai.com`）。
> 3. 官方服务器校验本地虚拟 Key 失败返回 401，导致客户端无法鉴权，下拉菜单无法加载模型列表。

##### 2. 检查并配置 `auth.json`
确保 `%USERPROFILE%\.codex\auth.json`（即 `C:\Users\<用户名>\.codex\auth.json`）内容如下：
```json
{
  "auth_mode": "apikey",
  "OPENAI_API_KEY": "sk-local-bridge"
}
```

##### 3. 配置 `config.toml`（必须写在最顶层！）
打开 `%USERPROFILE%\.codex\config.toml`，将以下内容粘贴在**文件的最顶层（任何 `[...]` 表格节之前）**：
```toml
# ==========================================
# Agent Bridge 本地转发配置（Codex Desktop 桌面客户端生效）
# ==========================================
openai_base_url = "http://127.0.0.1:8787/v1"
model = "gpt-5.5"
model_reasoning_effort = "low"
```
> 💡 **重要提醒**：千万不要将 `openai_base_url` 或 `model` 写在 `[projects.'...']` 下方，否则会被 TOML 解析器当做项目内部属性而直接被 Codex 忽略！

##### 4. 设置 Windows 用户环境变量（推荐，全局生效）
在 PowerShell 中运行以下命令，将环境变量持久化写入当前用户配置（只需执行一次）：
```powershell
[Environment]::SetEnvironmentVariable("OPENAI_BASE_URL", "http://127.0.0.1:8787/v1", "User")
[Environment]::SetEnvironmentVariable("OPENAI_API_KEY", "sk-local-bridge", "User")
[Environment]::SetEnvironmentVariable("BRIDGE_API_KEY", "sk-local-bridge", "User")
```

##### 5. 彻底重启桌面客户端
Windows 桌面版 ChatGPT 会在后台常驻进程。修改配置后，请在 PowerShell 中执行以下命令彻底关闭后台残留进程，然后重新打开客户端即可：
```powershell
Stop-Process -Name ChatGPT, codex -Force -ErrorAction SilentlyContinue
```
重新打开客户端后，即可看到模型列表正常加载，且所有对话自动通过本地 Agent Bridge 驱动！

---

#### 方案 B：Codex CLI (终端命令行客户端)

如果你在终端中使用 `codex` 命令行工具：

##### 1. 配置文件路径
- **Windows**：`%USERPROFILE%\.codex\config.toml`
- **Linux / macOS**：`~/.codex/config.toml`

##### 2. 全局配置推荐（直接设为默认供应商）
将以下内容写入 `%USERPROFILE%\.codex\config.toml`（需确保位于顶层或独立的 section）：
```toml
# 直接设为全局默认模型与供应商（每次执行 codex 默认生效）
model = "glm-5.2"
model_provider = "workbuddy"

# 定义 Agent Bridge 供应商
[model_providers.workbuddy]
name = "WorkBuddy via Agent Bridge"
base_url = "http://127.0.0.1:8787/v1"   # 注意必须包含 /v1 后缀
wire_api = "responses"                  # 必须指定为 responses 协议
env_key = "BRIDGE_API_KEY"              # 读取环境变量作为鉴权 Key
```

配置后，在终端中直接运行 `codex` 即可自动走本地桥！

---

#### 3. 进阶：多模型 Profile 切换（Profiles v2 规范）

> ⚠️ **注意**：新版 Codex (v0.162+) 采用了 **Profiles v2** 规范，不再支持在 `config.toml` 内部编写 `[profiles.xxx]` 表，而是要求将每个 profile 保存为独立的配置文件：`%USERPROFILE%\.codex\<profile名称>.config.toml`。

你可以在 `%USERPROFILE%\.codex\` 目录下创建以下独立 profile 文件：

1. **`workbuddy.config.toml`**（主力开发模型）
   ```toml
   model = "glm-5.2"
   model_provider = "workbuddy"
   ```
2. **`workbuddy-glm53.config.toml`**（智谱旗舰代码重构）
   ```toml
   model = "glm-5.3"
   model_provider = "workbuddy"
   ```
3. **`workbuddy-opus.config.toml`**（DeepSeek-V4-Pro 深度长思维链）
   ```toml
   model = "deepseek-v4-pro"
   model_provider = "workbuddy"
   ```
4. **`workbuddy-kimi.config.toml`**（Kimi-K3 200K 超长上下文与整库代码分析）
   ```toml
   model = "kimi-k3"
   model_provider = "workbuddy"
   ```
5. **`workbuddy-flash.config.toml`**（DeepSeek-V4.1-Flash 超低倍率极速响应）
   ```toml
   model = "deepseek-v4.1-flash"
   model_provider = "workbuddy"
   ```

#### 4. 设置环境变量 (API Key)

Codex 通过 `env_key = "BRIDGE_API_KEY"` 读取鉴权密匙，必须配置此环境变量（值与 `config.toml` 中的 `api_key` 一致，默认 `sk-local-bridge`）：

**Windows (PowerShell)**：
```powershell
# 临时会话生效：
$env:BRIDGE_API_KEY="sk-local-bridge"

# 或持久化到系统当前用户环境变量（推荐，只需执行一次）：
[Environment]::SetEnvironmentVariable("BRIDGE_API_KEY", "sk-local-bridge", "User")
```

**macOS / Linux (Bash/Zsh)**：
```bash
# 临时会话生效：
export BRIDGE_API_KEY="sk-local-bridge"

# 或持久化写入 shell 配置：
echo 'export BRIDGE_API_KEY="sk-local-bridge"' >> ~/.zshrc  # 或 ~/.bashrc
```

#### 5. 常用运行命令示例

```powershell
# 1. 默认直接运行（若已配置全局默认）
codex "请分析当前仓库的目录架构"

# 2. 进入交互式对话模式（REPL）
codex

# 3. 指定独立 Profile 执行深度推理
codex --profile workbuddy-opus "请设计一个高性能高并发缓存方案"

# 4. 指定独立 Profile 分析整库代码
codex --profile workbuddy-kimi "全面扫描仓库中的潜在问题"

# 5. 临时通过 -m 参数覆盖模型
codex -m glm-5.3 "请帮我为当前文件编写单元测试"
```

> 💡 **配置避坑要点**：
> 1. `wire_api` 必须精确配置为 `"responses"`（对应 Agent Bridge 的 Responses 协议网关）。
> 2. `base_url` 必须写为 `http://127.0.0.1:8787/v1`（包含 `/v1`）。
> 3. `env_key` 环境变量名称必须与设置的变量名一致（如 `BRIDGE_API_KEY`）。
> 4. 新版 Codex 报 `Error loading config.toml: --profile ... cannot be used while config.toml contains legacy [profiles....]` 时，说明你在主配置文件中写了旧版 profile 表，请将其迁移为独立的 `<name>.config.toml`。

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
# 1. 对应 Claude Desktop 官方硬编码模型名（将 8 款 WorkBuddy 模型映射到官方标准 ID）
# 官方最新旗舰：Claude 3.7 Sonnet / Sonnet 4.5 → GLM-5.3（旗舰代码重构）
"claude-3-7-sonnet-20250219"    = "glm-5.3"
"claude-3-7-sonnet"             = "glm-5.3"
"claude-sonnet-4-5"             = "glm-5.3"
"claude-sonnet-4"               = "glm-5.3"

# 官方主力模型：Claude 3.5 Sonnet → GLM-5.2（推荐主力，夜间折扣）
"claude-3-5-sonnet-20241022"    = "glm-5.2"
"claude-3-5-sonnet"             = "glm-5.2"
"claude"                        = "glm-5.2"

# 官方次级主力：Claude 3.5 Sonnet (旧版) → GLM-5.1
"claude-3-5-sonnet-20240620"    = "glm-5.1"

# 官方最强推理：Claude 3 Opus / Opus 4 → DeepSeek-V4-Pro（深度推理）
"claude-3-opus-20240229"        = "deepseek-v4-pro"
"claude-3-opus"                 = "deepseek-v4-pro"
"claude-opus-4"                 = "deepseek-v4-pro"

# 官方极速模型：Claude 3.5 Haiku → GLM-5.3-Flash（订阅优先，极速响应）
"claude-3-5-haiku-20241022"     = "glm-5.3-flash"
"claude-3-5-haiku"              = "glm-5.3-flash"
"claude-haiku"                  = "glm-5.3-flash"

# 官方闪电模型：Claude 3 Haiku → DeepSeek-V4.1-Flash（极低倍率，超轻量）
"claude-3-haiku-20240307"       = "deepseek-v4.1-flash"
"claude-3-haiku"                = "deepseek-v4.1-flash"

# 官方超长上下文：Claude 2.1 (200K) → Kimi-K3（长文本与深度文档）
"claude-2.1"                    = "kimi-k3"

# 官方通用多语言：Claude 2.0 / Instant → MiniMax-M3（低消耗综合模型）
"claude-2.0"                    = "minimax-m3"
"claude-2"                      = "minimax-m3"
"claude-instant-1.2"            = "minimax-m3"

# 2. 直观前缀别名（部分第三方客户端支持直接显示）
"claude-deepseek-v4-pro"     = "deepseek-v4-pro"
"claude-deepseek-v4.1-flash" = "deepseek-v4.1-flash"
"claude-deepseek-flash"      = "deepseek-v4.1-flash"
"claude-glm-5.3"             = "glm-5.3"
"claude-glm-5.3-flash"       = "glm-5.3-flash"
"claude-glm-5.2"             = "glm-5.2"
"claude-glm-5.1"             = "glm-5.1"
"claude-kimi-k3"             = "kimi-k3"
"claude-minimax-m3"          = "minimax-m3"

# 3. OpenAI / Codex 系列通用映射
"gpt-5"       = "glm-5.2"
"gpt-5-codex" = "glm-5.2"
"gpt-4.1"     = "glm-5.2"
"codex"       = "glm-5.2"
"o3"          = "deepseek-v4-pro"

# 4. DeepSeek 系列 (Deepseek-V4.1-Flash / Deepseek-V4-Pro)
"Deepseek-V4.1-Flash" = "deepseek-v4.1-flash"
"deepseek-v4.1-flash" = "deepseek-v4.1-flash"
"deepseek-flash"      = "deepseek-v4.1-flash"
"Deepseek-V4-Pro"     = "deepseek-v4-pro"
"deepseek-v4-pro"     = "deepseek-v4-pro"
"deepseek"            = "deepseek-v4-pro"

# 5. 智谱 GLM 系列 (GLM-5.3 / GLM-5.3-Flash / GLM-5.2 / GLM-5.1)
"GLM-5.3"       = "glm-5.3"
"glm-5.3"       = "glm-5.3"
"GLM-5.3-Flash" = "glm-5.3-flash"
"glm-5.3-flash" = "glm-5.3-flash"
"GLM-5.2"       = "glm-5.2"
"glm-5.2"       = "glm-5.2"
"GLM-5.1"       = "glm-5.1"
"glm-5.1"       = "glm-5.1"

# 6. 月之暗面 Kimi 系列 (Kimi-K3)
"Kimi-K3" = "kimi-k3"
"kimi-k3" = "kimi-k3"
"kimi"    = "kimi-k3"

# 7. MiniMax 系列 (MiniMax-M3)
"MiniMax-M3" = "minimax-m3"
"minimax-m3" = "minimax-m3"
"minimax"    = "minimax-m3"
```

### 常用真实后端模型参考

| 腾讯真实模型 ID | Claude Desktop 对应官方模型 | 直通展示名 / 别名 | 积分倍率与特点 | 适用场景 |
|---|---|---|---|---|
| `glm-5.3` | **Claude 3.7 Sonnet** / `claude-sonnet-4-5` | `GLM-5.3` / `claude-glm-5.3` | x0.79 credits，智谱旗舰 | 高质量代码生成、复杂重构与 Agent 任务 |
| `glm-5.2` | **Claude 3.5 Sonnet** (`20241022`) | `GLM-5.2` / `claude-glm-5.2` | x0.79 credits，夜间折扣 | 默认主力模型，代码能力全面扎实 |
| `glm-5.1` | **Claude 3.5 Sonnet (旧版)** (`20240620`) | `GLM-5.1` / `claude-glm-5.1` | x0.79 credits | 稳定版本代码与常规问答 |
| `deepseek-v4-pro` | **Claude 3 Opus** / `claude-opus-4` | `Deepseek-V4-Pro` / `deepseek` / `o3` | x0.51 credits，错峰使用推荐 | 深度思考与长推理、复杂架构设计 |
| `glm-5.3-flash` | **Claude 3.5 Haiku** / `claude-haiku` | `GLM-5.3-Flash` / `claude-glm-5.3-flash` | x0.06 credits，订阅优先 | 低消耗极速模型，适合高频交互与测试 |
| `deepseek-v4.1-flash` | **Claude 3 Haiku** (`20240307`) | `Deepseek-V4.1-Flash` / `deepseek-flash` | x0.11 credits，原生多模态 | 极速响应、轻量补全、性价比极高 |
| `kimi-k3` | **Claude 2.1** (200K) | `Kimi-K3` / `kimi` | x1.62 credits | 超长上下文理解、海量文档与复杂语境 |
| `minimax-m3` | **Claude 2.0 / Instant** | `MiniMax-M3` / `minimax` | x0.25 credits | 均衡代码与文本理解，低倍率低成本 |
| `auto` | 腾讯后端自动路由 | `auto` | 腾讯动态路由 | 由上游后端根据上下文自动调度模型 |

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

### Q5: Claude Desktop 桌面端下拉列表找不到自定义模型名称？

- **原因**：Claude Desktop 原生桌面端客户端内部硬编码了 Anthropic 官方模型名称白名单过滤逻辑，非官方格式的模型名称无法在原生下拉菜单中渲染。
- **解决**：无需手动修改客户端。Agent Bridge 已经自动将全部 8 款 WorkBuddy 模型无缝映射到了官方的标准选项（例如选择 `Claude 3.7 Sonnet` 即调用 `GLM-5.3`，选择 `Claude 3 Opus` 即调用 `DeepSeek-V4-Pro`，选择 `Claude 2.1` 即调用 `Kimi-K3` 等）。直接在官方桌面端下拉菜单中选择对应的官方模型即可！

### Q6: 我想更改 Claude Desktop 界面选项与腾讯模型的映射关系？

- **解决**：打开根目录下的 `config.toml`，找到 `[aliases]` 区域，按需修改等号右侧的目标模型 ID 即可。例如将 `"claude-3-7-sonnet" = "glm-5.3"` 改为 `"claude-3-7-sonnet" = "deepseek-v4-pro"`。修改后**无需重启服务**，Agent Bridge 内置热重载机制，保存后下一次请求立即生效！

### Q7: Windows 执行 `.\run.ps1` 报错 `因为在此系统上禁止运行脚本`？

- **原因**：Windows PowerShell 默认的执行策略（Execution Policy）限制了非签名脚本运行。
- **解决**：以管理员身份或当前用户在 PowerShell 中运行以下命令放行：
  ```powershell
  Set-ExecutionPolicy -Scope CurrentUser RemoteSigned -Force
  ```
  或者通过命令行临时绕过策略启动：
  ```powershell
  powershell -ExecutionPolicy Bypass -File .\run.ps1
  ```

### Q8: 上游报错 `400 model [...] service info not found`？

- **原因**：腾讯云后端接口对模型 ID 区分大小写，且要求全部为小写（如 `glm-5.3`、`deepseek-v4-pro`），若上游收到首字母大写的 `GLM-5.3` 会报找不到服务。
- **解决**：Agent Bridge 已在配置解析层与网关层内置大小写自动归一化处理。如果自行在 `config.toml` 中配置映射，请确保等号右侧的值为小写标准 ID。

---

## 📄 免责声明 (Disclaimer)

1. 本项目仅供个人学习、技术研究与合法拥有的个人订阅额度自用。
2. 本项目与腾讯（Tencent）、WorkBuddy、CodeBuddy、Anthropic、OpenAI 无官方关联，不提供任何商业 API 代理或破解服务。
3. 请严格遵守各平台及产品的使用协议与服务条款，严禁用于任何商业牟利、黑灰产或滥用行为，由此产生的一切后果由使用者自行承担。

---

## 📜 许可证 (License)

本项目基于 [MIT License](LICENSE) 开源。欢迎提交 Issue 与 Pull Request！

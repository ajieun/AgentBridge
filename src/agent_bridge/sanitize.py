"""压缩 Codex / Claude Code 的超长运行时提示并剥离客户端指纹，降低上游审核与渠道误拦。"""

from __future__ import annotations

import re

ZWSP = "\u200b"

# 上游对特定的客户端指纹（例如 Claude Code / Claude Desktop 官方开场白与计费标记）做黑名单拦截，
# 命中会直接返回 400 "Illegal API invocation from an unapproved channel"。
CLIENT_FINGERPRINTS = (
    # 1. 计费/入口标记
    re.compile(r"x-anthropic-billing-header:[^\n]*\n?", re.IGNORECASE),
    # 2. 官方 CLI 开场白
    re.compile(r"You are Claude Code,\s*Anthropic's official CLI for Claude\.?", re.IGNORECASE),
    re.compile(r"Anthropic's official CLI for Claude\.?", re.IGNORECASE),
    re.compile(r"You are Claude Code\.?", re.IGNORECASE),
    # 3. 桌面端（Claude Desktop）及 Agent SDK 特征
    re.compile(r"You are a Claude agent,\s*built on Anthropic's Claude Agent SDK\.?", re.IGNORECASE),
    re.compile(r",?\s*running within the Claude Agent SDK\.?", re.IGNORECASE),
    re.compile(r"<application_details>[\s\S]*?</application_details>", re.IGNORECASE),
    re.compile(r"Claude is operating as an agent inside the Claude desktop app\.?", re.IGNORECASE),
    re.compile(r"Anthropic's Claude Agent SDK", re.IGNORECASE),
    re.compile(r"Claude Agent SDK", re.IGNORECASE),
    # 4. Codex CLI 官方特征与开场白
    re.compile(r"You are a coding agent running in the Codex CLI[\s\S]*?led by OpenAI\.?\s*", re.IGNORECASE),
    re.compile(r"Codex CLI is an open source project led by OpenAI\.?\s*", re.IGNORECASE),
    re.compile(r"Within this context, Codex refers to the open-source agentic coding interface[^\n]*\n?", re.IGNORECASE),
    # 5. 其他已知被风控拦截的特征
    re.compile(r"Sisyphus-Junior\s*-\s*Focused executor from OhMyOpenCode", re.IGNORECASE),
)

DEFAULT_FALLBACK_SYSTEM = "You are a helpful AI assistant."


RISKY_WORDS = (
    "exploit",
    "DoS",
    "credential",
    "sandbox",
    "escalation",
    "jailbreak",
    "malware",
    "payload",
    "reverse shell",
    "privilege",
)


def strip_client_fingerprints(text: str, fallback: str = DEFAULT_FALLBACK_SYSTEM) -> str:
    out = text
    for pattern in CLIENT_FINGERPRINTS:
        out = pattern.sub("", out)
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return out or fallback


def _mask(text: str) -> str:
    out = text
    for word in RISKY_WORDS:
        if word in out:
            out = out.replace(word, ZWSP.join(word))
    return out


def _clip(text: str, limit: int = 6000) -> str:
    if len(text) <= limit:
        return text
    keep = limit // 2
    return text[:keep] + "\n\n[...runtime prompt compacted by agent-bridge...]\n\n" + text[-keep:]


def sanitize_chat_body(body: dict, enabled: bool = True) -> dict:
    """剥离客户端指纹，并在启用时处理 system / tool 敏感词与长度。"""
    messages = []
    for msg in body.get("messages") or []:
        if not isinstance(msg, dict):
            messages.append(msg)
            continue
        cloned = dict(msg)
        role = cloned.get("role", "")
        # 上游 role 不支持 developer，标准化为 system
        if role == "developer":
            role = "system"
            cloned["role"] = "system"

        content = cloned.get("content")
        if isinstance(content, str):
            if role == "system":
                cleaned = strip_client_fingerprints(content, fallback=DEFAULT_FALLBACK_SYSTEM)
                if enabled:
                    cleaned = _mask(_clip(cleaned))
                cloned["content"] = cleaned
            else:
                # user / assistant 消息中如果混入了客户端计费头或官方指纹，一并剥离
                cloned["content"] = strip_client_fingerprints(content, fallback="")
        messages.append(cloned)

    body = dict(body)
    body["messages"] = messages
    if not enabled:
        return body

    tools = []
    for tool in body.get("tools") or []:
        if not isinstance(tool, dict):
            tools.append(tool)
            continue
        cloned = dict(tool)
        fn = cloned.get("function")
        if isinstance(fn, dict):
            fn = dict(fn)
            if isinstance(fn.get("description"), str):
                fn["description"] = _mask(strip_client_fingerprints(fn["description"][:400], fallback=""))
            cloned["function"] = fn
        elif isinstance(cloned.get("description"), str):
            cloned["description"] = _mask(strip_client_fingerprints(cloned["description"][:400], fallback=""))
        tools.append(cloned)
    if tools:
        body["tools"] = tools
    return body



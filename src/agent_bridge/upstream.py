"""转发到 WorkBuddy / CodeBuddy 官方 Chat Completions 上游。"""

from __future__ import annotations

import json
import os
import time
from typing import Any, AsyncIterator

import httpx

from .auth import CredentialStore
from .config import FALLBACK_MODELS, Settings
from .sanitize import sanitize_chat_body

PASSTHROUGH = {
    "model",
    "messages",
    "tools",
    "tool_choice",
    "temperature",
    "max_tokens",
    "max_completion_tokens",
    "top_p",
    "stream",
    "stream_options",
    "stop",
    "presence_penalty",
    "frequency_penalty",
    "n",
    "response_format",
    "seed",
    "user",
    "reasoning_effort",
    "parallel_tool_calls",
}


def prepare_chat_body(payload: dict, settings: Settings) -> dict:
    body = {k: payload[k] for k in PASSTHROUGH if k in payload}
    body["model"] = settings.resolve_model(payload.get("model"))
    body["stream"] = True
    body.setdefault("stream_options", {"include_usage": True})
    return sanitize_chat_body(body, settings.desensitize)


async def collect_chat(response: httpx.Response) -> dict:
    content: list[str] = []
    reasoning: list[str] = []
    tools: dict[int, dict] = {}
    model = None
    finish = None
    usage = None
    async for line in response.aiter_lines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            break
        try:
            chunk = json.loads(data)
        except json.JSONDecodeError:
            continue
        model = chunk.get("model") or model
        if chunk.get("usage"):
            usage = chunk["usage"]
        for choice in chunk.get("choices") or []:
            if choice.get("finish_reason"):
                finish = choice["finish_reason"]
            delta = choice.get("delta") or {}
            if delta.get("content"):
                content.append(delta["content"])
            if delta.get("reasoning_content"):
                reasoning.append(delta["reasoning_content"])
            for tc in delta.get("tool_calls") or []:
                idx = tc.get("index", 0)
                slot = tools.setdefault(idx, {"id": None, "name": None, "arguments": ""})
                if tc.get("id"):
                    slot["id"] = tc["id"]
                fn = tc.get("function") or {}
                if fn.get("name"):
                    slot["name"] = fn["name"]
                if fn.get("arguments"):
                    slot["arguments"] += fn["arguments"]
    tcs = None
    if tools:
        tcs = [
            {
                "id": v["id"],
                "type": "function",
                "function": {"name": v["name"], "arguments": v["arguments"]},
            }
            for _, v in sorted(tools.items())
        ]
        finish = finish or "tool_calls"
    message: dict[str, Any] = {"role": "assistant", "content": "".join(content) or None}
    if reasoning:
        message["reasoning_content"] = "".join(reasoning)
    if tcs:
        message["tool_calls"] = tcs
    return {
        "id": "chatcmpl-" + os.urandom(12).hex(),
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model or "unknown",
        "choices": [{"index": 0, "message": message, "finish_reason": finish or "stop"}],
        "usage": usage or {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


async def stream_upstream(
    settings: Settings,
    store: CredentialStore,
    body: dict,
) -> AsyncIterator[bytes]:
    url = f"{settings.base_url}/v2/chat/completions"
    headers = store.headers()
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream("POST", url, headers=headers, json=body) as resp:
            if resp.status_code != 200:
                raw = await resp.aread()
                err_text = raw.decode("utf-8", "replace")
                print(f"[STREAM UPSTREAM ERROR {resp.status_code}] {err_text[:1000]}", flush=True)
                print(f"[REQUEST MODEL={body.get('model')}] messages_count={len(body.get('messages', []))}", flush=True)
                for idx, m in enumerate(body.get("messages", [])):
                    role = m.get("role")
                    content = str(m.get("content", ""))[:300]
                    print(f"  msg[{idx}] ({role}): {content}", flush=True)
                yield json.dumps(
                    {
                        "error": {
                            "message": err_text[:800],
                            "type": "upstream_error",
                            "code": resp.status_code,
                        }
                    },
                    ensure_ascii=False,
                ).encode("utf-8")
                return
            async for chunk in resp.aiter_bytes():
                if chunk:
                    yield chunk


async def complete_upstream(
    settings: Settings,
    store: CredentialStore,
    body: dict,
) -> tuple[int, dict | bytes]:
    url = f"{settings.base_url}/v2/chat/completions"
    headers = store.headers()
    async with httpx.AsyncClient(timeout=300.0) as client:
        async with client.stream("POST", url, headers=headers, json=body) as resp:
            if resp.status_code != 200:
                raw = await resp.aread()
                err_text = raw.decode("utf-8", "replace")
                print(f"[COMPLETE UPSTREAM ERROR {resp.status_code}] {err_text[:1000]}", flush=True)
                print(f"[REQUEST MODEL={body.get('model')}] messages_count={len(body.get('messages', []))}", flush=True)
                for idx, m in enumerate(body.get("messages", [])):
                    role = m.get("role")
                    content = str(m.get("content", ""))[:300]
                    print(f"  msg[{idx}] ({role}): {content}", flush=True)
                return resp.status_code, raw
            return 200, await collect_chat(resp)



async def fetch_models(settings: Settings, store: CredentialStore | None) -> list[str]:
    ids: list[str] = []
    if store is not None:
        try:
            headers = store.headers()
            async with httpx.AsyncClient(timeout=20.0) as client:
                for path in ("/v2/models", "/v3/config", "/v2/config"):
                    try:
                        resp = await client.get(f"{settings.base_url}{path}", headers=headers)
                        if resp.status_code != 200:
                            continue
                        payload = resp.json()
                        ids.extend(_extract_model_ids(payload))
                        if ids:
                            break
                    except Exception:
                        continue
        except Exception:
            pass
    seen: set[str] = set()
    out: list[str] = []
    # 优先输出以 claude 开头的别名模型，供 Claude Desktop / Claude Code 客户端优先识别与展示
    claude_models = [k for k in settings.aliases.keys() if k.lower().startswith("claude")]
    for name in claude_models + ids + FALLBACK_MODELS + list(settings.aliases.keys()):
        if name and name not in seen:
            seen.add(name)
            out.append(name)
    return out


def _extract_model_ids(payload: Any) -> list[str]:
    found: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            mid = node.get("id") or node.get("model") or node.get("modelId") or node.get("name")
            if isinstance(mid, str) and any(
                token in mid.lower()
                for token in ("glm", "kimi", "deepseek", "hy", "minimax", "auto", "claude", "gpt")
            ):
                found.append(mid)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, str):
            if any(
                token in node.lower()
                for token in ("glm", "kimi", "deepseek", "hy", "minimax", "auto", "claude", "gpt")
            ):
                found.append(node)

    walk(payload)
    return found

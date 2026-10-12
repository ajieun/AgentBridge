"""Anthropic Messages API（Claude Code）↔ Chat Completions。"""

from __future__ import annotations

import json
import time
from typing import Any

from .ids import rid


def anthropic_to_chat(body: dict) -> dict:
    messages: list[dict] = []
    system = body.get("system")
    sys_text = _system_text(system)
    if sys_text:
        messages.append({"role": "system", "content": sys_text})
    for msg in body.get("messages") or []:
        if isinstance(msg, dict):
            messages.extend(_convert_message(msg))
    chat: dict[str, Any] = {"messages": messages, "stream": True}
    if body.get("model"):
        chat["model"] = body["model"]
    if "max_tokens" in body:
        chat["max_tokens"] = body["max_tokens"]
    if body.get("tools"):
        chat["tools"] = _tools(body["tools"])
    if "tool_choice" in body:
        tc = body["tool_choice"]
        if isinstance(tc, dict):
            t = tc.get("type", "auto")
            if t in ("auto", "none", "any"):
                chat["tool_choice"] = "required" if t == "any" else t
            elif tc.get("name"):
                chat["tool_choice"] = {"type": "function", "function": {"name": tc["name"]}}
        elif isinstance(tc, str):
            chat["tool_choice"] = tc
    for key in ("temperature", "top_p", "stop", "top_k"):
        if key in body:
            chat[key] = body[key]
    return chat


def _system_text(system: Any) -> str:
    if isinstance(system, str):
        return system
    if isinstance(system, list):
        return "\n".join(
            b.get("text", "") for b in system if isinstance(b, dict) and b.get("type") == "text"
        )
    return ""


def _content_to_chat(content: Any) -> Any:
    if isinstance(content, str) or content is None:
        return content or ""
    if not isinstance(content, list):
        return str(content)
    parts: list[dict] = []
    has_image = False
    for block in content:
        if not isinstance(block, dict):
            continue
        kind = block.get("type")
        if kind == "text":
            parts.append({"type": "text", "text": block.get("text", "")})
        elif kind == "image":
            source = block.get("source") or {}
            url = ""
            if source.get("type") == "url":
                url = source.get("url") or ""
            elif source.get("type") == "base64":
                url = f"data:{source.get('media_type')};base64,{source.get('data')}"
            if url:
                parts.append({"type": "image_url", "image_url": {"url": url}})
                has_image = True
    if has_image:
        return parts
    return "".join(p.get("text", "") for p in parts)


def _convert_message(msg: dict) -> list[dict]:
    role = msg.get("role", "")
    content = msg.get("content")
    if isinstance(content, str):
        return [{"role": role, "content": content}]
    if not isinstance(content, list) or not content:
        return []
    if role == "user":
        out: list[dict] = []
        user_blocks: list[dict] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_result":
                out.append(
                    {
                        "role": "tool",
                        "tool_call_id": block.get("tool_use_id", ""),
                        "content": _content_to_chat(block.get("content", "")),
                    }
                )
            else:
                user_blocks.append(block)
        if user_blocks:
            out.append({"role": "user", "content": _content_to_chat(user_blocks)})
        return out
    if role == "assistant":
        texts: list[str] = []
        tool_calls: list[dict] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                texts.append(block.get("text", ""))
            elif block.get("type") == "tool_use":
                tool_calls.append(
                    {
                        "id": block.get("id") or rid("call_"),
                        "type": "function",
                        "function": {
                            "name": block.get("name", ""),
                            "arguments": json.dumps(block.get("input", {}), ensure_ascii=False),
                        },
                    }
                )
        result: dict[str, Any] = {
            "role": "assistant",
            "content": "".join(texts) if texts else None,
        }
        if tool_calls:
            result["tool_calls"] = tool_calls
        return [result]
    return [{"role": role, "content": _content_to_chat(content)}]


def _tools(tools: list) -> list:
    result = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        if "function" in tool:
            result.append(tool)
            continue
        fn: dict[str, Any] = {"name": tool.get("name", "")}
        if "description" in tool:
            fn["description"] = tool["description"]
        if "input_schema" in tool:
            fn["parameters"] = tool["input_schema"]
        elif "parameters" in tool:
            fn["parameters"] = tool["parameters"]
        result.append({"type": "function", "function": fn})
    return result


class AnthropicStreamConverter:
    def __init__(self, model: str = "unknown"):
        self.msg_id = rid("msg_")
        self.model = model
        self.created_at = int(time.time())
        self._started = False
        self._text = ""
        self._text_open = False
        self._text_idx = 0
        self._tools: dict[int, dict] = {}
        self._next = 0
        self._finish: str | None = None
        self._usage: dict | None = None

    def feed_line(self, line: str) -> str:
        line = line.strip()
        if not line.startswith("data:"):
            return ""
        data = line[5:].strip()
        if data == "[DONE]":
            return ""
        try:
            chunk = json.loads(data)
        except json.JSONDecodeError:
            return ""
        return self._chunk(chunk)

    def finish(self) -> str:
        events: list[str] = []
        if self._text_open:
            events.append(self._evt("content_block_stop", {"index": self._text_idx}))
            self._text_open = False
        for tc in self._tools.values():
            if tc.get("open"):
                events.append(self._evt("content_block_stop", {"index": tc["block_idx"]}))
                tc["open"] = False
        stop_map = {"stop": "end_turn", "tool_calls": "tool_use", "length": "max_tokens"}
        stop_reason = stop_map.get(self._finish or "stop", "end_turn")
        usage = None
        if self._usage:
            usage = {
                "input_tokens": self._usage.get("prompt_tokens", 0),
                "output_tokens": self._usage.get("completion_tokens", 0),
            }
        events.append(
            self._evt(
                "message_delta",
                {"delta": {"stop_reason": stop_reason, "stop_sequence": None}, "usage": usage},
            )
        )
        events.append(self._evt("message_stop", {}))
        return "".join(events)

    def error(self, message: str, code: Any) -> str:
        """Format an upstream error as an Anthropic SSE error event."""
        err_data = {
            "type": "error",
            "error": {"type": "api_error", "message": message},
        }
        return f"event: error\ndata: {json.dumps(err_data, ensure_ascii=False)}\n\n"

    def nonstream(self) -> dict:
        stop_map = {"stop": "end_turn", "tool_calls": "tool_use", "length": "max_tokens"}
        blocks: list[dict] = []
        if self._text:
            blocks.append({"type": "text", "text": self._text})
        for _, tc in sorted(self._tools.items()):
            try:
                parsed = json.loads(tc["args"] or "{}")
            except json.JSONDecodeError:
                parsed = tc["args"]
            blocks.append(
                {"type": "tool_use", "id": tc["id"], "name": tc["name"], "input": parsed}
            )
        resp: dict[str, Any] = {
            "id": self.msg_id,
            "type": "message",
            "role": "assistant",
            "content": blocks,
            "model": self.model,
            "stop_reason": stop_map.get(self._finish or "stop", "end_turn"),
            "stop_sequence": None,
        }
        if self._usage:
            resp["usage"] = {
                "input_tokens": self._usage.get("prompt_tokens", 0),
                "output_tokens": self._usage.get("completion_tokens", 0),
            }
        return resp

    def _chunk(self, chunk: dict) -> str:
        events: list[str] = []
        if chunk.get("model"):
            self.model = chunk["model"]
        if not self._started:
            events.append(
                self._evt(
                    "message_start",
                    {
                        "message": {
                            "id": self.msg_id,
                            "type": "message",
                            "role": "assistant",
                            "content": [],
                            "model": self.model,
                            "usage": {"input_tokens": 0, "output_tokens": 0},
                        }
                    },
                )
            )
            self._started = True
        if chunk.get("usage"):
            self._usage = chunk["usage"]
        for choice in chunk.get("choices") or []:
            delta = choice.get("delta") or {}
            content = delta.get("content")
            if content:
                self._text += content
                if not self._text_open:
                    self._text_idx = self._next
                    self._next += 1
                    events.append(
                        self._evt(
                            "content_block_start",
                            {
                                "index": self._text_idx,
                                "content_block": {"type": "text", "text": ""},
                            },
                        )
                    )
                    self._text_open = True
                events.append(
                    self._evt(
                        "content_block_delta",
                        {
                            "index": self._text_idx,
                            "delta": {"type": "text_delta", "text": content},
                        },
                    )
                )
            for tc in delta.get("tool_calls") or []:
                idx = tc.get("index", 0)
                if idx not in self._tools:
                    self._tools[idx] = {
                        "id": tc.get("id", ""),
                        "name": "",
                        "args": "",
                        "block_idx": self._next,
                        "open": False,
                    }
                    self._next += 1
                slot = self._tools[idx]
                if tc.get("id"):
                    slot["id"] = tc["id"]
                fn = tc.get("function") or {}
                if fn.get("name"):
                    slot["name"] = fn["name"]
                if not slot["open"]:
                    events.append(
                        self._evt(
                            "content_block_start",
                            {
                                "index": slot["block_idx"],
                                "content_block": {
                                    "type": "tool_use",
                                    "id": slot["id"],
                                    "name": slot["name"],
                                    "input": {},
                                },
                            },
                        )
                    )
                    slot["open"] = True
                if fn.get("arguments"):
                    slot["args"] += fn["arguments"]
                    events.append(
                        self._evt(
                            "content_block_delta",
                            {
                                "index": slot["block_idx"],
                                "delta": {
                                    "type": "input_json_delta",
                                    "partial_json": fn["arguments"],
                                },
                            },
                        )
                    )
            if choice.get("finish_reason"):
                self._finish = choice["finish_reason"]
                if self._text_open:
                    events.append(self._evt("content_block_stop", {"index": self._text_idx}))
                    self._text_open = False
                for slot in self._tools.values():
                    if slot.get("open"):
                        events.append(self._evt("content_block_stop", {"index": slot["block_idx"]}))
                        slot["open"] = False
        return "".join(events)

    def _evt(self, event_type: str, data: dict) -> str:
        payload = {"type": event_type, **data}
        return f"event: {event_type}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

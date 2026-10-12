"""OpenAI Responses API（Codex CLI）↔ Chat Completions。"""

from __future__ import annotations

import json
import time
from typing import Any

from .ids import rid


def responses_to_chat(body: dict) -> dict:
    messages: list[dict] = []
    instructions = body.get("instructions")
    if instructions:
        messages.append({"role": "system", "content": instructions})

    inp = body.get("input", [])
    if isinstance(inp, str):
        messages.append({"role": "user", "content": inp})
    elif isinstance(inp, list):
        messages.extend(_input_to_messages(inp))

    chat: dict[str, Any] = {"messages": messages, "stream": True}
    if body.get("model"):
        chat["model"] = body["model"]
    tools = body.get("tools")
    if tools:
        chat["tools"] = _tools_to_chat(tools)
    if "tool_choice" in body:
        choice = body["tool_choice"]
        if isinstance(choice, dict) and choice.get("type") == "function" and "name" in choice:
            choice = {"type": "function", "function": {"name": choice["name"]}}
        chat["tool_choice"] = choice
    for key in (
        "temperature",
        "top_p",
        "stop",
        "seed",
        "presence_penalty",
        "frequency_penalty",
        "reasoning_effort",
    ):
        if key in body:
            chat[key] = body[key]
    if "max_output_tokens" in body:
        chat["max_tokens"] = body["max_output_tokens"]
    elif "max_tokens" in body:
        chat["max_tokens"] = body["max_tokens"]
    return chat


def _extract_content(content: Any) -> Any:
    if isinstance(content, str) or content is None:
        return content or ""
    if not isinstance(content, list):
        return str(content)
    parts: list[dict] = []
    has_image = False
    for item in content:
        if isinstance(item, str):
            parts.append({"type": "text", "text": item})
            continue
        if not isinstance(item, dict):
            continue
        kind = item.get("type")
        if kind in ("input_text", "text", "output_text"):
            parts.append({"type": "text", "text": item.get("text", "")})
        elif kind in ("input_image", "image_url"):
            value = item.get("image_url")
            image = {"url": value} if isinstance(value, str) else dict(value or {})
            parts.append({"type": "image_url", "image_url": image})
            has_image = True
    if has_image:
        return parts
    return "".join(p.get("text", "") for p in parts)


def _input_to_messages(items: list) -> list[dict]:
    messages: list[dict] = []
    pending_content: Any = None
    pending_tools: list[dict] = []

    def flush() -> None:
        nonlocal pending_content, pending_tools
        if pending_content is not None or pending_tools:
            msg: dict[str, Any] = {"role": "assistant", "content": pending_content or ""}
            if pending_tools:
                msg["tool_calls"] = pending_tools[:]
            messages.append(msg)
            pending_content = None
            pending_tools.clear()

    for item in items:
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        role = item.get("role", "")
        if (item_type in (None, "message")) and role in ("user", "system", "developer"):
            flush()
            mapped = "system" if role == "developer" else role
            messages.append({"role": mapped, "content": _extract_content(item.get("content", ""))})
            continue
        if (item_type in (None, "message")) and role == "assistant":
            flush()
            pending_content = _extract_content(item.get("content", ""))
            continue
        if item_type == "function_call":
            if pending_content is None:
                pending_content = ""
            pending_tools.append(
                {
                    "id": item.get("call_id") or item.get("id") or rid("call_"),
                    "type": "function",
                    "function": {
                        "name": item.get("name", ""),
                        "arguments": item.get("arguments", "{}"),
                    },
                }
            )
            continue
        if item_type == "function_call_output":
            flush()
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": item.get("call_id", ""),
                    "content": _extract_content(item.get("output", "")),
                }
            )
    flush()
    return messages


def _tools_to_chat(tools: list) -> list:
    result = []
    for tool in tools:
        if not isinstance(tool, dict) or tool.get("type") != "function":
            continue
        if "function" in tool:
            result.append(tool)
            continue
        fn: dict[str, Any] = {"name": tool.get("name", "")}
        for key in ("description", "parameters", "strict"):
            if key in tool:
                fn[key] = tool[key]
        result.append({"type": "function", "function": fn})
    return result


class ResponsesStreamConverter:
    """把上游 Chat SSE 转成 Codex 需要的 Responses 事件流。"""

    def __init__(self, model: str = "unknown"):
        self.resp_id = rid("resp_")
        self.msg_id = rid("msg_")
        self.model = model
        self.created_at = int(time.time())
        self._created = False
        self._msg = False
        self._part = False
        self._content = ""
        self._tools: dict[int, dict] = {}
        self._finish: str | None = None
        self._usage: dict | None = None
        self._seq = 0
        self._next_out = 0
        self._msg_out: int | None = None
        self._error: dict | None = None
        self._done = False

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
        if self._done or self._error:
            return ""
        self._done = True
        events: list[str] = []
        response = self._obj("completed")
        if self._part:
            events.append(
                self._evt(
                    "response.output_text.done",
                    {
                        "output_index": self._msg_out,
                        "item_id": self.msg_id,
                        "content_index": 0,
                        "text": self._content,
                    },
                )
            )
            events.append(
                self._evt(
                    "response.content_part.done",
                    {
                        "output_index": self._msg_out,
                        "item_id": self.msg_id,
                        "content_index": 0,
                        "part": {"type": "output_text", "text": self._content, "annotations": []},
                    },
                )
            )
        if self._msg:
            events.append(
                self._evt(
                    "response.output_item.done",
                    {"output_index": self._msg_out, "item": self._msg_item(response["status"])},
                )
            )
        for idx in sorted(self._tools):
            tc = self._tools[idx]
            if not tc.get("emitted"):
                continue
            events.append(
                self._evt(
                    "response.function_call_arguments.done",
                    {
                        "output_index": tc["output_idx"],
                        "item_id": tc["fc_id"],
                        "arguments": tc["args"],
                    },
                )
            )
            events.append(
                self._evt(
                    "response.output_item.done",
                    {
                        "output_index": tc["output_idx"],
                        "item": self._fc_item(tc, response["status"]),
                    },
                )
            )
        events.append(self._evt("response." + response["status"], {"response": response}))
        return "".join(events)

    def nonstream(self) -> dict:
        return self._obj("completed")

    def error(self, message: str, code: Any) -> str:
        if self._error or self._done:
            return ""
        self._error = {"message": message, "code": str(code), "type": "upstream_error"}
        return self._evt("response.failed", {"response": self._obj("failed")})

    def _chunk(self, chunk: dict) -> str:
        if self._error or self._done:
            return ""
        if chunk.get("error"):
            err = chunk["error"]
            msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
            code = err.get("code", "upstream_error") if isinstance(err, dict) else "upstream_error"
            return self.error(msg, code)
        events: list[str] = []
        if chunk.get("model"):
            self.model = chunk["model"]
        if not self._created:
            obj = self._obj("in_progress")
            events.append(self._evt("response.created", {"response": obj}))
            events.append(self._evt("response.in_progress", {"response": obj}))
            self._created = True
        if chunk.get("usage"):
            self._usage = {**(self._usage or {}), **chunk["usage"]}
        for choice in chunk.get("choices") or []:
            delta = choice.get("delta") or {}
            content = delta.get("content")
            if content:
                if not self._msg:
                    self._msg_out = self._next_out
                    self._next_out += 1
                    events.append(
                        self._evt(
                            "response.output_item.added",
                            {
                                "output_index": self._msg_out,
                                "item": self._msg_item("in_progress", empty=True),
                            },
                        )
                    )
                    self._msg = True
                if not self._part:
                    events.append(
                        self._evt(
                            "response.content_part.added",
                            {
                                "output_index": self._msg_out,
                                "item_id": self.msg_id,
                                "content_index": 0,
                                "part": {"type": "output_text", "text": "", "annotations": []},
                            },
                        )
                    )
                    self._part = True
                self._content += content
                events.append(
                    self._evt(
                        "response.output_text.delta",
                        {
                            "output_index": self._msg_out,
                            "item_id": self.msg_id,
                            "content_index": 0,
                            "delta": content,
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
                        "fc_id": rid("fc_"),
                        "output_idx": self._next_out,
                        "emitted": False,
                    }
                    self._next_out += 1
                slot = self._tools[idx]
                if tc.get("id"):
                    slot["id"] = tc["id"]
                fn = tc.get("function") or {}
                if fn.get("name"):
                    slot["name"] = fn["name"]
                if not slot["emitted"]:
                    events.append(
                        self._evt(
                            "response.output_item.added",
                            {
                                "output_index": slot["output_idx"],
                                "item": self._fc_item(slot, "in_progress"),
                            },
                        )
                    )
                    slot["emitted"] = True
                if fn.get("arguments"):
                    slot["args"] += fn["arguments"]
                    events.append(
                        self._evt(
                            "response.function_call_arguments.delta",
                            {
                                "output_index": slot["output_idx"],
                                "item_id": slot["fc_id"],
                                "delta": fn["arguments"],
                            },
                        )
                    )
            if choice.get("finish_reason"):
                self._finish = choice["finish_reason"]
        return "".join(events)

    def _evt(self, event_type: str, data: dict) -> str:
        payload = {"type": event_type, "sequence_number": self._seq, **data}
        self._seq += 1
        return f"event: {event_type}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    def _msg_item(self, status: str, empty: bool = False) -> dict:
        content = [] if empty else [{"type": "output_text", "text": self._content, "annotations": []}]
        return {
            "type": "message",
            "id": self.msg_id,
            "status": status,
            "role": "assistant",
            "content": content,
        }

    def _fc_item(self, tc: dict, status: str) -> dict:
        return {
            "type": "function_call",
            "id": tc["fc_id"],
            "call_id": tc["id"],
            "name": tc["name"],
            "arguments": tc["args"],
            "status": status,
        }

    def _obj(self, status: str) -> dict:
        incomplete = None
        if self._error:
            status = "failed"
        elif status == "completed" and self._finish in ("length", "content_filter", "content-filter"):
            status = "incomplete"
            incomplete = {
                "reason": "max_output_tokens" if self._finish == "length" else "content_filter"
            }
        output: list[dict] = []
        if self._msg or self._content:
            output.append(self._msg_item(status))
        for idx in sorted(self._tools):
            tc = self._tools[idx]
            if tc.get("emitted"):
                output.append(self._fc_item(tc, status))
        usage = None
        if self._usage:
            u = self._usage
            prompt = u.get("prompt_tokens") or u.get("input_tokens") or 0
            completion = u.get("completion_tokens") or u.get("output_tokens") or 0
            usage = {
                "input_tokens": prompt,
                "input_tokens_details": {"cached_tokens": 0},
                "output_tokens": completion,
                "output_tokens_details": {"reasoning_tokens": 0},
                "total_tokens": u.get("total_tokens") or (prompt + completion),
            }
        return {
            "id": self.resp_id,
            "object": "response",
            "created_at": self.created_at,
            "status": status,
            "error": self._error,
            "incomplete_details": incomplete,
            "model": self.model,
            "output": output,
            "parallel_tool_calls": True,
            "usage": usage,
        }

"""本地 HTTP 桥：Chat Completions / Responses / Anthropic Messages。"""

from __future__ import annotations

import json
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse

from . import __version__
from .auth import CredentialStore, pick_store
from .billing import daily_checkin, fetch_credits
from .config import Settings, load_settings
from .protocols.anthropic import AnthropicStreamConverter, anthropic_to_chat
from .protocols.responses import ResponsesStreamConverter, responses_to_chat
from .upstream import complete_upstream, fetch_models, prepare_chat_body, stream_upstream

STATE: dict = {"settings": None, "store": None, "config_path": None}



def get_settings() -> Settings:
    try:
        cfg = load_settings(STATE.get("config_path"))
        if cfg:
            STATE["settings"] = cfg
    except Exception:
        pass
    return STATE["settings"]



def get_store() -> CredentialStore:
    store = STATE.get("store")
    if store is None:
        settings = get_settings()
        if settings:
            store = pick_store(settings)
            if store:
                STATE["store"] = store
    if store is None:
        raise HTTPException(
            status_code=503,
            detail={
                "error": {
                    "message": "未找到有效登录凭据。请在终端运行 python -m agent_bridge login 完成登录。",
                    "type": "auth_error",
                }
            },
        )
    return store


def _client_key(authorization: Optional[str], x_api_key: Optional[str]) -> str:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return (x_api_key or "").strip()


def require_key(
    authorization: Optional[str] = None,
    x_api_key: Optional[str] = None,
    anthropic_key: Optional[str] = None,
) -> None:
    expected = get_settings().api_key
    if not expected:
        return
    token = _client_key(authorization, x_api_key) or (anthropic_key or "").strip()
    if token != expected:
        raise HTTPException(
            status_code=401,
            detail={"error": {"message": "invalid api key", "type": "auth_error"}},
        )


def create_app(settings: Settings, store: CredentialStore | None) -> FastAPI:
    STATE["settings"] = settings
    STATE["store"] = store
    app = FastAPI(
        title="Agent Bridge",
        version=__version__,
        description="用 WorkBuddy / CodeBuddy 积分驱动 Codex 与 Claude Code",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/")
    async def root():
        return {
            "name": "agent-bridge",
            "version": __version__,
            "docs": {
                "codex": "POST /v1/responses  base=http://127.0.0.1:8787/v1",
                "claude": "POST /v1/messages  base=http://127.0.0.1:8787",
                "openai": "POST /v1/chat/completions  base=http://127.0.0.1:8787/v1",
            },
        }

    @app.head("/api/hello")
    @app.get("/api/hello")
    async def hello():
        return {"status": "ok"}

    @app.get("/health")
    async def health():
        current_settings = get_settings()
        current_store = STATE.get("store")
        if current_store is None and current_settings:
            current_store = pick_store(current_settings)
            if current_store:
                STATE["store"] = current_store
        info: dict = {
            "status": "ok",
            "network": current_settings.network,
            "endpoint": current_settings.base_url,
            "has_credentials": current_store is not None,
        }
        if current_store is not None:
            try:
                info["credential"] = current_store.summary()
            except Exception as exc:
                info["credential_error"] = str(exc)
        else:
            info["tip"] = "未检测到有效凭据，请在终端执行：python -m agent_bridge login 登录"
        return info

    @app.get("/v1/models")
    @app.get("/models")
    async def models(
        authorization: Optional[str] = Header(default=None),
        x_api_key: Optional[str] = Header(default=None, alias="X-Api-Key"),
        anthropic_api_key: Optional[str] = Header(default=None, alias="anthropic-api-key"),
    ):
        require_key(authorization, x_api_key, anthropic_api_key)
        current_settings = get_settings()
        current_store = STATE.get("store")
        if current_store is None and current_settings:
            current_store = pick_store(current_settings)
            if current_store:
                STATE["store"] = current_store
        ids = await fetch_models(current_settings, current_store)
        return {
            "object": "list",
            "data": [
                {
                    "id": mid,
                    "object": "model",
                    "created": 1700000000,
                    "owned_by": "anthropic" if mid.startswith("claude") else "workbuddy",
                }
                for mid in ids
            ],
        }

    @app.get("/status")
    async def status(
        authorization: Optional[str] = Header(default=None),
        x_api_key: Optional[str] = Header(default=None, alias="X-Api-Key"),
    ):
        require_key(authorization, x_api_key)
        cred = get_store()
        credits = await fetch_credits(get_settings(), cred)
        return {"credential": cred.summary(), "credits": credits}

    @app.post("/checkin")
    async def checkin(
        authorization: Optional[str] = Header(default=None),
        x_api_key: Optional[str] = Header(default=None, alias="X-Api-Key"),
    ):
        require_key(authorization, x_api_key)
        return await daily_checkin(get_settings(), get_store())

    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request):
        require_key(
            request.headers.get("authorization"),
            request.headers.get("x-api-key"),
            request.headers.get("anthropic-api-key"),
        )
        payload = await _json_body(request)
        client_stream = bool(payload.get("stream"))
        body = prepare_chat_body(payload, get_settings())
        cred = get_store()
        if client_stream:
            return StreamingResponse(
                _sse_or_error(settings, cred, body),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
        status_code, result = await complete_upstream(settings, cred, body)
        if status_code != 200:
            return _upstream_error(status_code, result)
        return JSONResponse(result)

    @app.head("/")
    @app.head("/v1/responses")
    @app.head("/responses")
    @app.head("/v1/models")
    @app.head("/models")
    async def responses_head():
        return Response(status_code=200)

    @app.post("/v1/responses")
    async def responses(request: Request):
        require_key(
            request.headers.get("authorization"),
            request.headers.get("x-api-key"),
            request.headers.get("anthropic-api-key"),
        )
        payload = await _json_body(request)
        client_stream = payload.get("stream", True)
        chat = responses_to_chat(payload)
        body = prepare_chat_body(chat, get_settings())
        print(f"[RECV /v1/responses] req_model={payload.get('model')} -> resolved={body.get('model')}, stream={client_stream}, tools={len(payload.get('tools') or [])}", flush=True)
        converter = ResponsesStreamConverter(model=body.get("model", "unknown"))
        cred = get_store()
        if client_stream:
            return StreamingResponse(
                _convert_stream(settings, cred, body, converter),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
        status_code, result = await complete_upstream(settings, cred, body)
        if status_code != 200:
            return _upstream_error(status_code, result)
        # 非流式：把聚合后的 Chat 对象喂给转换器
        fake = _chat_to_sse_chunks(result)
        for line in fake:
            converter.feed_line(line)
        return JSONResponse(converter.nonstream())

    @app.post("/v1/messages")
    @app.post("/messages")
    async def messages(request: Request):
        require_key(
            request.headers.get("authorization"),
            request.headers.get("x-api-key"),
            request.headers.get("anthropic-api-key"),
        )
        payload = await _json_body(request)
        client_stream = bool(payload.get("stream"))
        chat = anthropic_to_chat(payload)
        current_settings = get_settings()
        body = prepare_chat_body(chat, current_settings)
        print(f"[RECV /v1/messages] req_model={payload.get('model')} -> resolved={body.get('model')}, stream={client_stream}, sys_len={len(str(payload.get('system') or ''))}, tools={len(payload.get('tools') or [])}", flush=True)
        converter = AnthropicStreamConverter(model=body.get("model", "unknown"))
        cred = get_store()
        if client_stream:
            return StreamingResponse(
                _convert_stream(current_settings, cred, body, converter),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
        status_code, result = await complete_upstream(current_settings, cred, body)
        if status_code != 200:
            return _upstream_error(status_code, result)
        for line in _chat_to_sse_chunks(result):
            converter.feed_line(line)
        return JSONResponse(converter.nonstream())

    @app.post("/v1/messages/count_tokens")
    @app.post("/messages/count_tokens")
    async def count_tokens(request: Request):
        require_key(
            request.headers.get("authorization"),
            request.headers.get("x-api-key"),
            request.headers.get("anthropic-api-key"),
        )
        payload = await _json_body(request)
        total_chars = 0
        sys = payload.get("system")
        if isinstance(sys, str):
            total_chars += len(sys)
        elif isinstance(sys, list):
            total_chars += sum(len(b.get("text", "")) for b in sys if isinstance(b, dict))
        for m in payload.get("messages") or []:
            if isinstance(m, dict):
                content = m.get("content")
                if isinstance(content, str):
                    total_chars += len(content)
                elif isinstance(content, list):
                    for b in content:
                        if isinstance(b, dict):
                            total_chars += len(str(b.get("text", "") or b.get("content", "")))
        for t in payload.get("tools") or []:
            total_chars += len(json.dumps(t, ensure_ascii=False))
        tokens = max(1, total_chars // 3)
        return {"input_tokens": tokens}

    return app



async def _json_body(request: Request) -> dict:
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": {"message": f"bad json: {exc}", "type": "invalid_request_error"}},
        )
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=400,
            detail={"error": {"message": "json object required", "type": "invalid_request_error"}},
        )
    return payload


def _upstream_error(status_code: int, result) -> JSONResponse:
    if isinstance(result, (bytes, bytearray)):
        text = result.decode("utf-8", "replace")
        try:
            body = json.loads(text)
        except json.JSONDecodeError:
            body = {"error": {"message": text[:800], "type": "upstream_error", "code": status_code}}
    elif isinstance(result, dict):
        body = result
    else:
        body = {"error": {"message": str(result)[:800], "type": "upstream_error", "code": status_code}}

    # Anthropic Messages API expects: {"type": "error", "error": {"type": ..., "message": ...}}
    msg = ""
    if "error" in body and isinstance(body["error"], dict):
        msg = body["error"].get("message") or ""
    elif "msg" in body:
        msg = body["msg"]
    elif "displayMsg" in body and isinstance(body["displayMsg"], dict):
        msg = body["displayMsg"].get("zh") or body["displayMsg"].get("en") or ""
    if not msg:
        msg = json.dumps(body, ensure_ascii=False)

    anthropic_resp = {
        "type": "error",
        "error": {
            "type": "invalid_request_error" if status_code == 400 else "api_error",
            "message": msg,
        },
    }
    return JSONResponse(anthropic_resp, status_code=status_code)


async def _sse_or_error(settings: Settings, store: CredentialStore, body: dict):
    buf = b""
    async for chunk in stream_upstream(settings, store, body):
        if chunk.startswith(b"{") and b'"error"' in chunk and not buf:
            yield f"data: {chunk.decode('utf-8', 'replace')}\n\n".encode("utf-8")
            return
        buf += chunk
        yield chunk


async def _convert_stream(settings: Settings, store: CredentialStore, body: dict, converter):
    leftover = ""
    async for chunk in stream_upstream(settings, store, body):
        text = leftover + chunk.decode("utf-8", "replace")
        if text.lstrip().startswith("{") and '"error"' in text and "data:" not in text:
            err = json.loads(text)
            message = (err.get("error") or {}).get("message", text)
            if hasattr(converter, "error"):
                yield converter.error(message, (err.get("error") or {}).get("code", 502)).encode(
                    "utf-8"
                )
            else:
                yield f"event: error\ndata: {json.dumps(err, ensure_ascii=False)}\n\n".encode(
                    "utf-8"
                )
            return
        lines = text.split("\n")
        leftover = lines[-1]
        for line in lines[:-1]:
            events = converter.feed_line(line)
            if events:
                yield events.encode("utf-8")
    if leftover.strip():
        events = converter.feed_line(leftover)
        if events:
            yield events.encode("utf-8")
    tail = converter.finish()
    if tail:
        yield tail.encode("utf-8")


def _chat_to_sse_chunks(result: dict) -> list[str]:
    """把非流式 chat.completion 拆成假 SSE，复用流式转换器。"""
    choice = (result.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    model = result.get("model")
    chunks: list[dict] = []
    content = msg.get("content") or ""
    if content:
        chunks.append(
            {
                "model": model,
                "choices": [{"delta": {"content": content}, "finish_reason": None}],
            }
        )
    for idx, tc in enumerate(msg.get("tool_calls") or []):
        chunks.append(
            {
                "model": model,
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": idx,
                                    "id": tc.get("id"),
                                    "function": tc.get("function") or {},
                                }
                            ]
                        },
                        "finish_reason": None,
                    }
                ],
            }
        )
    chunks.append(
        {
            "model": model,
            "usage": result.get("usage"),
            "choices": [{"delta": {}, "finish_reason": choice.get("finish_reason") or "stop"}],
        }
    )
    return ["data: " + json.dumps(c, ensure_ascii=False) for c in chunks]


def build_app(settings: Settings) -> FastAPI:
    store = pick_store(settings)
    return create_app(settings, store)

"""浏览器授权登录 WorkBuddy / CodeBuddy，并把凭据落到本地。"""

from __future__ import annotations

import json
import os
import time
import uuid
import webbrowser
from pathlib import Path

import httpx

from .auth import normalize_session
from .config import Settings, default_credential_path


PENDING_CODE = 11217


def _trace_headers(settings: Settings) -> dict[str, str]:
    request_id = os.urandom(16).hex()
    span_id = os.urandom(8).hex()
    host = settings.endpoint.split("://", 1)[-1]
    return {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "User-Agent": "CLI/1.0.8 CodeBuddy/1.0.8",
        "X-Product": "SaaS",
        "X-Domain": host,
        "X-No-Authorization": "true",
        "X-No-Department-Info": "true",
        "X-No-Enterprise-Id": "true",
        "X-No-User-Id": "true",
        "X-Request-ID": request_id,
        "X-B3-TraceId": request_id,
        "X-B3-SpanId": span_id,
        "X-B3-Sampled": "1",
        "b3": f"{request_id}-{span_id}-1-",
    }


def save_credentials(path: Path, token_data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    session = normalize_session(
        {
            "accessToken": token_data.get("accessToken") or token_data.get("access_token"),
            "refreshToken": token_data.get("refreshToken") or token_data.get("refresh_token"),
            "expiresIn": token_data.get("expiresIn") or token_data.get("expires_in"),
            "expiresAt": token_data.get("expiresAt")
            or (
                int(time.time() * 1000)
                + int(token_data.get("expiresIn") or token_data.get("expires_in") or 0) * 1000
            ),
            "domain": token_data.get("domain") or "",
            "uid": token_data.get("uid") or "",
            "enterpriseId": token_data.get("enterpriseId")
            or token_data.get("enterprise_id")
            or token_data.get("tenantId"),
        }
    )
    payload = {"account": session["account"], "auth": session["auth"]}
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    return path


def run_login(settings: Settings, open_browser: bool = True) -> Path:
    """走官方 device/state 授权，轮询拿到 token。"""
    nonce = uuid.uuid4().hex
    headers = _trace_headers(settings)
    state_url = f"{settings.base_url}/v2/plugin/auth/state?platform=CLI&nonce={nonce}"
    with httpx.Client(timeout=30.0) as client:
        started = client.post(state_url, headers=headers, json={"nonce": nonce})
        payload = started.json()
        if payload.get("code") not in (0, "0") or not payload.get("data"):
            raise RuntimeError(f"发起登录失败：{payload}")
        data = payload["data"]
        auth_url = data.get("authUrl")
        state = data.get("state")
        if not auth_url or not state:
            raise RuntimeError(f"登录响应缺少 authUrl/state：{payload}")
        print(f"请在浏览器完成 WorkBuddy / CodeBuddy 登录：\n{auth_url}\n")
        if open_browser:
            try:
                webbrowser.open(auth_url)
            except Exception:
                pass
        token_url = f"{settings.base_url}/v2/plugin/auth/token?state={state}"
        deadline = time.time() + 600
        while time.time() < deadline:
            time.sleep(3)
            poll = client.get(token_url, headers=_trace_headers(settings))
            body = poll.json()
            if body.get("code") == PENDING_CODE:
                print("等待登录确认…")
                continue
            if body.get("code") not in (0, "0") or not body.get("data"):
                raise RuntimeError(f"登录失败：{body}")
            dest = Path(settings.credentials_file).expanduser()
            if not dest.parent.exists():
                dest = default_credential_path()
            saved = save_credentials(dest, body["data"])
            print(f"登录成功，凭据已写入：{saved}")
            return saved
    raise TimeoutError("登录超时，请重试 python -m agent_bridge login")

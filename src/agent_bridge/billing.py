"""查询积分 / 签到（官方 billing 接口，失败时静默降级）。"""

from __future__ import annotations

from typing import Any

import httpx

from .auth import CredentialStore
from .config import Settings

STATUS_PATHS = (
    "/v2/billing/meter/checkin-activity-status",
    "/v2/billing/meter/checkin-status",
)
CHECKIN_PATH = "/v2/billing/meter/daily-checkin"
QUOTA_PATHS = (
    "/v2/billing/quota",
    "/v2/billing/credits",
    "/v2/billing/resource",
)


async def _post_json(client: httpx.AsyncClient, url: str, headers: dict) -> Any | None:
    try:
        resp = await client.post(url, headers=headers, json={})
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        return None
    return None


async def _get_json(client: httpx.AsyncClient, url: str, headers: dict) -> Any | None:
    try:
        resp = await client.get(url, headers=headers)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        return None
    return None


async def fetch_credits(settings: Settings, store: CredentialStore) -> dict[str, Any]:
    headers = store.headers()
    result: dict[str, Any] = {"ok": False, "raw": {}}
    async with httpx.AsyncClient(timeout=20.0) as client:
        for path in STATUS_PATHS:
            data = await _post_json(client, f"{settings.base_url}{path}", headers)
            if data is not None:
                result["raw"]["status"] = data
                result["ok"] = True
                break
        for path in QUOTA_PATHS:
            data = await _get_json(client, f"{settings.base_url}{path}", headers)
            if data is None:
                data = await _post_json(client, f"{settings.base_url}{path}", headers)
            if data is not None:
                result["raw"]["quota"] = data
                result["ok"] = True
                break
    payload = result["raw"].get("status") or result["raw"].get("quota") or {}
    data = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(data, dict):
        result["credits"] = {
            "total": data.get("total_credits") or data.get("total") or data.get("quota"),
            "remaining": data.get("remaining") or data.get("balance") or data.get("left"),
            "used": data.get("used"),
            "streak_days": data.get("streak_days") or data.get("streakDays"),
        }
    return result


async def daily_checkin(settings: Settings, store: CredentialStore) -> dict[str, Any]:
    headers = store.headers()
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            f"{settings.base_url}{CHECKIN_PATH}", headers=headers, json={}
        )
        try:
            body = resp.json()
        except Exception:
            body = {"text": resp.text[:500]}
    return {"status_code": resp.status_code, "body": body}

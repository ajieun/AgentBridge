"""读取本机 WorkBuddy / CodeBuddy 登录态，并在过期时刷新。"""

from __future__ import annotations

import base64
import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any

import httpx

from .config import Settings, default_credential_path


def desktop_auth_dirs(extra: str = "") -> list[Path]:
    home = Path.home()
    dirs: list[Path] = []
    if extra:
        dirs.append(Path(extra))
    env_dir = os.environ.get("CODEBUDDY_AUTH_DIR")
    if env_dir:
        dirs.append(Path(env_dir))
    if sys.platform == "win32":
        local = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
        roaming = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
        dirs.extend(
            [
                local / "CodeBuddyExtension" / "Data" / "Public" / "auth",
                local / "WorkBuddyExtension" / "Data" / "Public" / "auth",
                roaming / "CodeBuddyExtension" / "Data" / "Public" / "auth",
            ]
        )
    elif sys.platform == "darwin":
        root = home / "Library" / "Application Support"
        dirs.extend(
            [
                root / "CodeBuddyExtension" / "Data" / "Public" / "auth",
                root / "WorkBuddyExtension" / "Data" / "Public" / "auth",
            ]
        )
    else:
        xdg = Path(os.environ.get("XDG_DATA_HOME", home / ".local" / "share"))
        dirs.extend(
            [
                xdg / "CodeBuddyExtension" / "Data" / "Public" / "auth",
                xdg / "WorkBuddyExtension" / "Data" / "Public" / "auth",
            ]
        )
    seen: set[Path] = set()
    out: list[Path] = []
    for d in dirs:
        try:
            resolved = d.expanduser()
        except OSError:
            continue
        if resolved not in seen:
            seen.add(resolved)
            out.append(resolved)
    return out


def find_auth_files(extra: str = "") -> list[Path]:
    files: list[Path] = []
    cred = default_credential_path()
    if cred.is_file():
        files.append(cred)
    for d in desktop_auth_dirs(extra):
        if d.is_dir():
            matches = list(d.glob("*.info"))
            # 优先非时间戳命名文件（主文件），并按修改时间降序排列
            matches.sort(
                key=lambda p: (
                    0 if not any(c.isdigit() for c in p.stem) else 1,
                    -p.stat().st_mtime if p.exists() else 0,
                )
            )
            files.extend(matches)
    return files


def _b64url_pad(raw: str) -> bytes:
    padded = raw + "=" * (-len(raw) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def decode_jwt_payload(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) < 2:
        return {}
    try:
        return json.loads(_b64url_pad(parts[1]).decode("utf-8"))
    except Exception:
        return {}


def _clean_token_str(val: Any) -> str:
    if isinstance(val, str):
        if "$wbEncrypted" in val or "envelope" in val:
            return ""
        return val.strip()
    return ""


def normalize_session(raw: dict[str, Any]) -> dict[str, Any]:
    """把桌面端 / OAuth / 手工 JSON 统一成 {account, auth}。"""
    if "auth" in raw or "account" in raw:
        auth = dict(raw.get("auth") or {})
        account = dict(raw.get("account") or {})
    else:
        auth = {
            "accessToken": raw.get("accessToken")
            or raw.get("access_token")
            or raw.get("bearer_token")
            or "",
            "refreshToken": raw.get("refreshToken") or raw.get("refresh_token") or "",
            "expiresAt": raw.get("expiresAt") or raw.get("expires_at") or 0,
            "expiresIn": raw.get("expiresIn") or raw.get("expires_in") or 0,
            "domain": raw.get("domain") or "",
        }
        account = {
            "uid": raw.get("uid") or raw.get("user_id") or "",
            "enterpriseId": raw.get("enterpriseId")
            or raw.get("enterprise_id")
            or raw.get("tenant_id")
            or "",
            "nickname": raw.get("nickname") or raw.get("name") or "",
        }

    raw_token = auth.get("accessToken") or auth.get("access_token") or auth.get("bearer_token") or ""
    is_encrypted = (
        isinstance(raw_token, dict) and ("$wbEncrypted" in raw_token or "envelope" in raw_token)
    ) or (isinstance(raw_token, str) and "$wbEncrypted" in raw_token)
    token = _clean_token_str(raw_token)

    jwt = decode_jwt_payload(token) if token else {}
    if not account.get("uid"):
        account["uid"] = str(
            jwt.get("sub")
            or jwt.get("preferred_username")
            or jwt.get("email")
            or account.get("uid")
            or ""
        )
    if not account.get("enterpriseId"):
        account["enterpriseId"] = str(
            jwt.get("enterprise_id") or jwt.get("tenant_id") or ""
        )

    auth["isEncrypted"] = is_encrypted
    auth["accessToken"] = token
    auth["refreshToken"] = _clean_token_str(auth.get("refreshToken") or auth.get("refresh_token") or "")
    return {"account": account, "auth": auth, "_raw": raw}


class CredentialStore:
    """读写一份凭据文件，必要时调用官方 refresh 接口。"""

    def __init__(self, path: Path, settings: Settings):
        self.path = path
        self.settings = settings
        self._lock = threading.Lock()
        self._cached: dict[str, Any] | None = None
        self._mtime: float = 0.0

    def load(self) -> dict[str, Any]:
        with self._lock:
            self._reload_if_needed()
            if not self._cached:
                raise RuntimeError(f"无法读取凭据：{self.path}")
            return normalize_session(self._cached)

    def _reload_if_needed(self) -> None:
        try:
            mt = self.path.stat().st_mtime
        except OSError as exc:
            raise RuntimeError(f"凭据文件不存在：{self.path}") from exc
        if self._cached is None or mt != self._mtime:
            with self.path.open("r", encoding="utf-8") as f:
                self._cached = json.load(f)
            self._mtime = mt

    def _expired(self, session: dict[str, Any]) -> bool:
        expires_at = int((session.get("auth") or {}).get("expiresAt") or 0)
        if expires_at <= 0:
            return False
        return time.time() * 1000 >= expires_at - 60_000

    def headers(self) -> dict[str, str]:
        with self._lock:
            self._reload_if_needed()
            session = normalize_session(self._cached or {})
            if self._expired(session) and session["auth"].get("refreshToken"):
                session = self._refresh_locked(session)
            return self.build_headers(session)

    def build_headers(self, session: dict[str, Any] | None = None) -> dict[str, str]:
        if session is None:
            session = self.load()
        auth = session.get("auth") or {}
        account = session.get("account") or {}
        domain = auth.get("domain") or self.settings.domain
        request_id = os.urandom(16).hex()
        span_id = os.urandom(8).hex()
        uid = str(account.get("uid") or "")
        ent = str(account.get("enterpriseId") or "")
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {auth.get('accessToken', '')}",
            "User-Agent": "CLI/1.0.8 CodeBuddy/1.0.8",
            "X-Product": "SaaS",
            "X-Product-Version": "1.0.8",
            "X-IDE-Type": "CLI",
            "X-IDE-Name": "CLI",
            "X-IDE-Version": "1.0.8",
            "X-Agent-Intent": "craft",
            "X-Domain": str(domain),
            "X-Request-ID": request_id,
            "X-B3-TraceId": request_id,
            "X-B3-SpanId": span_id,
            "X-B3-Sampled": "1",
            "b3": f"{request_id}-{span_id}-1-",
            "x-codebuddy-request": "1",
        }
        if uid:
            headers["X-User-Id"] = uid
        else:
            headers["X-No-User-Id"] = "true"
        if ent:
            headers["X-Enterprise-Id"] = ent
            headers["X-Tenant-Id"] = ent
        else:
            headers["X-No-Enterprise-Id"] = "true"
            headers["X-No-Tenant-Id"] = "true"
        return headers

    def _refresh_locked(self, session: dict[str, Any]) -> dict[str, Any]:
        auth = session.get("auth") or {}
        headers = self.build_headers(session)
        headers["X-Refresh-Token"] = str(auth.get("refreshToken") or "")
        headers["X-Auth-Refresh-Source"] = "plugin"
        url = f"{self.settings.base_url}/v2/plugin/auth/token/refresh"
        with httpx.Client(timeout=20.0) as client:
            resp = client.post(url, headers=headers, json={})
            payload = resp.json()
        if payload.get("code") not in (0, "0") or not payload.get("data"):
            raise RuntimeError(f"刷新 token 失败：{payload.get('msg') or payload}")
        data = payload["data"]
        new_auth = dict(auth)
        if isinstance(data, dict):
            # 官方返回 camelCase
            if data.get("accessToken"):
                new_auth["accessToken"] = data["accessToken"]
            if data.get("refreshToken"):
                new_auth["refreshToken"] = data["refreshToken"]
            if data.get("expiresIn"):
                new_auth["expiresIn"] = data["expiresIn"]
            if data.get("expiresAt"):
                new_auth["expiresAt"] = data["expiresAt"]
            elif data.get("expiresIn"):
                new_auth["expiresAt"] = int(time.time() * 1000) + int(data["expiresIn"]) * 1000
            if data.get("domain"):
                new_auth["domain"] = data["domain"]
        new_auth["lastRefreshTime"] = int(time.time() * 1000)
        raw = dict(self._cached or {})
        if "auth" in raw:
            raw["auth"] = new_auth
        else:
            raw.update(new_auth)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)
        self._cached = raw
        self._mtime = self.path.stat().st_mtime
        return normalize_session(raw)

    def summary(self) -> dict[str, Any]:
        session = self.load()
        auth = session.get("auth") or {}
        account = session.get("account") or {}
        token = str(auth.get("accessToken") or "")
        return {
            "path": str(self.path),
            "uid": account.get("uid"),
            "nickname": account.get("nickname"),
            "enterpriseId": account.get("enterpriseId"),
            "domain": auth.get("domain") or self.settings.domain,
            "token_expires_at": auth.get("expiresAt"),
            "has_token": bool(token),
            "is_encrypted": bool(auth.get("isEncrypted")),
            "has_refresh_token": bool(auth.get("refreshToken")),
        }


def pick_store(settings: Settings) -> CredentialStore | None:
    explicit = Path(settings.credentials_file).expanduser()
    candidates: list[Path] = []
    if explicit.is_file():
        candidates.append(explicit)
    candidates.extend(find_auth_files(settings.auth_dir))
    seen: set[Path] = set()
    unique_candidates: list[Path] = []
    for path in candidates:
        try:
            key = path.resolve() if path.exists() else path
        except OSError:
            key = path
        if key in seen:
            continue
        seen.add(key)
        unique_candidates.append(path)

    valid_stores: list[tuple[int, float, CredentialStore]] = []
    for path in unique_candidates:
        try:
            store = CredentialStore(path, settings)
            session = store.load()
            auth = session.get("auth") or {}
            if auth.get("isEncrypted"):
                continue
            token = auth.get("accessToken")
            if not token:
                continue

            expires_at = int(auth.get("expiresAt") or 0)
            now_ms = int(time.time() * 1000)
            is_valid = expires_at <= 0 or expires_at > now_ms + 60_000

            # 验证 headers 是否能正常获取（若过期会尝试刷新）
            try:
                store.headers()
                priority = 2 if is_valid else 1
                mtime = path.stat().st_mtime if path.exists() else 0.0
                valid_stores.append((priority, mtime, store))
            except Exception:
                continue
        except Exception:
            continue

    if valid_stores:
        # 按优先级和修改时间降序排序
        valid_stores.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return valid_stores[0][2]

    return None

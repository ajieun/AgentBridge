"""桥服务配置：环境变量、TOML、国内/国际上游。"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

CN_ENDPOINT = "https://copilot.tencent.com"
CN_DOMAIN = "www.codebuddy.cn"
GLOBAL_ENDPOINT = "https://www.codebuddy.ai"
GLOBAL_DOMAIN = "www.codebuddy.ai"
WORKBUDDY_GLOBAL_ENDPOINT = "https://www.workbuddy.ai"
WORKBUDDY_GLOBAL_DOMAIN = "www.workbuddy.ai"

FALLBACK_MODELS = [
    "auto",
    "hy3",
    "hy4-preview",
    "glm-5.3",
    "glm-5.3-flash",
    "glm-5.2",
    "glm-5.1",
    "glm-5v-turbo",
    "kimi-k3",
    "kimi-k3-1",
    "kimi-k2.8-preview",
    "kimi-k2.7",
    "kimi-k2.6",
    "kimi-k2.5",
    "deepseek-v4-pro",
    "deepseek-v4.1-flash",
    "deepseek-v4-flash",
    "minimax-m3",
    "minimax-m3-pay",
    "hy3-preview-agent",
]

# Codex / Claude Code 常用模型名 → 腾讯后端真实模型
DEFAULT_ALIASES = {
    # 常用客户端别名
    "claude": "glm-5.2",
    "claude-sonnet-4": "glm-5.2",
    "claude-sonnet-4-5": "glm-5.3",
    "claude-3-5-sonnet": "glm-5.2",
    "claude-3-7-sonnet": "glm-5.2",
    "claude-opus-4": "deepseek-v4-pro",
    "claude-haiku": "glm-5.3-flash",
    "gpt-5": "glm-5.2",
    "gpt-5-codex": "glm-5.2",
    "gpt-4.1": "glm-5.2",
    "o3": "deepseek-v4-pro",
    "codex": "glm-5.2",
    # 简写快捷别名
    "deepseek": "deepseek-v4-pro",
    "deepseek-flash": "deepseek-v4.1-flash",
    "kimi": "kimi-k3",
    "minimax": "minimax-m3",
    # WorkBuddy 界面原始展示名及标准名映射（大小写兼容）
    "deepseek-v4.1-flash": "deepseek-v4.1-flash",
    "Deepseek-V4.1-Flash": "deepseek-v4.1-flash",
    "deepseek-v4-pro": "deepseek-v4-pro",
    "Deepseek-V4-Pro": "deepseek-v4-pro",
    "glm-5.3": "glm-5.3",
    "GLM-5.3": "glm-5.3",
    "glm-5.3-flash": "glm-5.3-flash",
    "GLM-5.3-Flash": "glm-5.3-flash",
    "glm-5.2": "glm-5.2",
    "GLM-5.2": "glm-5.2",
    "glm-5.1": "glm-5.1",
    "GLM-5.1": "glm-5.1",
    "kimi-k3": "kimi-k3",
    "Kimi-K3": "kimi-k3",
    "minimax-m3": "minimax-m3",
    "MiniMax-M3": "minimax-m3",
}


def _home_data_dir() -> Path:
    return Path.home() / ".agent-bridge"


def default_credential_path() -> Path:
    return _home_data_dir() / "credentials.json"


@dataclass
class Settings:
    host: str = "127.0.0.1"
    port: int = 8787
    api_key: str = ""
    network: str = "cn"  # cn | global | workbuddy
    endpoint: str = CN_ENDPOINT
    domain: str = CN_DOMAIN
    default_model: str = "glm-5.2"
    auth_dir: str = ""
    credentials_file: str = str(default_credential_path())
    log_path: str = ""
    desensitize: bool = True
    aliases: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_ALIASES))

    @property
    def base_url(self) -> str:
        return self.endpoint.rstrip("/")

    def resolve_model(self, name: str | None) -> str:
        raw = (name or self.default_model or "auto").strip()
        if not raw:
            return self.default_model
        # 1. Exact match
        if raw in self.aliases:
            return self.aliases[raw]
        low = raw.lower()
        if low in self.aliases:
            return self.aliases[low]
        # 2. Direct match with known upstream model IDs
        if low in FALLBACK_MODELS:
            return low
        # 3. Match prefixes or keywords (e.g. claude-3-7-sonnet-20250219, claude-sonnet-4-5, etc.)
        if "opus" in low:
            return self.aliases.get("claude-opus-4", "deepseek-v4-pro")
        if "sonnet-4-5" in low or "sonnet-4.5" in low:
            return self.aliases.get("claude-sonnet-4-5", "glm-5.3")
        if "3-5" in low or "3.5" in low:
            return self.aliases.get("claude-3-5-sonnet", self.default_model)
        if "3-7" in low or "3.7" in low:
            return self.aliases.get("claude-3-7-sonnet", self.default_model)
        if "haiku" in low:
            return self.aliases.get("claude-haiku", "glm-5.3-flash")
        if "claude" in low:
            return self.aliases.get("claude-3-7-sonnet", self.aliases.get("claude", self.default_model))
        if "codex" in low or "gpt" in low:
            return self.aliases.get("codex", self.default_model)
        if "deepseek" in low:
            if "flash" in low or "4.1" in low:
                return "deepseek-v4.1-flash"
            return "deepseek-v4-pro"
        if "kimi" in low:
            return "kimi-k3"
        if "minimax" in low:
            return "minimax-m3"
        return raw



def apply_network(settings: Settings) -> None:
    """按 network 填充默认上游；显式 endpoint 优先。"""
    override = os.environ.get("CODEBUDDY_ENDPOINT") or os.environ.get("BRIDGE_ENDPOINT")
    if override:
        settings.endpoint = override.rstrip("/")
        host = settings.endpoint.split("://", 1)[-1]
        settings.domain = host
        return
    net = (settings.network or "cn").lower()
    if net in ("global", "internet", "intl", "codebuddy.ai"):
        settings.endpoint = GLOBAL_ENDPOINT
        settings.domain = GLOBAL_DOMAIN
        settings.network = "global"
    elif net in ("workbuddy", "workbuddy.ai"):
        settings.endpoint = WORKBUDDY_GLOBAL_ENDPOINT
        settings.domain = WORKBUDDY_GLOBAL_DOMAIN
        settings.network = "workbuddy"
    else:
        settings.endpoint = CN_ENDPOINT
        settings.domain = CN_DOMAIN
        settings.network = "cn"


def load_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as f:
        return tomllib.load(f)


def load_settings(config_path: str | None = None) -> Settings:
    settings = Settings()
    path = Path(config_path or os.environ.get("BRIDGE_CONFIG", "config.toml"))
    if path.is_file():
        data = load_toml(path)
        for key in (
            "host",
            "port",
            "api_key",
            "network",
            "endpoint",
            "domain",
            "default_model",
            "auth_dir",
            "credentials_file",
            "log_path",
            "desensitize",
        ):
            if key in data and data[key] is not None:
                setattr(settings, key, data[key])
        aliases = data.get("aliases") or {}
        if isinstance(aliases, dict):
            settings.aliases.update({str(k): str(v) for k, v in aliases.items()})

    settings.host = os.environ.get("BRIDGE_HOST", settings.host)
    if os.environ.get("BRIDGE_PORT"):
        settings.port = int(os.environ["BRIDGE_PORT"])
    settings.api_key = (
        os.environ.get("BRIDGE_API_KEY")
        or os.environ.get("CODEBUDDY2OPENAI_KEY")
        or settings.api_key
    )
    settings.network = os.environ.get("CODEBUDDY_NETWORK", settings.network)
    settings.auth_dir = os.environ.get("CODEBUDDY_AUTH_DIR", settings.auth_dir)
    settings.credentials_file = os.environ.get(
        "BRIDGE_CREDENTIALS", settings.credentials_file
    )
    settings.log_path = os.environ.get("BRIDGE_LOG", settings.log_path)
    if os.environ.get("BRIDGE_DESENSITIZE"):
        settings.desensitize = os.environ["BRIDGE_DESENSITIZE"].lower() in (
            "1",
            "true",
            "yes",
        )
    apply_network(settings)
    return settings

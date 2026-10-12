"""命令行入口：serve / login / credits / checkin。"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

import uvicorn

from .auth import pick_store
from .billing import daily_checkin, fetch_credits
from .config import apply_network, load_settings
from .login import run_login


def _preflight(settings) -> None:
    store = pick_store(settings)
    print("==== Agent Bridge 预检 ====")
    print(f"上游     : {settings.base_url}  ({settings.network})")
    print(f"监听     : http://{settings.host}:{settings.port}")
    if store is None:
        print("凭据     : 未检测到可用凭据")
        print("提示     : 请执行以下命令，在浏览器一键授权登录：")
        print("          python -m agent_bridge login")
    else:
        info = store.summary()
        print(f"凭据文件 : {info.get('path')}")
        print(f"账号     : {info.get('nickname') or info.get('uid')}")
        print(f"域名     : {info.get('domain')}")
        if info.get('token_expires_at'):
            print(f"有效状态 : 正常 (到期时间: {info.get('token_expires_at')})")
    print("==========================")


def _apply_runtime(args: argparse.Namespace):
    settings = load_settings(args.config)
    if getattr(args, "host", None):
        settings.host = args.host
    if getattr(args, "port", None):
        settings.port = args.port
    if getattr(args, "api_key", None):
        settings.api_key = args.api_key
    if getattr(args, "network", None):
        settings.network = args.network
        apply_network(settings)
    if getattr(args, "log", None):
        settings.log_path = args.log
    if getattr(args, "no_desensitize", False):
        settings.desensitize = False
    return settings


def cmd_serve(args: argparse.Namespace) -> None:
    settings = _apply_runtime(args)
    if not args.skip_check:
        _preflight(settings)
    from .app import build_app

    app = build_app(settings)
    print(f"\n桥已启动 http://{settings.host}:{settings.port}")
    print("  Codex CLI     → POST /v1/responses")
    print("  Claude Code   → POST /v1/messages")
    print("  OpenAI 客户端 → POST /v1/chat/completions")
    print("  模型列表      → GET  /v1/models")
    print("  积分状态      → GET  /status\n")
    uvicorn.run(app, host=settings.host, port=settings.port, log_level="info")


def cmd_login(args: argparse.Namespace) -> None:
    settings = _apply_runtime(args)
    run_login(settings, open_browser=not args.no_browser)


def cmd_credits(args: argparse.Namespace) -> None:
    settings = _apply_runtime(args)
    store = pick_store(settings)
    if store is None:
        print("未找到凭据，请先 login 或登录桌面端。", file=sys.stderr)
        sys.exit(1)
    data = asyncio.run(fetch_credits(settings, store))
    print(json.dumps({"credential": store.summary(), **data}, ensure_ascii=False, indent=2))


def cmd_checkin(args: argparse.Namespace) -> None:
    settings = _apply_runtime(args)
    store = pick_store(settings)
    if store is None:
        print("未找到凭据，请先 login 或登录桌面端。", file=sys.stderr)
        sys.exit(1)
    data = asyncio.run(daily_checkin(settings, store))
    print(json.dumps(data, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="用 WorkBuddy / CodeBuddy 积分给 Codex / Claude Code 当上游"
    )
    parser.add_argument("--config", default="config.toml", help="TOML 配置文件路径")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--api-key", default=None, help="本地客户端鉴权密钥")
    parser.add_argument(
        "--network",
        choices=["cn", "global", "workbuddy"],
        default=None,
        help="cn=国内；global=国际 CodeBuddy；workbuddy=国际 WorkBuddy",
    )
    parser.add_argument("--log", default=None)
    parser.add_argument("--no-desensitize", action="store_true")
    parser.add_argument("--skip-check", action="store_true")

    sub = parser.add_subparsers(dest="cmd")
    serve = sub.add_parser("serve", help="启动本地桥（默认）")
    serve.add_argument("--skip-check", action="store_true", help="跳过启动预检")
    serve.add_argument("--host", default=None)
    serve.add_argument("--port", type=int, default=None)
    serve.add_argument("--api-key", default=None, help="本地客户端鉴权密钥")
    serve.add_argument("--no-desensitize", action="store_true")

    login = sub.add_parser("login", help="浏览器授权并保存凭据")
    login.add_argument("--no-browser", action="store_true")
    sub.add_parser("credits", help="查询积分 / 余额")
    sub.add_parser("checkin", help="领取每日签到积分")

    args = parser.parse_args()
    if args.cmd in (None, "serve"):
        cmd_serve(args)
    elif args.cmd == "login":
        if not hasattr(args, "no_browser"):
            args.no_browser = False
        cmd_login(args)
    elif args.cmd == "credits":
        cmd_credits(args)
    elif args.cmd == "checkin":
        cmd_checkin(args)


if __name__ == "__main__":
    main()

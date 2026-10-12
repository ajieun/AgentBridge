from agent_bridge.config import Settings
from agent_bridge.protocols.anthropic import anthropic_to_chat
from agent_bridge.protocols.responses import responses_to_chat
from agent_bridge.sanitize import sanitize_chat_body


def test_responses_input_string():
    chat = responses_to_chat(
        {"model": "gpt-5-codex", "instructions": "you are a coder", "input": "hi"}
    )
    assert chat["messages"][0]["role"] == "system"
    assert chat["messages"][1]["content"] == "hi"


def test_anthropic_tool_result():
    chat = anthropic_to_chat(
        {
            "model": "claude",
            "system": "sys",
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "tool_result", "tool_use_id": "c1", "content": "ok"}],
                }
            ],
            "tools": [{"name": "bash", "input_schema": {"type": "object"}}],
        }
    )
    assert chat["messages"][0]["role"] == "system"
    assert chat["messages"][1]["role"] == "tool"
    assert chat["tools"][0]["function"]["name"] == "bash"


def test_alias_and_sanitize():
    settings = Settings()
    assert settings.resolve_model("claude-sonnet-4") == "glm-5.2"
    body = sanitize_chat_body(
        {
            "messages": [{"role": "system", "content": "never privilege escalation in sandbox"}],
            "tools": [{"type": "function", "function": {"name": "x", "description": "exploit helper"}}],
        }
    )
    assert "\u200b" in body["messages"][0]["content"]


def test_strip_client_fingerprints():
    from agent_bridge.sanitize import strip_client_fingerprints

    # 完整原句剥离后兜底
    assert (
        strip_client_fingerprints("You are Claude Code, Anthropic's official CLI for Claude.")
        == "You are a helpful AI assistant."
    )
    # 保留用户其他实质 instructions
    custom = "You are Claude Code, Anthropic's official CLI for Claude.\n\nPlease answer in Chinese."
    assert strip_client_fingerprints(custom) == "Please answer in Chinese."

    body = sanitize_chat_body(
        {
            "messages": [
                {
                    "role": "developer",
                    "content": "You are Claude Code, Anthropic's official CLI for Claude.\n\nKeep code concise.",
                }
            ]
        },
        enabled=False,
    )
    assert body["messages"][0]["role"] == "system"
    assert "Claude Code" not in body["messages"][0]["content"]
    assert "Keep code concise." in body["messages"][0]["content"]



def test_auth_encrypted_token():
    from agent_bridge.auth import normalize_session

    raw = {
        "auth": {
            "accessToken": {"$wbEncrypted": 1, "envelope": "abc"},
            "refreshToken": {"$wbEncrypted": 1, "envelope": "def"},
        },
        "account": {"uid": "123", "nickname": "test"},
    }
    session = normalize_session(raw)
    assert session["auth"]["isEncrypted"] is True
    assert session["auth"]["accessToken"] == ""
    assert session["account"]["uid"] == "123"


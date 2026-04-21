"""Unit tests for LLM provider adapters using a mocked `requests.Session`."""

from __future__ import annotations

from typing import Any

import pytest
import requests

from lazy_podcast_mate.config.env import EnvConfig
from lazy_podcast_mate.config.schema import RetryConfig, ScriptConfig
from lazy_podcast_mate.script.anthropic import AnthropicRewriter
from lazy_podcast_mate.script.base import ArticleMetadata
from lazy_podcast_mate.script.errors import PermanentError, TransientError
from lazy_podcast_mate.script.openai_compatible import OpenAICompatibleRewriter
from lazy_podcast_mate.script.registry import build_rewriter


class _FakeResponse:
    def __init__(self, status_code: int, json_body: Any | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._json = json_body
        self.text = text

    def json(self) -> Any:
        if self._json is None:
            raise ValueError("no json body")
        return self._json


class _ProgrammableSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls: list[dict] = []

    def post(self, url, *, headers, json, timeout):
        self.calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _fast_retry() -> RetryConfig:
    return RetryConfig(max_attempts=3, initial_delay_seconds=0, backoff_factor=1, max_delay_seconds=0)


def _script_cfg() -> ScriptConfig:
    return ScriptConfig(prompt_version="v1", token_budget=100_000, retry=_fast_retry())


def _md() -> ArticleMetadata:
    return ArticleMetadata(title="Demo", source_format="markdown")


def test_openai_compatible_happy_path():
    session = _ProgrammableSession(
        [_FakeResponse(200, {"choices": [{"message": {"content": "Hello, listeners."}}]})]
    )
    r = OpenAICompatibleRewriter(
        api_key="k", base_url="https://api.example.com/v1", model="gpt-4o",
        config=_script_cfg(), session=session,  # type: ignore[arg-type]
    )
    out = r.rewrite("cleaned text", metadata=_md())
    assert out.script == "Hello, listeners."
    assert out.provider == "openai_compatible"
    assert out.model == "gpt-4o"
    assert session.calls[0]["url"] == "https://api.example.com/v1/chat/completions"
    assert session.calls[0]["headers"]["Authorization"] == "Bearer k"


def test_openai_compatible_retries_on_5xx_then_succeeds():
    session = _ProgrammableSession(
        [
            _FakeResponse(503, text="upstream overloaded"),
            _FakeResponse(200, {"choices": [{"message": {"content": "ok"}}]}),
        ]
    )
    r = OpenAICompatibleRewriter(
        api_key="k", base_url="https://api.example.com/v1", model="m",
        config=_script_cfg(), session=session,  # type: ignore[arg-type]
    )
    out = r.rewrite("x", metadata=_md())
    assert out.script == "ok"
    assert len(session.calls) == 2


def test_openai_compatible_retries_on_network_then_exhausts():
    cfg = _script_cfg()
    session = _ProgrammableSession(
        [
            requests.ConnectionError("boom"),
            requests.ConnectionError("boom"),
            requests.ConnectionError("boom"),
        ]
    )
    r = OpenAICompatibleRewriter(
        api_key="k", base_url="https://api.example.com/v1", model="m",
        config=cfg, session=session,  # type: ignore[arg-type]
    )
    with pytest.raises(TransientError):
        r.rewrite("x", metadata=_md())
    assert len(session.calls) == 3


def test_openai_compatible_permanent_on_400():
    session = _ProgrammableSession([_FakeResponse(400, text="bad request")])
    r = OpenAICompatibleRewriter(
        api_key="k", base_url="https://api.example.com/v1", model="m",
        config=_script_cfg(), session=session,  # type: ignore[arg-type]
    )
    with pytest.raises(PermanentError):
        r.rewrite("x", metadata=_md())


def test_openai_compatible_default_sends_temperature():
    """Existing chat models: temperature should be in the request body."""
    session = _ProgrammableSession(
        [_FakeResponse(200, {"choices": [{"message": {"content": "ok"}}]})]
    )
    r = OpenAICompatibleRewriter(
        api_key="k", base_url="https://api.example.com/v1", model="gpt-4o",
        config=_script_cfg(), session=session,  # type: ignore[arg-type]
    )
    r.rewrite("x", metadata=_md())
    body = session.calls[0]["json"]
    assert body["temperature"] == 0.5
    assert "top_p" not in body
    assert "max_tokens" not in body


def test_openai_compatible_omits_temperature_when_none():
    """Reasoning models (claude-opus-4-7, o1, o3) reject `temperature` —
    setting it to None in config must drop the field from the request body.
    """
    session = _ProgrammableSession(
        [_FakeResponse(200, {"choices": [{"message": {"content": "ok"}}]})]
    )
    cfg = ScriptConfig(
        prompt_version="v1",
        token_budget=100_000,
        retry=_fast_retry(),
        temperature=None,
        top_p=None,
        max_tokens=None,
    )
    r = OpenAICompatibleRewriter(
        api_key="k", base_url="https://api.example.com/v1", model="claude-opus-4-7",
        config=cfg, session=session,  # type: ignore[arg-type]
    )
    r.rewrite("x", metadata=_md())
    body = session.calls[0]["json"]
    assert "temperature" not in body
    assert "top_p" not in body
    assert "max_tokens" not in body
    # Core request shape is preserved.
    assert body["model"] == "claude-opus-4-7"
    assert body["messages"][0]["role"] == "system"


def test_anthropic_omits_temperature_when_none_keeps_max_tokens():
    """Anthropic requires max_tokens, so the adapter must always send it,
    but `temperature` / `top_p` must still be droppable.
    """
    session = _ProgrammableSession(
        [_FakeResponse(200, {"content": [{"type": "text", "text": "ok"}]})]
    )
    cfg = ScriptConfig(
        prompt_version="v1",
        token_budget=100_000,
        retry=_fast_retry(),
        temperature=None,
        top_p=None,
        max_tokens=None,  # config-level; adapter ctor default should kick in.
    )
    r = AnthropicRewriter(
        api_key="k", model="claude-opus-4-7",
        config=cfg, session=session,  # type: ignore[arg-type]
    )
    r.rewrite("x", metadata=_md())
    body = session.calls[0]["json"]
    assert "temperature" not in body
    assert "top_p" not in body
    assert body["max_tokens"] == 4096  # ctor default


def test_openai_compatible_empty_response_is_permanent():
    session = _ProgrammableSession(
        [_FakeResponse(200, {"choices": [{"message": {"content": "   "}}]})]
    )
    r = OpenAICompatibleRewriter(
        api_key="k", base_url="https://api.example.com/v1", model="m",
        config=_script_cfg(), session=session,  # type: ignore[arg-type]
    )
    with pytest.raises(PermanentError):
        r.rewrite("x", metadata=_md())


def test_openai_compatible_strips_emoji_in_output():
    session = _ProgrammableSession(
        [_FakeResponse(200, {"choices": [{"message": {"content": "Great stuff 🎉!!!"}}]})]
    )
    r = OpenAICompatibleRewriter(
        api_key="k", base_url="https://api.example.com/v1", model="m",
        config=_script_cfg(), session=session,  # type: ignore[arg-type]
    )
    out = r.rewrite("x", metadata=_md())
    assert "🎉" not in out.script
    assert "!!" not in out.script


def test_anthropic_happy_path():
    session = _ProgrammableSession(
        [_FakeResponse(200, {"content": [{"type": "text", "text": "Hello, listeners."}]})]
    )
    r = AnthropicRewriter(
        api_key="k", model="claude-3-5-sonnet-20241022",
        config=_script_cfg(), session=session,  # type: ignore[arg-type]
    )
    out = r.rewrite("x", metadata=_md())
    assert out.script == "Hello, listeners."
    assert session.calls[0]["headers"]["x-api-key"] == "k"
    assert session.calls[0]["url"].endswith("/v1/messages")


def test_registry_dispatches_to_each_provider():
    cfg = _script_cfg()
    openai_env = EnvConfig(
        llm_provider="openai_compatible", llm_api_key="k", llm_base_url="https://x/v1",
        llm_model="m", tts_provider=None, tts_api_key=None, tts_region=None,
        tts_app_id=None, tts_cluster=None, tts_base_url=None, lpm_config_path=None,
    )
    assert build_rewriter(openai_env, cfg).provider_name == "openai_compatible"

    anthropic_env = EnvConfig(
        llm_provider="anthropic", llm_api_key="k", llm_base_url=None, llm_model="m",
        tts_provider=None, tts_api_key=None, tts_region=None, tts_app_id=None,
        tts_cluster=None, tts_base_url=None, lpm_config_path=None,
    )
    assert build_rewriter(anthropic_env, cfg).provider_name == "anthropic"

    domestic_env = EnvConfig(
        llm_provider="domestic", llm_api_key="k", llm_base_url="https://y/v1",
        llm_model="m", tts_provider=None, tts_api_key=None, tts_region=None,
        tts_app_id=None, tts_cluster=None, tts_base_url=None, lpm_config_path=None,
    )
    assert build_rewriter(domestic_env, cfg).provider_name == "domestic"

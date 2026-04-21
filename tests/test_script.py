"""Tests for the script-rewriting stage."""

from __future__ import annotations

import pytest

from lazy_podcast_mate.config.schema import RetryConfig, ScriptConfig
from lazy_podcast_mate.script.base import ArticleMetadata, RewriteResult, ScriptRewriter
from lazy_podcast_mate.script.budget import check_token_budget
from lazy_podcast_mate.script.errors import (
    PermanentError,
    TokenBudgetExceededError,
    TransientError,
)
from lazy_podcast_mate.script.persona import enforce_persona
from lazy_podcast_mate.script.retry import retry_call
from lazy_podcast_mate.script.stage import run_script_stage


class _FakeRewriter(ScriptRewriter):
    provider_name = "fake"

    def __init__(self, outputs: list[str]) -> None:
        self._outputs = list(outputs)
        self.calls = 0

    def rewrite(self, cleaned_text: str, *, metadata: ArticleMetadata) -> RewriteResult:
        self.calls += 1
        value = self._outputs.pop(0)
        if isinstance(value, Exception):
            raise value
        return RewriteResult(
            script=value,
            provider=self.provider_name,
            model="fake-1",
            prompt_version="v1",
        )


def _md() -> ArticleMetadata:
    return ArticleMetadata(title="t", source_format="markdown")


def test_persona_strips_emoji_and_exclamations():
    result = enforce_persona("Hello 🎉 world!!! Keep going！！！")
    assert "🎉" not in result
    assert "!!" not in result
    assert "！！" not in result
    assert "Hello" in result
    assert "!" in result  # a single exclamation still allowed


def test_token_budget_pre_check():
    check_token_budget("short", budget=1000)
    with pytest.raises(TokenBudgetExceededError):
        check_token_budget("x" * 10000, budget=100)


def test_retry_recovers_from_transient_failure():
    cfg = RetryConfig(max_attempts=3, initial_delay_seconds=0, backoff_factor=1, max_delay_seconds=0)
    attempts = {"n": 0}

    def flaky() -> str:
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise TransientError("boom")
        return "ok"

    assert retry_call(flaky, config=cfg, label="t", sleep=lambda _x: None) == "ok"
    assert attempts["n"] == 2


def test_retry_raises_after_budget():
    cfg = RetryConfig(max_attempts=2, initial_delay_seconds=0, backoff_factor=1, max_delay_seconds=0)

    def always_fail() -> str:
        raise TransientError("nope")

    with pytest.raises(TransientError):
        retry_call(always_fail, config=cfg, label="t", sleep=lambda _x: None)


def test_retry_permanent_error_propagates_immediately():
    cfg = RetryConfig(max_attempts=5, initial_delay_seconds=0, backoff_factor=1, max_delay_seconds=0)
    attempts = {"n": 0}

    def bad() -> str:
        attempts["n"] += 1
        raise PermanentError("bad key")

    with pytest.raises(PermanentError):
        retry_call(bad, config=cfg, label="t", sleep=lambda _x: None)
    assert attempts["n"] == 1


def test_run_script_stage_happy_path():
    cfg = ScriptConfig(token_budget=10_000)
    rewriter = _FakeRewriter(outputs=["intro.\nbody.\nclosing."])
    result = run_script_stage("cleaned text", metadata=_md(), rewriter=rewriter, token_budget=cfg.token_budget)
    assert "intro" in result.script


def test_run_script_stage_budget_fails_before_call():
    cfg = ScriptConfig(token_budget=10)
    rewriter = _FakeRewriter(outputs=["never used"])
    with pytest.raises(TokenBudgetExceededError):
        run_script_stage("x" * 100, metadata=_md(), rewriter=rewriter, token_budget=cfg.token_budget)
    assert rewriter.calls == 0

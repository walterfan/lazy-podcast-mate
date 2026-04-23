"""Anthropic Messages API adapter."""

from __future__ import annotations

import logging
from typing import Callable

import requests

from ..config.env import EnvConfig
from ..config.schema import ScriptConfig
from .base import ArticleMetadata, RewriteResult, ScriptRewriter
from .errors import PermanentError, TransientError
from .persona import enforce_persona
from .prompt_builder import build_user_message, render_system_prompt
from .retry import retry_call

log = logging.getLogger(__name__)

_TRANSIENT_STATUS = {408, 409, 425, 429, 500, 502, 503, 504, 529}
_ANTHROPIC_VERSION = "2023-06-01"


class AnthropicRewriter(ScriptRewriter):
    provider_name = "anthropic"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        config: ScriptConfig,
        base_url: str = "https://api.anthropic.com",
        max_tokens: int = 4096,
        timeout_seconds: float | None = None,
        session: requests.Session | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._config = config
        self._base_url = base_url.rstrip("/")
        self._max_tokens = max_tokens
        self._timeout = (
            config.request_timeout_seconds if timeout_seconds is None else timeout_seconds
        )
        self._session = session or requests.Session()

    @classmethod
    def from_env(cls, env: EnvConfig, config: ScriptConfig) -> "AnthropicRewriter":
        assert env.llm_api_key and env.llm_model
        return cls(
            api_key=env.llm_api_key,
            model=env.llm_model,
            config=config,
            base_url=env.llm_base_url or "https://api.anthropic.com",
            timeout_seconds=config.request_timeout_seconds,
        )

    def rewrite(
        self,
        cleaned_text: str,
        *,
        metadata: ArticleMetadata,
        on_delta: Callable[[str], None] | None = None,
    ) -> RewriteResult:
        system_prompt = render_system_prompt(self._config.prompt_version, metadata)
        user_message = build_user_message(cleaned_text)

        body: dict = {
            "model": self._model,
            # Anthropic requires max_tokens; fall back to ctor default if unset.
            "max_tokens": self._config.max_tokens or self._max_tokens,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_message}],
        }
        if self._config.temperature is not None:
            body["temperature"] = self._config.temperature
        if self._config.top_p is not None:
            body["top_p"] = self._config.top_p

        def call() -> str:
            try:
                response = self._session.post(
                    f"{self._base_url}/v1/messages",
                    headers={
                        "x-api-key": self._api_key,
                        "anthropic-version": _ANTHROPIC_VERSION,
                        "Content-Type": "application/json",
                    },
                    json=body,
                    timeout=self._timeout,
                )
            except requests.RequestException as exc:
                raise TransientError(f"network error: {exc}") from exc

            if response.status_code in _TRANSIENT_STATUS:
                raise TransientError(
                    f"anthropic returned HTTP {response.status_code}: {response.text[:200]}"
                )
            if response.status_code >= 400:
                raise PermanentError(
                    f"anthropic returned HTTP {response.status_code}: {response.text[:500]}"
                )

            try:
                payload = response.json()
                content_blocks = payload["content"]
                text_parts = [b["text"] for b in content_blocks if b.get("type") == "text"]
            except (ValueError, KeyError, TypeError) as exc:
                raise PermanentError(f"unexpected anthropic response: {exc}") from exc

            joined = "".join(text_parts).strip()
            if not joined:
                raise PermanentError("anthropic returned an empty response")
            return joined

        script = retry_call(
            call,
            config=self._config.retry,
            label=f"script.{self.provider_name}",
        )
        script = enforce_persona(script).strip()
        log.info(
            "script stage succeeded",
            extra={
                "prompt_version": self._config.prompt_version,
                "provider": self.provider_name,
                "model": self._model,
            },
        )
        return RewriteResult(
            script=script,
            provider=self.provider_name,
            model=self._model,
            prompt_version=self._config.prompt_version,
        )

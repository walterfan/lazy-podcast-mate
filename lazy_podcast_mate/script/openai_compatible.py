"""OpenAI-compatible chat-completions adapter (OpenAI, OpenRouter, etc.)."""

from __future__ import annotations

import logging

import requests

from ..config.env import EnvConfig
from ..config.schema import ScriptConfig
from .base import ArticleMetadata, RewriteResult, ScriptRewriter
from .errors import PermanentError, TransientError
from .persona import enforce_persona
from .prompt_builder import build_user_message, render_system_prompt
from .retry import retry_call

log = logging.getLogger(__name__)

_TRANSIENT_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}


class OpenAICompatibleRewriter(ScriptRewriter):
    provider_name = "openai_compatible"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        config: ScriptConfig,
        timeout_seconds: float = 60.0,
        session: requests.Session | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._config = config
        self._timeout = timeout_seconds
        self._session = session or requests.Session()

    @classmethod
    def from_env(cls, env: EnvConfig, config: ScriptConfig) -> "OpenAICompatibleRewriter":
        assert env.llm_api_key and env.llm_base_url and env.llm_model
        return cls(
            api_key=env.llm_api_key,
            base_url=env.llm_base_url,
            model=env.llm_model,
            config=config,
        )

    def rewrite(self, cleaned_text: str, *, metadata: ArticleMetadata) -> RewriteResult:
        system_prompt = render_system_prompt(self._config.prompt_version, metadata)
        user_message = build_user_message(cleaned_text)

        body: dict = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        }
        if self._config.temperature is not None:
            body["temperature"] = self._config.temperature
        if self._config.top_p is not None:
            body["top_p"] = self._config.top_p
        if self._config.max_tokens is not None:
            body["max_tokens"] = self._config.max_tokens

        def call() -> str:
            try:
                response = self._session.post(
                    f"{self._base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                    timeout=self._timeout,
                )
            except requests.RequestException as exc:
                raise TransientError(f"network error: {exc}") from exc

            if response.status_code in _TRANSIENT_STATUS:
                raise TransientError(
                    f"{self._base_url} returned HTTP {response.status_code}: {response.text[:200]}"
                )
            if response.status_code >= 400:
                raise PermanentError(
                    f"{self._base_url} returned HTTP {response.status_code}: {response.text[:500]}"
                )

            try:
                payload = response.json()
                content = payload["choices"][0]["message"]["content"]
            except (ValueError, KeyError, IndexError, TypeError) as exc:
                raise PermanentError(
                    f"unexpected response shape from {self._base_url}: {exc}"
                ) from exc

            if not isinstance(content, str) or not content.strip():
                raise PermanentError("LLM returned an empty response")
            return content

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

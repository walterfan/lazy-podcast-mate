"""OpenAI-compatible chat-completions adapter (OpenAI, OpenRouter, etc.)."""

from __future__ import annotations

import json
import logging
from contextlib import nullcontext
from typing import Callable

import httpx
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
        timeout_seconds: float | None = None,
        session: requests.Session | None = None,
        stream_client: httpx.Client | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._config = config
        self._timeout = (
            config.request_timeout_seconds if timeout_seconds is None else timeout_seconds
        )
        self._session = session or requests.Session()
        self._stream_client = stream_client

    @classmethod
    def from_env(cls, env: EnvConfig, config: ScriptConfig) -> "OpenAICompatibleRewriter":
        assert env.llm_api_key and env.llm_base_url and env.llm_model
        return cls(
            api_key=env.llm_api_key,
            base_url=env.llm_base_url,
            model=env.llm_model,
            config=config,
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
            if self._config.stream:
                return self._stream_rewrite(body, on_delta=on_delta)
            return self._non_stream_rewrite(body)

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

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def _non_stream_rewrite(self, body: dict) -> str:
        try:
            response = self._session.post(
                f"{self._base_url}/chat/completions",
                headers=self._headers(),
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

    def _stream_rewrite(self, body: dict, *, on_delta: Callable[[str], None] | None) -> str:
        stream_body = dict(body)
        stream_body["stream"] = True
        try:
            client_cm = (
                nullcontext(self._stream_client)
                if self._stream_client is not None
                else httpx.Client()
            )
            with client_cm as client:
                with client.stream(
                    "POST",
                    f"{self._base_url}/chat/completions",
                    headers=self._headers(),
                    json=stream_body,
                    timeout=httpx.Timeout(
                        connect=10.0,
                        read=self._timeout,
                        write=30.0,
                        pool=30.0,
                    ),
                ) as response:
                    if response.status_code in _TRANSIENT_STATUS:
                        raise TransientError(
                            f"{self._base_url} returned HTTP {response.status_code}: "
                            f"{self._read_stream_error_text(response)[:200]}"
                        )
                    if response.status_code >= 400:
                        raise PermanentError(
                            f"{self._base_url} returned HTTP {response.status_code}: "
                            f"{self._read_stream_error_text(response)[:500]}"
                        )

                    parts: list[str] = []
                    for raw_line in response.iter_lines():
                        line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
                        if not line or not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            payload = json.loads(data)
                        except ValueError as exc:
                            raise PermanentError(
                                f"unexpected streaming response from {self._base_url}: {exc}"
                            ) from exc
                        delta = self._extract_stream_delta(payload)
                        if delta:
                            parts.append(delta)
                            if on_delta is not None:
                                on_delta(delta)
        except httpx.RequestError as exc:
            raise TransientError(f"network error: {exc}") from exc

        content = "".join(parts)
        if not content.strip():
            raise PermanentError("LLM returned an empty streamed response")
        return content

    @staticmethod
    def _extract_stream_delta(payload: dict) -> str:
        try:
            choice = payload["choices"][0]
        except (KeyError, IndexError, TypeError) as exc:
            raise PermanentError(f"unexpected streaming response shape: {exc}") from exc

        delta = choice.get("delta", {})
        content = delta.get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            text_parts = []
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str):
                        text_parts.append(text)
            return "".join(text_parts)
        return ""

    @staticmethod
    def _read_stream_error_text(response: object) -> str:
        read = getattr(response, "read", None)
        if callable(read):
            try:
                read()
            except Exception:
                pass
        text = getattr(response, "text", "")
        return text if isinstance(text, str) else str(text)

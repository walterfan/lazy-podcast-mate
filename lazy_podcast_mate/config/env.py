"""Load secrets and endpoints from `.env` / environment variables.

Design: `.env` is loaded exactly once via `python-dotenv`. Everything else in
the package reads from `EnvConfig`. Secrets NEVER come from `config.yaml`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

SUPPORTED_LLM_PROVIDERS = ("openai_compatible", "anthropic", "domestic")
SUPPORTED_TTS_PROVIDERS = ("volcano", "azure", "cosyvoice")


@dataclass(frozen=True)
class EnvConfig:
    """Typed view over the environment variables used by the pipeline."""

    llm_provider: str | None
    llm_api_key: str | None
    llm_base_url: str | None
    llm_model: str | None

    tts_provider: str | None
    tts_api_key: str | None
    tts_region: str | None
    tts_app_id: str | None
    tts_cluster: str | None
    tts_base_url: str | None

    lpm_config_path: str | None

    # The set of raw secret values for log redaction.
    secret_values: frozenset[str] = field(default_factory=frozenset)

    @property
    def non_empty_secret_values(self) -> frozenset[str]:
        return frozenset(v for v in self.secret_values if v)


def _get(name: str) -> str | None:
    value = os.environ.get(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def load_env(*, dotenv_path: str | os.PathLike[str] | None = None) -> EnvConfig:
    """Load `.env` (if present) and return a typed `EnvConfig`.

    `dotenv_path` is mainly for tests. In production, the default
    discovery (nearest `.env`) is used.
    """
    if dotenv_path is not None:
        load_dotenv(dotenv_path=Path(dotenv_path), override=False)
    else:
        load_dotenv(override=False)

    cfg = EnvConfig(
        llm_provider=_get("LLM_PROVIDER"),
        llm_api_key=_get("LLM_API_KEY"),
        llm_base_url=_get("LLM_BASE_URL"),
        llm_model=_get("LLM_MODEL"),
        tts_provider=_get("TTS_PROVIDER"),
        tts_api_key=_get("TTS_API_KEY"),
        tts_region=_get("TTS_REGION"),
        tts_app_id=_get("TTS_APP_ID"),
        tts_cluster=_get("TTS_CLUSTER"),
        tts_base_url=_get("TTS_BASE_URL"),
        lpm_config_path=_get("LPM_CONFIG_PATH"),
        secret_values=frozenset(
            v
            for v in (
                _get("LLM_API_KEY"),
                _get("TTS_API_KEY"),
                _get("TTS_APP_ID"),
            )
            if v
        ),
    )
    return cfg

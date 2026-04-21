"""Map `LLM_PROVIDER` to a concrete `ScriptRewriter` factory."""

from __future__ import annotations

from ..config.env import EnvConfig
from ..config.schema import ScriptConfig
from .anthropic import AnthropicRewriter
from .base import ScriptRewriter
from .domestic import DomesticRewriter
from .errors import PermanentError
from .openai_compatible import OpenAICompatibleRewriter


def build_rewriter(env: EnvConfig, config: ScriptConfig) -> ScriptRewriter:
    provider = (env.llm_provider or "").lower()
    if provider == "openai_compatible":
        return OpenAICompatibleRewriter.from_env(env, config)
    if provider == "anthropic":
        return AnthropicRewriter.from_env(env, config)
    if provider == "domestic":
        return DomesticRewriter.from_env(env, config)
    raise PermanentError(f"unsupported LLM_PROVIDER: {provider!r}")

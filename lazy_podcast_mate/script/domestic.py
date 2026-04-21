"""Adapter for domestic commercial LLMs that expose an OpenAI-compatible endpoint.

Qwen (DashScope), Zhipu AI (GLM), Doubao, Moonshot, DeepSeek all offer an
OpenAI-compatible `/chat/completions` URL, so we reuse the same wire format
as `OpenAICompatibleRewriter` and only override the provider label so logs
are accurate.
"""

from __future__ import annotations

from .openai_compatible import OpenAICompatibleRewriter


class DomesticRewriter(OpenAICompatibleRewriter):
    provider_name = "domestic"

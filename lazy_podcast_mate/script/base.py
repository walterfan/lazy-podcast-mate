"""Abstract interface for LLM-backed script rewriters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ArticleMetadata:
    title: str
    source_format: str


@dataclass(frozen=True)
class RewriteResult:
    script: str
    provider: str
    model: str
    prompt_version: str


class ScriptRewriter(Protocol):
    """Rewrite cleaned article text into a spoken podcast script."""

    provider_name: str

    def rewrite(
        self,
        cleaned_text: str,
        *,
        metadata: ArticleMetadata,
    ) -> RewriteResult:
        ...

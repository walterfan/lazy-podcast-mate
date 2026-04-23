"""Top-level script stage: budget check + rewrite + persona enforcement."""

from __future__ import annotations

from typing import Callable

from .base import ArticleMetadata, RewriteResult, ScriptRewriter
from .budget import check_token_budget


def run_script_stage(
    cleaned_text: str,
    *,
    metadata: ArticleMetadata,
    rewriter: ScriptRewriter,
    token_budget: int,
    on_delta: Callable[[str], None] | None = None,
) -> RewriteResult:
    check_token_budget(cleaned_text, budget=token_budget)
    if on_delta is None:
        return rewriter.rewrite(cleaned_text, metadata=metadata)
    return rewriter.rewrite(cleaned_text, metadata=metadata, on_delta=on_delta)

"""Top-level script stage: budget check + rewrite + persona enforcement."""

from __future__ import annotations

from .base import ArticleMetadata, RewriteResult, ScriptRewriter
from .budget import check_token_budget


def run_script_stage(
    cleaned_text: str,
    *,
    metadata: ArticleMetadata,
    rewriter: ScriptRewriter,
    token_budget: int,
) -> RewriteResult:
    check_token_budget(cleaned_text, budget=token_budget)
    return rewriter.rewrite(cleaned_text, metadata=metadata)

"""Simple token-budget pre-check."""

from __future__ import annotations

from .errors import TokenBudgetExceededError


def estimate_tokens(text: str) -> int:
    """Very rough: ~0.5 tokens per character (covers both CJK and Latin).

    This is intentionally conservative. The purpose is to fail fast on
    clearly oversized inputs before we spend a provider call.
    """
    return max(1, (len(text) + 1) // 2)


def check_token_budget(text: str, *, budget: int) -> None:
    estimated = estimate_tokens(text)
    if estimated > budget:
        raise TokenBudgetExceededError(
            f"cleaned article is approximately {estimated} tokens, "
            f"exceeds configured token_budget={budget}. "
            "Shorten the article or raise `script.token_budget` in config.yaml."
        )

"""Script-rewriting errors."""

from __future__ import annotations


class ScriptError(Exception):
    """Raised when the LLM stage cannot complete."""


class TransientError(ScriptError):
    """Retryable LLM failure (network / 429 / 5xx)."""


class PermanentError(ScriptError):
    """Non-retryable LLM failure (4xx other than 429, invalid response)."""


class TokenBudgetExceededError(ScriptError):
    """Cleaned article exceeds the configured token budget."""

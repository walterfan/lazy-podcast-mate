"""Compose cleaning steps into a single deterministic pipeline."""

from __future__ import annotations

from ..config.schema import CleaningConfig
from ..ingestion.models import Article
from ..ingestion.placeholders import substitute_labels
from .terms import apply_terms
from .whitespace import normalise_whitespace


def clean_article(article: Article, config: CleaningConfig) -> str:
    """Return the cleaned speakable text for `article`.

    Placeholder tokens emitted by the ingestion layer (``[[LPM:code:1]]``,
    ``[[LPM:table:1]]`` …) are substituted with the short human-readable
    labels that the LLM should see (e.g. ``[此处有一段 Python 代码示例]``).

    The output is deterministic given the same ``article`` and ``config``.
    """
    text = article.body
    text = substitute_labels(text, article.placeholders)
    text = normalise_whitespace(text)
    text = apply_terms(text, config.terms)
    text = normalise_whitespace(text)
    return text

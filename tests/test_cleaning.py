"""Tests for cleaning."""

from __future__ import annotations

from lazy_podcast_mate.cleaning.cleaner import clean_article
from lazy_podcast_mate.cleaning.terms import apply_terms
from lazy_podcast_mate.cleaning.whitespace import normalise_whitespace
from lazy_podcast_mate.config.schema import CleaningConfig, TermEntry
from lazy_podcast_mate.ingestion.models import Article


def _article(body: str) -> Article:
    return Article(
        title="t",
        body=body,
        source_path="/tmp/x.md",
        source_format="markdown",
        detected_encoding="utf-8",
    )


def test_whitespace_collapses_blank_lines():
    out = normalise_whitespace("para one.\n\n\n\npara two.")
    assert out == "para one.\n\npara two."


def test_whitespace_repairs_mid_sentence_break():
    out = normalise_whitespace("Hello world\nthis should join.")
    assert out == "Hello world this should join."


def test_whitespace_keeps_separate_sentences():
    out = normalise_whitespace("One sentence.\nAnother sentence.")
    # first line terminates, so they stay on separate lines
    assert out == "One sentence.\nAnother sentence."


def test_term_dictionary_applied_with_word_boundary():
    entries = [TermEntry(from_="K8s", to="Kubernetes", case_sensitive=True, word_boundary=True)]
    assert apply_terms("run K8s cluster", entries) == "run Kubernetes cluster"
    # substring doesn't match when word_boundary is True
    assert apply_terms("K8sbook", entries) == "K8sbook"


def test_term_dictionary_case_insensitive():
    entries = [TermEntry(from_="api", to="接口", case_sensitive=False, word_boundary=True)]
    assert apply_terms("call the API.", entries) == "call the 接口."


def test_empty_dictionary_noop():
    assert apply_terms("hello world", []) == "hello world"


def test_cleaner_is_deterministic():
    article = _article(
        "Hello world\nthis should join.\n\n\nUse K8s and the API today.\n"
    )
    cfg = CleaningConfig(
        terms=[
            TermEntry(from_="K8s", to="Kubernetes"),
            TermEntry(from_="API", to="接口", case_sensitive=True, word_boundary=True),
        ]
    )
    a = clean_article(article, cfg)
    b = clean_article(article, cfg)
    assert a == b
    assert "Kubernetes" in a
    assert "接口" in a


def test_cleaner_preserves_terminated_paragraphs():
    article = _article("第一段。\n\n第二段。")
    cfg = CleaningConfig(terms=[])
    assert clean_article(article, cfg) == "第一段。\n\n第二段。"


def test_cleaner_substitutes_placeholder_tokens_with_labels():
    """Ingestion emits opaque [[LPM:...]] tokens; the cleaner must turn
    them into the short natural-language labels that go to the LLM —
    raw tokens must never leak into the LLM prompt.
    """
    from lazy_podcast_mate.ingestion.models import PlaceholderRef

    body = (
        "First paragraph introduces the architecture.\n\n"
        "[[LPM:code:1]]\n\n"
        "Then the article compares providers.\n\n"
        "[[LPM:table:1]]\n\n"
        "Closing paragraph."
    )
    article = Article(
        title="t",
        body=body,
        source_path="/tmp/x.md",
        source_format="markdown",
        detected_encoding="utf-8",
        placeholders=[
            PlaceholderRef(
                kind="code",
                token="[[LPM:code:1]]",
                label="[此处有一段 Python 代码示例]",
                detail="print('x')",
                language="python",
            ),
            PlaceholderRef(
                kind="table",
                token="[[LPM:table:1]]",
                label="[表格：包含 Provider、Free tier 等项对比]",
                detail="| Provider | Free tier |",
            ),
        ],
    )
    out = clean_article(article, CleaningConfig(terms=[]))
    assert "[[LPM:" not in out
    assert "[此处有一段 Python 代码示例]" in out
    assert "[表格：包含 Provider、Free tier 等项对比]" in out


def test_cleaner_drops_orphan_tokens_without_matching_placeholder():
    """If serialisation drops the placeholder list for any reason, any
    leftover tokens in the body must be scrubbed rather than reach the LLM.
    """
    article = _article("Intro.\n\n[[LPM:code:7]]\n\nClosing.")
    out = clean_article(article, CleaningConfig(terms=[]))
    assert "[[LPM:" not in out
    assert "Intro." in out
    assert "Closing." in out

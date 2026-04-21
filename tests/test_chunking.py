"""Tests for chunking."""

from __future__ import annotations

import logging

from lazy_podcast_mate.chunking.chunker import chunk_script
from lazy_podcast_mate.chunking.models import load_manifest, save_manifest
from lazy_podcast_mate.chunking.sentences import split_sentences


def test_sentence_splitter_english():
    assert split_sentences("Hello world. How are you? Great!") == [
        "Hello world.",
        "How are you?",
        "Great!",
    ]


def test_sentence_splitter_chinese():
    assert split_sentences("你好，世界。你好吗？很好！") == [
        "你好，世界。",
        "你好吗？",
        "很好！",
    ]


def test_sentence_splitter_trailing_fragment_kept():
    assert split_sentences("Complete. Incomplete") == ["Complete.", "Incomplete"]


def test_paragraph_aligned_chunks():
    script = "Para one sentence.\n\nPara two sentence.\n\nPara three."
    chunks = chunk_script(script, max_chars=500)
    assert len(chunks) == 3
    assert chunks[0].text == "Para one sentence."
    assert chunks[0].index == 0
    assert chunks[1].index == 1
    assert chunks[0].char_count == len(chunks[0].text)
    assert chunks[0].hash != chunks[1].hash


def test_long_paragraph_split_at_sentences():
    paragraph = "A" * 100 + ". " + "B" * 100 + ". " + "C" * 100 + "."
    chunks = chunk_script(paragraph, max_chars=150)
    assert all(c.char_count <= 150 for c in chunks)
    assert all(c.text.endswith(".") for c in chunks)


def test_oversized_sentence_hard_split_logs_warning(caplog):
    paragraph = "X" * 400  # no terminator at all
    with caplog.at_level(logging.WARNING, logger="lazy_podcast_mate.chunking.chunker"):
        chunks = chunk_script(paragraph, max_chars=100)
    assert sum(len(c.text) for c in chunks) == 400
    assert all(len(c.text) <= 100 for c in chunks)
    assert any("hard-splitting" in r.message for r in caplog.records)


def test_manifest_roundtrip(tmp_path):
    script = "Para one.\n\nPara two that is a bit longer."
    chunks = chunk_script(script, max_chars=500)
    path = tmp_path / "chunks.json"
    save_manifest(chunks, path)
    loaded = load_manifest(path)
    assert loaded == chunks


def test_indexes_are_zero_based_and_contiguous():
    chunks = chunk_script("a.\n\nb.\n\nc.\n\nd.", max_chars=50)
    assert [c.index for c in chunks] == list(range(len(chunks)))

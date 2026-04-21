"""Tests for the output management layer."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from lazy_podcast_mate.config.schema import ID3Config, OutputConfig
from lazy_podcast_mate.output.errors import OutputExistsError
from lazy_podcast_mate.output.filename import render_filename, slugify
from lazy_podcast_mate.output.history import HistoryEntry, append_history
from lazy_podcast_mate.output.writer import place_output


# ---------- slug/filename ----------


def test_slugify_ascii():
    assert slugify("Hello, World!") == "hello-world"
    assert slugify("Multi   spaces --here") == "multi-spaces-here"


def test_slugify_chinese_is_preserved():
    assert slugify("你好 世界") == "你好-世界"


def test_slugify_mixed():
    assert slugify("Vue3 组件实战！") == "vue3-组件实战"


def test_slugify_empty_fallback():
    assert slugify("") == "untitled"
    assert slugify("!!!") == "untitled"


def test_render_filename_date():
    when = datetime(2026, 4, 18, tzinfo=timezone.utc)
    name = render_filename("{date}-{slug}.mp3", title="Hello", run_id="r1", now=when)
    assert name == "2026-04-18-hello.mp3"


def test_render_filename_with_run_id():
    when = datetime(2026, 4, 18, tzinfo=timezone.utc)
    name = render_filename("{run_id}-{slug}.mp3", title="Hi", run_id="r99", now=when)
    assert name == "r99-hi.mp3"


# ---------- writer ----------


def _cfg(directory: Path, on_existing="suffix") -> OutputConfig:
    return OutputConfig(
        directory=str(directory),
        filename_pattern="{date}-{slug}.mp3",
        on_existing=on_existing,  # type: ignore[arg-type]
        id3=ID3Config(),
        run_data_directory=str(directory / "runs"),
        history_file=str(directory / "history.jsonl"),
    )


def test_place_output_suffix_mode_renames(tmp_path: Path):
    src = tmp_path / "src.mp3"
    src.write_bytes(b"first")
    out_dir = tmp_path / "out"
    cfg = _cfg(out_dir, on_existing="suffix")

    first = place_output(src, "episode.mp3", config=cfg)
    assert first == out_dir / "episode.mp3"

    src2 = tmp_path / "src2.mp3"
    src2.write_bytes(b"second")
    second = place_output(src2, "episode.mp3", config=cfg)
    assert second == out_dir / "episode-1.mp3"
    assert (out_dir / "episode.mp3").read_bytes() == b"first"
    assert (out_dir / "episode-1.mp3").read_bytes() == b"second"


def test_place_output_error_mode_refuses(tmp_path: Path):
    src = tmp_path / "src.mp3"
    src.write_bytes(b"hello")
    out_dir = tmp_path / "out"
    cfg = _cfg(out_dir, on_existing="error")

    place_output(src, "ep.mp3", config=cfg)
    with pytest.raises(OutputExistsError):
        place_output(src, "ep.mp3", config=cfg)


# ---------- history ----------


def test_history_append_line_appends_and_parses(tmp_path: Path):
    history = tmp_path / "history.jsonl"
    entry = HistoryEntry(
        run_id="r1",
        source_path="/tmp/a.md",
        output_path="/tmp/out.mp3",
        status="success",
        started_at="2026-04-18T00:00:00+00:00",
        ended_at="2026-04-18T00:00:10+00:00",
        duration_seconds=10.0,
        llm_provider="openai_compatible",
        llm_model="gpt-4o",
        tts_provider="azure",
        tts_voice_id="zh-CN-YunjianNeural",
    )
    append_history(history, entry)
    append_history(history, entry)

    lines = history.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    parsed = json.loads(lines[0])
    assert parsed["status"] == "success"
    assert parsed["run_id"] == "r1"


def test_history_records_failure_entry(tmp_path: Path):
    history = tmp_path / "history.jsonl"
    entry = HistoryEntry(
        run_id="r2",
        source_path="/tmp/a.md",
        output_path=None,
        status="failed",
        started_at="t0",
        ended_at="t1",
        duration_seconds=1.0,
        llm_provider=None,
        llm_model=None,
        tts_provider=None,
        tts_voice_id=None,
        error="ConfigError: LLM_API_KEY missing",
    )
    append_history(history, entry)
    parsed = json.loads(history.read_text(encoding="utf-8").splitlines()[0])
    assert parsed["status"] == "failed"
    assert "LLM_API_KEY" in parsed["error"]


# ---------- id3 (requires ffmpeg-produced MP3, so we test mutagen round-trip on a tiny file) ----------


def test_id3_tags_roundtrip(tmp_path: Path):
    from mutagen.id3 import ID3
    from mutagen.mp3 import MP3, HeaderNotFoundError
    import pytest

    # Create a minimal MP3 by writing ID3 tags into a file that mutagen will accept.
    # We use a pre-existing synthetic MP3 header; if pydub/ffmpeg aren't available
    # to generate one, skip this test.
    import shutil as _shutil
    if _shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg required to produce a valid MP3 for id3 round-trip test")

    from pydub.generators import Sine
    mp3 = tmp_path / "tiny.mp3"
    Sine(440).to_audio_segment(duration=500).export(mp3, format="mp3", bitrate="320k")

    from lazy_podcast_mate.output.id3 import write_id3_tags
    write_id3_tags(
        mp3,
        title="Test Episode",
        config=ID3Config(artist="Alice", album="Demo Album"),
        comment="Hello",
        release_date=datetime(2026, 4, 18, tzinfo=timezone.utc),
    )

    tags = ID3(mp3)
    assert tags.getall("TIT2")[0].text[0] == "Test Episode"
    assert tags.getall("TPE1")[0].text[0] == "Alice"
    assert tags.getall("TALB")[0].text[0] == "Demo Album"
    assert "2026-04-18" in str(tags.getall("TDRC")[0].text[0])
    assert tags.getall("COMM")[0].text[0] == "Hello"

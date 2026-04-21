"""Tests for the loudnorm JSON parser and end-to-end loudness normalisation."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from lazy_podcast_mate.post.errors import PostProductionError
from lazy_podcast_mate.post.loudnorm import _parse_loudnorm_json


FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None


# A realistic ffmpeg-8 stderr sample. Captured from `ffmpeg -loglevel info`
# running `loudnorm=...:print_format=json` against a 1s test tone. The key
# details: the JSON is introduced by a `[Parsed_loudnorm_0 @ 0x...]` line,
# may be followed by more ffmpeg progress noise, and uses stringified floats.
_FFMPEG8_SAMPLE = """
  Metadata:
    encoder         : Lavf62.12.100
  Stream #0:0: Audio: pcm_s16le, 192000 Hz, mono, s16, 3072 kb/s
    Metadata:
      encoder         : Lavc62.28.100 pcm_s16le
[Parsed_loudnorm_0 @ 0xb58c20c00]\x20
{
\t"input_i" : "-21.75",
\t"input_tp" : "-18.06",
\t"input_lra" : "0.00",
\t"input_thresh" : "-31.75",
\t"output_i" : "-16.05",
\t"output_tp" : "-12.31",
\t"output_lra" : "0.00",
\t"output_thresh" : "-26.05",
\t"normalization_type" : "linear",
\t"target_offset" : "0.05"
}
[out#0/null @ 0xb58c20480] video:0KiB audio:375KiB subtitle:0KiB other streams:0KiB
size=N/A time=00:00:01.00 bitrate=N/A speed= 120x
"""


def test_parse_loudnorm_json_from_ffmpeg8_stderr():
    stats = _parse_loudnorm_json(_FFMPEG8_SAMPLE)
    assert stats["input_i"] == "-21.75"
    assert stats["output_i"] == "-16.05"
    assert stats["target_offset"] == "0.05"


def test_parse_loudnorm_json_missing_block_gives_useful_error():
    """If ffmpeg is run with -loglevel error, stderr is empty — the error
    message must point the user at the likely cause rather than just saying
    'could not find JSON'.
    """
    with pytest.raises(PostProductionError) as excinfo:
        _parse_loudnorm_json("")
    assert "loglevel info" in str(excinfo.value)


def test_parse_loudnorm_json_prefers_block_after_marker():
    """If some upstream log line contains a stray '{...}' before the
    loudnorm block, we must still anchor on the Parsed_loudnorm marker and
    return the correct block.
    """
    stderr = (
        "[some_other_filter @ 0x1] { \"junk\": 1 }\n"
        "[Parsed_loudnorm_0 @ 0x2]\n"
        "{\n\t\"input_i\": \"-20.0\",\n\t\"output_i\": \"-16.0\"\n}\n"
    )
    stats = _parse_loudnorm_json(stderr)
    assert stats["input_i"] == "-20.0"
    assert stats["output_i"] == "-16.0"


def test_parse_loudnorm_json_invalid_json_reports_error():
    stderr = "[Parsed_loudnorm_0 @ 0x2]\n{ this is not json }\n"
    with pytest.raises(PostProductionError, match="invalid loudnorm JSON"):
        _parse_loudnorm_json(stderr)


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg not installed")
def test_normalise_loudness_runs_end_to_end(tmp_path: Path):
    """Exercises both loudnorm passes against real ffmpeg to guard against
    future ffmpeg releases changing the log format again.
    """
    from pydub.generators import Sine  # noqa: PLC0415 — only needed here

    from lazy_podcast_mate.post.loudnorm import normalise_loudness

    tone = (
        Sine(440)
        .to_audio_segment(duration=2000)
        .apply_gain(-30)
        .set_channels(2)
        .set_frame_rate(48000)
    )
    out = normalise_loudness(
        tone,
        work_dir=tmp_path,
        target_lufs=-16.0,
        true_peak_dbtp=-1.0,
        tolerance_lu=3.0,
    )
    assert len(out) == 2000

"""Two-pass ffmpeg loudnorm targeting podcast standard."""

from __future__ import annotations

import json
import logging
import math
import re
from pathlib import Path

from pydub import AudioSegment

from .errors import PostProductionError
from .ffmpeg_runner import read_ffmpeg_output, run_ffmpeg, tmp_wav_export

log = logging.getLogger(__name__)


def _safe_float(value: object) -> float:
    """Parse a loudnorm stats value that may be ``"-inf"`` / ``"nan"`` / etc.

    Returns ``-inf`` for unparseable input so callers can fall back.
    """
    try:
        result = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return float("-inf")
    return result

# ffmpeg prints the loudnorm stats block right after a line like
#   [Parsed_loudnorm_0 @ 0x7f8...]
# followed by a JSON object. We anchor on that marker so we never
# accidentally pick up an unrelated JSON-looking fragment elsewhere in the
# log, then do balanced-brace extraction to be robust to whitespace /
# internal braces in future ffmpeg versions.
_LOUDNORM_MARKER_RE = re.compile(r"\[Parsed_loudnorm[^\]]*\]")


def _extract_json_object(text: str, start: int) -> str | None:
    """Return the first balanced ``{...}`` substring starting at or after
    ``start``, or ``None`` if none is found.
    """
    depth = 0
    begin: int | None = None
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "{":
            if begin is None:
                begin = i
            depth += 1
        elif ch == "}" and depth > 0:
            depth -= 1
            if depth == 0 and begin is not None:
                return text[begin : i + 1]
    return None


def _parse_loudnorm_json(stderr: str) -> dict:
    marker = _LOUDNORM_MARKER_RE.search(stderr)
    search_from = marker.end() if marker else 0
    raw = _extract_json_object(stderr, search_from)
    if raw is None:
        raise PostProductionError(
            "could not find loudnorm JSON in ffmpeg output "
            f"(hint: run ffmpeg with '-loglevel info' or higher): {stderr[-500:]}"
        )
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PostProductionError(f"invalid loudnorm JSON: {exc}") from exc


def normalise_loudness(
    audio: AudioSegment,
    *,
    work_dir: Path,
    target_lufs: float,
    true_peak_dbtp: float,
    tolerance_lu: float,
) -> AudioSegment:
    """Run two-pass `loudnorm` and verify the integrated loudness is within
    `tolerance_lu` LU of `target_lufs`. Returns the normalised AudioSegment.
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    src = tmp_wav_export(audio, work_dir / "pre_loudnorm.wav")

    pass1_filter = (
        f"loudnorm=I={target_lufs}:TP={true_peak_dbtp}:LRA=11:print_format=json"
    )
    stats_stderr = read_ffmpeg_output(
        ["-i", str(src), "-af", pass1_filter, "-f", "null", "-"]
    )
    stats = _parse_loudnorm_json(stats_stderr)

    # Silent or near-silent inputs produce input_i="-inf". In that case
    # ffmpeg will reject pass 2 ("Value -inf for parameter 'measured_I'
    # out of range"). Skip normalisation and return the input unchanged
    # with a warning — you can't normalise silence to a target loudness.
    input_i = _safe_float(stats.get("input_i"))
    input_thresh = _safe_float(stats.get("input_thresh"))
    if not math.isfinite(input_i) or not math.isfinite(input_thresh):
        log.warning(
            "loudnorm: input measured as silent (input_i=%s); "
            "skipping pass 2 and returning audio unchanged",
            stats.get("input_i"),
        )
        return audio

    pass2_filter = (
        f"loudnorm=I={target_lufs}:TP={true_peak_dbtp}:LRA=11"
        f":measured_I={stats['input_i']}"
        f":measured_LRA={stats['input_lra']}"
        f":measured_TP={stats['input_tp']}"
        f":measured_thresh={stats['input_thresh']}"
        f":offset={stats.get('target_offset', 0)}"
        ":linear=true:print_format=json"
    )
    dst = work_dir / "post_loudnorm.wav"
    pass2_stderr = read_ffmpeg_output(
        ["-i", str(src), "-af", pass2_filter, "-ar", "48000", str(dst)]
    )

    result = _parse_loudnorm_json(pass2_stderr)
    output_i = _safe_float(result.get("output_i"))
    if not math.isfinite(output_i):
        log.warning(
            "loudnorm pass 2 reported output_i=%s; returning normalised file anyway",
            result.get("output_i"),
        )
        return AudioSegment.from_file(dst)
    if abs(output_i - target_lufs) > tolerance_lu:
        raise PostProductionError(
            f"loudnorm result {output_i:.2f} LUFS is outside tolerance "
            f"{tolerance_lu} LU of target {target_lufs} LUFS"
        )

    return AudioSegment.from_file(dst)

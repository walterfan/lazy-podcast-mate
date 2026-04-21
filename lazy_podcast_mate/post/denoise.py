"""Light noise-reduction via ffmpeg `afftdn`."""

from __future__ import annotations

from pathlib import Path

from pydub import AudioSegment

from .ffmpeg_runner import run_ffmpeg, tmp_wav_export


def denoise_audio(
    audio: AudioSegment,
    *,
    work_dir: Path,
) -> AudioSegment:
    work_dir.mkdir(parents=True, exist_ok=True)
    src = work_dir / "pre_denoise.wav"
    dst = work_dir / "post_denoise.wav"
    tmp_wav_export(audio, src)
    run_ffmpeg(["-i", str(src), "-af", "afftdn=nr=12:nf=-25", str(dst)])
    return AudioSegment.from_file(dst)

"""Top-level post-production pipeline."""

from __future__ import annotations

import logging
from pathlib import Path

from ..config.schema import PostConfig
from .bgm import mix_bgm
from .concat import concat_chunks
from .denoise import denoise_audio
from .export import export_mp3
from .fades import apply_fades
from .loudnorm import normalise_loudness

log = logging.getLogger(__name__)


def run_post_production(
    chunk_paths: list[Path],
    *,
    config: PostConfig,
    inter_chunk_silence_ms: int,
    output_path: Path,
    work_dir: Path,
) -> Path:
    """Run concat → denoise → loudnorm → BGM mix → fades → MP3 export.

    Returns the output path for convenience.
    """
    log.info("post-production: concatenating %d chunks", len(chunk_paths))
    voice = concat_chunks(chunk_paths, silence_ms=inter_chunk_silence_ms)

    if config.denoise:
        log.info("post-production: applying denoise")
        voice = denoise_audio(voice, work_dir=work_dir)

    log.info("post-production: normalising loudness")
    voice = normalise_loudness(
        voice,
        work_dir=work_dir,
        target_lufs=config.loudness_target_lufs,
        true_peak_dbtp=config.loudness_true_peak_dbtp,
        tolerance_lu=config.loudness_tolerance_lu,
    )

    if config.bgm_path:
        bgm_path = Path(config.bgm_path).expanduser()
        log.info("post-production: mixing BGM from %s at ratio %.2f", bgm_path, config.bgm_ratio)
        voice = mix_bgm(voice, bgm_path, ratio=config.bgm_ratio)

    log.info(
        "post-production: applying fades (in=%dms out=%dms)",
        config.fade_in_ms,
        config.fade_out_ms,
    )
    voice = apply_fades(
        voice,
        fade_in_ms=config.fade_in_ms,
        fade_out_ms=config.fade_out_ms,
    )

    log.info("post-production: exporting MP3 to %s", output_path)
    export_mp3(voice, output_path)
    return output_path

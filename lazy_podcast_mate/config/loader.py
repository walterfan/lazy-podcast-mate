"""Config loader: merge env + YAML, validate, and return a typed `AppConfig`.

Only reads behavioural keys from YAML; secrets come from `EnvConfig`.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml

from .env import SUPPORTED_LLM_PROVIDERS, SUPPORTED_TTS_PROVIDERS, EnvConfig
from .errors import ConfigError
from .schema import (
    AppConfig,
    ChunkingConfig,
    CleaningConfig,
    ID3Config,
    LoggingConfig,
    OutputConfig,
    PostConfig,
    RetryConfig,
    ScriptConfig,
    TermEntry,
    TTSConfig,
)

DEFAULT_CONFIG_PATH = Path("config.yaml")

# Keys that look like secrets and must NOT appear in YAML config.
# Match the whole key (case-insensitive), or a key ending in the secret-like
# suffix preceded by `_` or `-`. This avoids flagging innocent keys like
# `token_budget` or `secretly_enabled`.
_SECRET_KEY_PATTERN = re.compile(
    r"""^(
        (api[_-]?key)
        | (access[_-]?token)
        | (auth[_-]?token)
        | (bearer[_-]?token)
        | token
        | secret
        | password
        | (.+[_-](api[_-]?key|token|secret|password))
    )$""",
    re.IGNORECASE | re.VERBOSE,
)

_VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
_VALID_ON_EXISTING = {"error", "suffix"}
_VALID_FAILURE_MODES = {"strict", "lenient"}


def _scan_for_secrets(obj: Any, path: str = "") -> list[str]:
    """Return a list of paths in `obj` whose keys match secret patterns."""
    problems: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            if isinstance(key, str) and _SECRET_KEY_PATTERN.search(key):
                problems.append(
                    f"secret-looking key `{path + key}` found in config.yaml "
                    "(move secrets to environment variables / .env)"
                )
            problems.extend(_scan_for_secrets(value, f"{path}{key}."))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            problems.extend(_scan_for_secrets(item, f"{path}[{i}]."))
    return problems


def _get_section(data: dict, name: str) -> dict:
    section = data.get(name, {}) or {}
    if not isinstance(section, dict):
        raise ConfigError([f"config section `{name}` must be a mapping"])
    return section


def _coerce_retry(raw: dict, prefix: str, problems: list[str]) -> RetryConfig:
    defaults = RetryConfig()
    try:
        return RetryConfig(
            max_attempts=int(raw.get("max_attempts", defaults.max_attempts)),
            initial_delay_seconds=float(
                raw.get("initial_delay_seconds", defaults.initial_delay_seconds)
            ),
            backoff_factor=float(raw.get("backoff_factor", defaults.backoff_factor)),
            max_delay_seconds=float(raw.get("max_delay_seconds", defaults.max_delay_seconds)),
        )
    except (TypeError, ValueError) as exc:
        problems.append(f"{prefix}.retry is invalid: {exc}")
        return defaults


def _build_app_config(raw: dict) -> AppConfig:  # noqa: C901 — validation fan-out is intentional
    problems: list[str] = []

    # Cleaning
    cleaning_raw = _get_section(raw, "cleaning")
    terms: list[TermEntry] = []
    for i, entry in enumerate(cleaning_raw.get("terms", []) or []):
        if not isinstance(entry, dict):
            problems.append(f"cleaning.terms[{i}] must be a mapping")
            continue
        if "from" not in entry or "to" not in entry:
            problems.append(f"cleaning.terms[{i}] must have `from` and `to`")
            continue
        terms.append(
            TermEntry(
                from_=str(entry["from"]),
                to=str(entry["to"]),
                case_sensitive=bool(entry.get("case_sensitive", True)),
                word_boundary=bool(entry.get("word_boundary", True)),
            )
        )
    try:
        cleaning = CleaningConfig(
            max_input_bytes=int(cleaning_raw.get("max_input_bytes", 5_000_000)),
            terms=terms,
        )
        if cleaning.max_input_bytes <= 0:
            problems.append("cleaning.max_input_bytes must be > 0")
    except (TypeError, ValueError) as exc:
        problems.append(f"cleaning is invalid: {exc}")
        cleaning = CleaningConfig()

    # Chunking
    chunking_raw = _get_section(raw, "chunking")
    try:
        chunking = ChunkingConfig(
            max_chars=int(chunking_raw.get("max_chars", 800)),
            inter_chunk_silence_ms=int(chunking_raw.get("inter_chunk_silence_ms", 250)),
        )
        if chunking.max_chars <= 0:
            problems.append("chunking.max_chars must be > 0")
        if chunking.inter_chunk_silence_ms < 0:
            problems.append("chunking.inter_chunk_silence_ms must be >= 0")
    except (TypeError, ValueError) as exc:
        problems.append(f"chunking is invalid: {exc}")
        chunking = ChunkingConfig()

    # Script
    script_raw = _get_section(raw, "script")
    script_retry = _coerce_retry(
        script_raw.get("retry") or {}, prefix="script", problems=problems
    )

    def _optional_number(key: str, default: float | int | None, caster):
        if key not in script_raw:
            return default
        value = script_raw[key]
        if value is None or (isinstance(value, str) and value.strip().lower() == "omit"):
            return None
        try:
            return caster(value)
        except (TypeError, ValueError):
            problems.append(f"script.{key} must be a number, `null`, or 'omit'")
            return default

    temperature = _optional_number("temperature", 0.5, float)
    top_p = _optional_number("top_p", None, float)
    max_tokens = _optional_number("max_tokens", None, int)

    try:
        script = ScriptConfig(
            prompt_version=str(script_raw.get("prompt_version", "v2")),
            token_budget=int(script_raw.get("token_budget", 12000)),
            retry=script_retry,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
        )
        if script.token_budget <= 0:
            problems.append("script.token_budget must be > 0")
        if script.temperature is not None and not (0.0 <= script.temperature <= 2.0):
            problems.append("script.temperature must be within [0.0, 2.0]")
        if script.top_p is not None and not (0.0 <= script.top_p <= 1.0):
            problems.append("script.top_p must be within [0.0, 1.0]")
        if script.max_tokens is not None and script.max_tokens <= 0:
            problems.append("script.max_tokens must be > 0")
    except (TypeError, ValueError) as exc:
        problems.append(f"script is invalid: {exc}")
        script = ScriptConfig()

    # TTS
    tts_raw = _get_section(raw, "tts")
    tts_retry = _coerce_retry(tts_raw.get("retry") or {}, prefix="tts", problems=problems)
    try:
        rate = float(tts_raw.get("rate", 0.92))
    except (TypeError, ValueError):
        rate = 0.92
        problems.append("tts.rate must be a number")
    if not (0.9 <= rate <= 0.95):
        problems.append(f"tts.rate must be within [0.9, 0.95], got {rate}")
    failure_mode = str(tts_raw.get("failure_mode", "strict"))
    if failure_mode not in _VALID_FAILURE_MODES:
        problems.append(
            f"tts.failure_mode must be one of {sorted(_VALID_FAILURE_MODES)}, got {failure_mode!r}"
        )
        failure_mode = "strict"
    try:
        tts = TTSConfig(
            voice_id=str(tts_raw.get("voice_id", "")),
            rate=rate,
            volume=float(tts_raw.get("volume", 1.0)),
            concurrency=int(tts_raw.get("concurrency", 4)),
            retry=tts_retry,
            failure_mode=failure_mode,  # type: ignore[arg-type]
        )
        if tts.concurrency <= 0:
            problems.append("tts.concurrency must be > 0")
        if not tts.voice_id.strip():
            problems.append(
                "tts.voice_id is required — set it in config.yaml "
                "(e.g. 'zh-CN-YunjianNeural' for Azure; see README for other providers)"
            )
    except (TypeError, ValueError) as exc:
        problems.append(f"tts is invalid: {exc}")
        tts = TTSConfig()

    # Post
    post_raw = _get_section(raw, "post")
    try:
        bgm_ratio = float(post_raw.get("bgm_ratio", 0.12))
    except (TypeError, ValueError):
        bgm_ratio = 0.12
        problems.append("post.bgm_ratio must be a number")
    bgm_path = str(post_raw.get("bgm_path", ""))
    if bgm_path and not (0.10 <= bgm_ratio <= 0.15):
        problems.append(
            f"post.bgm_ratio must be within [0.10, 0.15] when bgm_path is set, got {bgm_ratio}"
        )
    try:
        post = PostConfig(
            fade_in_ms=int(post_raw.get("fade_in_ms", 500)),
            fade_out_ms=int(post_raw.get("fade_out_ms", 500)),
            bgm_path=bgm_path,
            bgm_ratio=bgm_ratio,
            loudness_target_lufs=float(post_raw.get("loudness_target_lufs", -16.0)),
            loudness_true_peak_dbtp=float(post_raw.get("loudness_true_peak_dbtp", -1.0)),
            loudness_tolerance_lu=float(post_raw.get("loudness_tolerance_lu", 1.0)),
            denoise=bool(post_raw.get("denoise", True)),
        )
        if post.fade_in_ms < 0 or post.fade_out_ms < 0:
            problems.append("post.fade_in_ms/fade_out_ms must be >= 0")
    except (TypeError, ValueError) as exc:
        problems.append(f"post is invalid: {exc}")
        post = PostConfig()

    # Output
    output_raw = _get_section(raw, "output")
    id3_raw = output_raw.get("id3") or {}
    if not isinstance(id3_raw, dict):
        problems.append("output.id3 must be a mapping")
        id3_raw = {}
    on_existing = str(output_raw.get("on_existing", "suffix"))
    if on_existing not in _VALID_ON_EXISTING:
        problems.append(
            f"output.on_existing must be one of {sorted(_VALID_ON_EXISTING)}, got {on_existing!r}"
        )
        on_existing = "suffix"
    try:
        output = OutputConfig(
            directory=str(output_raw.get("directory", "./data/output")),
            filename_pattern=str(output_raw.get("filename_pattern", "{date}-{slug}.mp3")),
            on_existing=on_existing,  # type: ignore[arg-type]
            id3=ID3Config(
                artist=str(id3_raw.get("artist", "Lazy Podcast Mate")),
                album=str(id3_raw.get("album", "Lazy Podcast Mate")),
            ),
            run_data_directory=str(output_raw.get("run_data_directory", "./data/runs")),
            history_file=str(output_raw.get("history_file", "./data/history.jsonl")),
        )
        if not output.directory:
            problems.append("output.directory is required")
    except (TypeError, ValueError) as exc:
        problems.append(f"output is invalid: {exc}")
        output = OutputConfig()

    # Logging
    logging_raw = _get_section(raw, "logging")
    level = str(logging_raw.get("level", "INFO")).upper()
    if level not in _VALID_LOG_LEVELS:
        problems.append(
            f"logging.level must be one of {sorted(_VALID_LOG_LEVELS)}, got {level!r}"
        )
        level = "INFO"
    log_cfg = LoggingConfig(level=level)

    if problems:
        raise ConfigError(problems)

    return AppConfig(
        cleaning=cleaning,
        chunking=chunking,
        script=script,
        tts=tts,
        post=post,
        output=output,
        logging=log_cfg,
    )


def load_yaml(path: Path) -> dict:
    if not path.exists():
        raise ConfigError([f"config file not found: {path}"])
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except yaml.YAMLError as exc:
        raise ConfigError([f"failed to parse {path}: {exc}"]) from exc
    if not isinstance(data, dict):
        raise ConfigError([f"{path} must contain a top-level mapping"])
    return data


def validate_env_requirements(env: EnvConfig) -> list[str]:
    """Check that required env vars are present for the declared providers."""
    problems: list[str] = []

    if not env.llm_provider:
        problems.append("LLM_PROVIDER is required (set in .env)")
    elif env.llm_provider not in SUPPORTED_LLM_PROVIDERS:
        problems.append(
            f"LLM_PROVIDER must be one of {list(SUPPORTED_LLM_PROVIDERS)}, "
            f"got {env.llm_provider!r}"
        )
    else:
        if not env.llm_api_key:
            problems.append("LLM_API_KEY is required")
        if not env.llm_model:
            problems.append("LLM_MODEL is required")
        if env.llm_provider in ("openai_compatible", "domestic") and not env.llm_base_url:
            problems.append(
                f"LLM_BASE_URL is required when LLM_PROVIDER={env.llm_provider!r}"
            )

    if not env.tts_provider:
        problems.append("TTS_PROVIDER is required (set in .env)")
    elif env.tts_provider not in SUPPORTED_TTS_PROVIDERS:
        problems.append(
            f"TTS_PROVIDER must be one of {list(SUPPORTED_TTS_PROVIDERS)}, "
            f"got {env.tts_provider!r}"
        )
    else:
        if not env.tts_api_key:
            problems.append("TTS_API_KEY is required")
        if env.tts_provider == "azure" and not env.tts_region:
            problems.append("TTS_REGION is required when TTS_PROVIDER='azure'")
        if env.tts_provider == "volcano" and (not env.tts_app_id or not env.tts_cluster):
            problems.append(
                "TTS_APP_ID and TTS_CLUSTER are required when TTS_PROVIDER='volcano'"
            )
        if env.tts_provider == "cosyvoice" and not env.tts_base_url:
            problems.append("TTS_BASE_URL is required when TTS_PROVIDER='cosyvoice'")

    return problems


def resolve_config_path(env: EnvConfig) -> Path:
    if env.lpm_config_path:
        return Path(env.lpm_config_path).expanduser().resolve()
    # Search from cwd up; stop at the nearest `config.yaml`.
    cwd = Path.cwd()
    for parent in (cwd, *cwd.parents):
        candidate = parent / "config.yaml"
        if candidate.exists():
            return candidate.resolve()
    return (cwd / DEFAULT_CONFIG_PATH).resolve()


def load_config(
    *,
    env: EnvConfig | None = None,
    config_path: str | os.PathLike[str] | None = None,
    require_env: bool = True,
) -> tuple[AppConfig, EnvConfig]:
    """Load env + YAML, validate, and return `(AppConfig, EnvConfig)`.

    Raises `ConfigError` on any problem, listing every issue at once.
    """
    from .env import load_env  # local import to allow easier testing

    if env is None:
        env = load_env()

    problems: list[str] = []

    # Resolve config path.
    if config_path is not None:
        path = Path(config_path).expanduser().resolve()
    else:
        path = resolve_config_path(env)

    if not path.exists():
        problems.append(f"config file not found: {path}")
        raise ConfigError(problems)

    try:
        raw = load_yaml(path)
    except ConfigError as exc:
        problems.extend(exc.problems)
        raise ConfigError(problems) from exc

    # Reject secrets in YAML.
    problems.extend(_scan_for_secrets(raw))

    if require_env:
        problems.extend(validate_env_requirements(env))

    # Build typed config; this may raise ConfigError with its own problems.
    try:
        app = _build_app_config(raw)
    except ConfigError as exc:
        problems.extend(exc.problems)
        raise ConfigError(problems) from exc

    if problems:
        raise ConfigError(problems)

    return app, env

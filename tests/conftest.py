"""Shared fixtures: isolate environment and cwd per test."""

from __future__ import annotations

import os
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


_ENV_VARS_TO_RESET = (
    "LLM_PROVIDER",
    "LLM_API_KEY",
    "LLM_BASE_URL",
    "LLM_MODEL",
    "TTS_PROVIDER",
    "TTS_API_KEY",
    "TTS_REGION",
    "TTS_APP_ID",
    "TTS_CLUSTER",
    "TTS_BASE_URL",
    "LPM_CONFIG_PATH",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in _ENV_VARS_TO_RESET:
        monkeypatch.delenv(name, raising=False)
    # Prevent load_env() from repopulating env from a real .env on disk
    # (devs often have one in the repo root for manual smoke tests).
    monkeypatch.setattr(
        "lazy_podcast_mate.config.env.load_dotenv",
        lambda *a, **kw: False,
    )
    yield


@pytest.fixture()
def isolated_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def write_minimal_config(path: pathlib.Path) -> None:
    path.write_text(
        """
cleaning:
  max_input_bytes: 1000000
  terms: []
chunking:
  max_chars: 500
  inter_chunk_silence_ms: 200
script:
  prompt_version: v1
  token_budget: 5000
tts:
  voice_id: test-voice
  rate: 0.92
  volume: 1.0
  concurrency: 2
  failure_mode: strict
post:
  fade_in_ms: 300
  fade_out_ms: 300
  bgm_path: ""
  bgm_ratio: 0.12
  loudness_target_lufs: -16.0
  loudness_true_peak_dbtp: -1.0
  loudness_tolerance_lu: 1.0
  denoise: false
output:
  directory: ./out
  filename_pattern: "{date}-{slug}.mp3"
  on_existing: suffix
  id3:
    artist: Tester
    album: Test Album
  run_data_directory: ./runs
  history_file: ./history.jsonl
logging:
  level: INFO
""".lstrip(),
        encoding="utf-8",
    )


def set_valid_env(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("LLM_API_KEY", "sk-test-123")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o")
    monkeypatch.setenv("TTS_PROVIDER", "azure")
    monkeypatch.setenv("TTS_API_KEY", "tts-secret-abc")
    monkeypatch.setenv("TTS_REGION", "eastus")

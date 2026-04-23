"""Tests for the configuration loader."""

from __future__ import annotations

import logging

import pytest

from lazy_podcast_mate.config.env import load_env
from lazy_podcast_mate.config.errors import ConfigError
from lazy_podcast_mate.config.loader import load_config
from lazy_podcast_mate.config.logging import setup_logging

from .conftest import set_valid_env, write_minimal_config


def test_load_config_happy_path(monkeypatch, isolated_cwd):
    set_valid_env(monkeypatch)
    write_minimal_config(isolated_cwd / "config.yaml")

    app, env = load_config(env=load_env())

    assert app.tts.voice_id == "test-voice"
    assert app.output.on_existing == "suffix"
    assert env.llm_api_key == "sk-test-123"
    assert "sk-test-123" in env.non_empty_secret_values


def test_missing_llm_key_fails_fast(monkeypatch, isolated_cwd):
    set_valid_env(monkeypatch)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    write_minimal_config(isolated_cwd / "config.yaml")

    with pytest.raises(ConfigError) as excinfo:
        load_config(env=load_env())

    assert any("LLM_API_KEY" in p for p in excinfo.value.problems)


def test_secret_in_yaml_is_rejected(monkeypatch, isolated_cwd):
    set_valid_env(monkeypatch)
    cfg = isolated_cwd / "config.yaml"
    write_minimal_config(cfg)
    cfg.write_text(cfg.read_text() + "\nllm:\n  api_key: hardcoded\n", encoding="utf-8")

    with pytest.raises(ConfigError) as excinfo:
        load_config(env=load_env())

    assert any("api_key" in p for p in excinfo.value.problems)


def test_lpm_config_path_override(monkeypatch, tmp_path):
    set_valid_env(monkeypatch)
    elsewhere = tmp_path / "somewhere" / "myconfig.yaml"
    elsewhere.parent.mkdir()
    write_minimal_config(elsewhere)
    monkeypatch.setenv("LPM_CONFIG_PATH", str(elsewhere))
    monkeypatch.chdir(tmp_path)

    app, _ = load_config(env=load_env())

    assert app.tts.voice_id == "test-voice"


def test_invalid_tts_rate_is_rejected(monkeypatch, isolated_cwd):
    set_valid_env(monkeypatch)
    cfg = isolated_cwd / "config.yaml"
    write_minimal_config(cfg)
    cfg.write_text(cfg.read_text().replace("rate: 0.92", "rate: 1.2"), encoding="utf-8")

    with pytest.raises(ConfigError) as excinfo:
        load_config(env=load_env())

    assert any("tts.rate" in p for p in excinfo.value.problems)


def test_empty_tts_voice_id_is_rejected(monkeypatch, isolated_cwd):
    """tts.voice_id is mandatory — an empty string would cause the Azure
    adapter to send malformed SSML and every chunk would 400. We fail fast
    in the loader instead.
    """
    set_valid_env(monkeypatch)
    cfg = isolated_cwd / "config.yaml"
    write_minimal_config(cfg)
    cfg.write_text(cfg.read_text().replace("voice_id: test-voice", 'voice_id: ""'), encoding="utf-8")

    with pytest.raises(ConfigError) as excinfo:
        load_config(env=load_env())

    assert any("tts.voice_id" in p for p in excinfo.value.problems)


def test_redactor_masks_secrets(isolated_cwd, caplog):
    log_path = isolated_cwd / "run.log"
    setup_logging(level="DEBUG", secrets=["topsecret"], run_log_path=log_path)
    logger = logging.getLogger("test")
    with caplog.at_level(logging.DEBUG):
        logger.info("value is topsecret=topsecret done")

    content = log_path.read_text(encoding="utf-8")
    assert "topsecret" not in content
    assert "***" in content


def test_bgm_ratio_required_when_bgm_set(monkeypatch, isolated_cwd):
    set_valid_env(monkeypatch)
    cfg = isolated_cwd / "config.yaml"
    write_minimal_config(cfg)
    text = cfg.read_text()
    text = text.replace('bgm_path: ""', 'bgm_path: "./bgm.mp3"')
    text = text.replace("bgm_ratio: 0.12", "bgm_ratio: 0.5")
    cfg.write_text(text, encoding="utf-8")

    with pytest.raises(ConfigError) as excinfo:
        load_config(env=load_env())

    assert any("bgm_ratio" in p for p in excinfo.value.problems)


def test_script_request_timeout_seconds_loads_from_yaml(monkeypatch, isolated_cwd):
    set_valid_env(monkeypatch)
    cfg = isolated_cwd / "config.yaml"
    write_minimal_config(cfg)
    cfg.write_text(
        cfg.read_text().replace("token_budget: 5000", "token_budget: 5000\n  request_timeout_seconds: 180"),
        encoding="utf-8",
    )

    app, _ = load_config(env=load_env())

    assert app.script.request_timeout_seconds == 180.0


def test_script_stream_flag_loads_from_yaml(monkeypatch, isolated_cwd):
    set_valid_env(monkeypatch)
    cfg = isolated_cwd / "config.yaml"
    write_minimal_config(cfg)
    cfg.write_text(
        cfg.read_text().replace("token_budget: 5000", "token_budget: 5000\n  stream: true"),
        encoding="utf-8",
    )

    app, _ = load_config(env=load_env())

    assert app.script.stream is True

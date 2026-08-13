"""Tests for Contract Studio settings and .env loading."""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

from tools.contract.env import _candidate_env_paths
from tools.contract.settings import (
    DebugLoggingLLM,
    configure_studio_logging,
    load_studio_settings,
)


def test_load_studio_settings_from_config(tmp_path: Path) -> None:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        yaml.safe_dump(
            {
                "studio": {
                    "db_path": "data/studio.db",
                    "use_mock_llm": True,
                    "llm_provider": "mock",
                    "debug": True,
                },
                "llm_defaults": {
                    "provider": "ollama",
                    "model": "gemma3:4b",
                    "gemini_model": "gemini-flash-lite-latest",
                },
            }
        ),
        encoding="utf-8",
    )
    settings = load_studio_settings(cfg)
    assert settings.use_mock_llm is True
    assert settings.llm_provider == "mock"
    assert settings.debug is True
    assert settings.db_path == (tmp_path / "data" / "studio.db").resolve()
    assert settings.llm_defaults["gemini_model"] == "gemini-flash-lite-latest"


def test_env_overrides_config(tmp_path: Path, monkeypatch) -> None:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        yaml.safe_dump(
            {
                "studio": {
                    "db_path": "data/a.db",
                    "use_mock_llm": False,
                    "llm_provider": "gemini",
                    "debug": False,
                },
                "llm_defaults": {},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("USE_MOCK_LLM", "1")
    monkeypatch.setenv("CONTRACT_STUDIO_LLM", "ollama")
    monkeypatch.setenv("CONTRACT_STUDIO_DEBUG", "true")
    monkeypatch.setenv("CONTRACT_STUDIO_DB", str(tmp_path / "override.db"))

    settings = load_studio_settings(cfg)
    assert settings.use_mock_llm is True
    assert settings.llm_provider == "ollama"
    assert settings.debug is True
    assert settings.db_path == tmp_path / "override.db"


def test_debug_logging_llm_emits_prompts(caplog) -> None:
    class StubLLM:
        def generate(self, prompt: str, system=None) -> str:
            return '{"ok": true}'

    wrapped = DebugLoggingLLM(StubLLM(), enabled=True)
    with caplog.at_level(logging.INFO, logger="tools.contract.settings"):
        out = wrapped.generate("user says hello", system="you are helpful")
    assert out == '{"ok": true}'
    text = "\n".join(r.message for r in caplog.records)
    assert "LLM SYSTEM PROMPT" in text
    assert "you are helpful" in text
    assert "LLM USER PROMPT" in text
    assert "user says hello" in text
    assert "LLM RAW RESPONSE" in text
    assert '{"ok": true}' in text


def test_debug_logging_llm_silent_when_disabled(caplog) -> None:
    class StubLLM:
        def generate(self, prompt: str, system=None) -> str:
            return "ok"

    wrapped = DebugLoggingLLM(StubLLM(), enabled=False)
    with caplog.at_level(logging.INFO, logger="tools.contract.settings"):
        wrapped.generate("secret prompt", system="secret system")
    text = "\n".join(r.message for r in caplog.records)
    assert "LLM USER PROMPT" not in text
    assert "secret prompt" not in text


def test_candidate_env_paths() -> None:
    assert isinstance(_candidate_env_paths(), list)
    assert any(p.name == ".env" for p in _candidate_env_paths())


def test_configure_studio_logging_noop_when_off() -> None:
    configure_studio_logging(debug=False)

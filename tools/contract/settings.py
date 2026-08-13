"""Contract Studio settings: config.yaml + .env (API keys only)."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from dir_core.utils.llm_client import LLMClient

logger = logging.getLogger(__name__)

_CONTRACT_DIR = Path(__file__).resolve().parent
_DEFAULT_CONFIG_PATH = _CONTRACT_DIR / "config.yaml"


@dataclass(frozen=True)
class StudioSettings:
    """Resolved Contract Studio settings."""

    config_path: Path
    db_path: Path
    use_mock_llm: bool
    llm_provider: Optional[str]
    debug: bool
    llm_defaults: Dict[str, Any]
    raw: Dict[str, Any]


class DebugLoggingLLM(LLMClient):
    """Wrap an LLM client and log full prompts + raw responses when enabled."""

    def __init__(self, inner: LLMClient, *, enabled: bool = False) -> None:
        self._inner = inner
        self._enabled = enabled

    def generate(self, prompt: str, system: Optional[str] = None) -> str:
        if self._enabled:
            logger.info(
                "=== LLM SYSTEM PROMPT ===\n%s\n=== END SYSTEM PROMPT ===",
                system or "(none)",
            )
            logger.info(
                "=== LLM USER PROMPT ===\n%s\n=== END USER PROMPT ===",
                prompt,
            )
        raw = self._inner.generate(prompt, system=system)
        if self._enabled:
            logger.info(
                "=== LLM RAW RESPONSE ===\n%s\n=== END RAW RESPONSE ===",
                raw,
            )
        return raw


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _resolve_db_path(raw: str, *, config_dir: Path) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path
    return (config_dir / path).resolve()


def load_studio_settings(
    config_path: Optional[Path] = None,
) -> StudioSettings:
    """
    Load ``tools/contract/config.yaml``.

    Environment overrides (for tests / one-off runs, not for secrets in .env):
    - ``USE_MOCK_LLM`` forces mock when set to a truthy value
    - ``CONTRACT_STUDIO_DB`` overrides ``studio.db_path``
    - ``CONTRACT_STUDIO_LLM`` overrides ``studio.llm_provider``
      (gemini|ollama|mock)
    - ``CONTRACT_STUDIO_DEBUG`` overrides ``studio.debug``
    """
    path = Path(config_path) if config_path else _DEFAULT_CONFIG_PATH
    raw: Dict[str, Any] = {}
    if path.is_file():
        with open(path, encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle) or {}
        if not isinstance(loaded, dict):
            raise ValueError(f"Config must be a YAML mapping: {path}")
        raw = loaded
    else:
        logger.warning(
            "Contract Studio config not found at %s — using defaults",
            path,
        )

    studio = dict(raw.get("studio") or {})
    llm_defaults = dict(raw.get("llm_defaults") or {})

    use_mock = _as_bool(studio.get("use_mock_llm"), False)
    env_mock = os.environ.get("USE_MOCK_LLM")
    if env_mock is not None and str(env_mock).strip() != "":
        use_mock = _as_bool(env_mock, False)

    provider = studio.get("llm_provider")
    if provider is not None:
        provider = str(provider).strip().lower() or None
        if provider in ("null", "none", "auto", ""):
            provider = None
    env_provider = os.environ.get("CONTRACT_STUDIO_LLM", "").strip().lower()
    if env_provider:
        provider = env_provider

    debug = _as_bool(studio.get("debug"), False)
    env_debug = os.environ.get("CONTRACT_STUDIO_DEBUG")
    if env_debug is not None and str(env_debug).strip() != "":
        debug = _as_bool(env_debug, False)

    db_raw = os.environ.get("CONTRACT_STUDIO_DB") or studio.get(
        "db_path", "data/contract_studio.db"
    )
    db_path = _resolve_db_path(str(db_raw), config_dir=path.parent)

    return StudioSettings(
        config_path=path.resolve(),
        db_path=db_path,
        use_mock_llm=use_mock,
        llm_provider=provider,
        debug=debug,
        llm_defaults=llm_defaults,
        raw=raw,
    )


def configure_studio_logging(*, debug: bool) -> None:
    """Ensure Contract Studio loggers emit INFO when debug mode is on."""
    if not debug:
        return
    package_logger = logging.getLogger("tools.contract")
    too_quiet = (
        package_logger.level == logging.NOTSET
        or package_logger.level > logging.INFO
    )
    if too_quiet:
        package_logger.setLevel(logging.INFO)
    if not logging.getLogger().handlers and not package_logger.handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        )
    logger.info(
        "Contract Studio debug logging enabled "
        "(prompts + raw LLM responses)"
    )

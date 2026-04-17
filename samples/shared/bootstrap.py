"""
bootstrap.py - Factory/Builder to wire LLM and Storage based on config.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from dir_core.storage import StorageBundle, sqlite_storage, memory_storage
from dir_core.utils.llm_client import LLMClient

from .llm.clients import OllamaClient, GeminiClient, MockLLMClient, check_ollama
from .contracts.provider import (
    ContractProvider,
    YamlContractProvider,
    JsonContractProvider,
    DatabaseContractProvider,
    OpaRegoContractProvider,
)

logger = logging.getLogger(__name__)


def normalize_database_provider(raw: object) -> str:
    """Map YAML / user spellings to internal provider tokens."""
    if raw is None:
        return "memory"
    s = str(raw).strip().lower()
    if s in ("postgresql", "psql", "pg"):
        return "postgres"
    return s


def resolve_sqlite_db_path_relative_to_config(
    database_cfg: Dict[str, Any],
    config_path: Optional[str],
) -> Dict[str, Any]:
    """If SQLite and ``db_path`` is relative, anchor it to the config file's directory.

    Avoids creating ``data/*.db`` under the process CWD when users run
    ``python path/to/sample/run.py`` from the repository root.
    """
    cfg = dict(database_cfg)
    if not config_path or normalize_database_provider(cfg.get("provider", "memory")) != "sqlite":
        return cfg
    raw = cfg.get("db_path", "data/app.db")
    path = Path(raw)
    if path.is_absolute():
        return cfg
    base = Path(config_path).resolve().parent
    cfg["db_path"] = str((base / path).resolve())
    return cfg


def open_storage_bundle(database_cfg: Dict[str, Any]) -> StorageBundle:
    """Build a :class:`StorageBundle` from a ``database`` config section only.

    Canonical wiring used across samples:

    - **PostgreSQL**: ``samples.shared.storage.pg_repo.connect`` →
      ``apply_schema`` → ``build_repository``.
    - **SQLite**: :func:`dir_core.storage.sqlite_storage`.
    - **memory**: :func:`dir_core.storage.memory_storage`.

    Environment overrides for PostgreSQL (``DB_HOST``, ``DB_PORT``, ``DB_NAME``,
    ``DB_USER``, ``DB_PASS``) match :func:`setup_environment`.
    """
    db_provider = normalize_database_provider(database_cfg.get("provider", "memory"))

    if db_provider == "postgres":
        try:
            from .storage.pg_repo import connect, apply_schema, build_repository
        except ImportError as e:
            raise ImportError(
                "PostgreSQL storage requires the 'psycopg2-binary' package. "
                "Install with: pip install psycopg2-binary"
            ) from e

        overrides = {
            "host": os.getenv("DB_HOST"),
            "port": os.getenv("DB_PORT"),
            "dbname": os.getenv("DB_NAME"),
            "user": os.getenv("DB_USER"),
            "password": os.getenv("DB_PASS"),
        }
        cfg = dict(database_cfg)
        for key, val in overrides.items():
            if val is not None:
                cfg[key] = int(val) if key == "port" else val
        cfg.pop("provider", None)

        conn = connect(cfg)
        apply_schema(conn)
        repository = build_repository(conn)
        logger.info("Using PostgreSQL repository.")
        return repository

    if db_provider == "sqlite":
        db_path = database_cfg.get("db_path", "data/app.db")
        parent = Path(db_path).parent
        if str(parent) not in (".", ""):
            parent.mkdir(parents=True, exist_ok=True)
        repository = sqlite_storage(db_path)
        logger.info("Using SQLite repository at %s.", db_path)
        return repository

    if db_provider == "memory":
        repository = memory_storage()
        logger.info("Using in-memory repository.")
        return repository

    raise ValueError(f"Unknown database provider: {db_provider}")


def database_connection_summary(config: Dict[str, Any]) -> str:
    """Short human-readable description of configured persistence (no I/O)."""
    db = config.get("database") or {}
    p = normalize_database_provider(db.get("provider", "memory"))
    if p == "postgres":
        return (
            f"PostgreSQL host={db.get('host')} port={db.get('port', 5432)} "
            f"dbname={db.get('dbname')} user={db.get('user')}"
        )
    if p == "sqlite":
        return f"SQLite path={db.get('db_path', 'data/app.db')}"
    return "In-memory storage"


def _default_eoam_mock_strategy() -> Callable[[str, Optional[str]], str]:
    """Placeholder policy JSON for EOAM samples when no mock strategy is injected."""

    def strategy(prompt: str, sys: Optional[str] = None) -> str:
        return (
            '{"policy_kind": "HOLD", "params": {}, '
            '"justification": "Mock default", "confidence": 0.8}'
        )

    return strategy


def materialize_storage_bundle(
    config: Dict[str, Any],
    config_path: Optional[str] = None,
) -> StorageBundle:
    """Resolve relative SQLite paths (if applicable) and open a :class:`StorageBundle`.

    Mutates ``config["database"]`` in place when paths are anchored — same rule as
    :func:`setup_environment`. Use this from composition roots (e.g. samples) so
    persistence stays an externally wired adapter.
    """
    db_section = config.get("database")
    if isinstance(db_section, dict) and config_path:
        config["database"] = resolve_sqlite_db_path_relative_to_config(db_section, config_path)
    return open_storage_bundle(config.get("database") or {})


def build_llm_from_config(
    config: Dict[str, Any],
    mock_llm_strategy: Optional[Callable[[str, Optional[str]], str]] = None,
    *,
    force_mock: bool = False,
    empty_llm_defaults_implies_mock: bool = False,
) -> LLMClient:
    """Build a :class:`~dir_core.utils.llm_client.LLMClient` from ``config["llm_defaults"]``.

    Shared by :func:`setup_environment` and samples that attach the LLM as a port
    (e.g. ``32_fraud_gate``) without pulling Ollama/Gemini construction into domain code.

    Args:
        config: Full YAML dict (must include ``llm_defaults`` unless *empty* branch).
        mock_llm_strategy: Injected mock ``generate`` behavior when mock path is used.
        force_mock: When True, use ``MockLLMClient`` even if YAML names a live provider
            (e.g. Ollama unreachable — caller decides after :func:`configured_live_llm_is_reachable`).
        empty_llm_defaults_implies_mock: Fraud sample: missing/empty ``llm_defaults`` means
            deterministic mock (requires ``mock_llm_strategy``).
    """
    raw_ld = config.get("llm_defaults")
    llm_defaults: Dict[str, Any] = raw_ld if isinstance(raw_ld, dict) else {}

    if empty_llm_defaults_implies_mock:
        if mock_llm_strategy is None:
            raise ValueError(
                "empty_llm_defaults_implies_mock=True requires mock_llm_strategy"
            )
        logger.info("Using MockLLMClient (no llm_defaults in config).")
        return MockLLMClient(strategy=mock_llm_strategy)

    use_mock_env = os.environ.get("USE_MOCK_LLM", "").strip().lower() in ("1", "true", "yes")
    provider = str(llm_defaults.get("provider", "")).strip().lower()
    model = str(llm_defaults.get("model", "llama3.2"))

    if not provider:
        if model.lower().startswith("gemini"):
            provider = "gemini"
        else:
            provider = "ollama"

    if force_mock or use_mock_env or provider == "mock":
        strat = mock_llm_strategy or _default_eoam_mock_strategy()
        logger.info("Using MockLLMClient.")
        return MockLLMClient(strategy=strat)

    if provider == "gemini":
        api_key = llm_defaults.get("api_key")
        timeout = int(llm_defaults.get("timeout", 60))
        llm = GeminiClient(model=model, api_key=api_key, timeout=timeout)
        logger.info("Using GeminiClient (model: %s)", llm.model)
        return llm

    if provider == "ollama":
        base_url = os.getenv(
            "OLLAMA_BASE_URL",
            llm_defaults.get("base_url", "http://localhost:11434"),
        )
        model_resolved = os.getenv("OLLAMA_MODEL", model)
        timeout = int(llm_defaults.get("timeout", 60))
        llm = OllamaClient(model=model_resolved, base_url=base_url, timeout=timeout)
        logger.info("Using OllamaClient (model: %s, url: %s)", llm.model, llm.base_url)
        return llm

    raise ValueError(f"Unknown LLM provider: {provider}")


def configured_live_llm_is_reachable(config: Dict[str, Any]) -> bool:
    """Return False when YAML selects Gemini/Ollama but keys or Ollama are not usable.

    Callers may then pass ``force_mock=True`` to :func:`build_llm_from_config`.
    Returns True when mock is intended, ``llm_defaults`` is empty, or live checks pass.
    """
    if os.environ.get("USE_MOCK_LLM", "").strip().lower() in ("1", "true", "yes"):
        return True
    raw_ld = config.get("llm_defaults")
    llm_defaults: Dict[str, Any] = raw_ld if isinstance(raw_ld, dict) else {}
    if not llm_defaults:
        return True
    provider = str(llm_defaults.get("provider", "")).strip().lower()
    model = str(llm_defaults.get("model", "llama3.2"))
    if not provider:
        provider = "gemini" if model.lower().startswith("gemini") else "ollama"
    if provider == "mock":
        return True
    if provider == "gemini":
        if llm_defaults.get("api_key") or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"):
            return True
        logger.warning(
            "Gemini selected but no API key (api_key / GOOGLE_API_KEY / GEMINI_API_KEY)."
        )
        return False
    if provider == "ollama":
        base_url = os.getenv(
            "OLLAMA_BASE_URL",
            llm_defaults.get("base_url", "http://localhost:11434"),
        )
        model_resolved = os.getenv("OLLAMA_MODEL", model)
        if not check_ollama(base_url, model_resolved):
            logger.warning(
                "Ollama not reachable at %s or model '%s' not found. "
                "(ollama serve && ollama pull %s)",
                base_url,
                model_resolved,
                model_resolved,
            )
            return False
        return True
    return True


@dataclass
class Environment:
    llm: LLMClient
    repository: StorageBundle
    contracts: ContractProvider


def setup_environment(
    config: Dict[str, Any],
    mock_llm_strategy: Optional[Callable[[str, Optional[str]], str]] = None,
    config_path: Optional[str] = None,
) -> Environment:
    """
    Build the Environment (LLM and Storage) based on the config dict.
    
    1. LLM: Will prioritize use_mock (strategy) -> config provider -> auto-detect
    2. Storage: Reads config["database"]["provider"]. Fallback to memory.
       Supported providers: "postgres", "sqlite", "memory"
    """
    llm = build_llm_from_config(
        config,
        mock_llm_strategy,
        force_mock=False,
        empty_llm_defaults_implies_mock=False,
    )
    repository = materialize_storage_bundle(config, config_path)

    # 3. Build Contract Provider
    contracts_config = config.get("contracts", {})
    contracts_provider_type = contracts_config.get("provider", "yaml").lower()
    
    if contracts_provider_type == "yaml":
        c_path = contracts_config.get("path", config_path)
        if not c_path:
            raise ValueError("YamlContractProvider requires a 'path' or fallback to 'config_path'")
        contracts_provider = YamlContractProvider(file_path=str(c_path))
        logger.info(f"Using YamlContractProvider at {c_path}.")
    elif contracts_provider_type == "json":
        c_path = contracts_config.get("path")
        if not c_path:
            raise ValueError("JsonContractProvider requires a 'path' in config.contracts")
        contracts_provider = JsonContractProvider(file_path=str(c_path))
        logger.info(f"Using JsonContractProvider at {c_path}.")
    elif contracts_provider_type == "database":
        conn_str = contracts_config.get("connection_string", "mock://db")
        contracts_provider = DatabaseContractProvider(connection_string=conn_str)
        logger.info("Using DatabaseContractProvider.")
    elif contracts_provider_type == "opa":
        endpoint = contracts_config.get("opa_endpoint", "http://localhost:8181")
        contracts_provider = OpaRegoContractProvider(opa_endpoint=endpoint)
        logger.info("Using OpaRegoContractProvider.")
    else:
        raise ValueError(f"Unknown contracts provider: {contracts_provider_type}")

    return Environment(llm=llm, repository=repository, contracts=contracts_provider)

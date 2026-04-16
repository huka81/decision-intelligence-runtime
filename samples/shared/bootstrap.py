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
    
    # 1. Build LLM
    use_mock_env = os.environ.get("USE_MOCK_LLM", "").strip().lower() in ("1", "true", "yes")
    llm_defaults = config.get("llm_defaults", {})
    provider = llm_defaults.get("provider", "").lower()
    model = llm_defaults.get("model", "llama3.2")
    
    if not provider:
        if model.startswith("gemini"):
            provider = "gemini"
        else:
            provider = "ollama"

    if use_mock_env or provider == "mock":
        if mock_llm_strategy is None:
            # Default mock strategy if none provided
            def default_mock(prompt: str, sys: Optional[str]) -> str:
                return '{"policy_kind": "HOLD", "params": {}, "justification": "Mock default", "confidence": 0.8}'
            mock_llm_strategy = default_mock
            
        llm = MockLLMClient(strategy=mock_llm_strategy)
        logger.info("Using MockLLMClient.")
    elif provider == "gemini":
        api_key = llm_defaults.get("api_key")
        timeout = llm_defaults.get("timeout", 60)
        llm = GeminiClient(model=model, api_key=api_key, timeout=timeout)
        logger.info(f"Using GeminiClient (model: {llm.model})")
    elif provider == "ollama":
        base_url = llm_defaults.get("base_url", "http://localhost:11434")
        timeout = llm_defaults.get("timeout", 60)
        llm = OllamaClient(model=model, base_url=base_url, timeout=timeout)
        logger.info(f"Using OllamaClient (model: {llm.model}, url: {llm.base_url})")
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")

    # 2. Build Storage (PostgreSQL via pg_repo.build_repository, SQLite via sqlite_storage)
    db_section = config.get("database")
    if isinstance(db_section, dict) and config_path:
        config["database"] = resolve_sqlite_db_path_relative_to_config(db_section, config_path)
    repository = open_storage_bundle(config.get("database") or {})

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

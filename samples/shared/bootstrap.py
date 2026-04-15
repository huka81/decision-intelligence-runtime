"""
bootstrap.py - Factory/Builder to wire LLM and Storage based on config.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
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

    # 2. Build Storage
    db_config = config.get("database", {})
    db_provider = db_config.get("provider", "memory").lower()
    
    if db_provider == "postgres":
        # Import dynamically to avoid psycopg2 dependency if not used
        try:
            from .storage.pg_repo import connect, apply_schema, build_repository
        except ImportError:
            raise ImportError("psycopg2-binary is required for PostgreSQL storage")
            
        overrides = {
            "host":     os.getenv("DB_HOST"),
            "port":     os.getenv("DB_PORT"),
            "dbname":   os.getenv("DB_NAME"),
            "user":     os.getenv("DB_USER"),
            "password": os.getenv("DB_PASS"),
        }
        cfg = dict(db_config)
        for key, val in overrides.items():
            if val is not None:
                cfg[key] = int(val) if key == "port" else val
        # Remove 'provider' as psycopg2.connect doesn't expect it
        cfg.pop("provider", None)
        
        conn = connect(cfg)
        apply_schema(conn)
        repository = build_repository(conn)
        logger.info("Using PostgreSQL repository.")
    elif db_provider == "sqlite":
        db_path = db_config.get("db_path", "data/app.db")
        dir_name = os.path.dirname(db_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        repository = sqlite_storage(db_path)
        logger.info(f"Using SQLite repository at {db_path}.")
    elif db_provider == "memory":
        repository = memory_storage()
        logger.info("Using in-memory repository.")
    else:
        raise ValueError(f"Unknown database provider: {db_provider}")

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

"""
Contract Provider interface and default implementations.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict

import yaml

from dir_core import ResponsibilityContract

logger = logging.getLogger(__name__)

class ContractProvider(ABC):
    """
    Abstract interface for loading Responsibility Contracts.
    Separates the DIR Kernel (which uses the ResponsibilityContract model)
    from the infrastructure layer that stores/delivers the policy definitions
    (YAML, JSON, Databases, OPA, etc.).
    """

    @abstractmethod
    def get_contract(self, agent_id: str) -> ResponsibilityContract:
        """
        Fetch and parse the contract for a specific agent.
        Raises ValueError if the agent_id is not found or parsing fails.
        """
        pass

    @abstractmethod
    def get_all_contracts(self) -> Dict[str, ResponsibilityContract]:
        """
        Fetch all contracts available from this provider.
        Useful for iterating over defined agents in config files.
        """
        pass


class YamlContractProvider(ContractProvider):
    """Loads Responsibility Contracts from a YAML file."""

    def __init__(self, file_path: str, contract_model: Any = ResponsibilityContract):
        self.file_path = file_path
        self._contract_model = contract_model
        self._data: Dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                self._data = yaml.safe_load(f) or {}
        except Exception as e:
            logger.error("Failed to load YAML contracts from %s: %s", self.file_path, e)
            raise

    def get_contract(self, agent_id: str) -> ResponsibilityContract:
        # In many samples, contracts are under an 'agents' list
        if "agents" in self._data:
            for agent_cfg in self._data["agents"]:
                if agent_cfg.get("agent_id") == agent_id:
                    c_dict = dict(agent_cfg.get("contract", {}))
                    c_dict["agent_id"] = agent_id
                    return self._contract_model(**c_dict)
        
        # Some samples define a single contract under the 'contract' key
        if "contract" in self._data:
            c_dict = dict(self._data["contract"])
            c_id = c_dict.get("agent_id") or self._data.get("agent_id")
            if c_id == agent_id:
                c_dict["agent_id"] = agent_id
                return self._contract_model(**c_dict)

        raise ValueError(f"Contract for agent '{agent_id}' not found in YAML {self.file_path}")

    def get_all_contracts(self) -> Dict[str, ResponsibilityContract]:
        contracts = {}
        
        if "agents" in self._data:
            for agent_cfg in self._data["agents"]:
                agent_id = agent_cfg.get("agent_id")
                if agent_id:
                    c_dict = dict(agent_cfg.get("contract", {}))
                    c_dict["agent_id"] = agent_id
                    contracts[agent_id] = self._contract_model(**c_dict)
                    
        elif "contract" in self._data:
            c_dict = dict(self._data["contract"])
            agent_id = c_dict.get("agent_id") or self._data.get("agent_id", "unknown_agent")
            c_dict["agent_id"] = agent_id
            contracts[agent_id] = self._contract_model(**c_dict)
            
        return contracts


class JsonContractProvider(ContractProvider):
    """Loads Responsibility Contracts from a JSON file."""

    def __init__(self, file_path: str, contract_model: Any = ResponsibilityContract):
        self.file_path = file_path
        self._contract_model = contract_model
        self._data: Dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                self._data = json.load(f) or {}
        except Exception as e:
            logger.error("Failed to load JSON contracts from %s: %s", self.file_path, e)
            raise

    def get_contract(self, agent_id: str) -> ResponsibilityContract:
        # Assumes a dictionary of agent_id -> contract parameters
        if agent_id in self._data:
            c_dict = dict(self._data[agent_id])
            c_dict["agent_id"] = agent_id
            return self._contract_model(**c_dict)
            
        raise ValueError(f"Contract for agent '{agent_id}' not found in JSON {self.file_path}")

    def get_all_contracts(self) -> Dict[str, ResponsibilityContract]:
        contracts = {}
        for agent_id, c_dict_raw in self._data.items():
            if isinstance(c_dict_raw, dict):
                c_dict = dict(c_dict_raw)
                c_dict["agent_id"] = agent_id
                contracts[agent_id] = self._contract_model(**c_dict)
        return contracts


class DatabaseContractProvider(ContractProvider):
    """
    Placeholder/Mockup for a Contract Provider that loads from a SQL/NoSQL Database.
    Demonstrates that DIR works seamlessly with dynamic, centrally-managed policies.
    """

    def __init__(self, connection_string: str, contract_model: Any = ResponsibilityContract):
        self.connection_string = connection_string
        self._contract_model = contract_model
        logger.info("Initializing DatabaseContractProvider connected to %s", connection_string)

    def get_contract(self, agent_id: str) -> ResponsibilityContract:
        # In a real implementation: SELECT * FROM responsibility_contracts WHERE agent_id = ?
        logger.debug("[DatabaseContractProvider] Mock fetch for agent_id: %s", agent_id)
        
        # Returning a mock contract
        return self._contract_model(
            agent_id=agent_id,
            mission=f"Dynamically loaded mission from DB for {agent_id}",
            authorized_instruments=["DB-ASSET-1"],
            allowed_policy_types=["DB_ACTION"],
        )

    def get_all_contracts(self) -> Dict[str, ResponsibilityContract]:
        logger.debug("[DatabaseContractProvider] Mock fetch ALL contracts")
        return {
            "db_agent_1": self.get_contract("db_agent_1")
        }


class OpaRegoContractProvider(ContractProvider):
    """
    Placeholder/Mockup for a Contract Provider that loads from Open Policy Agent (OPA).
    Demonstrates that DIR can integrate with external Policy-as-Code engines.
    """

    def __init__(self, opa_endpoint: str, contract_model: Any = ResponsibilityContract):
        self.opa_endpoint = opa_endpoint
        self._contract_model = contract_model
        logger.info("Initializing OpaRegoContractProvider connected to OPA at %s", opa_endpoint)

    def get_contract(self, agent_id: str) -> ResponsibilityContract:
        # In a real implementation: Call OPA Data API (e.g. GET /v1/data/dir/contracts/{agent_id})
        logger.debug("[OpaRegoContractProvider] Mock OPA policy evaluation for: %s", agent_id)
        
        # Returning a mock contract evaluated by "OPA"
        return self._contract_model(
            agent_id=agent_id,
            mission=f"OPA-governed mission for {agent_id}",
            authorized_instruments=["OPA-ASSET"],
            allowed_policy_types=["OPA_PERMITTED_ACTION"],
            max_drawdown_limit=0.01,
        )

    def get_all_contracts(self) -> Dict[str, ResponsibilityContract]:
        logger.debug("[OpaRegoContractProvider] Mock OPA fetch all")
        return {
            "opa_agent_1": self.get_contract("opa_agent_1")
        }

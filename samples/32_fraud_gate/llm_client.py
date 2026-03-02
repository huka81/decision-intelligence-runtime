"""
LLM client for Fraud Guard agent: Ollama (Gemma) and MockLLM.

Usage:
  client = OllamaClient(model="gemma3:4b", base_url="http://localhost:11435")
  text = client.generate("Evaluate this transaction...", system="You are a fraud analyst.")

MockLLM: USE_MOCK_LLM=1 for tests without Ollama. Returns structured fraud decision JSON.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from typing import Optional

logger = logging.getLogger(__name__)


class LLMClient(ABC):
    """Abstract LLM client: generate(prompt, system=None) -> str."""

    @abstractmethod
    def generate(self, prompt: str, system: Optional[str] = None) -> str:
        """Return generated text. May raise on network/API errors."""
        pass


class OllamaClient(LLMClient):
    """Sync client for local Ollama API (POST /api/generate)."""

    def __init__(
        self,
        model: str = "gemma3:4b",
        base_url: str = "http://localhost:11435",
        timeout: int = 60,
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def generate(self, prompt: str, system: Optional[str] = None) -> str:
        logger.debug(
            "Ollama request: model=%s, prompt_len=%d, system_len=%d",
            self.model, len(prompt), len(system or ""),
        )
        url = f"{self.base_url}/api/generate"
        body = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
        }
        if system:
            body["system"] = system
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url, data=data, method="POST", headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                out = json.loads(resp.read().decode("utf-8"))
            response = out.get("response", "").strip()
            preview = response[:200] + "..." if len(response) > 200 else response
            logger.debug("[LLM] Response (len=%d): %s", len(response), preview.replace("\n", " "))
            return response
        except urllib.error.URLError as e:
            logger.warning("Ollama request failed: %s", e)
            raise
        except (KeyError, json.JSONDecodeError) as e:
            logger.warning("Ollama response parse error: %s", e)
            raise


class MockLLM(LLMClient):
    """
    Returns structured fraud decision JSON for tests without Ollama.
    Deterministic logic based on transaction context and fallback_rules from config.
    """

    def __init__(self, fallback_rules: Optional[object] = None):
        """
        Args:
            fallback_rules: FallbackRules from config (block_amount_threshold, etc.).
                If None, uses default values.
        """
        self._rules = fallback_rules

    def generate(self, prompt: str, system: Optional[str] = None) -> str:
        import re
        # Extract context from prompt (matches _build_prompt format)
        amount = 0.0
        geo = ""
        device = ""
        velocity = 0
        m = re.search(r"Amount:\s*\$?([\d,]+(?:\.\d+)?)", prompt, re.I)
        if m:
            try:
                amount = float(m.group(1).replace(",", ""))
            except ValueError:
                pass
        m = re.search(r"Country:\s*(\w+)", prompt, re.I)
        if m:
            geo = m.group(1).lower()
        m = re.search(r"Device:\s*(\S+)", prompt, re.I)
        if m:
            device = m.group(1)
        m = re.search(r"last 24h:\s*(\d+)", prompt, re.I)
        if m:
            try:
                velocity = int(m.group(1))
            except ValueError:
                pass

        # Use config rules or defaults
        block_thresh = 5000
        block_countries = ["nigeria"]
        allow_max = 1000
        velocity_max = 10
        device_prefix = "dev_known_"
        if self._rules is not None and hasattr(self._rules, "block_amount_threshold"):
            block_thresh = self._rules.block_amount_threshold
            block_countries = self._rules.block_high_risk_countries
            allow_max = self._rules.allow_amount_max
            velocity_max = self._rules.allow_velocity_max
            device_prefix = self._rules.allow_device_prefix

        # Deterministic decision logic (same as agent._fallback_decision)
        if amount > block_thresh and geo in block_countries:
            out = {"action": "BLOCK", "reason_code": "HIGH_RISK_GEO_AMOUNT", "risk_score": 0.99}
        elif amount < allow_max and device.startswith(device_prefix) and velocity < velocity_max:
            out = {"action": "ALLOW", "reason_code": "LOW_RISK_LEGIT", "risk_score": 0.1}
        elif amount < allow_max:
            out = {"action": "ALLOW", "reason_code": "LOW_RISK_SNAPSHOT", "risk_score": 0.15}
        else:
            out = {"action": "CHALLENGE", "reason_code": "UNCERTAIN", "risk_score": 0.5}

        response = json.dumps(out)
        logger.info("[MockLLM] Response: %s", response)
        return response

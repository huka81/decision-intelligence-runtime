"""
Minimal LLM client for EOAM ROA agents: Ollama (sync) and MockLLM for tests without a server.

Usage:
  client = OllamaClient(model="llama3.2", base_url="http://localhost:11434")
  text = client.generate("What is the trend?", system="You are a market analyst.")
"""

from __future__ import annotations

import json
import logging
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

    def __init__(self, model: str = "llama3.2", base_url: str = "http://localhost:11434", timeout: int = 60):
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
        req = urllib.request.Request(url, data=data, method="POST", headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                out = json.loads(resp.read().decode("utf-8"))
            response = out.get("response", "").strip()
            preview = response[:200] + "..." if len(response) > 200 else response
            logger.info("LLM response received (length=%d): %s", len(response), preview.replace("\n", " "))
            logger.debug("LLM full response: %s", response)
            return response
        except urllib.error.URLError as e:
            logger.warning("Ollama request failed: %s", e)
            raise
        except (KeyError, json.JSONDecodeError) as e:
            logger.warning("Ollama response parse error: %s", e)
            raise


class MockLLM(LLMClient):
    """
    Returns fixed template responses for Explain and Policy without calling a real LLM.
    Useful when Ollama is not running or for fast tests.
    """

    def __init__(self, explain_suffix: str = "", policy_action: str = "HOLD", policy_confidence: float = 0.8):
        self.explain_suffix = explain_suffix
        self.policy_action = policy_action
        self.policy_confidence = policy_confidence

    def generate(self, prompt: str, system: Optional[str] = None) -> str:
        prompt_lower = prompt.lower()
        # Policy-style: prompt asks for one action / ACTION / Choose one action
        if "choose one action" in prompt_lower or "output action" in prompt_lower or "action, justification" in prompt_lower:
            response = (
                f"ACTION: {self.policy_action}\n"
                f"JUSTIFICATION: Mock policy per mission.\n"
                f"CONFIDENCE: {self.policy_confidence}"
            )
            logger.info("MockLLM response (policy): action=%s, confidence=%s", self.policy_action, self.policy_confidence)
            logger.debug("MockLLM full response: %s", response)
            return response
        # Explain-style: narrative/signals/risks/opportunities (and not Policy)
        if "narrative" in prompt_lower or "signals:" in prompt_lower or "risks:" in prompt_lower or "opportunities:" in prompt_lower:
            response = (
                "Narrative: Market context observed. "
                "SIGNALS: price_update, trend. RISKS: volatility. OPPORTUNITIES: trend continuation. "
                + self.explain_suffix
            )
            logger.info("MockLLM response (explain): narrative + SIGNALS/RISKS/OPPORTUNITIES")
            logger.debug("MockLLM full response: %s", response)
            return response
        # Default: Policy-style
        response = (
            f"ACTION: {self.policy_action}\n"
            f"JUSTIFICATION: Mock policy per mission.\n"
            f"CONFIDENCE: {self.policy_confidence}"
        )
        logger.info("MockLLM response (policy, default): action=%s, confidence=%s", self.policy_action, self.policy_confidence)
        logger.debug("MockLLM full response: %s", response)
        return response

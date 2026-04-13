"""
LLM client for EOAM ROA agents: Ollama and Gemini (from dir_core.utils), MockLLM for tests without a server.

Usage:
  from dir_core.utils.llm_client import OllamaClient, GeminiClient
  client = OllamaClient(model="gemma3:4b", base_url="http://localhost:11434")
  # or: client = GeminiClient(model="gemini-1.5-flash", api_key="your-key")
  text = client.generate("What is the trend?", system="You are a market analyst.")
"""

from __future__ import annotations

import logging
from typing import Optional

from dir_core.utils.llm_client import LLMClient

logger = logging.getLogger(__name__)

__all__ = ["LLMClient", "MockLLM"]


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

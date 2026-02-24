"""
Minimal LLM client for EOAM ROA agents: Ollama (sync), Gemini, and MockLLM for tests without a server.

Usage:
  # Ollama
  client = OllamaClient(model="gemma3:4b", base_url="http://localhost:11435")
  text = client.generate("What is the trend?", system="You are a market analyst.")
  
  # Gemini
  client = GeminiClient(model="gemini-1.5-pro", api_key="your-api-key")
  text = client.generate("What is the trend?", system="You are a market analyst.")
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from typing import Optional

from openai import OpenAI

logger = logging.getLogger(__name__)


class LLMClient(ABC):
    """Abstract LLM client: generate(prompt, system=None) -> str."""

    @abstractmethod
    def generate(self, prompt: str, system: Optional[str] = None) -> str:
        """Return generated text. May raise on network/API errors."""
        pass


class OllamaClient(LLMClient):
    """Sync client for local Ollama API using OpenAI library."""

    def __init__(self, model: str = "gemma3:4b", base_url: str = "http://localhost:11435", timeout: int = 60):
        self.model = model
        self.base_url = base_url.rstrip("/") + "/v1"
        self.timeout = timeout
        self.client = OpenAI(
            base_url=self.base_url,
            api_key="ollama"  # dowolny string
        )

    def generate(self, prompt: str, system: Optional[str] = None) -> str:
        logger.debug(
            "Ollama request: model=%s, prompt_len=%d, system_len=%d",
            self.model, len(prompt), len(system or ""),
        )
        
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages
            )
            response_text = response.choices[0].message.content.strip()
            preview = response_text[:200] + "..." if len(response_text) > 200 else response_text
            logger.info("LLM response received (length=%d): %s", len(response_text), preview.replace("\n", " "))
            logger.debug("LLM full response: %s", response_text)
            return response_text
        except Exception as e:
            logger.warning("Ollama request failed: %s", e)
            raise


class GeminiClient(LLMClient):
    """Sync client for Google Gemini API."""

    def __init__(
        self,
        model: str = "gemini-1.5-flash",
        api_key: Optional[str] = None,
        timeout: int = 60,
    ):
        """
        Initialize Gemini client.
        
        Args:
            model: Model name (e.g., "gemini-1.5-pro", "gemini-1.5-flash")
            api_key: Google API key. If None, reads from GOOGLE_API_KEY or GEMINI_API_KEY env var
            timeout: Request timeout in seconds
        """
        self.model = model
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Gemini API key not provided. Set api_key parameter or GOOGLE_API_KEY/GEMINI_API_KEY environment variable."
            )
        self.timeout = timeout
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"

    def generate(self, prompt: str, system: Optional[str] = None) -> str:
        logger.debug(
            "Gemini request: model=%s, prompt_len=%d, system_len=%d",
            self.model, len(prompt), len(system or ""),
        )
        
        url = f"{self.base_url}/models/{self.model}:generateContent?key={self.api_key}"
        
        # Build contents array
        contents = []
        if system:
            # Add system instruction as first user message
            contents.append({
                "role": "user",
                "parts": [{"text": system}]
            })
            contents.append({
                "role": "model",
                "parts": [{"text": "Understood. I will follow these instructions."}]
            })
        
        contents.append({
            "role": "user",
            "parts": [{"text": prompt}]
        })
        
        body = {
            "contents": contents,
            "generationConfig": {
                "temperature": 0.7,
                "topK": 40,
                "topP": 0.95,
                "maxOutputTokens": 2048,
            }
        }
        
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url, 
            data=data, 
            method="POST", 
            headers={"Content-Type": "application/json"}
        )
        
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                out = json.loads(resp.read().decode("utf-8"))
            
            # Extract text from response
            if "candidates" not in out or not out["candidates"]:
                logger.warning("Gemini response missing candidates: %s", out)
                return ""
            
            candidate = out["candidates"][0]
            if "content" not in candidate or "parts" not in candidate["content"]:
                logger.warning("Gemini response missing content/parts: %s", candidate)
                return ""
            
            parts = candidate["content"]["parts"]
            response = "".join(part.get("text", "") for part in parts).strip()
            
            preview = response[:200] + "..." if len(response) > 200 else response
            logger.info("LLM response received (length=%d): %s", len(response), preview.replace("\n", " "))
            logger.debug("LLM full response: %s", response)
            return response
            
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8") if e.fp else ""
            logger.warning("Gemini request failed (HTTP %s): %s", e.code, error_body)
            raise
        except urllib.error.URLError as e:
            logger.warning("Gemini request failed: %s", e)
            raise
        except (KeyError, json.JSONDecodeError) as e:
            logger.warning("Gemini response parse error: %s", e)
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

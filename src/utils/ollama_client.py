"""
Ollama LLM client for local inference (sync, urllib — no external deps).

Usage:
  client = OllamaClient(model="gemma3:12b", base_url="http://localhost:11434")
  text = client.generate("Analyze this...", system="You are an analyst.")
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

    def __init__(
        self,
        model: str = "gemma3:12b",
        base_url: str = "http://localhost:11434",
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
            logger.info(
                "Ollama response (len=%d): %s",
                len(response),
                preview.replace("\n", " "),
            )
            return response
        except urllib.error.URLError as e:
            logger.warning("Ollama request failed: %s", e)
            raise
        except (KeyError, json.JSONDecodeError) as e:
            logger.warning("Ollama response parse error: %s", e)
            raise


def check_ollama(base_url: str, model: str, timeout: int = 5) -> bool:
    """
    Verify Ollama is reachable and the requested model is available.

    Returns True if OK, False otherwise. Caller may fall back to MockLLM or sys.exit(1).
    """
    tags_url = base_url.rstrip("/") + "/api/tags"
    try:
        with urllib.request.urlopen(tags_url, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return False
    available = [m.get("name", "") for m in data.get("models", [])]
    model_base = model.split(":")[0]
    return any(model_base in name for name in available)

"""
LLM clients for local (Ollama) and cloud (Gemini) inference, plus Mocking.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Optional, Callable

from dir_core.utils.llm_client import LLMClient

logger = logging.getLogger(__name__)

__all__ = ["OllamaClient", "GeminiClient", "MockLLMClient", "check_ollama"]


class OllamaClient(LLMClient):
    """Sync client for local Ollama API (POST /api/generate)."""

    def __init__(
        self,
        model: str = "gemma3:4b",
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
        body: dict = {"model": self.model, "prompt": prompt, "stream": False}
        if system:
            body["system"] = system
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                out = json.loads(resp.read().decode("utf-8"))
            response = out.get("response", "").strip()
            preview = (
                response[:200] + "..." if len(response) > 200 else response
            )
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
            api_key: Google API key. If None, reads from GOOGLE_API_KEY or
                GEMINI_API_KEY env var.
            timeout: Request timeout in seconds
        """
        self.model = model
        self.api_key = (
            api_key
            or os.getenv("GOOGLE_API_KEY")
            or os.getenv("GEMINI_API_KEY")
        )
        if not self.api_key:
            raise ValueError(
                "Gemini API key not provided. Set api_key parameter or "
                "GOOGLE_API_KEY/GEMINI_API_KEY environment variable."
            )
        self.timeout = timeout
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"

    def generate(self, prompt: str, system: Optional[str] = None) -> str:
        logger.debug(
            "Gemini request: model=%s, prompt_len=%d, system_len=%d",
            self.model, len(prompt), len(system or ""),
        )

        url = (
            f"{self.base_url}/models/{self.model}"
            f":generateContent?key={self.api_key}"
        )

        contents = []
        if system:
            contents.append({"role": "user", "parts": [{"text": system}]})
            contents.append({
                "role": "model",
                "parts": [{"text": "Understood. I will follow these instructions."}],
            })
        contents.append({"role": "user", "parts": [{"text": prompt}]})

        body = {
            "contents": contents,
            "generationConfig": {
                "temperature": 0.7,
                "topK": 40,
                "topP": 0.95,
                "maxOutputTokens": 2048,
            },
        }

        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={"Content-Type": "application/json"},
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                out = json.loads(resp.read().decode("utf-8"))

            if "candidates" not in out or not out["candidates"]:
                logger.warning("Gemini response missing candidates: %s", out)
                return ""

            candidate = out["candidates"][0]
            has_content = (
                "content" in candidate and "parts" in candidate["content"]
            )
            if not has_content:
                logger.warning(
                    "Gemini response missing content/parts: %s", candidate
                )
                return ""

            parts = candidate["content"]["parts"]
            response = "".join(
                part.get("text", "") for part in parts
            ).strip()

            preview = (
                response[:200] + "..." if len(response) > 200 else response
            )
            logger.info(
                "Gemini response (len=%d): %s",
                len(response),
                preview.replace("\n", " "),
            )
            return response

        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8") if e.fp else ""
            logger.warning(
                "Gemini request failed (HTTP %s): %s", e.code, error_body
            )
            raise
        except urllib.error.URLError as e:
            logger.warning("Gemini request failed: %s", e)
            raise
        except (KeyError, json.JSONDecodeError) as e:
            logger.warning("Gemini response parse error: %s", e)
            raise


class MockLLMClient(LLMClient):
    """
    Mock LLM Client using composition for strategy.
    Accepts a callable strategy function:
        strategy(prompt: str, system: Optional[str]) -> str
    """

    def __init__(self, strategy: Callable[[str, Optional[str]], str]):
        self.strategy = strategy

    def generate(self, prompt: str, system: Optional[str] = None) -> str:
        response = self.strategy(prompt, system)
        logger.info("MockLLMClient response generated")
        logger.debug("MockLLMClient full response: %s", response)
        return response


def check_ollama(base_url: str, model: str, timeout: int = 5) -> bool:
    """
    Verify Ollama is reachable and the requested model is available.
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

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
    """Sync client for Google Gemini API using the google-genai SDK."""

    def __init__(
        self,
        model: str = "gemini-flash-lite-latest",
        api_key: Optional[str] = None,
        timeout: int = 60,
    ):
        """
        Initialize Gemini client.

        Args:
            model: Model name (e.g., "gemini-flash-lite-latest", "gemini-1.5-pro", "gemini-1.5-flash")
            api_key: Google API key. If None, reads from GOOGLE_API_KEY or
                GEMINI_API_KEY env var.
            timeout: Request timeout in seconds
        """
        try:
            from google import genai
            from google.genai import types
        except ImportError:
            raise ImportError(
                "google-genai package is not installed. "
                "Please install it using 'pip install google-genai'."
            )

        self.model_name = model
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
        self._client = genai.Client(
            api_key=self.api_key,
            http_options=types.HttpOptions(timeout=timeout * 1000),
        )

    def generate(self, prompt: str, system: Optional[str] = None) -> str:
        from google.genai import types

        logger.debug(
            "Gemini request (SDK): model=%s, prompt_len=%d, system_len=%d",
            self.model_name, len(prompt), len(system or ""),
        )

        try:
            config_kwargs: dict = {
                "temperature": 0.7,
                "top_k": 40,
                "top_p": 0.95,
                "max_output_tokens": 2048,
            }
            if system:
                config_kwargs["system_instruction"] = system

            response = self._client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(**config_kwargs),
            )

            res_text = (response.text or "").strip()

            preview = (
                res_text[:200] + "..." if len(res_text) > 200 else res_text
            )
            logger.info(
                "Gemini response (len=%d): %s",
                len(res_text),
                preview.replace("\n", " "),
            )
            return res_text

        except Exception as e:
            logger.warning("Gemini SDK request failed: %s", e)
            raise

    def list_available_models(self) -> None:
        """List available models from Google Generative AI."""
        print("Available models:")
        for model in self._client.models.list():
            name = getattr(model, "name", None) or str(model)
            print(name)


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


def test_ollama_alive_and_responds() -> None:
    """Verify Ollama service is alive and responds to LLM query. Prints response."""
    client = OllamaClient(model="gemma3:4b", base_url="http://localhost:11434", timeout=30)
    prompt = "Jaki jest sens zycia? Odpowiedz w jednym zdaniu."
    response = client.generate(prompt, system="You are a thoughtful assistant. Answer briefly.")

    # Print result (visible with pytest -s or in capsys)
    print("\n" + "=" * 60)
    print("Ollama LLM test - response:")
    print("=" * 60)
    print(f"Prompt: {prompt}")
    print(f"Response: {response.strip()}")
    print("=" * 60 + "\n")

if __name__ == "__main__":
    # test_ollama_alive_and_responds()
    gemini = GeminiClient()
    gemini.list_available_models()

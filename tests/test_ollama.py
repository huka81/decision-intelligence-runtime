"""Tests for dir_core.utils.llm_client module (OllamaClient)."""

import sys
from pathlib import Path
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SAMPLES = _REPO_ROOT / "samples"
if str(_SAMPLES) not in sys.path:
    sys.path.insert(0, str(_SAMPLES))

from shared.llm.clients import OllamaClient, check_ollama

BASE_URL = "http://localhost:11434"
MODEL = "gemma3:4b"


def test_check_ollama_unreachable() -> None:
    """check_ollama returns False when Ollama is not reachable."""
    assert check_ollama("http://127.0.0.1:19999", "nonexistent", timeout=1) is False


def test_check_ollama_invalid_url() -> None:
    """check_ollama returns False for invalid/unreachable URL."""
    assert check_ollama("http://invalid-host-that-does-not-exist.local", "model", timeout=1) is False


def test_ollama_client_init() -> None:
    """OllamaClient stores model and base_url."""
    client = OllamaClient(model="test-model", base_url=BASE_URL, timeout=30)
    assert client.model == "test-model"
    assert client.base_url == BASE_URL
    assert client.timeout == 30


def test_ollama_client_init_strips_trailing_slash() -> None:
    """OllamaClient strips trailing slash from base_url."""
    client = OllamaClient(base_url=f"{BASE_URL}/")
    assert client.base_url == BASE_URL


@pytest.mark.skipif(
    not check_ollama(BASE_URL, MODEL, timeout=2),
    reason="Ollama not running or model not available (ollama serve && ollama pull gemma3:4b)",
)
def test_ollama_alive_and_responds() -> None:
    """Verify Ollama service is alive and responds to LLM query. Prints response."""
    client = OllamaClient(model=MODEL, base_url=BASE_URL, timeout=30)
    prompt = "Jaki jest sens zycia? Odpowiedz w jednym zdaniu."
    response = client.generate(prompt, system="You are a thoughtful assistant. Answer briefly.")

    assert isinstance(response, str)
    assert len(response.strip()) > 0

    # Print result (visible with pytest -s or in capsys)
    print("\n" + "=" * 60)
    print("Ollama LLM test - response:")
    print("=" * 60)
    print(f"Prompt: {prompt}")
    print(f"Response: {response.strip()}")
    print("=" * 60 + "\n")

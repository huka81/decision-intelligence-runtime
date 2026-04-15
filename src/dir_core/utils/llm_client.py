"""
Abstract LLM client interface for dir_core.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

class LLMClient(ABC):
    """Abstract LLM client: generate(prompt, system=None) -> str."""

    @abstractmethod
    def generate(self, prompt: str, system: Optional[str] = None) -> str:
        """Return generated text. May raise on network/API errors."""
        pass

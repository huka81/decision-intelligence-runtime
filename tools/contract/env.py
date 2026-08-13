"""Load Contract Studio / tools.contract environment from .env files."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_CONTRACT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _CONTRACT_DIR.parents[1]


def _candidate_env_paths() -> list[Path]:
    """Search order: tools/contract/.env then repository root .env."""
    return [
        _CONTRACT_DIR / ".env",
        _REPO_ROOT / ".env",
    ]


def load_contract_env() -> Optional[Path]:
    """
    Load environment variables from the first existing .env file.

    Existing process environment variables are preserved (`override=False`).
    Returns the loaded file path, or None if no file was found or dotenv is missing.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        logger.debug("python-dotenv not installed; skipping .env load")
        return None

    for path in _candidate_env_paths():
        if path.is_file():
            load_dotenv(path, override=False)
            logger.info("Loaded Contract Studio environment from %s", path)
            return path
    return None

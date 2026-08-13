"""Flatten legacy sample contract shapes for the Runtime model."""

from __future__ import annotations

import sys
from pathlib import Path

# tools/ lives at the repo root; samples often only put src/ and samples/ on sys.path.
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.contract.flatten import (
    flatten_canonical,
    flatten_contract_dict,
    inflate_flat_to_canonical,
)

__all__ = [
    "flatten_canonical",
    "flatten_contract_dict",
    "inflate_flat_to_canonical",
]

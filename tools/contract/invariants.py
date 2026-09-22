"""Compile canonical contract sugar into declarative invariant IR (Contract Studio)."""

from __future__ import annotations

from typing import Any, Dict, List

from dir_core.invariant_compile import (
    compile_authority_invariants as _compile_authority_invariants,
    compile_sugar_invariants as _compile_sugar_invariants,
)
from dir_core.models import InvariantSpec

from .schema import CanonicalContract


def compile_authority_invariants(contract: Dict[str, Any] | CanonicalContract) -> List[InvariantSpec]:
    """Return merged invariant IR for a canonical or raw contract mapping."""
    if isinstance(contract, CanonicalContract):
        data = contract.model_dump(mode="json")
    else:
        data = dict(contract)
    return _compile_authority_invariants(data)


def compile_sugar_invariants(
    authority: Dict[str, Any],
    execution_conditions: Dict[str, Any] | None = None,
) -> List[InvariantSpec]:
    return _compile_sugar_invariants(authority, execution_conditions)

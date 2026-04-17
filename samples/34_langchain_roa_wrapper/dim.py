"""FinOps DIM extras: resource existence and environment boundary."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from dir_core import PolicyProposal


def finops_custom_validators() -> List[
    Callable[[PolicyProposal, Dict[str, Any], Dict[str, Any]], Optional[str]]
]:
    """Validators for ``dir_core.dim.validate_proposal`` ``custom_validators``."""

    def _resource_and_environment(
        proposal: PolicyProposal,
        context: Dict[str, Any],
        contract: Dict[str, Any],
    ) -> Optional[str]:
        allowed = contract.get("allowed_environments") or []
        if not allowed:
            return "Missing allowed_environments on contract for FinOps DIM"

        resource_id = (proposal.params or {}).get("resource_id")
        if not resource_id:
            return "Missing resource_id in proposal params"

        instances = context.get("instances") or {}
        if resource_id not in instances:
            return f"Resource {resource_id} not found in Context Store"

        instance_env = instances[resource_id].get("environment", "UNKNOWN")
        if instance_env not in allowed:
            return (
                f"Instance {resource_id} is {instance_env}; "
                f"allowed_environments={list(allowed)}"
            )
        return None

    return [_resource_and_environment]

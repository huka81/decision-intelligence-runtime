#!/usr/bin/env python3
"""
12_langchain_roa_wrapper - LangChain ReAct agent wrapped in ROA interface.

Demonstrates:
- Turning a task-driven LangChain agent into a Mission-Oriented ROA
- Submit_Policy_Proposal tool: intercepts intent, passes over "The Wall" to DIR Kernel
- FinOps use case: DIM rejects TERMINATE on PROD instance (allowed_environments=[DEV, STG])

Run from repo root: python samples/12_langchain_roa_wrapper/run.py
Requires: pip install -e .

ROA Manifesto §4-5, DIR Architectural Pattern §6.

Note: This sample uses a SIMULATED agent for demonstration purposes.
See README.md "Production Considerations" for real LangChain integration guidance.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional, Tuple

from dir import PolicyProposal, ResponsibilityContract, new_dfid
from dir.dim import validate_proposal
from dir.logging_utils import log_with_dfid

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Interception Mechanism (Claim vs. Fact boundary)
# -----------------------------------------------------------------------------


class ProposalIntercepted(Exception):
    """
    Control-flow exception raised when Submit_Policy_Proposal tool is invoked.

    This is NOT an error - it's the intentional mechanism to halt agent execution
    and capture the proposal (Claim) before any side effect occurs.
    The wrapper catches this and converts payload to PolicyProposal.
    """

    def __init__(self, proposal_json: str):
        self.proposal_json = proposal_json
        super().__init__("Proposal intercepted - crossing The Wall to Kernel Space")


# -----------------------------------------------------------------------------
# FinOps Responsibility Contract
# -----------------------------------------------------------------------------


@dataclass
class FinOpsContract:
    """
    FinOps-specific contract extending ROA pattern.

    allowed_environments restricts which instance environments the agent
    may propose actions on (e.g., ["DEV", "STG"] excludes PROD).
    """

    agent_id: str
    mission: str
    allowed_environments: List[str]
    allowed_policy_types: List[str]
    role: Literal["STRATEGIST", "EXECUTOR", "MONITOR"] = "EXECUTOR"

    def to_responsibility_contract(self) -> ResponsibilityContract:
        """Convert to standard ResponsibilityContract for DIR integration."""
        return ResponsibilityContract(
            agent_id=self.agent_id,
            role=self.role,
            mission=self.mission,
            authorized_instruments=[],
            allowed_policy_types=self.allowed_policy_types,
        )


# -----------------------------------------------------------------------------
# Submit_Policy_Proposal Tool - The Trojan Horse
# -----------------------------------------------------------------------------


def create_submit_policy_proposal_tool():
    """
    Create the Submit_Policy_Proposal tool.

    This tool is the ONLY action tool available to the agent. When invoked,
    it raises ProposalIntercepted - halting the agent and capturing intent.
    The tool never executes side effects; it only passes Claim over The Wall.

    In production with LangChain, wrap this with @tool decorator:
        from langchain_core.tools import tool
        submit_tool = tool(create_submit_policy_proposal_tool())
    """

    def submit_policy_proposal(proposal_json: str) -> str:
        """
        Submit a policy proposal to the DIR Kernel for validation.

        This tool does NOT execute any side effect. It passes the intent (Claim)
        over 'The Wall' to Kernel Space for deterministic validation.

        Args:
            proposal_json: JSON with action details.
                Format: {"action": "TERMINATE", "resource_id": "i-xxx", "reason": "..."}

        Raises:
            ProposalIntercepted: Always - this is the interception mechanism.
        """
        raise ProposalIntercepted(proposal_json)

    return submit_policy_proposal


# -----------------------------------------------------------------------------
# LangChain ROA Wrapper
# -----------------------------------------------------------------------------


class LangChainROAWrapper:
    """
    Wraps a LangChain-style agent in an ROA interface.

    Responsibilities:
    - Injects mission from ResponsibilityContract into agent context
    - Provides exactly one action tool: Submit_Policy_Proposal
    - Intercepts tool invocation, halts execution, returns PolicyProposal
    - Ensures no side effects occur in User Space (ROA Manifesto §4.4, §5)

    [DEMO]: This implementation uses a simulated agent. In production,
    replace _simulate_agent_decision() with LangChain AgentExecutor.
    See README.md "Production Considerations" for integration pattern.
    """

    def __init__(self, contract: FinOpsContract):
        self.contract = contract
        self._tool = create_submit_policy_proposal_tool()
        self._system_prompt = self._build_system_prompt()

    def _build_system_prompt(self) -> str:
        """
        Build system prompt injecting mission from contract.
        
        This is the KEY TRANSFORMATION: injecting mission boundaries into
        task-oriented agent context, converting "do X now" into "optimize Y
        over time within boundaries Z".
        """
        return f"""You are a FinOps agent operating under a MISSION CONTRACT.

MISSION (Your long-term optimization target):
{self.contract.mission}

AUTHORITY BOUNDARIES:
- Allowed environments: {self.contract.allowed_environments}
- Allowed actions: {self.contract.allowed_policy_types}
- Prohibited: Any action outside these boundaries

YOUR RESPONSIBILITY:
You are accountable for cost optimization WITHIN your boundaries.
If you identify high-value targets outside your authority (e.g., PROD instances),
you MUST NOT propose actions on them. Your mission is bounded by your contract.

OUTPUT FORMAT:
You may ONLY output actions by calling Submit_Policy_Proposal with JSON:
{{
  "action": "TERMINATE",
  "resource_id": "i-xxx",
  "reason": "Cost optimization rationale"
}}

Never execute cloud APIs directly. All proposals cross The Wall to Kernel Space.
"""

    # -------------------------------------------------------------------------
    # [DEMO SIMULATION BOUNDARY]
    # In production: Replace these methods with LangChain AgentExecutor invocation.
    # The agent would receive idle_resources as context and reason about which
    # instance to propose for termination. Here we simulate that decision.
    # -------------------------------------------------------------------------

    def _demonstrate_mission_injection(self, instances: List[Dict[str, Any]]) -> None:
        """
        [DEMO] Show how ROA wrapper injects mission into task-oriented context.
        
        This demonstrates the KEY TRANSFORMATION:
        Task-Oriented Agent: "Do X now" (stateless, unbounded)
            ↓
        Mission-Oriented Agent: "Optimize Y over time within boundaries Z" (stateful, governed)
        """
        print("\n" + "="*70)
        print("[MISSION INJECTION DEMO]")
        print("="*70)
        
        # What a NAKED LangChain agent would see:
        naked_prompt = (
            "Analyze these idle cloud instances and terminate the most expensive ones:\n"
            f"{json.dumps(instances, indent=2)}"
        )
        
        print("\n🔴 NAKED LangChain Agent (Task-Oriented):")
        print("-"*70)
        print(naked_prompt[:150] + "...")
        print("\n  Characteristics:")
        print("    ❌ No long-term mission")
        print("    ❌ No authority boundaries")
        print("    ❌ No continuity across decisions")
        print("    ❌ Stateless execution")
        print("\n  Risk: Agent might terminate PROD instance because task says")
        print("        'most expensive' and i-prod-api-01 has highest idle time.")
        
        print("\n🟢 ROA-WRAPPED Agent (Mission-Oriented):")
        print("-"*70)
        print(self._system_prompt[:200] + "...")
        print("\n  Characteristics:")
        print("    ✅ Mission provides long-term optimization context")
        print("    ✅ Contract boundaries constrain proposals")
        print("    ✅ Agent accountable to responsibility")
        print("    ✅ Decisions form coherent trajectory")
        print("\n  Safety: Agent sees i-prod-api-01 but recognizes it violates mission.")
        print("          Proposes within bounds even if savings are lower.")
        print("\n  → Mission CONTRACT transforms unbounded task into governed responsibility")
        print("="*70 + "\n")

    def _simulate_agent_decision(self, idle_instances: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        [DEMO] Simulate mission-aware agent reasoning to select target instance.

        In production, this would be the LangChain ReAct loop:
            agent_executor = AgentExecutor(agent=react_agent, tools=[self._tool])
            result = agent_executor.invoke({"input": context, "mission": self._system_prompt})

        This simulation demonstrates mission-bounded reasoning:
        - Agent sees ALL instances (including PROD)
        - Agent recognizes PROD violates mission boundaries
        - Agent selects best target WITHIN allowed_environments
        """
        if not idle_instances:
            return {"action": "NOOP", "resource_id": None, "reason": "No idle instances found"}

        # [MISSION-AWARE REASONING]
        # Identify instances by environment (simulated - real agent would reason via LLM)
        prod_instances = [i for i in idle_instances if "prod" in i.get("id", "").lower()]
        allowed_instances = [
            i for i in idle_instances 
            if "dev" in i.get("id", "").lower() or "stg" in i.get("id", "").lower()
        ]

        # Mission awareness: Log detection of out-of-bounds instances
        if prod_instances:
            logger.info(
                "[%s] Mission boundary awareness: Detected %d PROD instance(s) with total %d idle hours, "
                "but mission contract restricts to %s. Will not propose PROD actions.",
                self.contract.agent_id,
                len(prod_instances),
                sum(i.get("idle_hours", 0) for i in prod_instances),
                self.contract.allowed_environments
            )

        # Select best target WITHIN mission boundaries
        if not allowed_instances:
            return {
                "action": "NOOP",
                "resource_id": None,
                "reason": f"No instances found within allowed_environments {self.contract.allowed_environments}"
            }

        # Greedy optimization within bounds
        target = max(allowed_instances, key=lambda x: x.get("idle_hours", 0))

        return {
            "action": "TERMINATE",
            "resource_id": target.get("id", "unknown"),
            "reason": (
                f"Idle for {target.get('idle_hours', 0)}+ hours; highest savings within "
                f"mission boundaries {self.contract.allowed_environments}"
            ),
        }

    def run(self, dfid: str, idle_resources_json: str, show_mission_demo: bool = False) -> PolicyProposal:
        """
        Invoke the agent with idle resources context. Returns PolicyProposal (Claim).

        Args:
            dfid: Decision Flow ID for traceability
            idle_resources_json: JSON string with idle instances list
            show_mission_demo: If True, print mission injection demonstration

        Returns:
            PolicyProposal - the agent's intent, ready for DIM validation
        """
        # Parse input context
        try:
            resources = json.loads(idle_resources_json)
        except json.JSONDecodeError:
            resources = {"instances": []}

        instances = resources.get("instances", [])
        if not isinstance(instances, list):
            instances = []

        # [DEMO] Show mission injection transformation (first run only)
        if show_mission_demo:
            self._demonstrate_mission_injection(instances)

        # [DEMO] Simulate mission-aware agent decision
        # [PRODUCTION: This would be LangChain AgentExecutor with system_prompt]
        # agent_executor = AgentExecutor(agent=react_agent, tools=[self._tool])
        # result = agent_executor.invoke({"input": instances, "mission": self._system_prompt})
        decision = self._simulate_agent_decision(instances)
        proposal_json = json.dumps(decision)

        log_with_dfid(
            logger,
            dfid,
            logging.INFO,
            "[%s] Agent invoking Submit_Policy_Proposal: %s",
            self.contract.agent_id,
            decision.get("resource_id"),
        )

        # Invoke tool and intercept
        try:
            self._tool(proposal_json)
        except ProposalIntercepted as intercepted:
            # Convert intercepted JSON to structured PolicyProposal
            data = json.loads(intercepted.proposal_json)

            proposal = PolicyProposal(
                dfid=dfid,
                agent_id=self.contract.agent_id,
                policy_kind=data.get("action", "UNKNOWN"),
                params={
                    "resource_id": data.get("resource_id"),
                    "reason": data.get("reason", ""),
                },
                confidence=0.9,
                justification=data.get("reason", ""),
            )

            log_with_dfid(
                logger,
                dfid,
                logging.INFO,
                "[%s] Proposal intercepted: %s %s",
                self.contract.agent_id,
                proposal.policy_kind,
                proposal.params.get("resource_id"),
            )
            return proposal

        # Should never reach here - tool always raises
        raise RuntimeError("Tool interception failed - ProposalIntercepted not raised")


# -----------------------------------------------------------------------------
# FinOps DIM Validation
# -----------------------------------------------------------------------------


def validate_finops_proposal(
    proposal: PolicyProposal,
    context: Dict[str, Any],
    contract: FinOpsContract,
    allowed_agents: Optional[List[str]] = None,
) -> Tuple[str, str]:
    """
    Validate FinOps proposal: base DIM checks + environment boundary.

    Validation layers:
    1. Base DIM validation (schema, RBAC via allowed_agents)
    2. Resource existence check (resource_id in Context Store)
    3. Environment boundary check (instance env in allowed_environments)

    Args:
        proposal: The PolicyProposal to validate
        context: Must contain {"instances": {"i-xxx": {"environment": "PROD"|"DEV"|"STG"}}}
        contract: FinOpsContract with allowed_environments
        allowed_agents: List of authorized agent IDs

    Returns:
        Tuple of (verdict, reason) where verdict is "ACCEPT" or "REJECT"
    """
    # Layer 1: Base validation (schema, RBAC)
    base_context = {"state": context.get("state", {})}
    verdict, reason = validate_proposal(proposal, base_context, allowed_agents or [])
    if verdict == "REJECT":
        return verdict, reason

    # Layer 2: Resource existence
    resource_id = proposal.params.get("resource_id")
    if not resource_id:
        return "REJECT", "Missing resource_id in proposal params"

    instances = context.get("instances", {})
    if resource_id not in instances:
        return "REJECT", f"Resource {resource_id} not found in Context Store"

    # Layer 3: Environment boundary
    instance_env = instances[resource_id].get("environment", "UNKNOWN")
    if instance_env not in contract.allowed_environments:
        return (
            "REJECT",
            f"Instance {resource_id} is {instance_env}; agent allowed_environments={contract.allowed_environments}",
        )

    return "ACCEPT", "Validation passed"


# -----------------------------------------------------------------------------
# Main: End-to-End Flow
# -----------------------------------------------------------------------------


def run_scenario(
    name: str,
    wrapper: LangChainROAWrapper,
    idle_resources: Dict[str, Any],
    context_store: Dict[str, Any],
    contract: FinOpsContract,
    show_mission_demo: bool = False,
) -> Tuple[PolicyProposal, str, str]:
    """Run a single scenario and return proposal + verdict."""
    dfid = new_dfid()
    log_with_dfid(logger, dfid, logging.INFO, "Starting scenario: %s", name)

    proposal = wrapper.run(dfid, json.dumps(idle_resources), show_mission_demo=show_mission_demo)
    verdict, reason = validate_finops_proposal(
        proposal, context_store, contract, allowed_agents=[contract.agent_id]
    )

    print(f"  Proposal: {proposal.policy_kind} {proposal.params.get('resource_id')}")
    print(f"  DIM Verdict: {verdict}")
    print(f"  Reason: {reason}")

    return proposal, verdict, reason


def main() -> None:
    print("=" * 70)
    print("12_langchain_roa_wrapper - LangChain ROA Wrapper / FinOps Demo")
    print("=" * 70)

    # -------------------------------------------------------------------------
    # Setup: Contract, Context Store, Wrapper
    # -------------------------------------------------------------------------

    # FinOps contract: agent may only act on DEV and STG (PROD excluded)
    contract = FinOpsContract(
        agent_id="finops_autoscaler_v1",
        mission="Analyze cloud usage logs and reduce costs by shutting down idle resources, without disrupting production.",
        allowed_environments=["DEV", "STG"],
        allowed_policy_types=["TERMINATE", "STOP", "SCALE_DOWN"],
    )

    # Context Store: authoritative infrastructure state (source of truth)
    # This is what DIM validates against - NOT what agent sees
    context_store = {
        "instances": {
            "i-prod-api-01": {"environment": "PROD", "idle_hours": 72, "name": "prod-api-01"},
            "i-dev-worker-03": {"environment": "DEV", "idle_hours": 48, "name": "dev-worker-03"},
        }
    }

    wrapper = LangChainROAWrapper(contract)

    # -------------------------------------------------------------------------
    # Scenario A: Agent sees PROD instance as most idle -> proposes TERMINATE
    # DIM REJECTS because PROD not in allowed_environments
    # -------------------------------------------------------------------------
    print("\n[SCENARIO A] Agent analyzes logs, proposes TERMINATE on most-idle instance (PROD)")
    print("-" * 70)

    # Agent receives this view of idle resources (highest idle_hours = PROD)
    idle_resources_a = {
        "instances": [
            {"id": "i-prod-api-01", "idle_hours": 72, "name": "prod-api-01"},
            {"id": "i-dev-worker-03", "idle_hours": 48, "name": "dev-worker-03"},
        ]
    }

    proposal_a, verdict_a, reason_a = run_scenario(
        "PROD termination attempt", wrapper, idle_resources_a, context_store, contract, show_mission_demo=True
    )

    # Check what agent actually proposed
    proposed_resource_id = proposal_a.params.get("resource_id", "")
    if verdict_a == "ACCEPT" and "dev" in proposed_resource_id.lower():
        print("  -> Mission-aware agent autonomously avoided PROD, selected DEV instead.")
    elif verdict_a == "REJECT" and "prod" in proposed_resource_id.lower():
        print("  -> DIM rejected PROD termination (defense-in-depth).")
    else:
        print("  -> Agent respected mission boundaries.")

    # -------------------------------------------------------------------------
    # Scenario B: Agent sees only DEV instance -> proposes TERMINATE
    # DIM ACCEPTS because DEV is in allowed_environments
    # -------------------------------------------------------------------------
    print("\n[SCENARIO B] Agent analyzes logs, proposes TERMINATE on DEV instance")
    print("-" * 70)

    # Agent receives this view (only DEV visible - simulates filtered input)
    idle_resources_b = {
        "instances": [
            {"id": "i-dev-worker-03", "idle_hours": 48, "name": "dev-worker-03"},
        ]
    }

    proposal_b, verdict_b, reason_b = run_scenario("DEV termination", wrapper, idle_resources_b, context_store, contract)

    if verdict_b == "ACCEPT":
        print("  -> Safe to execute (DEV within allowed_environments).")
    else:
        print("  -> Unexpected REJECT for DEV instance.")

    # -------------------------------------------------------------------------
    # Summary
    # -------------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("[SUMMARY] LangChain ROA Wrapper - FinOps Demo")
    print("=" * 70)
    print(f"  Scenario A: Agent saw PROD (72h) + DEV (48h)")
    print(f"    → Mission-aware agent selected: DEV (within bounds)")
    print(f"    → DIM verdict: {verdict_a}")
    print(f"  Scenario B: Agent saw only DEV (48h)")
    print(f"    → Agent selected: DEV")
    print(f"    → DIM verdict: {verdict_b}")
    print()
    print("  KEY INSIGHT: Mission injection transforms agent behavior BEFORE DIM.")
    print("  The wrapper doesn't just intercept - it makes the agent")
    print("  mission-aware during reasoning, not just during validation.")
    print()
    print("  A naked LangChain agent would have selected PROD (highest idle)")
    print("  → Direct AWS termination → catastrophic outage.")
    print()
    print("  ROA-wrapped agent respects mission boundaries in its reasoning")
    print("  → Proposes DEV → DIM validates → Safe execution.")
    print("=" * 70)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
34_langchain_roa_wrapper - LangChain ReAct agent wrapped in ROA interface.

Demonstrates:
- Real LangChain ReAct agent + LLM (Ollama) for mission-aware reasoning
- Submit_Policy_Proposal tool: intercepts intent, passes over "The Wall" to DIR Kernel
- Context Store from config.yaml - source of truth for DIM validation
- FinOps use case: DIM rejects TERMINATE on PROD instance (allowed_environments=[DEV, STG])

Run from repo root: python samples/34_langchain_roa_wrapper/run.py
Requires: pip install -e . pip install -r samples/34_langchain_roa_wrapper/requirements.txt

ROA Manifesto §4-5, DIR Architectural Pattern §6.

Requirements:
    ollama serve
    ollama pull gemma3:4b   # or model from config.yaml (must support tool/function calling)
"""
from __future__ import annotations

import json
import logging
import sys
from typing import Any, Dict, List, Optional, Tuple

from dir import PolicyProposal, new_dfid
from dir.dim import validate_proposal
from utils.logging_utils import log_with_dfid
from utils.ollama_client import check_ollama

from contracts import FinOpsContract
from config_loader import AppConfig, LlmConfig, ScenarioConfig, load_config

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)
# Reduce httpx noise (HTTP Request logs)
logging.getLogger("httpx").setLevel(logging.WARNING)


# -----------------------------------------------------------------------------
# Ollama health check
# -----------------------------------------------------------------------------


def _check_ollama(llm_cfg: LlmConfig) -> None:
    """Verify Ollama is reachable and the requested model is available."""
    base_url = llm_cfg.effective_base_url()
    model = llm_cfg.effective_model()
    if not check_ollama(base_url, model):
        print()
        print(f"[ERROR] Ollama not reachable at {base_url} or model '{model}' not found.")
        print()
        print("  Start Ollama:    ollama serve")
        print(f"  Pull the model:  ollama pull {model}")
        print()
        print("  Or set env:  OLLAMA_BASE_URL=http://localhost:11434")
        print(f"               OLLAMA_MODEL={model}")
        print()


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
# Submit_Policy_Proposal Tool - The Trojan Horse
# -----------------------------------------------------------------------------


def _create_submit_policy_proposal_tool():
    """
    Create the Submit_Policy_Proposal LangChain tool.

    When invoked by the agent, raises ProposalIntercepted - halting execution
    and capturing intent. The tool never executes side effects.
    """
    from langchain_core.tools import tool

    @tool
    def submit_policy_proposal(proposal_json: str) -> str:
        """Submit a policy proposal to the DIR Kernel for validation.
        Call with JSON: {"action": "TERMINATE"|"STOP"|"SCALE_DOWN", "resource_id": "i-xxx", "reason": "..."}"""
        raise ProposalIntercepted(proposal_json)

    return submit_policy_proposal


# -----------------------------------------------------------------------------
# LangChain ROA Wrapper
# -----------------------------------------------------------------------------


def _make_llm(llm_cfg: LlmConfig):
    """Create ChatOllama: native Ollama integration, no openai dependency."""
    from langchain_ollama import ChatOllama

    return ChatOllama(
        model=llm_cfg.effective_model(),
        base_url=llm_cfg.effective_base_url().rstrip("/"),
        temperature=llm_cfg.temperature,
    )


class LangChainROAWrapper:
    """
    Wraps a real LangChain ReAct agent + LLM in an ROA interface.

    - Injects mission from contract into agent prompt
    - Provides exactly one action tool: Submit_Policy_Proposal
    - Intercepts tool invocation, halts execution, returns PolicyProposal
    - Uses Context Store from config for DIM validation (not for LLM input)
    """

    def __init__(self, contract: FinOpsContract, llm_cfg: LlmConfig):
        self.contract = contract
        self._llm = _make_llm(llm_cfg)
        self._tool = _create_submit_policy_proposal_tool()
        self._tools = [self._tool]
        self._agent_executor = self._build_agent()

    def _build_agent(self):
        """Build agent using langchain create_agent (LangGraph-based)."""
        from langchain.agents import create_agent

        system_prompt = f"""You are a FinOps agent under a MISSION CONTRACT.
MISSION: {self.contract.mission}
AUTHORITY: Allowed environments {", ".join(self.contract.allowed_environments)}.
Allowed actions: {", ".join(self.contract.allowed_policy_types)}. PROHIBITED: PROD.
You MUST call Submit_Policy_Proposal with JSON: {{"action": "TERMINATE", "resource_id": "i-xxx", "reason": "..."}}
Choose ONE instance within your boundaries. Infer environment from instance id (prod/dev/stg) if not provided."""

        return create_agent(
            model=self._llm,
            tools=self._tools,
            system_prompt=system_prompt,
        )

    def _invoke_prompt_fallback(self, agent_input: str) -> Dict[str, Any]:
        """Fallback for models that don't support tools: prompt for JSON output."""
        from langchain_core.messages import HumanMessage

        prompt = agent_input + """

Output ONLY a valid JSON object: {"action": "TERMINATE"|"STOP"|"SCALE_DOWN", "resource_id": "i-xxx", "reason": "..."}
No markdown, no explanation, only the JSON."""
        response = self._llm.invoke([HumanMessage(content=prompt)])
        raw = response.content if hasattr(response, "content") else str(response)
        text = raw if isinstance(raw, str) else str(raw)

        # Extract JSON block (handle markdown, extra text)
        start = text.find("{")
        if start >= 0:
            depth = 0
            for i, c in enumerate(text[start:], start):
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        return json.loads(text[start : i + 1])
        raise ValueError(f"Could not parse JSON from LLM response: {text[:200]}")

    def _build_agent_input(self, instances: List[Dict[str, Any]]) -> str:
        """Build task input for the agent with idle instances from scenario."""
        if not instances:
            return "No idle instances. Respond with NOOP or explain no action needed."
        return (
            "Analyze these idle cloud instances. Propose ONE termination using Submit_Policy_Proposal. "
            "Select the best target WITHIN your allowed environments (DEV, STG). "
            "Never propose PROD. Instances:\n" + json.dumps(instances, indent=2)
        )

    def _demonstrate_mission_injection(self, instances: List[Dict[str, Any]]) -> None:
        """Show mission injection transformation (first scenario only)."""
        print("\n" + "=" * 70)
        print("[MISSION INJECTION DEMO]")
        print("=" * 70)
        print("\n🔴 NAKED LangChain Agent: 'terminate the most expensive ones', no boundaries")
        print("🟢 ROA-WRAPPED: Mission + allowed_environments=[DEV, STG], PROD prohibited")
        print("=" * 70 + "\n")

    def run(
        self,
        dfid: str,
        idle_resources_json: str,
        show_mission_demo: bool = False,
        trust_input_labels: bool = False,
    ) -> PolicyProposal:
        """
        Invoke LangChain agent with idle resources. Returns PolicyProposal (Claim).
        DIM validates against Context Store from config; agent sees only idle_resources.
        """
        try:
            resources = json.loads(idle_resources_json)
        except json.JSONDecodeError:
            resources = {"instances": []}

        instances = resources.get("instances", [])
        if not isinstance(instances, list):
            instances = []

        if show_mission_demo:
            self._demonstrate_mission_injection(instances)

        agent_input = self._build_agent_input(instances)

        from langchain_core.messages import HumanMessage

        data = None
        try:
            self._agent_executor.invoke({"messages": [HumanMessage(content=agent_input)]})
        except ProposalIntercepted as intercepted:
            data = json.loads(intercepted.proposal_json)
        except Exception as e:
            # Fallback: models like gemma3 don't support tools; use prompt-based JSON output
            if "does not support tools" in str(e) or "400" in str(e):
                print("  [MODE] Prompt-based JSON (model does not support tools)")
                data = self._invoke_prompt_fallback(agent_input)
            else:
                raise

        if data:
            return PolicyProposal(
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

        raise RuntimeError("Could not obtain proposal from agent")


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
    trust_input_labels: bool = False,
) -> Tuple[PolicyProposal, str, str]:
    """Run a single scenario and return proposal + verdict."""
    dfid = new_dfid()
    log_with_dfid(logger, dfid, logging.INFO, "Starting scenario: %s", name)

    # --- REQUEST: what the agent sees ---
    instances = idle_resources.get("instances", [])
    print("\n  [REQUEST] Agent input (idle instances):")
    for inst in instances:
        print(f"    - {inst.get('id', '?')}: idle_hours={inst.get('idle_hours', '?')}, env={inst.get('environment', '(infer from id)')}")
    if not instances:
        print("    (none)")

    proposal = wrapper.run(
        dfid,
        json.dumps(idle_resources),
        show_mission_demo=show_mission_demo,
        trust_input_labels=trust_input_labels,
    )

    # --- LANGCHAIN OUTPUT: what the agent proposed ---
    print("\n  [LANGCHAIN OUTPUT] Agent proposal:")
    print(f"    action: {proposal.policy_kind}")
    print(f"    resource_id: {proposal.params.get('resource_id', 'N/A')}")
    print(f"    reason: {proposal.params.get('reason', '')}")

    verdict, reason = validate_finops_proposal(
        proposal, context_store, contract, allowed_agents=[contract.agent_id]
    )

    # --- DIM VERDICT: why accepted or rejected ---
    resource_id = proposal.params.get("resource_id", "")
    instance_env = context_store.get("instances", {}).get(resource_id, {}).get("environment", "?")
    print(f"\n  [DIM VERDICT] {verdict}")
    if verdict == "ACCEPT":
        print(f"    WHY ACCEPTED: {resource_id} is {instance_env}, within allowed {contract.allowed_environments}")
    else:
        print(f"    WHY REJECTED: {reason}")

    return proposal, verdict, reason


def main() -> None:
    print("=" * 70)
    print("34_langchain_roa_wrapper - LangChain ROA Wrapper / FinOps Demo")
    print("=" * 70)

    # Load configuration from config.yaml
    cfg = load_config()
    _check_ollama(cfg.llm)
    contract = cfg.contract
    context_store = cfg.context_store
    wrapper = LangChainROAWrapper(contract, cfg.llm)

    # Run all scenarios from config
    results: List[Tuple[str, str, str]] = []
    for i, scenario in enumerate(cfg.scenarios):
        print(f"\n[{scenario.label}]")
        print("-" * 70)

        # Ensure idle_resources has 'instances' key (list format for agent input)
        idle_resources = scenario.idle_resources
        if "instances" not in idle_resources:
            idle_resources = {"instances": []}

        proposal, verdict, reason = run_scenario(
            scenario.label,
            wrapper,
            idle_resources,
            context_store,
            contract,
            show_mission_demo=scenario.show_mission_demo,
            trust_input_labels=scenario.trust_input_labels,
        )
        results.append((scenario.label, verdict, proposal.params.get("resource_id", "")))

        # Scenario-specific feedback
        proposed_resource_id = proposal.params.get("resource_id", "")
        if verdict == "ACCEPT" and "dev" in proposed_resource_id.lower():
            print("  -> Mission-aware agent autonomously avoided PROD, selected DEV instead.")
        elif verdict == "REJECT" and "prod" in proposed_resource_id.lower():
            print("  -> DIM rejected PROD termination (defense-in-depth).")
        elif verdict == "ACCEPT":
            print("  -> Safe to execute (within allowed_environments).")
        elif verdict == "REJECT":
            print("  -> Agent trusted input labels; DIM validated against Context Store.")
            print("  -> Catastrophic production outage PREVENTED by DIM.")

    # Summary
    print("\n" + "=" * 70)
    print("[SUMMARY] LangChain ROA Wrapper - FinOps Demo")
    print("=" * 70)
    for label, verdict, resource_id in results:
        short_label = (label[:50] + "...") if len(label) > 50 else label
        print(f"  {short_label}")
        print(f"    -> DIM verdict: {verdict} (resource: {resource_id or 'N/A'})")
    print()
    print("  KEY INSIGHT: Mission injection transforms agent behavior BEFORE DIM.")
    print("  The wrapper doesn't just intercept - it makes the agent")
    print("  mission-aware during reasoning, not just during validation.")
    print()
    print("  When input quality fails (Scenario C), DIM catches dangerous proposals")
    print("  by validating against Context Store - not agent input.")
    print()
    print("  ROA: Mission injection + DIM validation = defense in depth.")
    print("=" * 70)


if __name__ == "__main__":
    main()

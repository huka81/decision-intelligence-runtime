"""User Space: LangChain ReAct + explicit ROA stages Explain → Policy → Self-Check → Proposal."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from dir_core import PolicyProposal, ResponsibilityContract
from dir_core.utils.logging_utils import log_with_dfid
from shared.llm.clients import MockLLMClient

from schemas import parse_llm_json

logger = logging.getLogger(__name__)


class ProposalIntercepted(Exception):
    """Control flow when Submit_Policy_Proposal is invoked (Claim, not Fact)."""

    def __init__(self, proposal_json: str) -> None:
        self.proposal_json = proposal_json
        super().__init__("Proposal intercepted — handoff to Kernel Space")


def _create_submit_policy_proposal_tool():
    from langchain_core.tools import tool

    @tool
    def submit_policy_proposal(proposal_json: str) -> str:
        """Submit a policy proposal to the DIR Kernel for validation.
        JSON: {"action": "TERMINATE"|"STOP"|"SCALE_DOWN", "resource_id": "i-xxx", "reason": "..."}"""
        raise ProposalIntercepted(proposal_json)

    return submit_policy_proposal


def _make_chat_ollama(llm_defaults: Dict[str, Any]):
    import os

    from langchain_ollama import ChatOllama

    model = os.getenv("OLLAMA_MODEL", str(llm_defaults.get("model", "gemma3:4b")))
    base_url = os.getenv(
        "OLLAMA_BASE_URL",
        str(llm_defaults.get("base_url", "http://localhost:11434")),
    ).rstrip("/")
    temperature = float(llm_defaults.get("temperature", 0.2))
    return ChatOllama(model=model, base_url=base_url, temperature=temperature)


class LangChainROAWrapper:
    """LangChain ReAct agent with a single kernel handoff tool."""

    def __init__(
        self,
        contract: ResponsibilityContract,
        llm_defaults: Dict[str, Any],
        allowed_environments: List[str],
    ) -> None:
        self.contract = contract
        self._allowed_envs = allowed_environments
        self._llm = _make_chat_ollama(llm_defaults)
        self._tool = _create_submit_policy_proposal_tool()
        self._agent_executor = self._build_agent()

    def _build_agent(self):
        from langchain.agents import create_agent

        mission = self.contract.mission
        envs = ", ".join(self._allowed_envs) if self._allowed_envs else "DEV, STG"
        system_prompt = f"""You are a FinOps agent under a MISSION CONTRACT.
MISSION: {mission}
Allowed instance environments ONLY: {envs}. Never terminate PROD.
Allowed policy actions: {", ".join(self.contract.allowed_policy_types)}.
You MUST call Submit_Policy_Proposal with JSON:
{{"action": "TERMINATE", "resource_id": "i-xxx", "reason": "..."}}
Choose ONE instance within these boundaries."""

        return create_agent(
            model=self._llm,
            tools=[self._tool],
            system_prompt=system_prompt,
        )

    def _invoke_prompt_fallback(self, agent_input: str) -> Dict[str, Any]:
        from langchain_core.messages import HumanMessage

        prompt = agent_input + """

Output ONLY a valid JSON object: {"action": "TERMINATE"|"STOP"|"SCALE_DOWN", "resource_id": "i-xxx", "reason": "..."}
No markdown, no explanation, only the JSON."""
        response = self._llm.invoke([HumanMessage(content=prompt)])
        raw = response.content if hasattr(response, "content") else str(response)
        text = raw if isinstance(raw, str) else str(raw)
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

    def _build_agent_input(
        self,
        instances: List[Dict[str, Any]],
        trust_input_labels: bool,
    ) -> str:
        if not instances:
            return "No idle instances. Explain briefly; then output SCALE_DOWN with empty resource_id if appropriate."
        hint = ""
        if trust_input_labels:
            hint = "Trust environment labels from the payload when choosing a target.\n"
        return (
            hint
            + "Analyze these idle cloud instances. Propose ONE action using Submit_Policy_Proposal. "
            + "Instances:\n"
            + json.dumps(instances, indent=2)
        )

    def run_live(
        self,
        dfid: str,
        agent_id: str,
        instances: List[Dict[str, Any]],
        trust_input_labels: bool,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """Policy stage only (Explain handled separately via shared LLM in run). Returns parsed policy dict or error."""
        from langchain_core.messages import HumanMessage

        agent_input = self._build_agent_input(instances, trust_input_labels)
        try:
            self._agent_executor.invoke({"messages": [HumanMessage(content=agent_input)]})
        except ProposalIntercepted as intercepted:
            parsed = parse_llm_json(intercepted.proposal_json)
            if not parsed:
                return None, "Submit_Policy_Proposal payload is not valid JSON"
            return parsed, None
        except Exception as e:
            if "does not support tools" in str(e) or "400" in str(e):
                log_with_dfid(
                    logger,
                    dfid,
                    logging.INFO,
                    "LangChain prompt fallback (model does not support tools)",
                )
                try:
                    return self._invoke_prompt_fallback(agent_input), None
                except Exception as e2:
                    return None, str(e2)
            return None, str(e)
        return None, "No proposal captured from LangChain"


def run_finops_roa_cycle(
    llm: Any,
    contract: ResponsibilityContract,
    dfid: str,
    agent_id: str,
    idle_resources: Dict[str, Any],
    trust_input_labels: bool,
    llm_defaults: Dict[str, Any],
    allowed_environments: List[str],
    *,
    show_mission_demo: bool = False,
) -> Tuple[Optional[PolicyProposal], Optional[str], Dict[str, Any]]:
    """
    Explain → Policy → Self-Check → Proposal.

    Returns ``(proposal | None, error | None, explain_meta)`` for audit and HTML reports.
    Policy uses LangChain when ``llm`` is not :class:`MockLLMClient`; otherwise mock ``generate`` only.
    """
    instances = idle_resources.get("instances", [])
    if not isinstance(instances, list):
        instances = []

    if show_mission_demo:
        log_with_dfid(
            logger,
            dfid,
            logging.INFO,
            "Mission injection demo: ROA contract boundaries vs task-only agent",
        )

    mission = contract.mission
    explain_prompt = (
        "[FINOPS_EXPLAIN]\n"
        "Summarize risks and opportunities for idle cloud instances under this mission:\n"
        f"{mission}\n"
        f"Instances preview:\n{json.dumps(instances)[:4000]}\n"
    )
    explain_raw = llm.generate(explain_prompt, system=mission)
    explain_parsed = parse_llm_json(explain_raw) or {}
    narrative = str(explain_parsed.get("narrative", explain_raw[:500]))

    policy_data: Optional[Dict[str, Any]] = None
    policy_err: Optional[str] = None

    if isinstance(llm, MockLLMClient):
        policy_prompt = (
            "[FINOPS_POLICY]\n"
            f"trust_input_labels={int(trust_input_labels)}\n"
            "PAYLOAD_JSON\n"
            + json.dumps({"trust_input_labels": trust_input_labels, "idle_resources": idle_resources})
        )
        policy_raw = llm.generate(policy_prompt, system=mission)
        policy_data = parse_llm_json(policy_raw)
        if not policy_data:
            policy_err = "Mock policy JSON parse failed"
    else:
        wrapper = LangChainROAWrapper(contract, llm_defaults, allowed_environments)
        policy_data, policy_err = wrapper.run_live(dfid, agent_id, instances, trust_input_labels)
        if policy_data is not None:
            policy_data.setdefault("reason", narrative[:200])
            policy_data.setdefault("confidence", 0.85)

    if policy_err or not policy_data:
        return None, policy_err or "Policy stage produced no data", explain_parsed

    action = str(policy_data.get("action", "SCALE_DOWN"))
    try:
        confidence = float(policy_data.get("confidence", 0.85))
    except (TypeError, ValueError):
        confidence = 0.0

    if action not in contract.allowed_policy_types:
        return None, f"Self-check: action {action} not in allowed_policy_types", explain_parsed
    if confidence < float(contract.escalate_on_uncertainty):
        return None, (
            f"Self-check: confidence {confidence} below escalate_on_uncertainty "
            f"{contract.escalate_on_uncertainty}"
        ), explain_parsed

    return (
        PolicyProposal(
            dfid=dfid,
            agent_id=agent_id,
            policy_kind=action,
            params={
                "resource_id": policy_data.get("resource_id"),
                "reason": policy_data.get("reason", ""),
            },
            confidence=confidence,
            justification=str(policy_data.get("reason", "")),
        ),
        None,
        explain_parsed,
    )

"""
CrewAI User Space adapter: Explain (Analyst) → Policy (Decision Maker JSON) → Self-Check → Proposal.

When ``use_crew_llm`` is False (``USE_MOCK_LLM=1`` / mock bootstrap), uses deterministic claim→proposal
so the sample runs without Ollama (Sample Guide §12).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Optional, Tuple

from pydantic import BaseModel, Field

from dir_core import PolicyProposal
from dir_core.utils.logging_utils import log_with_dfid

from contracts import ClaimsContract
from schemas import CrewConfig, parse_llm_json


class RefundProposalOutput(BaseModel):
    action: str = Field(
        description="Always 'REFUND'. The DIR Kernel decides ACCEPT/REJECT/ESCALATE."
    )
    order_id: str = Field(description="Order ID from the claim.")
    amount_eur: float = Field(description="Refund amount in EUR.")
    category: str = Field(description="Product category from the claim.")
    reason: str = Field(description="Brief justification for the refund proposal.")


class ClaimExtractionOutput(BaseModel):
    order_id: str = Field(description="Order ID mentioned in the text (e.g. ord_001).")
    amount_eur: float = Field(description="Refund amount in EUR.")
    category: str = Field(
        description="Product category: electronics, clothing, home, or other."
    )
    reason: str = Field(description="Brief reason for the refund claim.")
    purchase_date: Optional[str] = Field(
        default=None,
        description="Purchase date in ISO format if mentioned, else null.",
    )


def _ensure_crewai_openai_compat() -> None:
    """CrewAI native OpenAI provider imports a symbol renamed in openai 1.83."""
    import openai.types.chat as chat_types

    if not hasattr(chat_types, "ChatCompletionMessageFunctionToolCall"):
        from openai.types.chat import ChatCompletionMessageToolCall

        chat_types.ChatCompletionMessageFunctionToolCall = ChatCompletionMessageToolCall


def _make_crew_llm(model: str, base_url: str, temperature: float) -> Any:
    _ensure_crewai_openai_compat()
    from crewai import LLM

    return LLM(
        model=model,
        provider="openai",
        base_url=base_url.rstrip("/") + "/v1",
        api_key="ollama",
        temperature=temperature,
    )


def mock_extract_claim_from_text(claim_text: str) -> Dict[str, Any]:
    """Deterministic NL intake for mock mode (no CrewAI extraction call)."""
    oid_m = re.search(r"(ord_[a-z0-9]+)", claim_text, re.I)
    order_id = oid_m.group(1) if oid_m else "ord_000"
    amt_m = re.search(r"(\d+(?:\.\d+)?)\s*EUR", claim_text, re.I)
    if not amt_m:
        amt_m = re.search(r"for\s+(\d+(?:\.\d+)?)\s*EUR", claim_text, re.I)
    amount = float(amt_m.group(1)) if amt_m else 0.0
    lo = claim_text.lower()
    if "clothing" in lo or "shirt" in lo:
        category = "clothing"
    elif "home" in lo or "furniture" in lo:
        category = "home"
    else:
        category = "electronics"
    reason = "Mock extraction from NL."
    claim: Dict[str, Any] = {
        "order_id": order_id,
        "amount_eur": amount,
        "category": category,
        "reason": reason,
    }
    pd_m = re.search(r"(\d{4}-\d{2}-\d{2})", claim_text)
    if pd_m:
        claim["purchase_date"] = pd_m.group(1) + "T10:00:00Z"
    return claim


def extract_claim_from_text(claim_text: str, llm: Any) -> Dict[str, Any]:
    from crewai import Agent, Crew, Process, Task

    extractor = Agent(
        role="Claim Extractor",
        goal="Extract structured refund claim data from customer text.",
        backstory=(
            "You extract order_id, amount_eur, category, reason from customer messages. "
            "Use order IDs like ord_001, ord_002. Categories: electronics, clothing, home. "
            "If purchase date is mentioned, use ISO format (YYYY-MM-DD or full ISO)."
        ),
        llm=llm,
        verbose=False,
    )
    task = Task(
        description=(
            f"Extract refund claim from this customer message:\n\n{claim_text}\n\n"
            "Output a JSON object with: order_id, amount_eur, category, reason, purchase_date (optional)."
        ),
        expected_output="JSON with order_id, amount_eur, category, reason",
        output_json=ClaimExtractionOutput,
        agent=extractor,
    )
    crew = Crew(agents=[extractor], tasks=[task], verbose=False, process=Process.sequential)
    result = crew.kickoff()
    data: Optional[Dict[str, Any]] = getattr(result, "json_dict", None)
    if not data:
        raw = getattr(result, "raw", "") or ""
        parsed = parse_llm_json(raw)
        if parsed and "order_id" in parsed:
            data = parsed
    if not data:
        raise RuntimeError(f"Could not extract claim from NL: {claim_text[:120]!r}")
    amt = data.get("amount_eur") or data.get("amount_pln", 0)
    claim = {
        "order_id": str(data.get("order_id", "")),
        "amount_eur": float(amt),
        "category": str(data.get("category", "")),
        "reason": str(data.get("reason", "")),
    }
    if data.get("purchase_date"):
        claim["purchase_date"] = str(data["purchase_date"])
    return claim


def _extract_proposal_from_text(text: str) -> Optional[Dict[str, Any]]:
    def _valid(d: dict) -> bool:
        return "action" in d and "order_id" in d and ("amount_eur" in d or "amount_pln" in d)

    for attempt in [text.strip(), *re.findall(r"\{[^{}]{10,}\}", text, re.DOTALL)]:
        try:
            data = json.loads(attempt)
            if _valid(data):
                if "amount_eur" not in data and "amount_pln" in data:
                    data["amount_eur"] = data["amount_pln"]
                return data
        except (json.JSONDecodeError, TypeError):
            continue
    block = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if block:
        try:
            data = json.loads(block.group(1))
            if _valid(data):
                if "amount_eur" not in data and "amount_pln" in data:
                    data["amount_eur"] = data["amount_pln"]
                return data
        except (json.JSONDecodeError, TypeError):
            pass
    return None


def _mock_policy_dict_from_claim(claim: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "action": "REFUND",
        "order_id": str(claim.get("order_id", "")),
        "amount_eur": float(claim.get("amount_eur") or claim.get("amount_pln") or 0.0),
        "category": str(claim.get("category", "")),
        "reason": str(claim.get("reason", "mock deterministic proposal")),
    }


class CrewAIROAWrapper:
    """CrewAI sequential crew: Analyst (Explain) → Decision Maker (Policy JSON)."""

    def __init__(self, claims_contract: ClaimsContract, crew_cfg: CrewConfig, crew_llm: Any) -> None:
        self.claims_contract = claims_contract
        self.crew_cfg = crew_cfg
        self._llm = crew_llm

    def _boundaries_text(self) -> str:
        c = self.claims_contract
        return (
            f"- Allowed refund categories: {c.allowed_refund_categories}\n"
            f"- Return window: {c.return_window_days} days from purchase\n"
            f"- Max refund without escalation: {c.max_refund_without_escalation} EUR\n"
            f"- Allowed actions: {c.allowed_policy_types}"
        )

    def run_llm_stages(
        self,
        dfid: str,
        claim: Dict[str, Any],
        logger: logging.Logger,
    ) -> Tuple[Optional[Dict[str, Any]], str, Optional[str]]:
        """Returns ``(policy_dict, explain_narrative, error)``."""
        from crewai import Agent, Crew, Process, Task

        claim_str = json.dumps(claim, indent=2)
        boundaries = self._boundaries_text()
        mission = self.claims_contract.mission

        analyst = Agent(
            role=self.crew_cfg.analyst_role,
            goal=self.crew_cfg.analyst_goal,
            backstory=(
                f"You are a senior claims analyst.\n"
                f"Mission: {mission}\n\n"
                f"Authority boundaries:\n{boundaries}\n\n"
                "Analyze only. Do not make decisions. Pass findings to Decision Maker."
            ),
            llm=self._llm,
            verbose=False,
        )
        decision_maker = Agent(
            role=self.crew_cfg.decision_maker_role,
            goal=self.crew_cfg.decision_maker_goal,
            backstory=(
                f"You make refund proposals.\n"
                f"Mission: {mission}\n\n"
                f"Authority boundaries:\n{boundaries}\n\n"
                "RULES:\n"
                "- Always set action to 'REFUND'.\n"
                "- Copy order_id, amount_eur, category exactly from the claim (never cap or reduce amount_eur).\n"
                "- The DIM Kernel decides ACCEPT/REJECT/ESCALATE — you only propose.\n"
                "- Output ONLY valid JSON, nothing else."
            ),
            llm=self._llm,
            verbose=False,
        )
        analyze_task = Task(
            description=(
                f"Analyze this customer refund claim:\n\n{claim_str}\n\n"
                f"Check against boundaries:\n{boundaries}\n\n"
                "Summarize briefly:\n"
                "  1. Is the category allowed?\n"
                "  2. Is the purchase within the return window?\n"
                "  3. How does the amount compare to the escalation limit?\n"
                "  4. Your recommendation for the Decision Maker."
            ),
            expected_output=(
                "Concise eligibility assessment: category OK/NOK, "
                "return window OK/NOK, amount vs limit, recommendation."
            ),
            agent=analyst,
        )
        decide_task = Task(
            description=(
                "Based on the analyst's assessment, produce a refund proposal.\n\n"
                "Output a JSON object with these exact fields:\n"
                "  action     : always the string 'REFUND'\n"
                "  order_id   : from the claim\n"
                "  amount_eur : exact numeric value from the claim (do not cap at 500)\n"
                "  category   : from the claim\n"
                "  reason     : one sentence justification\n\n"
                f"Claim data:\n{claim_str}\n\n"
                "Return ONLY the JSON object. No explanation, no markdown, just JSON."
            ),
            expected_output=(
                '{"action":"REFUND","order_id":"...","amount_eur":0.0,"category":"...","reason":"..."}'
            ),
            output_json=RefundProposalOutput,
            agent=decision_maker,
        )
        crew = Crew(
            agents=[analyst, decision_maker],
            tasks=[analyze_task, decide_task],
            process=Process.sequential,
            verbose=False,
        )
        log_with_dfid(
            logger,
            dfid,
            logging.INFO,
            "[%s] CrewAI Explain→Policy starting for order %s",
            self.claims_contract.agent_id,
            claim.get("order_id"),
        )
        result = crew.kickoff()
        explain_narrative = ""
        if hasattr(result, "tasks_output") and result.tasks_output:
            try:
                explain_narrative = str(result.tasks_output[0]).strip()
            except (IndexError, TypeError):
                explain_narrative = ""
        if not explain_narrative:
            explain_narrative = "(analyst output not captured separately; see policy justification)"

        data: Optional[Dict[str, Any]] = getattr(result, "json_dict", None)
        if not data:
            raw_text: str = getattr(result, "raw", "") or ""
            data = _extract_proposal_from_text(raw_text)
        if not data:
            return None, explain_narrative, "Crew output contains no parseable refund proposal"
        return data, explain_narrative, None


def _self_check_policy(
    policy_kind: str,
    confidence: float,
    claims_contract: ClaimsContract,
) -> Tuple[bool, str]:
    if policy_kind not in claims_contract.allowed_policy_types:
        return False, f"policy_kind {policy_kind!r} not in allowed_policy_types"
    if confidence < claims_contract.escalate_on_uncertainty:
        return (
            False,
            f"confidence {confidence} below escalate_on_uncertainty {claims_contract.escalate_on_uncertainty}",
        )
    return True, ""


def run_claims_roa_cycle(
    *,
    dfid: str,
    claim: Dict[str, Any],
    claims_contract: ClaimsContract,
    crew_cfg: CrewConfig,
    use_crew_llm: bool,
    llm_model: str,
    llm_base_url: str,
    temperature: float,
    logger: logging.Logger,
) -> Tuple[Optional[PolicyProposal], Optional[str], Dict[str, Any]]:
    """
    ROA lifecycle: Explain → Policy → Self-Check → Proposal.

    Returns ``(proposal | None, error | None, meta)`` where ``meta`` may include
    ``explain_narrative`` for telemetry.
    """
    meta: Dict[str, Any] = {"explain_narrative": ""}
    data: Optional[Dict[str, Any]] = None
    err: Optional[str] = None

    if use_crew_llm:
        try:
            crew_llm = _make_crew_llm(llm_model, llm_base_url, temperature)
            wrapper = CrewAIROAWrapper(claims_contract, crew_cfg, crew_llm)
            data, explain, err = wrapper.run_llm_stages(dfid, claim, logger)
            meta["explain_narrative"] = explain
        except Exception as exc:
            return None, str(exc), meta
    else:
        data = _mock_policy_dict_from_claim(claim)
        meta["explain_narrative"] = (
            f"Mock Explain: deterministic summary for order {claim.get('order_id')} "
            f"(no CrewAI LLM calls)."
        )

    if err or not data:
        return None, err or "empty policy", meta

    policy_kind = str(data.get("action", "UNKNOWN")).upper()
    justification = str(data.get("reason", ""))
    confidence = 0.9 if use_crew_llm else 0.85

    ok, why = _self_check_policy(policy_kind, confidence, claims_contract)
    if not ok:
        return None, f"Self-check failed: {why}", meta

    proposal = PolicyProposal(
        dfid=dfid,
        agent_id=claims_contract.agent_id,
        policy_kind=policy_kind,
        params={
            "order_id": data.get("order_id"),
            "amount_eur": data.get("amount_eur") or data.get("amount_pln"),
            "category": data.get("category"),
            "reason": justification,
        },
        confidence=confidence,
        justification=justification,
    )
    log_with_dfid(
        logger,
        dfid,
        logging.INFO,
        "[%s] Proposal after Self-Check: %s %s",
        claims_contract.agent_id,
        proposal.policy_kind,
        proposal.params.get("order_id"),
    )
    return proposal, None, meta


def resolve_scenario_claim(
    scenario_claim: Optional[Dict[str, Any]],
    scenario_text: Optional[str],
    *,
    use_crew_llm: bool,
    llm_model: str,
    llm_base_url: str,
    temperature: float,
    logger: logging.Logger,
    dfid: str,
) -> Dict[str, Any]:
    if scenario_text:
        if use_crew_llm:
            llm = _make_crew_llm(llm_model, llm_base_url, temperature)
            return extract_claim_from_text(scenario_text, llm)
        return mock_extract_claim_from_text(scenario_text)
    return dict(scenario_claim or {})

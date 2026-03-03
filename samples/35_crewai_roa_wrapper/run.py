#!/usr/bin/env python3
"""
35_crewai_roa_wrapper - Real CrewAI Crew + local Ollama + DIR Kernel.

Demonstrates:
- Natural language intake: claim_text → LLM extracts structured claim (realistic use case)
- Real CrewAI Crew (Claims Analyst + Decision Maker) powered by local Ollama
- "The Wall" pattern: User Space (LLM reasoning) vs Kernel Space (deterministic DIM)
- Submit_Policy_Proposal as structured JSON output (output_json, no tool-calling)
- All configuration (LLM, agent contract, context store, scenarios) in config.yaml

Why structured output instead of tool-calling?
  Gemma3 (and many local models) do not support OpenAI-style function calling.
  The Decision Maker's task uses output_json=RefundProposalOutput, which instructs
  CrewAI to extract validated JSON from the LLM response without function calls.
  The boundary ("The Wall") still holds: LLM writes a Claim, DIM validates it
  deterministically before any Fact (execution) occurs.

Requirements:
    pip install -e ".[crewai]"
    ollama serve
    ollama pull gemma3:4b       # or whatever model is set in config.yaml

Run from repo root:
    python samples/35_crewai_roa_wrapper/run.py

Config:
    samples/35_crewai_roa_wrapper/config.yaml   (LLM, agent, context, scenarios)

Env var overrides (same as 31_finance_trading):
    OLLAMA_MODEL      overrides llm_defaults.model
    OLLAMA_BASE_URL   overrides llm_defaults.base_url

ROA Manifesto §4-5, §10 (Boxed Intelligence), DIR Architectural Pattern §6.
"""
from __future__ import annotations

import json
import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from crewai import Agent, Crew, LLM, Process, Task

from dir import PolicyProposal, new_dfid
from utils.logging_utils import log_with_dfid
from utils.ollama_client import check_ollama

from contracts import ClaimsContract
from config_loader import AppConfig, LlmConfig, ScenarioConfig, load_config
from dim_validators import validate_claims_proposal

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Ollama health check
# ---------------------------------------------------------------------------


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
        sys.exit(1)


# ---------------------------------------------------------------------------
# LLM factory
# ---------------------------------------------------------------------------


def _make_llm(llm_cfg: LlmConfig) -> LLM:
    """
    Create a CrewAI LLM pointing to local Ollama via OpenAI-compatible API.

    provider="openai" forces the native OpenAI SDK with a custom base_url,
    bypassing the LiteLLM fallback (which may not be installed).
    Ollama exposes an OpenAI-compatible API at /v1 — no cloud key needed.
    """
    return LLM(
        model=llm_cfg.effective_model(),
        provider="openai",
        base_url=llm_cfg.effective_base_url().rstrip("/") + "/v1",
        api_key="ollama",
        temperature=llm_cfg.temperature,
    )


# ---------------------------------------------------------------------------
# Structured output schema (Submit_Policy_Proposal equivalent)
# ---------------------------------------------------------------------------


class RefundProposalOutput(BaseModel):
    """
    Structured output for the Decision Maker's task.

    Represents the "Submit_Policy_Proposal" in JSON form.
    CrewAI's output_json extracts and validates this from the LLM response
    without requiring function-calling support from the model.
    """

    action: str = Field(
        description="Always 'REFUND'. The DIR Kernel decides ACCEPT/REJECT/ESCALATE."
    )
    order_id: str = Field(description="Order ID from the claim.")
    amount_eur: float = Field(description="Refund amount in EUR.")
    category: str = Field(description="Product category from the claim.")
    reason: str = Field(description="Brief justification for the refund proposal.")


class ClaimExtractionOutput(BaseModel):
    """
    Structured output for natural language claim intake.

    LLM extracts these fields from free-form customer text.
    Used when scenario has claim_text instead of claim (dict).
    """

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


# ---------------------------------------------------------------------------
# Natural language claim intake
# ---------------------------------------------------------------------------


def extract_claim_from_text(claim_text: str, llm: LLM) -> Dict[str, Any]:
    """
    Extract structured claim from natural language using a single LLM call.

    Realistic use case: customer writes "I bought ord_001 for 299 EUR, defective product"
    instead of filling a JSON form. LLM extracts order_id, amount, category, reason.
    """
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
    crew = Crew(agents=[extractor], tasks=[task], verbose=False)
    result = crew.kickoff()
    data: Optional[Dict[str, Any]] = getattr(result, "json_dict", None)
    if not data:
        raw = getattr(result, "raw", "") or ""
        for attempt in [raw.strip(), *re.findall(r"\{[^{}]{10,}\}", raw, re.DOTALL)]:
            try:
                parsed = json.loads(attempt)
                if "order_id" in parsed and ("amount_eur" in parsed or "amount_pln" in parsed):
                    data = parsed
                    break
            except (json.JSONDecodeError, TypeError):
                continue
        if not data:
            raise RuntimeError(f"Could not extract claim from: {claim_text[:200]}")
    # Normalize to claim dict (add purchase_date if present)
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


# ---------------------------------------------------------------------------
# Fallback JSON parser (small models may skip structured output)
# ---------------------------------------------------------------------------


def _extract_proposal_from_text(text: str) -> Optional[Dict[str, Any]]:
    """Try to parse a RefundProposalOutput dict from raw LLM text."""
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


# ---------------------------------------------------------------------------
# CrewAI ROA Wrapper
# ---------------------------------------------------------------------------


class CrewAIROAWrapper:
    """
    Wraps a real CrewAI Crew in an ROA interface.

    USER SPACE (probabilistic, Ollama LLM):
      Claims Analyst   → text eligibility analysis (no tools)
      Decision Maker   → structured JSON output via output_json Task

    THE WALL (Claim → PolicyProposal)

    KERNEL SPACE (deterministic):
      DIM validate_claims_proposal() → ACCEPT | REJECT | ESCALATE

    Configuration comes entirely from config.yaml via AppConfig.
    """

    def __init__(self, cfg: AppConfig) -> None:
        self.contract: ClaimsContract = cfg.contract
        self.crew_cfg = cfg.crew
        self._llm: LLM = _make_llm(cfg.llm)

    def _boundaries_text(self) -> str:
        c = self.contract
        return (
            f"- Allowed refund categories: {c.allowed_refund_categories}\n"
            f"- Return window: {c.return_window_days} days from purchase\n"
            f"- Max refund without escalation: {c.max_refund_without_escalation} EUR\n"
            f"- Allowed actions: {c.allowed_policy_types}"
        )

    def run(self, dfid: str, claim: Dict[str, Any]) -> PolicyProposal:
        """
        Run the Crew on one claim. Returns PolicyProposal (Claim, not Fact).

        Flow:
          Analyst       → text eligibility summary
          Decision Maker → RefundProposalOutput JSON (output_json)
          wrapper        → PolicyProposal → DIM
        """
        claim_str = json.dumps(claim, indent=2)
        boundaries = self._boundaries_text()
        mission = self.contract.mission

        # ---- Agent 1: Claims Analyst (text reasoning) ---------------------
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

        # ---- Agent 2: Decision Maker (structured JSON output) -------------
        decision_maker = Agent(
            role=self.crew_cfg.decision_maker_role,
            goal=self.crew_cfg.decision_maker_goal,
            backstory=(
                f"You make refund proposals.\n"
                f"Mission: {mission}\n\n"
                f"Authority boundaries:\n{boundaries}\n\n"
                "RULES:\n"
                "- Always set action to 'REFUND'.\n"
                "- Copy order_id, amount_eur, category exactly from the claim.\n"
                "- The DIM Kernel decides ACCEPT/REJECT/ESCALATE — you only propose.\n"
                "- Output ONLY valid JSON, nothing else."
            ),
            llm=self._llm,
            verbose=False,
        )

        # ---- Task 1: Analyze ----------------------------------------------
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

        # ---- Task 2: Produce structured proposal (The Wall crossing) ------
        decide_task = Task(
            description=(
                "Based on the analyst's assessment, produce a refund proposal.\n\n"
                "Output a JSON object with these exact fields:\n"
                "  action     : always the string 'REFUND'\n"
                "  order_id   : from the claim\n"
                "  amount_eur : from the claim (numeric)\n"
                "  category   : from the claim\n"
                "  reason     : one sentence justification\n\n"
                f"Claim data:\n{claim_str}\n\n"
                "Return ONLY the JSON object. No explanation, no markdown, just JSON."
            ),
            expected_output=(
                'A JSON object: {"action":"REFUND","order_id":"...",'
                '"amount_eur":0.0,"category":"...","reason":"..."}'
            ),
            output_json=RefundProposalOutput,
            agent=decision_maker,
        )

        crew = Crew(
            agents=[analyst, decision_maker],
            tasks=[analyze_task, decide_task],
            process=Process.sequential,
            verbose=True,
        )

        log_with_dfid(
            logger, dfid, logging.INFO,
            "[%s] Crew starting for order %s",
            self.contract.agent_id, claim.get("order_id"),
        )

        result = crew.kickoff()

        # --- Extract proposal (The Wall: Claim → PolicyProposal) -----------
        # getattr used for type-checker compatibility with CrewOutput|CrewStreamingOutput
        data: Optional[Dict[str, Any]] = getattr(result, "json_dict", None)

        if not data:
            raw_text: str = getattr(result, "raw", "") or ""
            data = _extract_proposal_from_text(raw_text)
            if data:
                print("  [note] Parsed JSON from raw output (output_json skipped).")
            else:
                raise RuntimeError(
                    "Crew output contains no parseable refund proposal.\n"
                    f"Raw: {raw_text[:400]}"
                )

        proposal = PolicyProposal(
            dfid=dfid,
            agent_id=self.contract.agent_id,
            policy_kind=str(data.get("action", "UNKNOWN")).upper(),
            params={
                "order_id": data.get("order_id"),
                "amount_eur": data.get("amount_eur") or data.get("amount_pln"),
                "category": data.get("category"),
                "reason": data.get("reason", ""),
            },
            confidence=0.9,
            justification=str(data.get("reason", "")),
        )

        log_with_dfid(
            logger, dfid, logging.INFO,
            "[%s] Proposal: %s %s",
            self.contract.agent_id, proposal.policy_kind, proposal.params.get("order_id"),
        )
        return proposal


# ---------------------------------------------------------------------------
# Scenario runner
# ---------------------------------------------------------------------------


def run_scenario(
    scenario: ScenarioConfig,
    wrapper: CrewAIROAWrapper,
    context_store: Dict[str, Any],
    contract: ClaimsContract,
    llm: Optional[LLM] = None,
) -> Tuple[PolicyProposal, str, str]:
    """Run one scenario: Crew → proposal → DIM → verdict."""
    if scenario.claim_text and llm:
        claim = extract_claim_from_text(scenario.claim_text, llm)
        print(f"\n{'=' * 70}")
        print(f"[{scenario.label}]")
        print(f"  Input (NL): {scenario.claim_text[:80]}{'...' if len(scenario.claim_text) > 80 else ''}")
        print(
            f"  Extracted: order={claim.get('order_id')}  "
            f"amount={claim.get('amount_eur') or claim.get('amount_pln')} EUR  "
            f"cat={claim.get('category')}"
        )
        print("=" * 70)
    else:
        claim = scenario.claim or {}
        print(f"\n{'=' * 70}")
        print(f"[{scenario.label}]")
        print(
        f"  Claim: order={claim.get('order_id')}  "
        f"amount={claim.get('amount_eur') or claim.get('amount_pln')} EUR  "
        f"cat={claim.get('category')}"
        )
        print("=" * 70)

    dfid = new_dfid()
    proposal = wrapper.run(dfid, claim)

    verdict, reason = validate_claims_proposal(
        proposal, context_store, contract, allowed_agents=[contract.agent_id]
    )

    print(f"\n  --> Proposal : {proposal.policy_kind} "
          f"{proposal.params.get('order_id')} "
          f"{proposal.params.get('amount_eur') or proposal.params.get('amount_pln')} EUR")
    print(f"  --> DIM      : {verdict}")
    print(f"  --> Reason   : {reason}")

    return proposal, verdict, reason


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    # Load config from YAML (agent contract, LLM, context store, scenarios)
    cfg = load_config()

    _check_ollama(cfg.llm)

    print("=" * 70)
    print("35_crewai_roa_wrapper  -  CrewAI + Ollama + DIR Kernel")
    print("=" * 70)
    print(f"  Config : config.yaml")
    print(f"  LLM    : {cfg.llm.effective_model()} @ {cfg.llm.effective_base_url()}")
    print(f"  Agent  : {cfg.contract.agent_id}")
    print(f"  Crew   : Claims Analyst → Decision Maker (sequential, output_json)")
    print(f"  DIM    : 5-layer validation (RBAC, order, window, category, amount)")
    print(f"  Scenarios: {len(cfg.scenarios)}")

    wrapper = CrewAIROAWrapper(cfg)
    llm = _make_llm(cfg.llm)

    results: List[Tuple[str, str, str]] = []
    for scenario in cfg.scenarios:
        try:
            _, verdict, _ = run_scenario(
                scenario, wrapper, cfg.context_store, cfg.contract, llm=llm
            )
            ok = "✓" if verdict == scenario.expected else "✗ UNEXPECTED"
            results.append((scenario.label, verdict, ok))
        except Exception as exc:
            print(f"\n  [ERROR] {exc}")
            results.append((scenario.label, "ERROR", "✗"))

    print("\n" + "=" * 70)
    print("[SUMMARY]")
    print("=" * 70)
    for label, verdict, ok in results:
        print(f"  {ok}  {verdict:10s}  {label}")

    print()
    print("  KEY INSIGHT:")
    print("  - NL intake: claim_text → LLM extracts order_id, amount, category (realistic).")
    print("  - Gemma3 (CrewAI) reasons about claims in User Space (probabilistic).")
    print("  - DIM validates proposals in Kernel Space (deterministic).")
    print("  - output_json replaces tool-calling for models without function support.")
    print("  - All configuration lives in config.yaml — no hardcoded values in code.")


if __name__ == "__main__":
    main()

"""
ROA Underwriter Agent with full Explain → Policy → Self-Check lifecycle (ROA Manifesto §4).

Uses LLM for Explain and Policy; deterministic Self-Check; produces Proof-Carrying Intent (PCI)
with evidence_hash for Topology C (DL+PCI) verification.
"""

from __future__ import annotations

import re
import hmac
import hashlib
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Union

from dir import new_dfid
from dir.models import ProofCarryingIntent
from dir.pci import compute_evidence_hash, hash_content, proposal_params_for_hash

from kernel import AgentRegistry
from models import ClientApplication, PolicyProposal


@dataclass
class DecisionCycleReport:
    """Report data from one agent decision cycle (for HTML audit)."""
    dfid: str
    context: ClientApplication
    explain_result: Dict[str, Any]
    policy_proposal: PolicyProposal
    self_check_passed: bool
    self_check_reason: Optional[str]
    evidence_hash: str
    forge_evidence_hash: bool

try:
    from .llm_client import LLMClient
except ImportError:
    from llm_client import LLMClient

logger = logging.getLogger(__name__)

AGENT_SECRET = b"underwriter_roa_secret"


def _sign(data: str) -> str:
    """HMAC-SHA256 signature."""
    return hmac.new(AGENT_SECRET, data.encode(), hashlib.sha256).hexdigest()


# -----------------------------------------------------------------------------
# LLM response parsing
# -----------------------------------------------------------------------------


def _parse_explain(text: str, dfid: str, agent_id: str) -> Dict[str, Any]:
    """Parse LLM Explain output. Returns dict with narrative, signals, risks, opportunities."""
    narrative = text[:500] if len(text) > 500 else text
    signals: List[str] = []
    risks: List[str] = []
    opportunities: List[str] = []
    for block, key in [
        (r"SIGNALS?:\s*(.+?)(?=RISKS?:|OPPORTUNITIES?:|$)", "signals"),
        (r"RISKS?:\s*(.+?)(?=SIGNALS?:|OPPORTUNITIES?:|$)", "risks"),
        (r"OPPORTUNITIES?:\s*(.+?)(?=SIGNALS?:|RISKS?:|$)", "opportunities"),
    ]:
        m = re.search(block, text, re.DOTALL | re.IGNORECASE)
        if m:
            part = m.group(1).strip()
            items = [s.strip() for s in re.split(r"[,;]", part) if s.strip()]
            if key == "signals":
                signals = items
            elif key == "risks":
                risks = items
            else:
                opportunities = items
    if "Narrative:" in text:
        n = re.search(
            r"Narrative:\s*(.+?)(?=SIGNALS?:|RISKS?:|OPPORTUNITIES?:|$)",
            text, re.DOTALL | re.IGNORECASE,
        )
        if n:
            narrative = n.group(1).strip()
    return {
        "narrative": narrative or "Context reviewed.",
        "signals": signals or ["context_observed"],
        "risks": risks,
        "opportunities": opportunities,
    }


def _parse_policy(
    text: str, context: ClientApplication, max_limit: float
) -> PolicyProposal:
    """Parse LLM Policy output into PolicyProposal."""
    coverage = min(context.revenue * 2, max_limit)
    premium = coverage * 0.02
    industry = context.industry

    m = re.search(r"COVERAGE_LIMIT[:\s]+([\d.]+)", text, re.IGNORECASE)
    if m:
        try:
            coverage = float(m.group(1).replace(",", ""))
        except ValueError:
            pass

    m = re.search(r"PREMIUM[:\s]+([\d.]+)", text, re.IGNORECASE)
    if m:
        try:
            premium = float(m.group(1).replace(",", ""))
        except ValueError:
            pass

    m = re.search(r"INDUSTRY[:\s]+(\S+)", text, re.IGNORECASE)
    if m:
        industry = m.group(1).strip()

    return PolicyProposal(
        coverage_limit=coverage,
        premium=premium,
        industry=industry,
    )


# -----------------------------------------------------------------------------
# ROA Underwriter Agent
# -----------------------------------------------------------------------------


class ROAUnderwriterAgent:
    """
    Full ROA agent: Explain(LLM) → Policy(LLM) → Self-Check → PCI.

    Contract and mission from config. Produces Proof-Carrying Intent with
    evidence_hash for DIM verification (Topology C).
    """

    def __init__(self, registry: AgentRegistry, llm: LLMClient):
        self.registry = registry
        self.llm = llm
        self.agent_id = registry.contract.agent_id

    def explain(self, dfid: str, context: ClientApplication) -> Dict[str, Any]:
        """§4.1: LLM interprets client application."""
        system = (
            f"Mission: {self.registry.contract.mission}\n"
            "Output format: Narrative: <summary>. SIGNALS: <comma-separated>. "
            "RISKS: <comma-separated>. OPPORTUNITIES: <comma-separated>."
        )
        user = (
            f"Client application:\n"
            f"  business_type: {context.business_type}\n"
            f"  revenue: {context.revenue}\n"
            f"  industry: {context.industry}\n"
            "Analyze and output Narrative, SIGNALS, RISKS, OPPORTUNITIES."
        )
        logger.info("[DFID=%s] [%s] Calling LLM for Explain", dfid[:8], self.agent_id)
        response = self.llm.generate(user, system=system)
        return _parse_explain(response, dfid, self.agent_id)

    def formulate_policy(
        self, dfid: str, explain_result: Dict[str, Any], context: ClientApplication
    ) -> PolicyProposal:
        """§4.2: LLM proposes coverage, premium, industry."""
        system = (
            f"Mission: {self.registry.contract.mission}\n"
            f"Max coverage limit: {self.registry.max_limit}. "
            f"Prohibited industries: {self.registry.prohibited_industries}.\n"
            "Output format (one per line):\n"
            "COVERAGE_LIMIT: <number>\nPREMIUM: <number>\nINDUSTRY: <from context>\n"
            "JUSTIFICATION: <short reason>\nCONFIDENCE: <0.0-1.0>"
        )
        user = (
            f"Interpretation: {explain_result['narrative']}\n"
            f"Signals: {explain_result['signals']}\n"
            f"Risks: {explain_result['risks']}\n"
            f"Client: business_type={context.business_type}, revenue={context.revenue}, industry={context.industry}\n"
            "Propose COVERAGE_LIMIT, PREMIUM, INDUSTRY (must match client industry)."
        )
        logger.info("[DFID=%s] [%s] Calling LLM for Policy", dfid[:8], self.agent_id)
        response = self.llm.generate(user, system=system)
        return _parse_policy(response, context, self.registry.max_limit)

    def self_check(self, proposal: PolicyProposal) -> tuple[bool, Optional[str]]:
        """§4.3: Deterministic boundary check."""
        if proposal.industry in self.registry.prohibited_industries:
            return False, f"Industry {proposal.industry} is prohibited"
        if proposal.coverage_limit > self.registry.max_limit:
            return False, f"Coverage {proposal.coverage_limit} exceeds max {self.registry.max_limit}"
        return True, None

    def run_decision_cycle(
        self,
        context: ClientApplication,
        *,
        forge_evidence_hash: bool = False,
    ) -> Tuple[ProofCarryingIntent, DecisionCycleReport]:
        """
        Explain → Policy → Self-Check → PCI.

        Returns (PCI, report). Self-check failure: still emits PCI (agent may
        hallucinate); DIM will reject on business rules.
        """
        dfid = new_dfid()

        logger.info("[DFID=%s] [%s] Starting decision cycle", dfid[:8], self.agent_id)

        explain_result = self.explain(dfid, context)
        proposal = self.formulate_policy(dfid, explain_result, context)

        passed, reason = self.self_check(proposal)
        if not passed:
            logger.warning(
                "[DFID=%s] [%s] Self-check FAILED: %s (DIM will reject)",
                dfid[:8], self.agent_id, reason,
            )

        context_hash = hash_content(context.model_dump())
        contract_hash = self.registry.get_contract_hash()
        proposal_params = proposal_params_for_hash(proposal.model_dump())

        if forge_evidence_hash:
            evidence_hash = "0" * 64
            logger.info("[DFID=%s] Agent forging evidence_hash (simulated attack)", dfid[:8])
        else:
            evidence_hash = compute_evidence_hash(
                dfid, context_hash, contract_hash, proposal_params
            )

        payload_str = f"{dfid}{proposal.model_dump_json()}{evidence_hash}"
        signature = _sign(payload_str)

        pci = ProofCarryingIntent(
            dfid=dfid,
            intent_payload=proposal.model_dump(),
            context_ref=context_hash,
            evidence_hash=evidence_hash,
            signature=signature,
        )

        report = DecisionCycleReport(
            dfid=dfid,
            context=context,
            explain_result=explain_result,
            policy_proposal=proposal,
            self_check_passed=passed,
            self_check_reason=reason,
            evidence_hash=evidence_hash,
            forge_evidence_hash=forge_evidence_hash,
        )

        logger.info(
            "[DFID=%s] [%s] PCI emitted: coverage=%.0f, premium=%.0f, industry=%s",
            dfid[:8], self.agent_id,
            proposal.coverage_limit, proposal.premium, proposal.industry,
        )
        return pci, report

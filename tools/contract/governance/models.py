"""Typed models for governance-aware contract authoring."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator

ConstraintClassLiteral = Literal[
    "architectural_boundary",
    "transaction_invariant",
    "evidence_obligation",
    "aggregate_policy",
    "process_rule",
]
NormativeLevelLiteral = Literal["mandatory", "recommended", "informational"]
ReversibilityLiteral = Literal["irreversible", "reversible", "unknown"]
EnforcementTargetLiteral = Literal["DIM", "EVIDENCE", "MONITOR", "CI_CD", "advisory"]
PredicateOpLiteral = Literal[
    "eq", "neq", "lt", "le", "gt", "ge", "in", "not_in", "and", "or", "not"
]
VariableTypeLiteral = Literal["number", "string", "boolean", "enum"]
SeverityLiteral = Literal["blocking", "warning", "info"]

ALLOWED_CONTRACT_PATCH_ROOTS = frozenset(
    {
        "api_version",
        "kind",
        "metadata",
        "subject",
        "mission",
        "authority",
        "execution_conditions",
        "responsibility",
        "governance",
    }
)


class GovernanceClause(BaseModel):
    """Normative clause curated from ROA/DIR source documents."""

    clause_id: str
    source_document: Literal["ROA_MANIFESTO", "DIR_GOVERNANCE"]
    source_anchor: str
    statement: str
    quote: str
    quote_hash: str = ""
    constraint_class: ConstraintClassLiteral
    normative_level: NormativeLevelLiteral = "mandatory"
    presets: List[str] = Field(default_factory=list)
    roles: List[str] = Field(default_factory=list)
    fundamental: bool = False

    model_config = {"extra": "forbid"}


class GovernanceContextPack(BaseModel):
    """Versioned bundle of governance clauses for Contract Studio."""

    pack_id: str
    version: str
    description: str = ""
    clauses: List[GovernanceClause]

    model_config = {"extra": "forbid"}

    @field_validator("clauses")
    @classmethod
    def unique_clause_ids(cls, clauses: List[GovernanceClause]) -> List[GovernanceClause]:
        ids = [c.clause_id for c in clauses]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate clause_id in governance pack")
        return clauses


class VariableSpec(BaseModel):
    name: str
    var_type: VariableTypeLiteral = "number"
    unit: Optional[str] = None
    domain: Optional[List[str]] = None

    model_config = {"extra": "forbid"}


class PredicateAST(BaseModel):
    """Typed predicate tree for invariant candidates (no free-form eval)."""

    op: PredicateOpLiteral
    left: Optional[Union["PredicateAST", VariableSpec, float, str, bool]] = None
    right: Optional[Union["PredicateAST", VariableSpec, float, str, bool, List[Any]]] = None
    value: Optional[Union[float, str, bool]] = None
    variable: Optional[str] = None

    model_config = {"extra": "forbid"}


PredicateAST.model_rebuild()


class SourceBinding(BaseModel):
    clause_id: str
    rationale: str = ""

    model_config = {"extra": "forbid"}


class ActionClass(BaseModel):
    action_type: str
    reversibility: ReversibilityLiteral = "unknown"
    rationale: str = ""
    source_bindings: List[SourceBinding] = Field(default_factory=list)
    linked_limit_key: Optional[str] = None

    model_config = {"extra": "forbid"}


class GoalModel(BaseModel):
    objective: str
    success_criteria: List[str] = Field(default_factory=list)
    non_goals: List[str] = Field(default_factory=list)
    source_bindings: List[SourceBinding] = Field(default_factory=list)

    model_config = {"extra": "forbid"}


class InvariantCandidate(BaseModel):
    invariant_id: str
    constraint_class: ConstraintClassLiteral
    applies_to_actions: List[str] = Field(default_factory=list)
    business_rationale: str = ""
    predicate: Optional[PredicateAST] = None
    enforcement_target: EnforcementTargetLiteral = "DIM"
    source_bindings: List[SourceBinding] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)
    ambiguities: List[str] = Field(default_factory=list)
    linked_limit_key: Optional[str] = None

    model_config = {"extra": "forbid"}


class GovernanceAnalysis(BaseModel):
    """Untrusted LLM synthesis of goal, actions, and invariant candidates."""

    goal: Optional[GoalModel] = None
    action_classes: List[ActionClass] = Field(default_factory=list)
    invariant_candidates: List[InvariantCandidate] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)
    ambiguities: List[str] = Field(default_factory=list)
    open_questions: List[str] = Field(default_factory=list)

    model_config = {"extra": "forbid"}


class ValidationIssue(BaseModel):
    code: str
    message: str
    severity: SeverityLiteral = "blocking"
    field: Optional[str] = None

    model_config = {"extra": "forbid"}


class GovernanceValidationReport(BaseModel):
    blocking_errors: List[ValidationIssue] = Field(default_factory=list)
    warnings: List[ValidationIssue] = Field(default_factory=list)
    formal_checks: Dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "forbid"}

    @property
    def blocking_ok(self) -> bool:
        return not self.blocking_errors

    @property
    def has_warnings(self) -> bool:
        return bool(self.warnings)


class LLMContractResponse(BaseModel):
    """Structured JSON expected from the governance-aware LLM."""

    assistant_reply: str
    contract_patch: Dict[str, Any] = Field(default_factory=dict)
    change_summary: str = ""
    governance_analysis: Optional[GovernanceAnalysis] = None

    model_config = {"extra": "forbid"}

    @field_validator("contract_patch")
    @classmethod
    def validate_patch_roots(cls, patch: Dict[str, Any]) -> Dict[str, Any]:
        invalid = set(patch.keys()) - ALLOWED_CONTRACT_PATCH_ROOTS
        if invalid:
            raise ValueError(f"contract_patch has disallowed root keys: {sorted(invalid)}")
        return patch


class ChatTurnResult(BaseModel):
    """Result of one governance-aware chat turn."""

    assistant_reply: str
    merged_contract: Dict[str, Any]
    contract_yaml: str
    validation_ok: bool
    blocking_errors: List[str]
    warnings: List[str]
    change_summary: str
    governance_analysis: Optional[GovernanceAnalysis] = None
    validation_report: Optional[GovernanceValidationReport] = None
    llm_response: Optional[LLMContractResponse] = None

    model_config = {"extra": "forbid"}

"""Shared data types: validation verdicts, DIM reasons, models, registry, event bus."""

from enum import StrEnum
from typing import Tuple, TypeAlias


class ValidationVerdict(StrEnum):
    """Outcome of deterministic validation (DIM, JIT, domain gates)."""

    ACCEPT = "ACCEPT"
    REJECT = "REJECT"


ValidationResult: TypeAlias = Tuple[ValidationVerdict, str]


class DimReasonCode(StrEnum):
    """Stable machine-readable DIM rejection reasons (subset; others remain free text)."""

    REASONING_EXHAUSTION = "REASONING_EXHAUSTION"
    TTL_EXPIRED = "TTL_EXPIRED"


class ContractRole(StrEnum):
    """ROA responsibility role (Manifesto §3.1)."""

    STRATEGIST = "STRATEGIST"
    EXECUTOR = "EXECUTOR"
    MONITOR = "MONITOR"


class DecisionRecordOutcome(StrEnum):
    """Outcome of a single decision in agent trajectory."""

    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    ESCALATED = "ESCALATED"
    PENDING = "PENDING"


class EscalationSeverity(StrEnum):
    """Severity on EscalationRequest (Manifesto §5.3)."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class FlowTimelineEventType(StrEnum):
    """Event type on DecisionFlow.timeline (DIR §5.4)."""

    FLOW_STARTED = "FLOW_STARTED"
    CONTEXT_SNAPSHOT = "CONTEXT_SNAPSHOT"
    EXPLAIN = "EXPLAIN"
    POLICY = "POLICY"
    SELF_CHECK = "SELF_CHECK"
    PROPOSAL = "PROPOSAL"
    VALIDATION = "VALIDATION"
    EXECUTION = "EXECUTION"
    ESCALATION = "ESCALATION"
    CHILD_FLOW_CREATED = "CHILD_FLOW_CREATED"
    FLOW_COMPLETED = "FLOW_COMPLETED"
    FLOW_ABORTED = "FLOW_ABORTED"


class DecisionFlowStatus(StrEnum):
    """High-level status on DecisionFlow aggregate (distinct from lifecycle.FlowStatus)."""

    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    ESCALATED = "ESCALATED"
    ABORTED = "ABORTED"


class HumanDecision(StrEnum):
    """Human resolution of an escalation (DIR §9)."""

    OVERRIDE = "OVERRIDE"
    MODIFY = "MODIFY"
    ABORT = "ABORT"


class AgentRegistryStatus(StrEnum):
    """Agent row status in registry storage."""

    ACTIVE = "ACTIVE"


class HandshakeRejectionReason(StrEnum):
    """Handshake failure codes (DIR §2.3)."""

    VERSION_MISMATCH = "VERSION_MISMATCH"


class EventBusBackend(StrEnum):
    """Pluggable event bus implementation (factory)."""

    MEMORY = "memory"
    KAFKA = "kafka"
    PUBSUB = "pubsub"


class EventType(StrEnum):
    """Canonical event types for EOAM (DIR Topologies §2.4)."""

    OBSERVATION = "OBSERVATION"
    MARKET_SIGNAL = "MARKET_SIGNAL"
    NEWS = "NEWS"
    RISK_ALERT = "RISK_ALERT"
    POLICY_PROPOSAL = "POLICY_PROPOSAL"
    ESCALATION = "ESCALATION"
    VALIDATION_RESULT = "VALIDATION_RESULT"
    VALIDATION_REJECTED = "VALIDATION_REJECTED"
    EXECUTION_INTENT = "EXECUTION_INTENT"
    EXECUTION_RESULT = "EXECUTION_RESULT"
    AGENT_ACTIVATED = "AGENT_ACTIVATED"
    FLOW_COMPLETED = "FLOW_COMPLETED"

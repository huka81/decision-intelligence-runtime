"""
Decision Intelligence Runtime (DIR) - core package for ROA/DIR.

Core components: DFID, EventBus, DIM, Context Store, models, pluggable storage.

Install::

    pip install dir-runtime

Custom storage backend example::

    from dir_core import AgentRegistry
    from dir_core.storage import AgentRegistryStorage

    class MyPostgresStorage:
        def init_schema(self) -> None: ...
        def upsert_agent(self, agent_id, contract_json, priority,
                         status, agent_version, session_token) -> None: ...
        # implement remaining AgentRegistryStorage methods

    registry = AgentRegistry(storage=MyPostgresStorage())
"""

from .agent_registry import AgentRegistry, HandshakeResult
from .arbitration import DEFAULT_PRIORITY_MATRIX, select_winner
from .dim import validate_proposal
from .data_types import (
    AgentRegistryStatus,
    ContractRole,
    DecisionFlowStatus,
    DecisionRecordOutcome,
    DimReasonCode,
    EscalationSeverity,
    EventBusBackend,
    EventType,
    FlowTimelineEventType,
    HandshakeRejectionReason,
    HumanDecision,
    ValidationReason,
    ValidationResult,
    ValidationVerdict,
)
from .context_store import ContextStore
from .runtime import DecisionRuntime
from .dfid import new_dfid, new_dfid_with_parent
from .event_bus import (
    Event,
    EventBus,
    EventMetadata,
    LoggingEventBus,
    create_event_bus,
)
from .escalation import (
    EscalationManager,
    EscalationOutcome,
    ImpactCategory,
)
from .idempotency import (
    IdempotencyGuard,
    MemoryBackend,
    SQLiteBackend,
    idempotency_key,
)
from .intent_retry import REASONING_EXHAUSTION, IntentRetryGovernor
from .lifecycle import FlowStatus, transition
from .resource_lock import LockResult, ResourceLockManager
from .jit import JITStateVerifier, verify_drift
from .ledger import DecisionLedger
from .models import (
    AgentState,
    ContextSnapshot,
    DecisionAtom,
    DecisionFlow,
    DecisionRecord,
    EscalationRequest,
    ExecutionIntent,
    ExplainResult,
    FlowEvent,
    Policy,
    PolicyProposal,
    ProofCarryingIntent,
    CompensationAction,
    ResponsibilityContract,
    SelfCheckResult,
)
from .saga import SagaCompensation
from .pci import (
    ProofChecker,
    compute_evidence_hash,
    hash_content,
    proposal_params_for_hash,
)
from .wakeup import (
    WakeupPredicate,
    is_relevant_instrument,
    price_change_significant,
    should_wake,
    volatility_elevated,
)

# Storage layer - protocols and built-in backends
from .storage import (
    # Protocols (implement these to create a custom backend)
    AgentRegistryStorage,
    AuditStore,
    ContextStorage,
    DecisionAuditStorage,
    IdempotencyStorage,
    SagaStorage,
    ResourceLockStorage,
    IntentRetryStorage,
    EscalationStorage,
    LifecycleStorage,
    # Exceptions
    StorageError,
    ResourceContentionError,
    # SQLite backends (default, no extra deps)
    SqliteAgentRegistryStorage,
    SqliteContextStorage,
    SqliteDecisionAuditStorage,
    SqliteIdempotencyStorage,
    SqliteSagaStorage,
    SqliteResourceLockStorage,
    SqliteIntentRetryStorage,
    SqliteEscalationStorage,
    SqliteLifecycleStorage,
    # Memory backends (testing / ephemeral)
    MemoryAgentRegistryStorage,
    MemoryContextStorage,
    MemoryDecisionAuditStorage,
    MemoryIdempotencyStorage,
    MemorySagaStorage,
    MemoryResourceLockStorage,
    MemoryIntentRetryStorage,
    MemoryEscalationStorage,
    MemoryLifecycleStorage,
    # Bundles & factories
    StorageBundle,
    sqlite_storage,
    memory_storage,
)

__all__ = [
    "DEFAULT_PRIORITY_MATRIX",
    # DIM (DIR ?6)
    "validate_proposal",
    "ValidationVerdict",
    "ValidationResult",
    "ValidationReason",
    "DimReasonCode",
    "ContractRole",
    "DecisionRecordOutcome",
    "EscalationSeverity",
    "FlowTimelineEventType",
    "DecisionFlowStatus",
    "HumanDecision",
    "AgentRegistryStatus",
    "HandshakeRejectionReason",
    "EventBusBackend",
    "new_dfid",
    "new_dfid_with_parent",
    "select_winner",
    # EventBus (DIR Topologies ?2)
    "Event",
    "EventBus",
    "EventMetadata",
    "EventType",
    "LoggingEventBus",
    "create_event_bus",
    # EOAM (Topologies ?2)
    "WakeupPredicate",
    "price_change_significant",
    "volatility_elevated",
    "is_relevant_instrument",
    "should_wake",
    # DL+PCI (Topology C)
    "ProofCarryingIntent",
    "DecisionLedger",
    "compute_evidence_hash",
    "hash_content",
    "proposal_params_for_hash",
    "ProofChecker",
    # Intent Retry Governor (DIR ?6.2)
    "IntentRetryGovernor",
    "REASONING_EXHAUSTION",
    # Lifecycle (DIR ?4.3)
    "FlowStatus",
    "transition",
    # Escalation Manager (DIR ?9)
    "EscalationManager",
    "EscalationOutcome",
    "ImpactCategory",
    # Resource Locking (DIR ?6.2)
    "ResourceLockManager",
    "LockResult",
    # Agent Registry (DIR ?2.3)
    "AgentRegistry",
    "HandshakeResult",
    # Context Store (DIR ?8)
    "ContextStore",
    # Facade (DX)
    "DecisionRuntime",
    # Idempotency (DIR ?7)
    "IdempotencyGuard",
    "idempotency_key",
    "SQLiteBackend",
    "MemoryBackend",
    # Saga Compensation (DIR ?7)
    "SagaCompensation",
    "CompensationAction",
    # SDS (Topology B)
    "DecisionAtom",
    "JITStateVerifier",
    "verify_drift",
    # Core models
    "ResponsibilityContract",
    "PolicyProposal",
    "ExecutionIntent",
    # ROA Lifecycle models
    "ExplainResult",
    "Policy",
    "SelfCheckResult",
    # Agent state
    "AgentState",
    "DecisionRecord",
    "EscalationRequest",
    # DecisionFlow (DIR ?5.4)
    "DecisionFlow",
    "ContextSnapshot",
    "FlowEvent",
    # Storage layer - protocols
    "AgentRegistryStorage",
    "AuditStore",
    "ContextStorage",
    "DecisionAuditStorage",
    "IdempotencyStorage",
    "SagaStorage",
    "ResourceLockStorage",
    "IntentRetryStorage",
    "EscalationStorage",
    "LifecycleStorage",
    "StorageError",
    "ResourceContentionError",
    # Storage layer - SQLite backends
    "SqliteAgentRegistryStorage",
    "SqliteContextStorage",
    "SqliteDecisionAuditStorage",
    "SqliteIdempotencyStorage",
    "SqliteSagaStorage",
    "SqliteResourceLockStorage",
    "SqliteIntentRetryStorage",
    "SqliteEscalationStorage",
    "SqliteLifecycleStorage",
    # Storage layer - memory backends
    "MemoryAgentRegistryStorage",
    "MemoryContextStorage",
    "MemoryDecisionAuditStorage",
    "MemoryIdempotencyStorage",
    "MemorySagaStorage",
    "MemoryResourceLockStorage",
    "MemoryIntentRetryStorage",
    "MemoryEscalationStorage",
    "MemoryLifecycleStorage",
    # Storage bundles & factories
    "StorageBundle",
    "sqlite_storage",
    "memory_storage",
]

__version__ = "0.1.1"

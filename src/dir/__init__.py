"""
Decision Intelligence Runtime (DIR) – core package for ROA/DIR.

Core components per docs: DFID, EventBus, DIM, Context Store, models, etc.
Samples import from this package after `pip install -e .` from repo root.

Supporting utilities (market simulation, logging) are in utils package.
Re-exported here for backward compatibility.
"""

from .arbitration import DEFAULT_PRIORITY_MATRIX, select_winner
from .dfid import new_dfid, new_dfid_with_parent
from .event_bus import (
    Event,
    EventBus,
    EventMetadata,
    EventType,
    LoggingEventBus,
    create_event_bus,
)
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
    ResponsibilityContract,
    SelfCheckResult,
)
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
from utils import (
    NewsEvent,
    NewsGenerator,
    QuoteGenerator,
    QuoteTick,
    format_dfid_prefix,
    log_with_dfid,
    score_news,
)

__all__ = [
    "DEFAULT_PRIORITY_MATRIX",
    "new_dfid",
    "new_dfid_with_parent",
    "select_winner",
    # EventBus (DIR Topologies §2)
    "Event",
    "EventBus",
    "EventMetadata",
    "EventType",
    "LoggingEventBus",
    "create_event_bus",
    # EOAM (Topologies §2)
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
    # DecisionFlow (DIR §5.4)
    "DecisionFlow",
    "ContextSnapshot",
    "FlowEvent",
    # Re-exports from utils (backward compatibility)
    "QuoteTick",
    "NewsEvent",
    "QuoteGenerator",
    "NewsGenerator",
    "score_news",
    "log_with_dfid",
    "format_dfid_prefix",
]

__version__ = "0.1.0"

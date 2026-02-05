"""
Decision Intelligence Runtime (DIR) – shared package for ROA/DIR samples.

Provides: DFID, event bus, bootstrap SQLite, models, logging helpers.
Samples import from this package after `pip install -e .` from repo root.
"""

from dir.dfid import new_dfid, new_dfid_with_parent
from dir.event_bus import (
    Event,
    EventBus,
    EventMetadata,
    EventType,
    LoggingEventBus,
    create_event_bus,
)
from dir.market_events import NewsEvent, QuoteTick
from dir.models import (
    AgentState,
    ContextSnapshot,
    DecisionFlow,
    DecisionRecord,
    EscalationRequest,
    ExecutionIntent,
    ExplainResult,
    FlowEvent,
    Policy,
    PolicyProposal,
    ResponsibilityContract,
    SelfCheckResult,
)
from dir.news_generator import NewsGenerator, score_news
from dir.quote_generator import QuoteGenerator

__all__ = [
    "new_dfid",
    "new_dfid_with_parent",
    # EventBus (DIR Topologies §2)
    "Event",
    "EventBus",
    "EventMetadata",
    "EventType",
    "LoggingEventBus",
    "create_event_bus",
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
    # Market simulation (EOAM demo)
    "QuoteTick",
    "NewsEvent",
    "QuoteGenerator",
    "NewsGenerator",
    "score_news",
]

__version__ = "0.1.0"

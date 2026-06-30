"""Independent intent signals for Semantic Governance (Evidence Validation)."""

from __future__ import annotations

import re
from typing import Literal

IntentLabel = Literal["CANCEL_SUBSCRIPTION", "RETENTION_ELIGIBLE", "AMBIGUOUS"]


def classify_customer_intent(email_body: str, cancel_patterns: list[str]) -> IntentLabel:
    text = email_body.lower()
    for pattern in cancel_patterns:
        if pattern.lower() in text:
            return "CANCEL_SUBSCRIPTION"
    if re.search(r"\b(cancel|terminate|unsubscribe)\b", text):
        return "CANCEL_SUBSCRIPTION"
    if re.search(r"\b(price|pricing|discount|expensive|cheaper)\b", text):
        return "RETENTION_ELIGIBLE"
    return "AMBIGUOUS"


def is_retention_action(policy_kind: str, retention_actions: list[str]) -> bool:
    return policy_kind in retention_actions

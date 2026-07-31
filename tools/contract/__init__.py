"""
Bootstrap Responsibility Contract wizard for ROA agents.

Run: python -m tools.contract init
"""

from .schema import AuthoritySpec, CanonicalContract, InterviewAnswers, ResponsibilitySpec

__all__ = [
    "AuthoritySpec",
    "CanonicalContract",
    "InterviewAnswers",
    "ResponsibilitySpec",
]

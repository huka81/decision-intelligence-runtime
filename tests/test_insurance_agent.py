"""ROA agent JSON policy proposal parsing for sample 33."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SAMPLE_DIR = _REPO_ROOT / "samples" / "33_insurance_underwriting"
for _path in (
    _REPO_ROOT,
    _REPO_ROOT / "src",
    _REPO_ROOT / "samples",
    _SAMPLE_DIR,
):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from agent import _parse_policy_response_json


def test_parse_policy_response_json() -> None:
    text = """
    {
      "total_insured_value": 1850000,
      "territory": "United Kingdom",
      "justification": "Within delegated authority."
    }
    """
    proposal = _parse_policy_response_json(text)
    assert proposal.total_insured_value == 1_850_000
    assert proposal.territory == "United Kingdom"
    assert proposal.justification == "Within delegated authority."

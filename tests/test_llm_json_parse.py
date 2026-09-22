"""Tests for LLM JSON parsing in contract interview."""

from __future__ import annotations

import pytest

from tools.contract.llm_interview import (
    _close_truncated_json,
    _extract_json,
    _json_response_likely_truncated,
)


def test_extract_json_from_fence() -> None:
    data = _extract_json('```json\n{"assistant_reply": "ok", "contract_patch": {}}\n```')
    assert data["assistant_reply"] == "ok"


def test_close_truncated_json_repairs_unclosed_object() -> None:
    broken = '{"assistant_reply": "hi", "governance_analysis": {"invariant_candidates": ['
    repaired = _close_truncated_json(broken)
    parsed = _extract_json(repaired)
    assert parsed["assistant_reply"] == "hi"


def test_json_response_likely_truncated() -> None:
    import json

    raw = '{"assistant_reply": "x", "contract_patch": {}'
    exc = json.JSONDecodeError("msg", raw, len(raw) - 1)
    assert _json_response_likely_truncated(raw, exc)

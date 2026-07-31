"""Interactive interview for Bootstrap Contract generation."""

from __future__ import annotations

import sys
from typing import List, Optional

import yaml

from .presets import PresetDefinition, get_preset, list_preset_names
from .schema import InterviewAnswers


def _prompt(text: str, default: Optional[str] = None) -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{text}{suffix}: ").strip()
    if not value and default is not None:
        return default
    return value


def _prompt_float(text: str, default: float) -> float:
    while True:
        raw = _prompt(text, str(default))
        try:
            return float(raw)
        except ValueError:
            print("Enter a valid number.", file=sys.stderr)


def _prompt_list(text: str, default: List[str]) -> List[str]:
    default_str = ", ".join(default) if default else ""
    raw = _prompt(text, default_str)
    if not raw:
        return list(default)
    return [item.strip() for item in raw.split(",") if item.strip()]


def _confirm(text: str, default: bool = True) -> bool:
    default_label = "Y/n" if default else "y/N"
    raw = _prompt(f"{text} ({default_label})", "Y" if default else "N").lower()
    if not raw:
        return default
    return raw in {"y", "yes", "true", "1"}


def run_interview(
    preset_name: Optional[str] = None,
    seed: Optional[InterviewAnswers] = None,
) -> InterviewAnswers:
    """Run CLI interview; optional seed pre-fills answers (from-sample)."""
    if seed is not None:
        answers = seed.model_copy()
        preset_name = answers.preset
    else:
        print("\n=== ROA Bootstrap Contract Interview ===\n")
        print("Available presets:", ", ".join(list_preset_names()))
        preset_name = preset_name or _prompt("Domain preset", "generic")
        preset = get_preset(preset_name)
        answers = InterviewAnswers(
            preset=preset.name,
            agent_id=_prompt("agent_id", "my_agent_01"),
            owner=_prompt("owner (human accountable)", "owner@example.com"),
            role=preset.default_role,  # type: ignore[arg-type]
            mission=_prompt("mission", preset.mission_template),
            allowed_policy_types=list(preset.allowed_policy_types),
            authorized_instruments=list(preset.authorized_instruments),
            irreversible_limits=dict(preset.suggested_limits),
            evidence_level=preset.evidence_level,  # type: ignore[arg-type]
            escalate_on_uncertainty=preset.escalate_on_uncertainty,
        )

    preset = get_preset(preset_name or answers.preset)
    _collect_core_fields(answers, preset)
    _collect_irreversible_limits(answers, preset)
    _collect_recommended_fields(answers, preset)
    _collect_responsibility(answers, preset)
    return answers


def _collect_core_fields(answers: InterviewAnswers, preset: PresetDefinition) -> None:
    if not sys.stdin.isatty():
        return
    answers.agent_id = _prompt("agent_id", answers.agent_id)
    answers.owner = _prompt("owner", answers.owner)
    role = _prompt("role", answers.role)
    answers.role = role  # type: ignore[assignment]
    answers.mission = _prompt("mission", answers.mission or preset.mission_template)


def _collect_irreversible_limits(answers: InterviewAnswers, preset: PresetDefinition) -> None:
    if answers.role in {"INTERFACE", "MONITOR"}:
        answers.irreversible_limits = {}
        return

    keys = preset.required_limit_keys or list(preset.suggested_limits.keys())
    if not keys and not answers.irreversible_limits:
        key = _prompt("irreversible limit key (e.g. max_order_size_usd)", "max_order_size_usd")
        value = _prompt_float(key, 1000.0)
        answers.irreversible_limits = {key: value}
        return

    if not sys.stdin.isatty():
        for key in preset.required_limit_keys:
            if key not in answers.irreversible_limits:
                answers.irreversible_limits[key] = preset.suggested_limits.get(key, 1.0)
        return

    print("\n--- Irreversible limits (Bootstrap required) ---")
    for key in keys:
        default = answers.irreversible_limits.get(
            key, preset.suggested_limits.get(key, 1.0)
        )
        answers.irreversible_limits[key] = _prompt_float(key, float(default))


def _collect_recommended_fields(answers: InterviewAnswers, preset: PresetDefinition) -> None:
    if answers.role == "INTERFACE":
        answers.allowed_policy_types = []
        return
    if not sys.stdin.isatty():
        return
    if _confirm("Edit allowed_policy_types?", default=False):
        answers.allowed_policy_types = _prompt_list(
            "allowed_policy_types (comma-separated)",
            answers.allowed_policy_types or list(preset.allowed_policy_types),
        )
    if _confirm("Edit authorized_instruments?", default=False):
        answers.authorized_instruments = _prompt_list(
            "authorized_instruments (comma-separated)",
            answers.authorized_instruments or list(preset.authorized_instruments),
        )


def _collect_responsibility(answers: InterviewAnswers, preset: PresetDefinition) -> None:
    if not sys.stdin.isatty():
        return
    if not _confirm("Adjust responsibility defaults?", default=False):
        return
    answers.escalate_on_uncertainty = _prompt_float(
        "escalate_on_uncertainty",
        answers.escalate_on_uncertainty,
    )
    answers.evidence_level = _prompt(  # type: ignore[assignment]
        "evidence_level (high|medium|low)",
        answers.evidence_level,
    )


def load_answers_file(path: str) -> InterviewAnswers:
    """Load non-interactive answers from YAML."""
    with open(path, encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return InterviewAnswers(**data)

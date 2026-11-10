"""Deterministic validation and compilation of authored responsibility contracts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

from dir_core import project_contract

from .presets import list_preset_names
from .validation import validate_contract


def _read_contract(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("contract YAML must be a mapping")
    return data


def cmd_contract(args: argparse.Namespace) -> int:
    try:
        data = _read_contract(Path(args.path))
        contract, ok, errors, warnings = validate_contract(data, preset=args.preset)
        for warning in warnings:
            print(f"Warning: {warning}", file=sys.stderr)
        if not ok or contract is None:
            for error in errors:
                print(f"Validation failed: {error}", file=sys.stderr)
            return 1

        if args.command == "validate":
            print(f"OK: {args.path}")
        else:
            projection = project_contract(contract.model_dump(mode="json", exclude_none=True))
            output = json.dumps(projection.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
            if args.out:
                Path(args.out).write_text(output, encoding="utf-8")
            else:
                sys.stdout.write(output)
    except (OSError, UnicodeError, yaml.YAMLError, ValueError, TypeError) as exc:
        print(f"{args.command} failed: {exc}", file=sys.stderr)
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tools.contract",
        description="Validate and compile responsibility contracts. Author them in tools.contract.web.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for command, help_text in (
        ("validate", "Validate a canonical contract and its runtime compatibility"),
        ("compile", "Validate and compile a contract to RuntimeContractProjection JSON"),
    ):
        cmd = sub.add_parser(command, help=help_text)
        cmd.add_argument("path", help="Path to contract YAML")
        cmd.add_argument("--preset", choices=list_preset_names(), help="Domain Bootstrap rules")
        if command == "compile":
            cmd.add_argument("--out", help="Output JSON file (default: stdout)")
        cmd.set_defaults(func=cmd_contract)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))

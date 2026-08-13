"""CLI for Bootstrap Responsibility Contract wizard."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from .bootstrap_rules import BootstrapValidationError, validate_bootstrap
from .from_sample import answers_from_sample
from .interview import load_answers_file, run_interview
from .presets import list_preset_names
from .render import EmitMode, write_emitted_files
from .schema import CanonicalContract


def _default_out_dir() -> Path:
    return Path("contracts")


def cmd_init(args: argparse.Namespace) -> int:
    answers_file = getattr(args, "answers", None)
    from_sample = getattr(args, "from_sample", None)
    non_interactive = getattr(args, "non_interactive", False)
    agent_id = getattr(args, "agent_id", None)

    if answers_file:
        answers = load_answers_file(answers_file)
    elif from_sample:
        answers = answers_from_sample(from_sample, agent_id=agent_id)
        if not answers_file and not non_interactive:
            answers = run_interview(preset_name=answers.preset, seed=answers)
    else:
        answers = run_interview(preset_name=getattr(args, "preset", None))

    contract = answers.to_canonical()
    try:
        validate_bootstrap(contract, preset=answers.preset)
    except BootstrapValidationError as exc:
        print("Bootstrap validation failed:", file=sys.stderr)
        for error in exc.errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    emit: EmitMode = args.emit  # type: ignore[assignment]
    out_dir = Path(args.out) if args.out else _default_out_dir()
    written = write_emitted_files(contract, emit=emit, out_dir=out_dir)

    print("\nBootstrap contract generated successfully.")
    for label, path in written.items():
        print(f"  {label}: {path}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    path = Path(args.path)
    if not path.is_file():
        print(f"File not found: {path}", file=sys.stderr)
        return 1

    with open(path, encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    try:
        contract = CanonicalContract.from_raw(data)
        validate_bootstrap(contract, preset=args.preset)
    except (BootstrapValidationError, ValueError) as exc:
        print(f"Validation failed: {exc}", file=sys.stderr)
        return 1

    print(f"OK: {path}")
    return 0


def cmd_from_sample(args: argparse.Namespace) -> int:
    args.from_sample = args.sample_dir
    args.answers = None
    return cmd_init(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tools.contract",
        description="Bootstrap Responsibility Contract wizard for ROA agents.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    init_p = sub.add_parser("init", help="Generate a Bootstrap contract (interactive or from answers file)")
    init_p.add_argument("--preset", choices=list_preset_names(), help="Domain preset")
    init_p.add_argument("--emit", choices=["sample", "registry", "both"], default="both")
    init_p.add_argument("--out", help="Output directory (default: contracts/)")
    init_p.add_argument("--answers", help="Non-interactive answers YAML")
    init_p.add_argument("--from-sample", dest="from_sample", help="Seed from samples/<dir>")
    init_p.add_argument("--agent-id", help="Agent id when sample config has multiple agents")
    init_p.add_argument(
        "--non-interactive",
        action="store_true",
        help="Skip prompts when using --from-sample",
    )
    init_p.set_defaults(func=cmd_init)

    validate_p = sub.add_parser("validate", help="Validate a canonical registry YAML file")
    validate_p.add_argument("path", help="Path to contract YAML")
    validate_p.add_argument("--preset", help="Preset name for required limit keys")
    validate_p.set_defaults(func=cmd_validate)

    fs_p = sub.add_parser(
        "from-sample",
        help="Alias for init --from-sample <dir>",
    )
    fs_p.add_argument("sample_dir", help="Path to samples/<NN>_<use_case>/")
    fs_p.add_argument("--emit", choices=["sample", "registry", "both"], default="both")
    fs_p.add_argument("--out", help="Output directory (default: contracts/)")
    fs_p.add_argument("--agent-id", help="Agent id when sample config has multiple agents")
    fs_p.add_argument("--non-interactive", action="store_true", help="Skip interview prompts")
    fs_p.set_defaults(func=cmd_from_sample)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))

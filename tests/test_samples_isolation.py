"""Samples are Runtime consumers: they may depend on ``dir_core`` but never on Build-Time ``tools``."""

from __future__ import annotations

import ast
from pathlib import Path

SAMPLES_DIR = Path(__file__).resolve().parents[1] / "samples"


def _imported_modules(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.append(node.module)
    return modules


def test_samples_do_not_import_build_time_tools() -> None:
    offenders = [
        f"{path.relative_to(SAMPLES_DIR)}: {module}"
        for path in SAMPLES_DIR.rglob("*.py")
        if "__pycache__" not in path.parts
        for module in _imported_modules(path)
        if module == "tools" or module.startswith("tools.")
    ]
    assert not offenders, f"samples must not depend on tools: {offenders}"


def test_samples_do_not_mutate_sys_path_with_repo_root() -> None:
    offenders = [
        str(path.relative_to(SAMPLES_DIR))
        for path in SAMPLES_DIR.rglob("*.py")
        if "__pycache__" not in path.parts and "parents[3]" in path.read_text(encoding="utf-8")
    ]
    assert not offenders, f"samples must not add the repo root to sys.path: {offenders}"

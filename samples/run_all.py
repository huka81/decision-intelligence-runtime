#!/usr/bin/env python3
"""
Run all sample scripts and summarize results.

Usage:
  From repo root: python samples/run_all.py
  Or: PYTHONPATH=src python samples/run_all.py

Samples 31, 32, 33: runs with USE_MOCK_LLM=1 (no Ollama required).
Samples 34, 35: require Ollama server (may fail if not running).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLES_DIR = REPO_ROOT / "samples"
SRC_DIR = REPO_ROOT / "src"

# Samples that use MockLLM when USE_MOCK_LLM=1 (no Ollama needed)
MOCK_LLM_SAMPLES = {"31_finance_trading", "32_fraud_gate", "33_insurance_underwriting"}


def find_samples() -> list[Path]:
    """Find all sample directories that have run.py."""
    samples = []
    for d in sorted(SAMPLES_DIR.iterdir()):
        if d.is_dir() and (d / "run.py").exists():
            samples.append(d)
    return samples


def run_sample(sample_dir: Path) -> tuple[int, str, str]:
    """Run sample's run.py. Returns (exit_code, stdout, stderr)."""
    run_py = sample_dir / "run.py"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_DIR)
    if sample_dir.name in MOCK_LLM_SAMPLES:
        env["USE_MOCK_LLM"] = "1"

    result = subprocess.run(
        [sys.executable, str(run_py)],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return result.returncode, result.stdout or "", result.stderr or ""


def main() -> None:
    samples = find_samples()
    if not samples:
        print("No samples found.")
        sys.exit(1)

    print("=" * 70)
    print("Running all samples")
    print("=" * 70)

    results: list[tuple[str, int, str, str]] = []
    for sample_dir in samples:
        name = sample_dir.name
        print(f"\n--- {name} ---")
        try:
            exit_code, stdout, stderr = run_sample(sample_dir)
            results.append((name, exit_code, stdout, stderr))
            status = "OK" if exit_code == 0 else f"FAILED (exit {exit_code})"
            print(f"  {status}")
            if exit_code != 0 and stderr:
                # Show last few lines of stderr
                lines = stderr.strip().split("\n")
                for line in lines[-5:]:
                    print(f"    | {line}")
        except subprocess.TimeoutExpired:
            results.append((name, -1, "", "Timeout (120s)"))
            print("  TIMEOUT")
        except Exception as e:
            results.append((name, -1, "", str(e)))
            print(f"  ERROR: {e}")

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    ok = [r[0] for r in results if r[1] == 0]
    failed = [(r[0], r[1], r[3]) for r in results if r[1] != 0]

    print(f"\nPassed ({len(ok)}):")
    for name in ok:
        print(f"  + {name}")

    if failed:
        print(f"\nFailed ({len(failed)}):")
        for name, code, err in failed:
            print(f"  - {name} (exit {code})")
            if err:
                last_line = err.strip().split("\n")[-1] if err else ""
                if last_line and len(last_line) < 80:
                    print(f"    {last_line}")
                elif last_line:
                    print(f"    {last_line[:77]}...")

    print("\n" + "=" * 70)
    print(f"Total: {len(results)} | Passed: {len(ok)} | Failed: {len(failed)}")
    print("=" * 70)

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()

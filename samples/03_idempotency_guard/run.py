#!/usr/bin/env python3
"""
03_idempotency_guard - Demonstrates EXACT-ONCE execution semantic (DIR §7).

Shows:
- IdempotencyKey generation (DFID + step_id + canonical_params).
- Caching of results in ``idempotency_cache`` (canonical schema).
- Re-execution returns cached result efficiently.
- Append-only ``decision_audit_events`` for ``IDEMPOTENCY_CACHE_HIT`` /
  ``IDEMPOTENCY_CACHE_MISS`` (telemetry guidelines).

Run from repo root: python samples/03_idempotency_guard/run.py
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from dir_core import new_dfid  # noqa: E402
from dir_core.idempotency import IdempotencyGuard, idempotency_key  # noqa: E402
from dir_core.storage import AuditStore, ensure_db, sqlite_storage  # noqa: E402

from telemetry import (  # noqa: E402
    record_idempotency_outcome,
    record_simulation_end,
    record_simulation_start,
)

SIMULATION_ID = "sample_03_idempotency_guard"

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def expensive_operation(prompt: str, temperature: float = 0.7) -> Dict[str, Any]:
    """Simulate an expensive LLM call."""
    logger.info("EXECUTING expensive operation: %r (temp=%s)", prompt, temperature)
    time.sleep(1.0)
    return {
        "response": f"Processed: {prompt}",
        "usage": {"tokens": len(prompt) * 2},
        "timestamp": time.time(),
    }


def _params_summary(params: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "prompt": str(params.get("prompt", ""))[:200],
        "temperature": params.get("temperature"),
    }


def _run_guard_once(
    guard: IdempotencyGuard,
    bundle_idempo: Any,
    audit: AuditStore,
    dfid: str,
    step_id: str,
    params: Dict[str, Any],
) -> tuple[Dict[str, Any], float]:
    key = idempotency_key(dfid, step_id, params)
    cache_hit = bundle_idempo.get(key) is not None
    t0 = time.time()
    result = guard.run(  # type: ignore[arg-type]
        dfid, step_id, params, expensive_operation
    )
    elapsed = time.time() - t0
    record_idempotency_outcome(
        audit,
        dfid,
        SIMULATION_ID,
        op_step_id=step_id,
        cache_hit=cache_hit,
        idempotency_key_prefix=key[:16],
        duration_sec=elapsed,
        params_summary=_params_summary(params),
    )
    return result, elapsed


def main() -> None:
    print("=" * 70)
    print("Idempotency Guard Demonstration")
    print("=" * 70)

    data_dir = Path(__file__).resolve().parent / "data"
    db_path = ensure_db(data_dir / "03_idempotency_guard.db")
    print(f"Database: {db_path}")

    bundle = sqlite_storage(str(db_path))
    guard = IdempotencyGuard(bundle.idempotency)
    audit = AuditStore(bundle.decision_audit, bundle.idempotency)

    dfid = new_dfid()
    step_id = "step_gen_summary"
    params = {"prompt": "Analyze ROI of project X", "temperature": 0.5}

    run_status = "ok"
    end_error: str | None = None
    try:
        record_simulation_start(audit, SIMULATION_ID)

        print(f"\n[Run 1] New DFID={dfid}, step={step_id}")
        print("Calling Guard.run()...")

        result1, duration1 = _run_guard_once(
            guard, bundle.idempotency, audit, dfid, step_id, params
        )

        print(f"Result: {result1['response']}")
        print(f"Duration: {duration1:.4f}s (Simulated execution)")

        print(f"\n[Run 2] SAME DFID={dfid}, step={step_id} (Retrying)")
        print("Calling Guard.run()...")

        result2, duration2 = _run_guard_once(
            guard, bundle.idempotency, audit, dfid, step_id, params
        )

        print(f"Result: {result2['response']}")
        print(f"Duration: {duration2:.4f}s (Cache Hit!)")

        if duration2 < 0.1 and result1 == result2:
            print("\nSUCCESS: Second run used cache (Idempotency preserved).")
        else:
            print("\nFAILURE: Idempotency check failed.")

        print("\n[Run 3] SAME DFID, DIFFERENT params (temperature=0.9)")
        params_diff = {"prompt": "Analyze ROI of project X", "temperature": 0.9}

        result3, duration3 = _run_guard_once(
            guard, bundle.idempotency, audit, dfid, step_id, params_diff
        )

        print(f"Result: {result3['response']}")
        print(f"Duration: {duration3:.4f}s (Execution due to param change)")
    except Exception as exc:
        run_status = "error"
        end_error = str(exc)
        raise
    finally:
        record_simulation_end(
            audit,
            SIMULATION_ID,
            status=run_status,
            error_message=end_error,
        )

    print(
        "\nTelemetry: correlation_id == simulation_id ==",
        SIMULATION_ID,
    )


if __name__ == "__main__":
    main()

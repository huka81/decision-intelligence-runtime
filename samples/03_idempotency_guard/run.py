#!/usr/bin/env python3
"""
03_idempotency_guard - Demonstrates EXACT-ONCE execution semantic (DIR §7).

Shows:
- IdempotencyKey generation (DFID + step_id + canonical_params).
- Caching of results to prevent duplicate expensive operations (Token Burn).
- Re-execution returns cached result efficiently.

Run from repo root: python samples/03_idempotency_guard/run.py
"""

import logging
import time
from pathlib import Path
from typing import Any, Dict

from dir import new_dfid
from utils import ensure_db
from dir.idempotency import IdempotencyGuard, SQLiteBackend

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def expensive_operation(prompt: str, temperature: float = 0.7) -> Dict[str, Any]:
    """Simulate an expensive LLM call."""
    logger.info(f"⚡ EXECUTING expensive operation: '{prompt}' (temp={temperature})")
    time.sleep(1.0)  # Simulate latency
    return {
        "response": f"Processed: {prompt}",
        "usage": {"tokens": len(prompt) * 2},
        "timestamp": time.time(),
    }


def main() -> None:
    print("=" * 70)
    print("Idempotency Guard Demonstration")
    print("=" * 70)

    # 1. Setup DB
    data_dir = Path(__file__).resolve().parent / "data"
    db_path = ensure_db(data_dir / "idempotency.db")
    print(f"Database: {db_path}")

    # 2. Initialize Guard
    backend = SQLiteBackend(str(db_path))
    guard = IdempotencyGuard(backend)

    # 3. Define operation context
    dfid = new_dfid()
    step_id = "step_gen_summary"
    params = {"prompt": "Analyze ROI of project X", "temperature": 0.5}

    print(f"\n[Run 1] New DFID={dfid}, step={step_id}")
    print("Calling Guard.run()...")
    
    start = time.time()
    # Note: We pass the function and its params to the guard
    result1 = guard.run(dfid, step_id, params, expensive_operation)  # type: ignore
    duration1 = time.time() - start
    
    print(f"Result: {result1['response']}")
    print(f"Duration: {duration1:.4f}s (Simulated execution)")

    # 4. Re-run with SAME context (Idempotency Check)
    print(f"\n[Run 2] SAME DFID={dfid}, step={step_id} (Retrying)")
    print("Calling Guard.run()...")

    start = time.time()
    result2 = guard.run(dfid, step_id, params, expensive_operation)  # type: ignore
    duration2 = time.time() - start

    print(f"Result: {result2['response']}")
    print(f"Duration: {duration2:.4f}s (Cache Hit!)")

    # Verification
    if duration2 < 0.1 and result1 == result2:
        print("\nSUCCESS: Second run used cache (Idempotency preserved).")
    else:
        print("\nFAILURE: Idempotency check failed.")

    # 5. Run with DIFFERENT params (Cache Miss)
    print(f"\n[Run 3] SAME DFID, DIFFERENT params (temperature=0.9)")
    params_diff = {"prompt": "Analyze ROI of project X", "temperature": 0.9}
    
    start = time.time()
    result3 = guard.run(dfid, step_id, params_diff, expensive_operation)  # type: ignore
    duration3 = time.time() - start
    
    print(f"Result: {result3['response']}")
    print(f"Duration: {duration3:.4f}s (Execution due to param change)")


if __name__ == "__main__":
    main()

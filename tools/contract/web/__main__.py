"""Run Contract Studio: python -m tools.contract.web"""

from __future__ import annotations

import sys


def main() -> int:
    try:
        import uvicorn
    except ImportError:
        print(
            "Contract Studio requires: pip install fastapi uvicorn",
            file=sys.stderr,
        )
        return 1

    from .app import app

    host = "127.0.0.1"
    port = 8765
    print(f"Contract Studio: http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

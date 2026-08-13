"""Run Contract Studio: python -m tools.contract.web"""

from __future__ import annotations

import sys

from ..env import load_contract_env
from ..settings import configure_studio_logging, load_studio_settings


def main() -> int:
    load_contract_env()
    settings = load_studio_settings()
    configure_studio_logging(debug=settings.debug)

    try:
        import uvicorn
    except ImportError:
        print(
            "Contract Studio requires: pip install fastapi uvicorn",
            file=sys.stderr,
        )
        return 1

    from .app import create_app

    host = "127.0.0.1"
    port = 8765
    print(f"Contract Studio: http://{host}:{port}")
    if settings.debug:
        print("Debug mode ON — LLM prompts and raw responses will be logged.")
    uvicorn.run(
        create_app(settings),
        host=host,
        port=port,
        log_level="info",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

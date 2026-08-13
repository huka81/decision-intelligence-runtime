"""Entry point: python -m tools.contract"""

from .env import load_contract_env
from .cli import main

if __name__ == "__main__":
    load_contract_env()
    raise SystemExit(main())

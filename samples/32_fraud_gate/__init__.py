"""
32_fraud_gate package initialization.
Loads environment variables from .env when python-dotenv is installed.
"""

import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        if os.getenv("VERBOSE", "").lower() in ("1", "true", "yes"):
            print(f"Loaded environment variables from {env_path}")
except ImportError:
    pass

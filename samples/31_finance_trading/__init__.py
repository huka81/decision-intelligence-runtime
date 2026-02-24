"""
31_finance_trading package initialization.
Loads environment variables from .env file if available.
"""

import os
from pathlib import Path

# Try to load .env file if python-dotenv is available
try:
    from dotenv import load_dotenv
    
    # Look for .env in the same directory as this file
    env_path = Path(__file__).parent / ".env"
    
    if env_path.exists():
        load_dotenv(env_path)
        # Optional: log that .env was loaded (only if not in quiet mode)
        if os.getenv("VERBOSE", "").lower() in ("1", "true", "yes"):
            print(f"Loaded environment variables from {env_path}")
    else:
        # Silently skip if .env doesn't exist
        pass
        
except ImportError:
    # python-dotenv not installed - environment variables will be read from system only
    # This is not an error; users can still set env vars via system/shell
    pass

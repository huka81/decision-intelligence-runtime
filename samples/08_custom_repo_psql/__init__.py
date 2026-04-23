"""Sample 08 — PostgreSQL-backed StorageBundle (DIR classic topology)."""

from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent / ".env", override=False)
except ImportError:
    pass

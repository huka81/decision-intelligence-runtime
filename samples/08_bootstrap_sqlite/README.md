# 08 - Bootstrap SQLite

**Goal:** Before running, ensure the database file exists; if not, create it and create all tables required by the sample. Other samples that use SQLite call the same bootstrap from `dir_runtime`.

**ROA/DIR:** Implementation guideline: every sample using SQLite must run bootstrap first.

## How to run

From repo root:

```bash
pip install -e .
python samples/08_bootstrap_sqlite/run.py
```

## Expected output

- Message that DB was created or already existed.
- Path to the DB file (e.g. `samples/08_bootstrap_sqlite/data/sample.db`).
- Optional: list of created tables.

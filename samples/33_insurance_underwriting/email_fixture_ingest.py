"""
Load London Market markdown email fixtures into coarse ClientApplication context.

Coarse ingest only. Structured submission facts come from the ROA agent LLM
policy proposal, not from table regexes in this module.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from schemas import ClientApplication


@dataclass
class MarkdownEmailFixture:
    """Fixture load: subject, body hash, and coarse industry hint for Explain."""

    source_path: Path
    subject: str
    body_text: str
    industry: str


def _cell_after_label(table_block: str, label: str) -> str | None:
    lines = [ln.strip() for ln in table_block.splitlines() if ln.strip().startswith("|")]
    for ln in lines:
        parts = [p.strip() for p in ln.split("|")]
        parts = [p for p in parts if p]
        if not parts:
            continue
        first = parts[0].lower()
        if first.startswith(label.lower()):
            for cell in parts[1:]:
                c = cell.strip().strip('"').strip("'")
                if c and c not in (
                    '"',
                    "—",
                    "-",
                    "RENEWAL TERMS",
                    "EXPIRING",
                    "PROPOSED TERMS",
                    "REMARKS",
                ):
                    return c
    return None


def _subject_from_header_table(text: str, fallback: str) -> str:
    m = re.search(r"\|\s*Subject\s*\|\s*([^|]+)\|", text, re.I)
    return m.group(1).strip() if m else fallback


def load_markdown_email_fixture(path: Path) -> MarkdownEmailFixture:
    raw = path.read_text(encoding="utf-8")
    subject = _subject_from_header_table(raw, path.stem)
    industry_cell = _cell_after_label(raw, "Industry") or "General"
    return MarkdownEmailFixture(
        source_path=path,
        subject=subject,
        body_text=raw,
        industry=industry_cell[:200],
    )


def client_application_from_fixture(fixture: MarkdownEmailFixture) -> ClientApplication:
    body_hash = hashlib.sha256(fixture.body_text.encode()).hexdigest()
    return ClientApplication(
        industry=fixture.industry,
        source_file=str(fixture.source_path.name),
        mail_subject=fixture.subject,
        mail_body_sha256=body_hash,
    )


def list_markdown_fixtures(emails_dir: Path) -> list[Path]:
    return sorted(emails_dir.glob("*.md"))

"""
Load London Market markdown email fixtures into coarse ClientApplication context.

Authority TiV for kernel gates comes from LLM extraction in the pipeline, not
from the table regexes in this module.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from models import ClientApplication


@dataclass
class MarkdownEmailFixture:
    """Fixture load: metadata + TiV-derived revenue proxy for context / Explain."""

    source_path: Path
    subject: str
    body_text: str
    industry: str
    original_insured: str
    territory_snippet: str
    tiv_numeric: float
    tiv_currency: str


def _cell_after_label(table_block: str, label: str) -> str | None:
    """Find markdown table row starting with label and return first substantial cell."""
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


def _tiv_row_value_and_currency(text: str) -> tuple[float, str]:
    """TiV from Total Insurable Values row (**Total: CUR n** or last **CUR n**)."""
    for ln in text.splitlines():
        if not re.match(r"^\|\s*Total\s+Insurable\s+Values\s*\|", ln, re.I):
            continue
        tot_pairs = re.findall(
            r"\*\*Total:\s*(GBP|USD|EUR)\s*([\d_,]+(?:\.\d+)?)\*\*",
            ln,
            re.I,
        )
        if tot_pairs:
            cur, raw = tot_pairs[-1]
            return float(raw.replace(",", "")), cur.upper()
        pairs = re.findall(
            r"\*\*(GBP|USD|EUR)\s*([\d_,]+(?:\.\d+)?)\*\*",
            ln,
            re.I,
        )
        if pairs:
            cur, raw = pairs[-1]
            return float(raw.replace(",", "")), cur.upper()
    return 500_000.0, "USD"


def _body_sha256(fixture: MarkdownEmailFixture) -> str:
    return hashlib.sha256(fixture.body_text.encode()).hexdigest()


def load_markdown_email_fixture(path: Path) -> MarkdownEmailFixture:
    raw = path.read_text(encoding="utf-8")
    subject = _subject_from_header_table(raw, path.stem)
    tiv, tiv_cur = _tiv_row_value_and_currency(raw)

    industry_cell = _cell_after_label(raw, "Industry") or "General"
    insured = _cell_after_label(raw, "Original Insured") or subject
    territory = _cell_after_label(raw, "Territory") or ""

    return MarkdownEmailFixture(
        source_path=path,
        subject=subject,
        body_text=raw,
        industry=industry_cell[:200],
        original_insured=insured[:200],
        territory_snippet=territory[:500],
        tiv_numeric=tiv,
        tiv_currency=tiv_cur,
    )


def client_application_from_fixture(
    fixture: MarkdownEmailFixture,
    fx: dict[str, float],
) -> ClientApplication:
    """
    Build context from coarse table metadata only.

    Broker TiV for gates is not from these regexes; the agent extracts it.
    ``requested_tiv_usd`` stays None until extraction. Revenue uses TiV×FX.
    """
    rev_base = fixture.tiv_numeric * float(fx.get(fixture.tiv_currency, 1.0))
    revenue = float(rev_base) if rev_base > 0 else 500_000.0

    return ClientApplication(
        business_type=fixture.original_insured,
        revenue=revenue,
        industry=fixture.industry,
        source_file=str(fixture.source_path.name),
        mail_subject=fixture.subject,
        requested_tiv_usd=None,
        territory_summary=f"{fixture.territory_snippet} {fixture.body_text[:2000]}",
        mail_body_sha256=_body_sha256(fixture),
    )


def list_markdown_fixtures(
    emails_dir: Path,
    exclude_substrings: list[str],
) -> list[Path]:
    paths = sorted(emails_dir.glob("*.md"))
    out: list[Path] = []
    for p in paths:
        name = p.name.lower()
        if any(ex.lower() in name for ex in exclude_substrings):
            continue
        out.append(p)
    return out

"""MkDocs hooks: assets under docs_dir, README link fixes, post-build cleanup."""

from __future__ import annotations

import logging
import os
import re
import subprocess
from pathlib import Path

import mkdocs.plugins

log = logging.getLogger("mkdocs")

# Sync with docs/09-pages/samples/*.md stubs and mkdocs.yml nav → Samples.
_SAMPLE_IDS: tuple[str, ...] = (
    "00_quick_start",
    "01_roa_agent",
    "02_dfid_propagation",
    "03_idempotency_guard",
    "04_context_store",
    "05_dim_validation",
    "06_agent_registry",
    "07_event_bus_swappable",
    "08_custom_repo_psql",
    "09_topology_a_eoam",
    "10_topology_b_sds",
    "11_topology_c_dl_pci",
    "12_compliant_lie",
    "31_finance_trading",
    "32_fraud_gate",
    "33_insurance_underwriting",
    "34_langchain_roa_wrapper",
    "35_crewai_roa_wrapper",
    "36_drift_optimization_discount",
    "37_drift_semantic_refund",
    "38_drift_environmental_bidding",
    "39_fintech_evidence_governance",
    "88_meta_context_engineering",
)

_SAMPLES_LINK_RE = re.compile(r"\]\((?:\.\./)*(?:\./)?samples/([^)]+)\)")


def _repo_assets(config) -> Path:
    return Path(config["docs_dir"]).resolve().parent / "assets"


def _docs_assets(config) -> Path:
    return Path(config["docs_dir"]).resolve() / "assets"


def _sample_id_from_path(rest: str) -> str:
    """Extract sample folder id from a samples/... href tail."""
    rest = rest.strip().rstrip("/")
    if rest in ("README.md", "README"):
        return ""
    head = rest.split("/")[0]
    if head.endswith(".md"):
        return head.removesuffix(".md")
    return head


def _mkdocs_sample_href(rest: str, page_uri: str) -> str:
    """Map samples/... targets to MkDocs Samples section URLs (not GitHub tree)."""
    rest = rest.strip()
    sample_id = _sample_id_from_path(rest)

    if not sample_id:
        if page_uri == "09-pages/samples/index.md":
            return "."
        return "09-pages/samples/"

    if page_uri == "09-pages/samples/index.md":
        return f"{sample_id}.md"

    if page_uri.startswith("09-pages/samples/"):
        return f"{sample_id}.md"

    # Home (docs/index.md includes root README.md)
    return f"09-pages/samples/{sample_id}/"


def _rewrite_sample_links(markdown: str, page_uri: str) -> str:
    markdown = _SAMPLES_LINK_RE.sub(
        lambda m: f"]({_mkdocs_sample_href(m.group(1), page_uri)})",
        markdown,
    )

    if page_uri == "09-pages/samples/index.md":
        for sid in _SAMPLE_IDS:
            markdown = markdown.replace(f"]({sid}/README.md)", f"]({sid}.md)")
            markdown = markdown.replace(f"]({sid}/)", f"]({sid}.md)")

    return markdown


def _rewrite_root_readme_doc_links(markdown: str) -> str:
    """Root README uses ./docs/...; MkDocs docs_dir is already docs/."""
    return re.sub(r"\]\(\./docs/([^)]+)\)", r"](\1)", markdown)


@mkdocs.plugins.event_priority(50)
def on_page_markdown(markdown, page, config, **kwargs):
    """Fix asset paths, samples includes, and Home-only GitHub links."""
    markdown = markdown.replace("../../assets/", "../assets/")
    uri = page.file.src_uri.replace("\\", "/")

    if uri.startswith("09-pages/samples/"):
        markdown = markdown.replace("](../docs/", "](../")
        return _rewrite_sample_links(markdown, uri)

    if uri == "09-pages/faq.md":
        markdown = markdown.replace("](../docs/", "](../")
        markdown = markdown.replace("](assets/", "](../assets/")
        return markdown

    if uri != "index.md":
        return markdown

    markdown = markdown.replace("../assets/", "assets/")
    markdown = _rewrite_root_readme_doc_links(markdown)
    markdown = _rewrite_sample_links(markdown, uri)

    repo = (config.get("repo_url") or "").rstrip("/")
    if repo:
        for old, new in (
            ("](./FAQ.md)", f"]({repo}/blob/main/FAQ.md)"),
            ("](../FAQ.md)", f"]({repo}/blob/main/FAQ.md)"),
            ("](FAQ.md)", f"]({repo}/blob/main/FAQ.md)"),
            ("](../LICENSE)", f"]({repo}/blob/main/LICENSE)"),
            ("](./LICENSE)", f"]({repo}/blob/main/LICENSE)"),
            ("](LICENSE)", f"]({repo}/blob/main/LICENSE)"),
        ):
            markdown = markdown.replace(old, new)

    return markdown


def on_pre_build(config, **kwargs) -> None:
    repo_assets = _repo_assets(config)
    link = _docs_assets(config)
    if not repo_assets.is_dir():
        log.warning(
            "mkdocs_hooks: repo assets directory not found at %s",
            repo_assets,
        )
        return

    if link.is_symlink():
        return

    if link.exists():
        try:
            link.rmdir()
        except OSError:
            log.warning(
                "mkdocs_hooks: %s exists and is not empty; remove or rename it.",
                link,
            )
            return

    try:
        link.symlink_to(repo_assets, target_is_directory=True)
    except OSError:
        if os.name != "nt":
            raise
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(repo_assets)],
            check=True,
            capture_output=True,
            text=True,
        )


def on_post_build(config, **kwargs) -> None:
    link = _docs_assets(config)
    if link.is_symlink():
        link.unlink(missing_ok=True)
        return
    if link.is_dir():
        try:
            link.rmdir()
        except OSError:
            pass

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
_SAMPLE_READMES: tuple[str, ...] = (
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
    "31_finance_trading",
    "32_fraud_gate",
    "33_insurance_underwriting",
    "34_langchain_roa_wrapper",
    "35_crewai_roa_wrapper",
    "36_drift_optimization_discount",
    "37_drift_semantic_refund",
    "38_drift_environmental_bidding",
    "88_meta_context_engineering",
)


def _repo_assets(config) -> Path:
    return Path(config["docs_dir"]).resolve().parent / "assets"


def _docs_assets(config) -> Path:
    return Path(config["docs_dir"]).resolve() / "assets"


@mkdocs.plugins.event_priority(50)
def on_page_markdown(markdown, page, config, **kwargs):
    """Fix asset paths, samples includes, and Home-only GitHub links."""
    markdown = markdown.replace("../../assets/", "../assets/")
    uri = page.file.src_uri.replace("\\", "/")

    if uri.startswith("09-pages/samples/"):
        markdown = markdown.replace("](../docs/", "](../")
        if uri == "09-pages/samples/index.md":
            for d in _SAMPLE_READMES:
                markdown = markdown.replace(f"]({d}/README.md)", f"]({d}.md)")
                markdown = markdown.replace(f"]({d}/)", f"]({d}.md)")
        return markdown

    if uri == "09-pages/faq.md":
        markdown = markdown.replace("](../docs/", "](../")
        markdown = markdown.replace("](assets/", "](../assets/")
        return markdown

    if uri != "index.md":
        return markdown

    markdown = markdown.replace("../assets/", "assets/")
    repo = (config.get("repo_url") or "").rstrip("/")
    if not repo:
        return markdown

    def samples_repl(match: re.Match[str]) -> str:
        rest = match.group(1)
        head = rest.rstrip("/")
        kind = "blob" if head.endswith(".md") else "tree"
        return f"]({repo}/{kind}/main/samples/{rest}"

    markdown = re.sub(r"\]\((?:\.\./)*(?:\./)?samples/([^)]+)\)", samples_repl, markdown)

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

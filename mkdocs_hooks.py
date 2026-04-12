"""MkDocs hooks: assets under docs_dir, link fixes for included README, cleanup after build."""

from __future__ import annotations

import logging
import os
import re
import subprocess
from pathlib import Path

import mkdocs.plugins

log = logging.getLogger("mkdocs")


def _repo_assets(config) -> Path:
    return Path(config["docs_dir"]).resolve().parent / "assets"


def _docs_assets(config) -> Path:
    return Path(config["docs_dir"]).resolve() / "assets"


@mkdocs.plugins.event_priority(50)
def on_page_markdown(markdown, page, config, **kwargs):
    """Keep asset links inside docs_dir; point repo-only paths on Home to GitHub."""
    markdown = markdown.replace("../../assets/", "../assets/")
    if page.file.src_uri != "index.md":
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
        log.warning("mkdocs_hooks: repo assets directory not found at %s", repo_assets)
        return

    if link.is_symlink():
        return

    if link.exists():
        try:
            link.rmdir()
        except OSError:
            log.warning(
                "mkdocs_hooks: %s already exists and is not empty; remove or rename it.",
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

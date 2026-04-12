"""MkDocs hooks: expose repo-root `assets/` under `docs/assets` during builds only."""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

log = logging.getLogger("mkdocs")


def _repo_assets(config) -> Path:
    return Path(config["docs_dir"]).resolve().parent / "assets"


def _docs_assets(config) -> Path:
    return Path(config["docs_dir"]).resolve() / "assets"


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

"""Tests for unified YAML config loading."""

import tempfile
from pathlib import Path

import pytest

from dir_core.utils.config_loader import load_yaml_config


def test_load_yaml_config_parses_mapping() -> None:
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".yaml",
        delete=False,
        encoding="utf-8",
    ) as f:
        f.write("app:\n  name: test\n  port: 8080\n")
        path = f.name
    try:
        cfg = load_yaml_config(path)
        assert cfg == {"app": {"name": "test", "port": 8080}}
    finally:
        Path(path).unlink(missing_ok=True)


def test_load_yaml_config_empty_file_returns_empty_dict() -> None:
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".yaml",
        delete=False,
        encoding="utf-8",
    ) as f:
        f.write("")
        path = f.name
    try:
        assert load_yaml_config(path) == {}
    finally:
        Path(path).unlink(missing_ok=True)


def test_load_yaml_config_null_document_returns_empty_dict() -> None:
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".yaml",
        delete=False,
        encoding="utf-8",
    ) as f:
        f.write("null\n")
        path = f.name
    try:
        assert load_yaml_config(path) == {}
    finally:
        Path(path).unlink(missing_ok=True)


def test_load_yaml_config_missing_file() -> None:
    name = "dir_core_config_loader_missing_xyz.yaml"
    missing = Path(tempfile.gettempdir()) / name
    missing.unlink(missing_ok=True)
    with pytest.raises(FileNotFoundError, match="not found"):
        load_yaml_config(missing)


def test_load_yaml_config_rejects_non_mapping() -> None:
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".yaml",
        delete=False,
        encoding="utf-8",
    ) as f:
        f.write("- a\n- b\n")
        path = f.name
    try:
        with pytest.raises(ValueError, match="mapping"):
            load_yaml_config(path)
    finally:
        Path(path).unlink(missing_ok=True)
